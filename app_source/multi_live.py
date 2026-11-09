"""Shared opt-in acquisition and timestamped, bounded multi-source audio.

A source is opened once. Source reader threads only append PCM; the analysis and
recording worker mixes outside Tk and outside the reader callback. The compatibility
microphone property represents the first running audio input, not an exclusive bus.
"""
from __future__ import annotations
import copy,json,math,queue,threading,time,wave
from collections import deque
from pathlib import Path
import numpy as np
from live_sources import LiveInputs,Capture,AUDIO_RATE
from signal_engine import analyze_samples
from sound_routes import source_id,default_route,contribution

class MultiLiveInputs(LiveInputs):
    def __init__(self):
        super().__init__();self.sources={};self.routes={};self.file_reaction=None;self.mix_stop=threading.Event();self.raw_jobs=queue.Queue(maxsize=256);self.record_fault='';self.input_latency=.12
        self.mix_thread=threading.Thread(target=self._pump,name='Sound source mix / retention',daemon=True);self.mix_thread.start()
    def add_buffered_source(self,sid,label='',staged=False):
        with self.lock:
            self.sources.setdefault(sid,{'label':label or sid,'device':None,'capture':None,'ring':deque(maxlen=128),'level':0.,'frames':0,'stamp':0.})
            if sid not in self.routes:
                route=default_route(sid,label)
                if staged:route['enabled']=False
                self.routes[sid]=route
        return sid
    def configure(self,routes,project_time=None):
        with self.lock:
            updated=copy.deepcopy(routes);self.routes=updated
            r=self.recording
            if r is not None and project_time is not None:
                event={'time':float(project_time),'routes':copy.deepcopy(updated)}
                events=r.setdefault('routing_events',[])
                if not events or events[-1].get('routes')!=event['routes']:events.append(event)
    def add_audio(self,device,label='',staged=False):
        if self.mix_stop.is_set():raise RuntimeError('Input registry is closed')
        sid=source_id(device)
        with self.lock:
            existing=self.sources.get(sid)
            if existing and existing.get('capture') and existing['capture'].state in ('starting','live'):return sid
        if isinstance(device,dict):
            from system_audio import validate_application
            validate_application(device)
        self.add_buffered_source(sid,label or ('Microphone' if not isinstance(device,dict) else device.get('label','Device audio')),staged=staged)
        cap=Capture('microphone',device,lambda samples,stamp:self.feed(sid,samples,stamp))
        with self.lock:
            if self.mix_stop.is_set():cap.close();raise RuntimeError('Input registry is closing')
            self.sources[sid].update(capture=cap,device=copy.deepcopy(device));self.microphone=self.microphone or cap
        return sid
    def start_camera(self,device):
        if self.mix_stop.is_set():raise RuntimeError('Input registry is closed')
        super().start_camera(device)
        if self.mix_stop.is_set():self.stop_camera();raise RuntimeError('Input registry is closing')
    def start_microphone(self,device):
        return self.add_audio(device,'Microphone' if not isinstance(device,dict) else device.get('label','Device audio'))
    def stop_audio(self,sid):
        with self.lock:
            entry=self.sources.get(sid);cap=entry.get('capture') if entry else None
            if entry:entry['capture']=None;entry['ring'].clear();entry['level']=0.
        if cap:cap.close()
        with self.lock:self.microphone=next((e['capture'] for e in self.sources.values() if e.get('capture')),None)
    def stop_microphone(self):
        for sid in list(self.sources):self.stop_audio(sid)
        self.microphone=None;self._signal=({},time.monotonic())
    def feed(self,sid,samples,stamp):
        samples=np.asarray(samples,dtype=np.float32).reshape(-1).copy();samples[~np.isfinite(samples)]=0
        with self.lock:
            if sid not in self.sources:self.add_buffered_source(sid)
            e=self.sources[sid];e['ring'].append((float(stamp)-len(samples)/AUDIO_RATE,samples));e['level']=float(np.sqrt(np.mean(samples*samples))) if len(samples) else 0.;e['stamp']=stamp;e['frames']+=len(samples)
            r=self.recording
        if r:
            try:self.raw_jobs.put_nowait((r,sid,samples,float(stamp)))
            except queue.Full:r['error']='Raw source recording could not keep up; retained output may be partial.'
    def read_pcm(self,first,n,rate,purpose='react'):
        times=float(first)+np.arange(n)/float(rate);out=np.zeros(n,np.float32)
        with self.lock:entries=[(sid,list(e['ring']),copy.copy(self.routes.get(sid,default_route(sid)))) for sid,e in self.sources.items()]
        for sid,chunks,route in entries:
            gain=contribution(route,purpose)
            if not gain:continue
            source=np.zeros(n,np.float32)
            for origin,data in chunks:
                end=origin+len(data)/AUDIO_RATE
                if end<=first or origin>=first+n/rate:continue
                mask=(times>=origin)&(times<end)
                if not mask.any():continue
                x=np.minimum(len(data)-1,(times[mask]-origin)*AUDIO_RATE)
                i=np.floor(x).astype(np.int64);f=x-i
                source[mask]=data[i]*(1-f)+data[np.minimum(i+1,len(data)-1)]*f
            out+=source*gain
        return np.clip(out,-.98,.98)
    def external_active(self,purpose='react'):
        with self.lock:return any(contribution(self.routes.get(sid,default_route(sid)),purpose)>0 and e['stamp']>time.monotonic()-1 for sid,e in self.sources.items())
    def source_states(self):
        with self.lock:
            return {sid:dict(label=e['label'],device=e['device'],level=e['level'] if time.monotonic()-e['stamp']<1 else 0.,state=getattr(e.get('capture'),'state','stopped'),error=getattr(e.get('capture'),'error',''),frames=e['frames']) for sid,e in self.sources.items()}
    def _drain_raw(self,r=None):
        while True:
            try:target,sid,samples,stamp=self.raw_jobs.get_nowait()
            except queue.Empty:break
            if target.get('raw_closed'):continue
            record=target.setdefault('raw_sources',{}).get(sid)
            if record is None:
                path=str(Path(target['directory'])/(target['stem']+'-'+sid.replace(':','-')+'.wav'))
                writer=wave.open(path+'.partial','wb');writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(AUDIO_RATE)
                with self.lock:e=self.sources.get(sid,{})
                record={'path':path,'first':max(0.,stamp-target['clock']-len(samples)/AUDIO_RATE),'samples':0,'label':e.get('label',sid),'writer':writer};target['raw_sources'][sid]=record
            record['writer'].writeframesraw((np.clip(samples,-1,1)*32767).astype('<i2').tobytes());record['samples']+=len(samples)
    def _pump(self):
        n=1024;period=n/AUDIO_RATE;deadline=time.monotonic();previous=0.
        while not self.mix_stop.is_set():
            now=time.monotonic();first=now-self.input_latency
            try:
                live_reactive=self.read_pcm(first,n,AUDIO_RATE,'react');reactive=live_reactive.copy();sound=self.read_pcm(first,n,AUDIO_RATE,'sound')
                file=self.file_reaction
                if file is not None and now-file[2]<.3:
                    samples=np.mean(file[0],axis=1);x=np.arange(n)*file[1]/AUDIO_RATE
                    reactive=np.clip(reactive+np.interp(x,np.arange(len(samples)),samples,left=0,right=0),-.98,.98)
                data=analyze_samples(reactive,AUDIO_RATE);ref=data.get('reference_rms',.02)
                values={k:min(1.,v[0]*ref/.18) if v else 0. for k,v in data['bands'].items()}
                rms=values.get('full',0.);values['onset']=min(1.,max(0.,rms-previous)*4);previous=rms;values['_has_external']=float(self.external_active())
                live_data=analyze_samples(live_reactive,AUDIO_RATE);live_ref=live_data.get('reference_rms',.02)
                live_values={k:min(1.,v[0]*live_ref/.18) if v else 0. for k,v in live_data['bands'].items()}
                self._signal=({**live_values,'_reaction_mix':values,'_has_external':values['_has_external'],'_has_mix':bool(values['_has_external'] or (file is not None and now-file[2]<.3))},now)
                with self.lock:
                    r=self.recording
                    self.retain_mix_block(r,now,sound,live_values,values)
                    self._drain_raw(r)
            except Exception as exc:
                self.record_fault=str(exc)
                with self.lock:
                    if self.recording:self.recording['error']=self.record_fault
            deadline+=period;delay=deadline-time.monotonic()
            if delay<-.3:deadline=time.monotonic();delay=0
            self.mix_stop.wait(max(0,delay))
    def retain_mix_block(self,r,stamp,sound,live_values,values):
        # FFT/mixing can overlap the user arming a new take. A pre-arm block
        # belongs to the preceding interval, not a negative offset in this take.
        # Caller holds the acquisition lock; writing remains on the mix worker.
        if not r or not r.get('wav') or stamp<r['clock']:return
        if r['audio_first'] is None:r['audio_first']=stamp-r['clock']
        r['wav'].writeframesraw((sound*32767).astype('<i2').tobytes());r['audio_samples']+=len(sound)
        for band in r['bands']:r['bands'][band].append(round(float(live_values.get(band,0)),6))
        for band in r.get('mix_bands',{}):r['mix_bands'][band].append(round(float(values.get(band,0)),6))
    def start_recording(self,directory,project_time):
        with self.lock:
            self.microphone=next((e['capture'] for e in self.sources.values() if e.get('capture') and e['capture'].state=='live'),self.microphone)
        super().start_recording(directory,project_time)
        with self.lock:
            r=self.recording;r['raw_sources']={};r['mix_bands']={b:[] for b in r['bands']};r['raw_closed']=False;r['routing_start']=copy.deepcopy(self.routes);r['routing_events']=[{'time':float(project_time),'routes':copy.deepcopy(self.routes)}]
            # Retain analysis even with camera-only input: file-driven patches can
            # become mic-driven later without inventing a separate recorder.
            if not r['wav']:
                r['audio']=str(Path(r['directory'])/(r['stem']+'.wav'));r['wav']=wave.open(r['audio']+'.partial','wb');r['wav'].setnchannels(1);r['wav'].setsampwidth(2);r['wav'].setframerate(AUDIO_RATE)
    def stop_recording(self):
        with self.lock:
            r=self.recording
            if r is None:raise ValueError('No take is recording')
            self._drain_raw(r);r['raw_closed']=True
            raw=[]
            for sid,item in r.get('raw_sources',{}).items():
                item['writer'].close();path=Path(item['path']);Path(str(path)+'.partial').replace(path)
                raw.append(dict(source_id=sid,path=str(path),first=item['first'],duration=item['samples']/AUDIO_RATE,label=item['label']))
            take=super().stop_recording()
            take['reaction_analysis']={**take.get('analysis',{}),'bands':r.get('mix_bands',{}),'source':'recorded-full-reaction-mix'}
            take['raw_sources']=raw;take['sound_mix_recorded']=True;take['reaction_mix_recorded']=True;take['routing_start']=r.get('routing_start',{});take['routing_events']=r.get('routing_events',[]);take['latency_seconds']=self.input_latency
            Path(take['manifest']).write_text(json.dumps(take,indent=2))
        return take
    def close(self):
        self.mix_stop.set();self.mix_thread.join(timeout=3)
        self.stop_all()


