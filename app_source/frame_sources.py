"""Local image/procedural sources and bounded, reusable FFmpeg video readers."""
from __future__ import annotations
import hashlib
import json
import math
import os
import queue
import subprocess
import threading
from collections import OrderedDict,deque
from bisect import bisect_right
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
from process_tools import popen_options,stop_process


def tool(name):
    # Imported lazily because the public media facade also imports this module.
    from media_engine import find_tool
    return find_tool(name) or name


def choose_font(size,path=''):
    candidates=[path,'DejaVuSans.ttf','Arial.ttf','/System/Library/Fonts/Supplemental/Arial.ttf','C:/Windows/Fonts/arial.ttf']
    for candidate in candidates:
        if not candidate:continue
        try:return ImageFont.truetype(candidate,max(8,int(size)))
        except (OSError,ValueError):pass
    return ImageFont.load_default()


def fit_image(image:Image.Image,size,fit='contain'):
    image=ImageOps.exif_transpose(image).convert('RGBA')
    if image.size==tuple(size):return image
    if fit=='stretch':return image.resize(size,Image.Resampling.BICUBIC)
    if fit=='cover':return ImageOps.fit(image,size,method=Image.Resampling.BICUBIC)
    scaled=ImageOps.contain(image,size,method=Image.Resampling.BICUBIC)
    out=Image.new('RGBA',size);out.alpha_composite(scaled,((size[0]-scaled.width)//2,(size[1]-scaled.height)//2));return out


def procedural_image(asset,size,project_size):
    w,h=size;out=Image.new('RGBA',size);draw=ImageDraw.Draw(out)
    m=asset.metadata;colour=m.get('colour','#ffffff')
    if asset.kind=='text':
        font=choose_font(float(m.get('font_size',64))*h/max(1,project_size[1]),m.get('font_path',''))
        text=str(m.get('text',asset.name));spacing=max(1,round(float(m.get('line_spacing',8))*h/project_size[1]))
        box=draw.multiline_textbbox((0,0),text,font=font,spacing=spacing,align='center',stroke_width=0)
        x=(w-(box[2]-box[0]))/2-box[0];y=(h-(box[3]-box[1]))/2-box[1]
        stroke=max(0,round(float(m.get('stroke',0))*h/project_size[1]))
        draw.multiline_text((x,y),text,font=font,fill=colour,spacing=spacing,align='center',stroke_width=stroke,stroke_fill=m.get('stroke_colour','#000000'))
    elif asset.kind=='shape':
        box=(w*.18,h*.18,w*.82,h*.82);kind=m.get('shape','rectangle')
        if kind=='ellipse':draw.ellipse(box,fill=colour)
        elif kind=='triangle':draw.polygon([(w*.5,h*.18),(w*.82,h*.82),(w*.18,h*.82)],fill=colour)
        elif kind=='polygon' and m.get('points'):draw.polygon([(x*w,y*h) for x,y in m['points']],fill=colour)
        else:draw.rounded_rectangle(box,radius=min(w,h)*float(m.get('radius',.06)),fill=colour)
    elif asset.kind=='colour':draw.rectangle((0,0,w,h),fill=colour)
    return out


class VideoReader:
    def __init__(self,path,size,fps,start,fit='contain',history_frames=120):
        self.size=tuple(size);self.fps=fps;self.base=math.floor(start*fps+1e-5)/fps
        self.history=OrderedDict();self.history_limit=max(2,int(history_frames));self.closed=False
        self.index=-1;self.last=None;self.frames=queue.Queue(maxsize=3);self.stop=threading.Event();self.tail=deque(maxlen=12);self.eof=False
        w,h=size
        if fit=='cover':scale=f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}'
        elif fit=='stretch':scale=f'scale={w}:{h}'
        else:scale=f'scale={w}:{h}:force_original_aspect_ratio=decrease,format=rgba,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0'
        self.command=[tool('ffmpeg'),'-hide_banner','-loglevel','error','-threads','1','-ss',f'{self.base:.9f}','-i',str(path),'-an','-sn','-dn','-vf',f'fps={fps:.9f},{scale},format=rgba','-filter_threads','1','-threads','1','-f','rawvideo','-pix_fmt','rgba','pipe:1']
        self.proc=subprocess.Popen(self.command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,**popen_options())
        self.stderr_thread=threading.Thread(target=self._errors,daemon=True);self.stderr_thread.start()
        self.worker=threading.Thread(target=self._read,daemon=True);self.worker.start()
    def _errors(self):
        try:
            while True:
                b=self.proc.stderr.read(2048)
                if not b:break
                self.tail.append(b)
        finally:
            try:self.proc.stderr.close()
            except OSError:pass
    def _read(self):
        count=self.size[0]*self.size[1]*4
        try:
            while not self.stop.is_set():
                buffer=bytearray()
                while len(buffer)<count and not self.stop.is_set():
                    chunk=self.proc.stdout.read(count-len(buffer))
                    if not chunk:break
                    buffer.extend(chunk)
                value=bytes(buffer) if len(buffer)==count else None
                while not self.stop.is_set():
                    try:self.frames.put(value,timeout=.1);break
                    except queue.Full:pass
                if value is None:break
        except (OSError,ValueError):
            try:self.frames.put_nowait(None)
            except queue.Full:pass
    def at(self,t):
        target=max(0,int(math.floor((t-self.base)*self.fps+1e-4)))
        if target in self.history:return self.history[target]
        if target<self.index:raise LookupError('Requested video frame is outside retained decoder history')
        while self.index<target and not self.eof:
            try:raw=self.frames.get(timeout=12)
            except queue.Empty:raise TimeoutError('Video decoder did not deliver a frame; try a lower preview quality or check media')
            if raw is None:
                self.eof=True
                if self.last is None:raise RuntimeError(b''.join(self.tail).decode('utf-8','replace')[-5000:] or 'No video frame was decoded')
                break
            self.index+=1;self.last=Image.frombytes('RGBA',self.size,raw)
            self.history[self.index]=self.last
            while len(self.history)>self.history_limit:self.history.popitem(last=False)
        return self.last
    def contains(self,t):
        index=int(math.floor((t-self.base)*self.fps+1e-4))
        return index>=0 and index in self.history
    def abort(self):
        """Unblock decoder pipes immediately; cleanup never waits for graceful EOF."""
        self.stop.set()
        try:
            if self.proc.poll() is None:self.proc.kill()
        except OSError:pass
    def close(self):
        if self.closed:return
        self.closed=True;self.abort()
        try:self.proc.wait(timeout=.5)
        except (OSError,subprocess.SubprocessError):pass
        self.worker.join(timeout=.5);self.stderr_thread.join(timeout=.5)
        try:self.proc.stdout.close()
        except (OSError,ValueError):pass
        self.history.clear()


class FrameSources:
    def __init__(self,max_readers=6,cache_bytes=48*1024*1024,live=None):
        self.retired=queue.Queue();self.retire_thread=None;self.video_cache_bytes=96*1024*1024
        self.readers=OrderedDict();self.images=OrderedDict();self.gif_times=OrderedDict();self.image_bytes=0;self.max_readers=max_readers;self.cache_bytes=cache_bytes;self.live=live
    def _cache(self,key,image):
        if key in self.images:return self.images[key]
        self.images[key]=image;self.image_bytes+=image.width*image.height*4
        while self.image_bytes>self.cache_bytes and len(self.images)>1:
            _,old=self.images.popitem(last=False);self.image_bytes-=old.width*old.height*4
        return image
    def frame(self,asset,t,size,*,reader_key='',fit='contain',fps=30,project_size=(1280,720)):
        if asset.kind in ('camera','screen','window'):
            provider=getattr(getattr(self.live,'__self__',None),'camera_frame_for',None)
            image=provider(asset) if provider is not None else self.live() if self.live is not None else None
            if image is None:raise RuntimeError('The selected live visual source is unavailable. Reselect it or use a retained recording.')
            return fit_image(image,size,fit)
        if asset.kind in {'text','shape','colour'}:
            key=(asset.id,json.dumps(asset.metadata,sort_keys=True),tuple(size),tuple(project_size))
            if key not in self.images:self._cache(key,procedural_image(asset,size,project_size))
            self.images.move_to_end(key);return self.images[key]
        path=Path(asset.path)
        if not path.is_file():raise FileNotFoundError(f'Missing source: {path.name}. Use Library → Relink; the source was not silently omitted.')
        mtime=path.stat().st_mtime_ns
        if asset.kind=='image':
            gif_frame=None
            if path.suffix.lower()=='.gif':
                timing_key=(str(path),mtime)
                if timing_key not in self.gif_times:
                    ends=[];elapsed=0.
                    with Image.open(path) as im:
                        for index in range(getattr(im,'n_frames',1)):
                            im.seek(index);elapsed+=max(.02,float(im.info.get('duration',100))/1000);ends.append(elapsed)
                    self.gif_times[timing_key]=ends
                    while len(self.gif_times)>32:self.gif_times.popitem(last=False)
                ends=self.gif_times[timing_key];self.gif_times.move_to_end(timing_key)
                gif_frame=min(len(ends)-1,bisect_right(ends,t%max(.02,ends[-1])))
            key=(str(path),mtime,tuple(size),fit,gif_frame)
            if key not in self.images:
                with Image.open(path) as image:
                    if gif_frame is not None:image.seek(gif_frame)
                    self._cache(key,fit_image(image,size,fit))
            self.images.move_to_end(key);return self.images[key]
        if asset.kind!='video':raise ValueError(f'Unsupported visual source: {asset.kind}')
        # A delayed tap is a timestamp, not a separate source. Sharing by media
        # preserves decoded history across clips, temporal taps and repeated views.
        key=(str(path),mtime,tuple(size),fit,float(fps))
        reader=self.readers.get(key)
        if reader is not None:
            current=reader.base+max(0,reader.index)/fps
            if not reader.contains(t) and (t<current-.6/fps or t>current+2.5):
                self.readers.pop(key);self._retire(reader);reader=None
        if reader is None:
            while len(self.readers)>=self.max_readers:
                self._retire(self.readers.popitem(last=False)[1])
            bytes_per_frame=max(1,size[0]*size[1]*4)
            history_frames=max(2,min(240,self.video_cache_bytes//bytes_per_frame))
            # A small decode pre-roll makes ordinary finite echoes available on
            # the first frame. Longer/high-resolution history remains bounded.
            lookback=min(2.,max(0.,(history_frames-2)/fps))
            reader=VideoReader(path,size,fps,max(0.,t-lookback),fit,history_frames)
            self.readers[key]=reader
        self.readers.move_to_end(key)
        result=reader.at(t)
        self._trim_video_history()
        if result is None:raise RuntimeError(f'No frame decoded from {path.name}')
        return result
    def _trim_video_history(self):
        total=sum(len(r.history)*r.size[0]*r.size[1]*4 for r in self.readers.values())
        for r in self.readers.values():
            cost=r.size[0]*r.size[1]*4
            while total>self.video_cache_bytes and len(r.history)>2:
                r.history.popitem(last=False);total-=cost
    def _retire(self,reader):
        # kill() is nonblocking; waits and thread joins belong to a reaper,
        # never inside the active render loop.
        reader.abort();self.retired.put(reader)
        if self.retire_thread is None or not self.retire_thread.is_alive():
            def reap():
                while True:
                    r=self.retired.get()
                    if r is None:return
                    try:r.close()
                    finally:self.retired.task_done()
            self.retire_thread=threading.Thread(target=reap,name='Video decoder cleanup',daemon=True)
            self.retire_thread.start()
    def close(self):
        for r in list(self.readers.values()):r.close()
        self.readers.clear();self.images.clear();self.gif_times.clear();self.image_bytes=0
        if self.retire_thread is not None:
            self.retired.put(None);self.retire_thread.join(timeout=1);self.retire_thread=None
