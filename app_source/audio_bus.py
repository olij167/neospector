"""Bounded, sample-addressable soundtrack mixing for preview and export.

PCM decoding and mixing occur on workers, never in Tk callbacks. Every event uses
project seconds and an independent source in-point. FFplay is the compatibility
output device (bounded pre-roll, not claimed sample-accurate hardware latency).
"""
from __future__ import annotations
import copy, math, os, queue, struct, subprocess, threading, time, wave
from pathlib import Path
from collections import OrderedDict
import numpy as np
from sequencer_model import Project, new_id
from process_tools import run_process, popen_options, stop_process, Cancelled

RATE=48000

def sound_events(project,*,include_linked=True):
    result=copy.deepcopy(project.extra.get('sound_events',[]))
    if not project.extra.get('audio_bus_enabled') and not result and project.audio_asset_id:
        a=project.asset(project.audio_asset_id)
        if a:result=[dict(id='primary',asset_id=a.id,start=0.,duration=a.duration or project.max_end(),in_point=0.,gain=1.,enabled=True,fade_in=0.,fade_out=0.,curve='equal_power')]
    for tr in project.extra.get('audio_takes',[]):
        a=project.asset(tr.get('asset_id'));start=float(tr.get('start',0))
        if not a or not tr.get('enabled'):continue
        if any(e['asset_id']==a.id and abs(float(e['start'])-start)<1e-6 for e in result):continue
        result.append(dict(id=tr.get('id','take-'+a.id),asset_id=a.id,start=start,duration=a.duration,in_point=0.,gain=tr.get('gain',1.),enabled=True,fade_in=0.,fade_out=0.,route_id=tr.get('route_id',''),captured_sound=tr.get('captured_sound',False)))
    for e in result:e.setdefault('route_id','soundtrack' if not str(e.get('id','')).startswith('take-') else '')
    if include_linked:
        from sound_routes import linked_events
        result.extend(linked_events(project))
    valid=[]
    for e in result:
        if not e.get('enabled',True):continue
        a=project.asset(e.get('asset_id'))
        if a is None and not e.get('queue_gap'):raise ValueError('Sound event references a missing source')
        for k,default in [('start',0),('duration',a.duration if a else 1.),('in_point',0),('gain',1),('fade_in',0),('fade_out',0)]:
            v=float(e.get(k,default))
            if not math.isfinite(v) or v<0:raise ValueError(f'Invalid audio event {k}')
            e[k]=v
        if e['gain']>4:raise ValueError('Audio event gain exceeds 4×')
        if e['duration']>0:valid.append(e)
    return sorted(valid,key=lambda e:(e['start'],e.get('id','')))

def add_sound(project,asset_id,*,start=0.,fade=0.,in_point=None,duration=None):
    a=project.asset(asset_id)
    if not a or (a.kind!='audio' and not a.metadata.get('has_audio')):raise ValueError('This source has no audio stream')
    pref=a.metadata.get('sequence_preferences',{});in_point=float(pref.get('source_in',0.) if in_point is None else in_point);speed=float(pref.get('playback_rate',1.))
    source_end=min(a.duration,float(pref.get('source_out',a.duration)))
    start=max(0.,float(start));dur=float(duration if duration is not None else max(.01,(source_end-in_point)/speed));fade=max(0.,min(float(fade),dur))
    existing=[e for e in sound_events(project) if e.get('route_id')=='soundtrack']
    if start<=0:existing=[]
    else:
        existing=[e for e in existing if e['start']<start]
        for e in existing:
            if e['start']+e['duration']>start:
                overlap=min(fade,max(0.,e['start']+e['duration']-start))
                e['duration']=start+overlap-e['start'];e['fade_out']=overlap
                fade=min(fade,overlap)
    event=dict(id=new_id('snd'),asset_id=asset_id,start=start,duration=dur,in_point=float(in_point),gain=float(pref.get('sound_gain',1.)),playback_rate=speed,source_lo=in_point,source_hi=source_end,source_policy=pref.get('source_policy','hold'),fade_in=fade,fade_out=0.,curve='equal_power',enabled=True)
    project.extra['sound_events']=existing+[event];project.extra['audio_bus_enabled']=True
    project.audio_asset_id=asset_id;project.duration=max(project.duration,start+dur);return event

