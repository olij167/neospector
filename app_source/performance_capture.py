"""Local performance retention and recording, independent of the editing cursor.

Record Output receives actual Programme frames. Editable takes preserve project
seconds and measured live envelopes. No camera is reopened to reconstruct history.
"""
from __future__ import annotations
import copy, hashlib, json, math, queue, threading, time
from pathlib import Path
import numpy as np
from PIL import Image
from sequencer_model import add_asset, new_id, project_to_dict
from instrument_model import capture_interval, walk_parameters
from process_tools import EncoderPipe,run_process
from media_engine import FFMPEG
from audio_bus import render_audio,sound_events


def _covers(intervals,start,end,tolerance=.12):
    cursor=start
    for a,b in sorted(intervals):
        if b<=cursor:continue
        if a>cursor+tolerance:return False
        cursor=max(cursor,b)
        if cursor>=end-tolerance:return True
    return cursor>=end-tolerance


def join_analysis(analysis_segments):
    if analysis_segments:
        offset=min(float(s['analysis'].get('offset',s['start'])) for s in analysis_segments);stop=max(float(s['analysis'].get('offset',s['start']))+float(s['analysis'].get('duration',s['duration'])) for s in analysis_segments);step=.02
        times=np.arange(max(1,math.ceil((stop-offset)/step)))*step+offset;bands={}
        for band in ('full','bass','mid','high','onset'):
            values=np.zeros(len(times))
            for s in analysis_segments:
                data=s['analysis'];raw=np.asarray(data.get('bands',{}).get(band,[]),float)
                if not len(raw):continue
                origin=float(data.get('offset',s['start']));hop=float(data.get('hop_seconds',.02));valid=(times>=origin)&(times<origin+float(data.get('duration',s['duration'])))
                values[valid]=np.interp(times[valid],origin+np.arange(len(raw))*hop,raw)
            bands[band]=values.tolist()
        return {'offset':offset,'duration':stop-offset,'hop_seconds':step,'bands':bands,'normalization':'measured-live-v1'}
    return {}


def attach_retained_sound(project,start,end,segments):
    """Attach the retained Sound mix once, validating requested live coverage."""
    from sound_routes import external_intervals
    spans=external_intervals(project,'sound',start,end)
    sounds=[s for s in segments if s.get('audio') and s['start']<end and s['start']+s['duration']>start]
    coverage=[(s['start']+float(s.get('audio_first') or 0),s['start']+s['duration']) for s in sounds]
    for lo,hi in spans:
        if not _covers(coverage,lo,hi):raise ValueError('Live Sound has no complete retained audio coverage. Retain inputs before performing, then Capture Recent.')
    # Route history is authoritative. Retention never grants audibility by itself.
    if spans:
        existing={project.asset(t['asset_id']).path for t in project.extra.get('audio_takes',[]) if project.asset(t.get('asset_id'))}
        for s in sounds:
            if s['audio'] in existing:continue
            origin=s['start']+float(s.get('audio_first') or 0)
            a=add_asset(project,path=s['audio'],kind='audio',name='Retained live Sound',duration=max(0,s['start']+s['duration']-origin),metadata={'has_audio':True})
            project.extra.setdefault('audio_takes',[]).append({'asset_id':a.id,'start':origin,'gain':1.,'enabled':True,'route_id':'','captured_sound':True})
            existing.add(s['audio'])
    return project

