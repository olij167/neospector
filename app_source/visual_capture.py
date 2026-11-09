"""Explicit X11 display/window capture with bounded, cropped raw-frame delivery.

A descriptor is an identity and crop, never an authorization token. The chooser
must make a fresh descriptor; project load never instantiates this class.
"""
from __future__ import annotations
import math,os,subprocess,threading,time
from collections import deque
from PIL import Image
from media_engine import FFMPEG
from process_tools import popen_options,stop_process

MAX_WIDTH=1280
MAX_HEIGHT=720

def _xdisplay(name=None):
    if os.environ.get('XDG_SESSION_TYPE','').lower()=='wayland':
        raise RuntimeError('The X11 capture path cannot capture a Wayland desktop. ScreenCast portal support is required in this session.')
    from Xlib import display
    return display.Display(name or os.environ.get('DISPLAY'))

def list_sources(name=None):
    """List current X11 identities. Listing neither acquires nor records pixels."""
    from Xlib import X
    d=_xdisplay(name);result=[]
    try:
        root=d.screen().root;g=root.get_geometry()
        result.append(dict(kind='screen',display=d.get_display_name(),window_id=root.id,
                           name='Entire X11 screen',width=g.width,height=g.height))
        prop=root.get_full_property(d.intern_atom('_NET_CLIENT_LIST_STACKING'),X.AnyPropertyType)
        ids=list(prop.value) if prop is not None else []
        if not ids:
            def descend(node,depth=0):
                if depth>4:return
                try:children=node.query_tree().children
                except Exception:return
                for child in children:
                    ids.append(child.id);descend(child,depth+1)
            descend(root)
        seen=set()
        for xid in ids:
            if int(xid) in seen:continue
            seen.add(int(xid))
            try:
                w=d.create_resource_object('window',int(xid));a=w.get_attributes();geo=w.get_geometry()
                if a.map_state!=X.IsViewable or geo.width<100 or geo.height<80:continue
                title=w.get_wm_name()
                if not title:
                    p=w.get_full_property(d.intern_atom('_NET_WM_NAME'),X.AnyPropertyType)
                    title=p.value.decode('utf-8','replace') if p is not None and isinstance(p.value,bytes) else ''
                if not title:continue
                result.append(dict(kind='window',display=d.get_display_name(),window_id=int(xid),
                                   name=str(title)[:100],width=geo.width,height=geo.height))
            except Exception:continue  # a window can close while the chooser lists it
        return result
    finally:d.close()

def describe(source,crop=(0.,0.,1.,1.),fps=20,cursor=True):
    kind=source.get('kind')
    if kind not in ('screen','window'):raise ValueError('Choose Screen or Window')
    width=int(source['width']);height=int(source['height']);window_id=int(source['window_id'])
    if not (64<=width<=16384 and 64<=height<=16384 and window_id>0):raise ValueError('Invalid visual-source geometry')
    if int(fps) not in (10,15,20,30):raise ValueError('Choose 10, 15, 20 or 30 frames per second')
    box=tuple(float(v) for v in crop)
    if len(box)!=4 or any(not math.isfinite(v) for v in box):raise ValueError('Crop needs four finite values')
    x,y,w,h=box
    if x<0 or y<0 or w<=0 or h<=0 or x+w>1.000001 or y+h>1.000001:raise ValueError('Crop must fit inside the selected source')
    px=max(0,min(width-1,round(x*width)));py=max(0,min(height-1,round(y*height)))
    pw=max(1,min(width-px,round(w*width)));ph=max(1,min(height-py,round(h*height)))
    if pw<32 or ph<32:raise ValueError('Crop is too small; choose at least 32×32 pixels')
    scale=min(1.,MAX_WIDTH/pw,MAX_HEIGHT/ph)
    ow=max(2,round(pw*scale));oh=max(2,round(ph*scale))
    return dict(kind=kind,display=str(source['display']),window_id=window_id,
                name=str(source.get('name',kind))[:100],width=width,height=height,
                crop=[x,y,w,h],crop_px=[px,py,pw,ph],frame_size=[ow,oh],fps=int(fps),cursor=bool(cursor))