class ChannelLiveInputs(MultiLiveInputs):
    """Shared physical cameras with independent, asset-addressed consumers.

    Up to four assigned devices plus one prepared replacement. A new device is
    never substituted into an existing camera asset. No acquisition on restore.
    """
    def __init__(self):
        super().__init__();self.camera_sources={};self.camera_recorders=[];self.camera_epoch=0
    @staticmethod
    def camera_key(device):return json.dumps(device,sort_keys=True)
    def acquire_camera(self,device):
        with self.lock:
            if self.mix_stop.is_set():raise RuntimeError('Input registry is closed')
            self.camera_epoch+=1;key=self.camera_key(device);entry=self.camera_sources.get(key)
            if entry and entry.camera and entry.camera.state in ('starting','live'):return entry.camera
            if self.recording:raise ValueError('Finish retained-input recording before opening another physical camera. Switching between already running cameras remains available.')
            if len(self.camera_sources)>=5 and key not in self.camera_sources:raise ValueError('Four camera assignments plus one prepared replacement are supported.')
            # Construct before changing any existing reference: failure keeps output.
            source=LiveInputs();source.start_camera(device)
            if entry:entry.stop_all()
            self.camera_sources[key]=source
            if self.camera is None or self.camera.state not in ('starting','live'):self.camera=source.camera
            return source.camera
    def start_camera(self,device):
        ready=self.acquire_camera(device)
        if not self.recording:self.camera=ready
        return ready
    def camera_frame_for(self,asset):
        device=asset.metadata.get('device')
        if device is None:return self.camera_frame()
        source=self.camera_sources.get(self.camera_key(device))
        return source.camera_frame() if source is not None else None
    def release_unused_cameras(self,devices,expected_epoch=None):
        if self.recording:return
        keys={self.camera_key(d) for d in devices};removed=[]
        with self.lock:
            if expected_epoch is not None and self.camera_epoch!=expected_epoch:return
            for key in list(self.camera_sources):
                if key not in keys:removed.append(self.camera_sources.pop(key))
            current={id(e.camera) for e in self.camera_sources.values()}
            if id(self.camera) not in current:self.camera=next((e.camera for e in self.camera_sources.values()),None)
        for source in removed:source.stop_all()
    def stop_camera(self):
        if self.recording:raise ValueError('Finish retained recording before stopping cameras')
        with self.lock:entries=list(self.camera_sources.values());self.camera_sources={};primary=self.camera;self.camera=None
        captures={id(e.camera) for e in entries}
        for source in entries:source.stop_all()
        if primary and id(primary) not in captures:primary.close()
    def start_recording(self,directory,project_time):
        self.camera_recorders=[];super().start_recording(directory,project_time)
        r=self.recording
        try:
            for key,source in list(self.camera_sources.items()):
                if source.camera is self.camera or source.camera.state!='live':continue
                offset=max(0.,time.monotonic()-r['clock'])
                source.start_recording(Path(directory)/('camera-'+source_id(source.camera.device).replace(':','-')),project_time+offset)
                self.camera_recorders.append(source)
        except Exception:
            # Preserve and finalise anything already recorded rather than leaking encoders.
            for source in self.camera_recorders:
                if source.recording:source.stop_recording()
            self.camera_recorders=[];super().stop_recording();raise
    def stop_recording(self):
        children=[]
        for source in self.camera_recorders:
            if source.recording:children.append(source.stop_recording())
        self.camera_recorders=[];take=super().stop_recording();take['camera_sources']=children
        errors=[c.get('error') for c in children if c.get('error')]
        if errors:take['error']='\n'.join([take.get('error',''),*errors]).strip()
        Path(take['manifest']).write_text(json.dumps(take,indent=2));return take