def capture_with_recordings(project,start,end,segments=()):
    """Create an independent take; caller pins referenced segments before this call.

Very small segment-rotation gaps are retained as gaps (not fabricated camera
frames). Larger unavailable intervals are rejected with an actionable message.
"""
    start=float(start);end=float(end)
    if not (math.isfinite(start) and math.isfinite(end) and 0<=start<end):raise ValueError('Choose a valid capture interval')
    if start<float(project.extra.get('history_start',0)):raise ValueError('This interval is older than the retained editable history')
    from queue_model import materialize
    p=materialize(project,start,end);used=[s for s in segments if float(s['start'])<end and float(s['start'])+float(s['duration'])>start]
    analysis_segments=[s for s in used if s.get('analysis')]
    live_params=[q for q in walk_parameters(p) if q.mode=='react' and q.source in ('microphone','device','mix')]
    def needs_live(raw):
        if isinstance(raw,dict):return (raw.get('mode')=='react' and raw.get('source') in ('microphone','device','mix')) or any(needs_live(v) for v in raw.values())
        return any(needs_live(v) for v in raw) if isinstance(raw,list) else False
    historical=[e for l in p.layers for e in l.extra.get('treatment_history',[]) if e['start']<end and e['end']>start]+[e for k in ('master_history','mixer_history') for e in p.extra.get(k,[]) if e['start']<end and e['end']>start]
    if (live_params or needs_live(historical)) and not _covers([(s['analysis'].get('offset',s['start']),s['analysis'].get('offset',s['start'])+s['analysis'].get('duration',s['duration'])) for s in analysis_segments],start,end):
        raise ValueError('Live audio reaction has no complete retained coverage. Arm retention before performing, or choose a newer interval.')
    # Camera media is replaced only in the interval actually retained.
    for layer in p.layers:
        replacements=[]
        for clip in layer.clips:
            asset=p.asset(clip.asset_id)
            if not asset or asset.kind!='camera' or clip.end<=start or clip.start>=end:
                replacements.append(clip);continue
            lo=max(start,clip.start);hi=min(end,clip.end)
            candidates=[camera for s in used for camera in [s,*s.get('camera_sources',[])]]
            device=asset.metadata.get('device')
            cameras=[s for s in candidates if s.get('video') and (device is None or s.get('camera_device')==device)]
            spans=[(s['start']+float(s.get('video_first') or 0),s['start']+s['duration']) for s in cameras]
            if not _covers(spans,lo,hi):raise ValueError('Camera interval has no complete retained coverage. Arm retention and capture a newer interval.')
            for segment in cameras:
                origin=segment['start']+float(segment.get('video_first') or 0);finish=segment['start']+segment['duration'];a=max(lo,origin);b=min(hi,finish)
                if b<=a:continue
                source=add_asset(p,path=segment['video'],kind='video',name='Camera take · '+Path(segment['video']).stem,duration=max(0,finish-origin),width=640,height=360,metadata={'retained_live':True,'captured_start':origin})
                clone=copy.deepcopy(clip);clone.asset_id=source.id;clone.id=clip.id if not any(c.id==clip.id for c in replacements) else new_id('clp');clone.start=a;clone.duration=b-a;clone.in_point=a-origin;clone.playback_rate=1.;clone.source_policy='hold';replacements.append(clone)
        layer.clips=replacements
        # An internal transition uses original IDs. Captures spanning a camera
        # segment boundary must not leave a dangling link; ordinary camera layers
        # have no transition. Drop only transitions whose referenced clip expired.
        ids={c.id for c in replacements};layer.transitions=[t for t in layer.transitions if t.from_clip in ids and t.to_clip in ids]
    p.recorded_analysis=join_analysis(analysis_segments) or p.recorded_analysis
    mix_segments=[{**s,'analysis':s['reaction_analysis']} for s in used if s.get('reaction_analysis')]
    if mix_segments:p.extra['recorded_mix_analysis']=join_analysis(mix_segments)
    from sound_routes import external_reaction_active
    if external_reaction_active(p):
        if not _covers([(s['reaction_analysis'].get('offset',s['start']),s['reaction_analysis'].get('offset',s['start'])+s['reaction_analysis'].get('duration',s['duration'])) for s in mix_segments],start,end):raise ValueError('The selected interval lacks retained mixed-reaction audio. Retain inputs before performing.')
    attach_retained_sound(p,start,end,used)
    for segment in used:
        for raw in segment.get('raw_sources',[]):
            add_asset(p,path=raw['path'],kind='audio',name=raw.get('label','Raw input')+' · retained original',duration=raw['duration'],metadata={'has_audio':True,'retained_live':True,'source_id':raw['source_id'],'captured_start':segment['start']+raw['first'],'raw_unmixed':True})
    p.extra['retained_segments']=[{k:v for k,v in s.items() if k not in ('analysis','reaction_analysis')} for s in used]
    return capture_interval(p,start,end)