def capture_command(descriptor):
    d=describe(descriptor,descriptor.get('crop',(0.,0.,1.,1.)),descriptor.get('fps',20),descriptor.get('cursor',True))
    x,y,w,h=d['crop_px'];ow,oh=d['frame_size'];display=d['display']
    if not display or not display.startswith(':') and not display.startswith('127.0.0.1:'):
        raise ValueError('An X11 display name is required')
    cmd=[FFMPEG,'-hide_banner','-loglevel','warning','-nostdin','-threads','1',
         '-f','x11grab','-framerate',str(d['fps']),'-draw_mouse','1' if d['cursor'] else '0',
         '-video_size',f"{d['width']}x{d['height']}"]
    if d['kind']=='window':cmd+=['-window_id',str(d['window_id'])]
    cmd+=['-i',display, '-an','-vf',f'crop={w}:{h}:{x}:{y},scale={ow}:{oh}',
          '-pix_fmt','rgba','-threads','1','-f','rawvideo','pipe:1']
    return cmd,d

class VisualCapture:
    def __init__(self,descriptor):
        self.command,self.device=capture_command(descriptor);self.size=tuple(self.device['frame_size']);self.fps=self.device['fps']
        self.latest=None;self.stamp=0.;self.count=0;self.state='starting';self.error='';self.tail=deque(maxlen=20)
        self.stop=threading.Event()
        self._verify_identity()
        self.proc=subprocess.Popen(self.command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**popen_options())
        self.reader=threading.Thread(target=self._read,name='Visual capture frames',daemon=True)
        self.logger=threading.Thread(target=self._stderr,name='Visual capture log',daemon=True)
        self.monitor=threading.Thread(target=self._monitor,name='Visual source identity',daemon=True)
        self.logger.start();self.reader.start();self.monitor.start()
    def _verify_identity(self):
        from Xlib import X
        d=_xdisplay(self.device['display'])
        try:
            target=d.create_resource_object('window',self.device['window_id'])
            g=target.get_geometry()
            if (g.width,g.height)!=(self.device['width'],self.device['height']):
                raise RuntimeError('The selected source size changed. Reselect and review the crop before sharing again.')
            if self.device['kind']=='window':
                if target.get_attributes().map_state!=X.IsViewable:
                    raise RuntimeError('The selected window is no longer visible. Sharing stopped; reselect it when available.')
                title=target.get_wm_name()
                if title and str(title)[:100]!=self.device['name']:
                    raise RuntimeError('The selected window identity changed. Sharing stopped; choose it again.')
        except Exception as exc:
            if isinstance(exc,RuntimeError):raise
            raise RuntimeError('The selected source closed. Choose it again; no other window was substituted.') from exc
        finally:d.close()
    def _stderr(self):
        try:
            for line in iter(self.proc.stderr.readline,b''):self.tail.append(line)
        finally:self.proc.stderr.close()
    def _read(self):
        length=self.size[0]*self.size[1]*4
        try:
            while not self.stop.is_set():
                raw=self.proc.stdout.read(length)
                if len(raw)!=length:break
                if self.stop.is_set():break
                self.latest=Image.frombytes('RGBA',self.size,raw);self.stamp=time.monotonic();self.count+=1;self.state='live'
            if not self.stop.is_set():
                self.logger.join(timeout=.2);self.state='error'
                self.error=b''.join(self.tail).decode('utf-8','replace')[-1200:] or 'The selected visual source stopped. Reselect it to share again.'
        except Exception as exc:self.state='error';self.error=str(exc)
        finally:self.proc.stdout.close()
    def _monitor(self):
        while not self.stop.wait(.5):
            try:self._verify_identity()
            except Exception as exc:
                self.error=str(exc);self.state='error';self.stop.set();stop_process(self.proc);return
    def close(self):
        self.stop.set();stop_process(self.proc)
        self.reader.join(timeout=3);self.logger.join(timeout=2)
        if threading.current_thread() is not self.monitor:self.monitor.join(timeout=2)
        self.state='stopped'