def event_gain(event,times):
    t=np.asarray(times,dtype=np.float64);local=t-event['start'];duration=event['duration']
    gain=np.ones_like(t)*event.get('gain',1.)
    curve=event.get('curve','equal_power')
    for seconds,position in [(event.get('fade_in',0),t-event.get('fade_start',event['start'])),(event.get('fade_out',0),event.get('fade_end',event['start']+duration)-t)]:
        if seconds>0:
            ramp=np.clip(position/seconds,0,1)
            if curve=='equal_power':ramp=np.sin(ramp*np.pi/2)
            gain*=ramp
    gain[(local<0)|(local>=duration)]=0
    return gain

class PCMCache:
    def __init__(self,rate=RATE,block_seconds=2,max_blocks=24,cancel=None):
        self.rate=rate;self.block_size=round(rate*block_seconds);self.max_blocks=max_blocks;self.blocks=OrderedDict();self.cancel=cancel;self.lock=threading.RLock();self.inflight={};self.prefetch_jobs=queue.Queue(maxsize=8);self.prefetch_pending=set();self.prefetch_stop=threading.Event();self.prefetch_thread=None
    def _key(self,asset,index):
        path=Path(asset.path);stat=path.stat();return (str(path),stat.st_size,stat.st_mtime_ns,index,self.rate)
    def _block(self,asset,index):
        from media_engine import FFMPEG
        key=self._key(asset,index)
        while True:
            with self.lock:
                if key in self.blocks:self.blocks.move_to_end(key);return self.blocks[key]
                wait=self.inflight.get(key)
                if wait is None:self.inflight[key]=threading.Event();break
            if self.cancel is not None and self.cancel.is_set():raise Cancelled('Audio preparation cancelled')
            wait.wait(.02)
        try:
            cp=run_process([FFMPEG,'-hide_banner','-loglevel','error','-threads','1','-ss',f'{index*self.block_size/self.rate:.9f}','-i',str(asset.path),'-vn','-t',f'{self.block_size/self.rate:.9f}','-ac','2','-ar',str(self.rate),'-f','f32le','pipe:1'],timeout=30,cancel=self.cancel)
            raw=np.frombuffer(cp.stdout,dtype='<f4');data=raw[:len(raw)//2*2].reshape(-1,2)
            out=np.zeros((self.block_size,2),np.float32);out[:min(len(data),self.block_size)]=data[:self.block_size]
            with self.lock:
                self.blocks[key]=out
                while len(self.blocks)>self.max_blocks:self.blocks.popitem(last=False)
            return out
        finally:
            with self.lock:self.inflight.pop(key).set()
    def prefetch(self,asset,source_time):
        """Queue one imminent PCM block without blocking the transport caller."""
        if self.prefetch_stop.is_set():return
        index=max(0,int(source_time*self.rate)//self.block_size)
        if asset.duration and index*self.block_size>=asset.duration*self.rate:return
        try:key=self._key(asset,index)
        except OSError:return  # Actual playback reports unavailable media.
        with self.lock:
            if key in self.blocks or key in self.inflight or key in self.prefetch_pending:return
            try:self.prefetch_jobs.put_nowait((asset,index,key))
            except queue.Full:return
            self.prefetch_pending.add(key)
            if self.prefetch_thread is None:
                self.prefetch_thread=threading.Thread(target=self._prepare,name='Prepare upcoming PCM',daemon=True);self.prefetch_thread.start()
    def _prepare(self):
        while not self.prefetch_stop.is_set():
            try:asset,index,key=self.prefetch_jobs.get(timeout=.1)
            except queue.Empty:continue
            try:self._block(asset,index)
            except Exception:pass  # Preparation is speculative; consumption reports failures.
            finally:
                with self.lock:self.prefetch_pending.discard(key)
    def close(self):
        self.prefetch_stop.set()
        if self.prefetch_thread:self.prefetch_thread.join(timeout=.2)
    def read(self,asset,source_time,n):
        first=round(source_time*self.rate);out=np.zeros((n,2),np.float32);offset=0
        if first<0:offset=min(n,-first);first+=offset
        while offset<n:
            index,local=divmod(first,self.block_size);count=min(n-offset,self.block_size-local)
            if asset.duration and first>=round(asset.duration*self.rate):break
            out[offset:offset+count]=self._block(asset,index)[local:local+count];first+=count;offset+=count
        return out
    def read_positions(self,asset,positions):
        x=np.asarray(positions,dtype=np.float64)*self.rate
        i=np.floor(x).astype(np.int64);f=(x-i).astype(np.float32)
        out=np.zeros((len(i),2),np.float32)
        for offsets,weights in ((i,1-f),(i+1,f)):
            valid=offsets>=0
            if asset.duration:valid&=offsets<round(asset.duration*self.rate)
            block_ids=offsets//self.block_size
            for index in np.unique(block_ids[valid]):
                mask=valid&(block_ids==index);out[mask]+=self._block(asset,int(index))[offsets[mask]%self.block_size]*weights[mask,None]
        return out

class AudioMixer:
    def __init__(self,project,rate=RATE,cache=None,purpose='sound',missing_policy='error'):
        self.project=project;self.rate=rate;self.cache=cache or PCMCache(rate);self.events=sound_events(project,include_linked=False);self.purpose=purpose;self.levels={};self.missing_policy=missing_policy;self.missing={}
        from sound_routes import LinkedEventClock
        self.linked_clock=LinkedEventClock(project)
    def block(self,start,n):
        from sound_routes import gain_curve
        out=np.zeros((n,2),np.float32);end=start+n/self.rate;times=None;self.levels={}
        from queue_policies import music_segments
        events=[e for e in self.events if e.get('route_id')!='soundtrack']+self.linked_clock.events(start,end)
        for lo,hi,q,state in music_segments(self.project,start,end):
            source_events=state['events'] or [e for e in self.events if e.get('route_id')=='soundtrack']
            from queue_seams import active_seam
            seam=active_seam(sorted([e for e in source_events if e.get('route_id','soundtrack')=='soundtrack'],key=lambda e:(e['start'],e['id'])),state.get('seam'))
            seam_length=max((e['start']+e['duration'] for e in source_events if e.get('route_id','soundtrack')=='soundtrack'),default=0.)
            for original in source_events:
                if original.get('route_id','soundtrack')!='soundtrack' or not original.get('enabled',True):continue
                e=dict(original);delta=lo-q
                e.setdefault('in_point',0.);e.setdefault('gain',1.);e.setdefault('fade_in',0.);e.setdefault('fade_out',0.);e.setdefault('route_id','soundtrack')
                e['start']=original['start']+delta
                e['fade_start']=original.get('fade_start',original['start'])+delta
                e['fade_end']=original.get('fade_end',original['start']+original['duration'])+delta
                if seam:e['_queue_seam']={'seam':seam,'length':seam_length,'origin':delta}
                e['_segment']=(lo,hi);events.append(e)
        for e in events:
            if e.get('queue_gap'):continue
            if e['start']>=end or e['start']+e['duration']<=start:continue
            if times is None:times=start+np.arange(n)/self.rate
            gain=event_gain(e,times)
            if e.get('_queue_seam'):
                from queue_seams import seam_gain
                seam=e['_queue_seam'];gain*=seam_gain(times-seam['origin'],seam['length'],seam['seam'])
            if '_segment' in e:
                lo,hi=e['_segment'];gain[(times<lo-1e-8)|(times>=hi-1e-8)]=0
            if e.get('route_id'):gain*=gain_curve(self.project,e['route_id'],times,self.purpose)
            # Retained live recordings are already mixed for Sound, not locally
            # monitored or re-analysed as another copy of the same reaction.
            elif self.purpose=='react' and e.get('captured_sound',False):continue
            if not np.any(gain):continue
            a=self.project.asset(e['asset_id']);speed=float(e.get('playback_rate',1.))
            if self.missing_policy=='silence' and (a is None or not Path(a.path).is_file()):
                self.missing[e['asset_id']]=a.name if a else 'Missing source';continue
            self.missing.pop(e['asset_id'],None)
            if speed!=1 or e.get('source_policy')=='loop':
                positions=(times-e['start'])*speed+e['in_point']
                lo=float(e.get('source_lo',0));hi=float(e.get('source_hi',a.duration));span=max(1/self.rate,hi-lo)
                if e.get('source_policy')=='loop':positions=lo+np.maximum(0.,positions-lo)%span
                elif hi>lo:positions=np.minimum(positions,hi-1/self.rate)
                pcm=self.cache.read_positions(a,positions)
            else:pcm=self.cache.read(a,start-e['start']+e['in_point'],n)
            piece=pcm*gain[:,None];out+=piece
            rid=e.get('route_id') or 'retained';self.levels[rid]=max(self.levels.get(rid,0.),float(np.sqrt(np.mean(piece*piece))))
        if self.purpose in ('sound','monitor'):
            from visual_channels import master_curve
            out*=master_curve(self.project,'audio',start+np.arange(n)/self.rate)[:,None]
        return np.clip(out,-.98,.98)

    def prefetch(self,start,horizon=2.3):
        if not hasattr(self.cache,'prefetch'):return
        from sound_routes import route_gain
        from queue_policies import music_position
        session_start=start
        start=music_position(self.project,start)
        for e in self.events:
            if e.get('queue_gap'):continue
            if e['start']>start+horizon or e['start']+e['duration']<=start:continue
            when=max(start,e['start']);rid=e.get('route_id')
            if rid and not route_gain(self.project,rid,when,self.purpose):continue
            a=self.project.asset(e['asset_id']);speed=float(e.get('playback_rate',1.))
            for t in (when,when+horizon):
                pos=e['in_point']+(t-e['start'])*speed
                if e.get('source_policy')=='loop':
                    lo=float(e.get('source_lo',0));hi=float(e.get('source_hi',a.duration));pos=lo+max(0.,pos-lo)%max(1/self.rate,hi-lo)
                self.cache.prefetch(a,max(0.,pos))
        for e in self.linked_clock.events(session_start,session_start+horizon):
            when=max(session_start,e['start'],e['_segment'][0]);rid=e.get('route_id')
            if rid and not route_gain(self.project,rid,when,self.purpose):continue
            a=self.project.asset(e['asset_id']);pos=e['in_point']+(when-e['start'])*float(e.get('playback_rate',1.))
            if e.get('source_policy')=='loop':
                lo=float(e.get('source_lo',0));hi=float(e.get('source_hi',a.duration));pos=lo+max(0.,pos-lo)%max(1/self.rate,hi-lo)
            self.cache.prefetch(a,max(0.,pos))

def render_audio(project,path,start,end,*,cancel=None,progress=None,purpose='sound'):
    mix=AudioMixer(project,cache=PCMCache(cancel=cancel),purpose=purpose);frames=round((end-start)*RATE);path=Path(path)
    with wave.open(str(path),'wb') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(RATE)
        for i in range(0,frames,RATE//2):
            if cancel is not None and cancel.is_set():raise Cancelled('Audio rendering cancelled')
            block=mix.block(start+i/RATE,min(RATE//2,frames-i));w.writeframesraw((block*32767).astype('<i2').tobytes())
            if progress:progress(f'Preparing soundtrack {100*min(frames,i+RATE//2)/max(1,frames):.0f}%')
    return path

class AudioTransport:
    """Single mixed output, replacing the old per-song FFplay restarts.

Document replacement is an atomic pointer swap at a block boundary. Stop/seek use
an epoch and a new worker. At most ~120ms is intentionally queued ahead; OS/device
latency is reported as uncalibrated rather than presented as exact acquisition.
"""
    def __init__(self,status=None):
        self.status=status or (lambda *_:None);self.stop_event=None;self.thread=None;self.proc=None;self.project=None;self.error='';self.muted=False;self.last_block=None;self.position=0.;self.epoch=0;self.live_inputs=None;self.levels={}
    def update(self,project):self.project=project
    def start(self,project,start=0.):
        self.stop();self.project=project;self.position=float(start);self.error='';self.epoch+=1
        stop=threading.Event();self.stop_event=stop;epoch=self.epoch
        self.thread=threading.Thread(target=self._run,args=(project,float(start),stop,epoch),name='Soundtrack bus',daemon=True);self.thread.start()
    def _run(self,project,start,stop,epoch):
        from media_engine import FFPLAY
        proc=None;cache=PCMCache(cancel=stop);clock=time.monotonic();i=0;mix=AudioMixer(project,cache=cache,purpose='monitor',missing_policy='silence');reaction=AudioMixer(project,cache=cache,purpose='react',missing_policy='silence');current=project
        try:
            if not FFPLAY:raise RuntimeError('FFplay is not available for soundtrack monitoring')
            # A streaming IEEE-float WAV header describes channels/rate without
            # version-sensitive FFplay raw-input options (-ac was removed).
            cmd=[FFPLAY,'-hide_banner','-loglevel','error','-nodisp','-autoexit','-f','wav','-i','pipe:0']
            proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**popen_options())
            header=struct.pack('<4sI4s4sIHHIIHH4sI',b'RIFF',0xffffffff,b'WAVE',b'fmt ',16,3,2,RATE,RATE*8,8,32,b'data',0xffffffff)
            proc.stdin.write(header);proc.stdin.flush()
            if epoch==self.epoch:self.proc=proc
            while not stop.is_set():
                p=self.project
                if p is not current:mix=AudioMixer(p,cache=cache,purpose='monitor',missing_policy='silence');reaction=AudioMixer(p,cache=cache,purpose='react',missing_policy='silence');current=p
                t=start+i/RATE;mix.prefetch(t);reaction.prefetch(t);block=mix.block(t,2048)
                reactive=reaction.block(t,2048)
                self.levels={rid:max(mix.levels.get(rid,0),reaction.levels.get(rid,0)) for rid in set(mix.levels)|set(reaction.levels)}
                self.last_block=(t,reactive)
                missing={**mix.missing,**reaction.missing}
                if missing!=getattr(self,'missing',{}):
                    self.missing=missing
                    if missing:self.status('Missing audio is silent: '+', '.join(missing.values())+'. Use Locate missing media; pictures continue.')
                if self.live_inputs is not None:
                    self.live_inputs.file_reaction=(reactive.copy(),RATE,time.monotonic())
                    live=self.live_inputs.read_pcm(time.monotonic()-.12,2048,RATE,'monitor')
                    from visual_channels import master_curve
                    live*=master_curve(p,'audio',t+np.arange(len(live))/RATE)
                    block=np.clip(block+live[:,None],-.98,.98)
                if self.muted:block=np.zeros_like(block)
                proc.stdin.write(np.asarray(block,dtype='<f4').tobytes());proc.stdin.flush();i+=len(block)
                if epoch==self.epoch:self.position=start+min(i/RATE,max(0.,time.monotonic()-clock))
                stop.wait(max(0.,clock+i/RATE-.12-time.monotonic()))
        except Exception as exc:
            if not stop.is_set():self.error=str(exc);self.status('Audio output: '+str(exc))
        finally:
            cache.close()
            if proc:
                try:proc.stdin.close()
                except Exception:pass
                stop_process(proc)
    def stop(self):
        if self.stop_event:self.stop_event.set()
        p=self.proc;self.proc=None
        if p:
            try:p.terminate()
            except OSError:pass
        if self.thread and self.thread.is_alive():self.thread.join(timeout=.15)
        self.thread=None;self.levels={}