class OutputRecorder:
    """Bounded frame queue; rendered gaps become held frames at a declared FPS.

Only Programme frames enter this queue. Overflow is a visible failure, not a
silent dropped-frame claim. The soundtrack uses the frozen resolved audio bus.
"""
    def __init__(self,directory,start,size,fps=20,profile='web'):
        from media_engine import EXPORT_PROFILES
        if profile not in ('web','small','master'):raise ValueError('Choose a supported recording profile')
        spec=EXPORT_PROFILES[profile]
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True);self.start=float(start);self.size=tuple(size);self.fps=int(fps);self.profile=profile;self.frames=0;self.received=0;self.error='';self.last_time=-math.inf;self.closed=False;self.end=None
        if self.fps<1 or self.fps>60:raise ValueError('Recording frame rate must be between 1 and 60 fps')
        if min(self.size)<16 or any(int(v)%2 for v in self.size):raise ValueError('Recording dimensions must be even and at least 16 pixels')
        self.q=queue.Queue(maxsize=32);self.cancel=threading.Event();self.video=self.directory/('programme.partial'+spec['extension']);self.last=Image.new('RGB',self.size,'black')
        command=[FFMPEG,'-hide_banner','-loglevel','warning','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{size[0]}x{size[1]}','-r',str(self.fps),'-i','pipe:0','-an',*spec['video'],'-threads','2',str(self.video)]
        self.encoder=EncoderPipe(command,self.directory/'record.log',cancel=self.cancel);self.thread=threading.Thread(target=self._run,name='Programme recorder',daemon=True);self.thread.start()
    def submit(self,t,image):
        if self.closed or self.error or t<self.start or t<self.last_time:return False
        try:self.q.put_nowait((float(t),image.copy()));self.last_time=t;self.received+=1;return True
        except queue.Full:self.error='Recording storage could not keep up; frame queue reached its limit.';return False
    def _write_to(self,t):
        target=max(0,math.ceil((t-self.start)*self.fps-1e-8));raw=self.last.tobytes()
        while self.frames<target:self.encoder.write(raw);self.frames+=1
    def _run(self):
        try:
            while True:
                item=self.q.get()
                if item is None:break
                t,image=item;self._write_to(t);self.last=image.convert('RGB').resize(self.size,Image.Resampling.BILINEAR)
            self._write_to(self.end if self.end is not None else self.start+self.frames/self.fps)
            self.encoder.finish()
        except Exception as exc:self.error=str(exc);self.encoder.close()
    def finish(self,project,end,target,integrity=None):
        """Publish one media file after validating the frozen recording integrity record.

        Integrity data is validated in memory and retained only in the private capture cache.
        If final media promotion fails, a complete recording is never claimed.
        """
        from media_engine import EXPORT_PROFILES
        from recording_integrity import SCHEMA
        target=Path(target);spec=EXPORT_PROFILES[self.profile]
        if target.exists():raise FileExistsError('Choose a new output filename; recording will not overwrite a file')
        if target.suffix.lower()!=spec['extension']:raise ValueError('Recording filename does not match the selected export profile')
        if not self.received:raise ValueError('No Programme frames were received')
        self.end=max(self.start+1/self.fps,float(end));self.closed=True;self.q.put(None,timeout=10);self.thread.join(timeout=120)
        if self.thread.is_alive():self.cancel.set();raise TimeoutError('Programme recording finalisation timed out')
        if self.error:raise RuntimeError(self.error)
        target.parent.mkdir(parents=True,exist_ok=True);tmp=target.with_name(target.stem+'.recording-partial'+target.suffix)
        command=[FFMPEG,'-hide_banner','-loglevel','error','-y','-i',str(self.video)]
        has_sound=bool(sound_events(project))
        if has_sound:
            audio=render_audio(project,self.directory/'programme-audio.wav',self.start,self.end)
            command+=['-i',str(audio),'-map','0:v','-map','1:a',*spec['audio']]
        else:command+=['-map','0:v','-an']
        command+=['-c:v','copy','-t',f'{self.end-self.start:.9f}']
        if target.suffix.lower() in ('.mp4','.mov'):command+=['-movflags','+faststart']
        command.append(str(tmp))
        record=None
        try:
            run_process(command,timeout=180)
            run_process([FFMPEG,'-v','error','-i',str(tmp),'-f','null','-'],timeout=180)
            digest=hashlib.sha256()
            with tmp.open('rb') as fh:
                for chunk in iter(lambda:fh.read(1024*1024),b''):digest.update(chunk)
            record={'kind':'neospector/programme-recording','integrity_schema':SCHEMA,'start':self.start,'end':self.end,'fps':self.fps,'size':list(self.size),'profile':self.profile,'frames':self.frames,'received_frames':self.received,'gap_policy':'hold last rendered Programme frame','sound_policy':'Programme Sound route only; Monitor excluded; React-only retention never becomes audible','has_programme_sound':has_sound,'output':str(target),'output_sha256':digest.hexdigest()}
            if integrity is not None:record['integrity']=integrity
            payload=json.dumps(record,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)
            # Validate the integrity payload before exposing the media. It remains internal
            # diagnostic/recovery data rather than a sibling user-facing sidecar file.
            json.loads(payload)
            if target.exists():raise FileExistsError('Output destination appeared during recording; original preserved')
            tmp.replace(target)
            try:(self.directory/'recording.json').write_text(payload)
            except OSError:pass
        finally:
            tmp.unlink(missing_ok=True)
        return target
    def close(self):
        self.cancel.set();self.closed=True
        try:self.q.put_nowait(None)
        except queue.Full:pass
        self.encoder.close()
        self.thread.join(timeout=2)
