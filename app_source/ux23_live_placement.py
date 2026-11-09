"""UX23 queue intents for physical sources, using the existing clip and audio routes.

Nothing acquires a device merely because the source shelf is opened or browsed.
Explicit visual placement prepares capture BEFORE committing a queue clip.
Audio capture is reaction-only; it is never misrepresented as a soundtrack file.
"""
from __future__ import annotations
import copy,threading,time

VISUAL=('camera','screen','window')
AUDIO=('microphone','system','application')

def eligible_source_roles(kind):
    return ('A','B') if kind in VISUAL else ('Music',) if kind in AUDIO else ()

class LiveVisualPlacement:
    def __init__(self,app):self.app=app;self._pending=set()
    def place(self,role,device,kind,action):
        if role not in ('A','B') or kind not in VISUAL or action not in ('now','next','queue'):
            raise ValueError('Unsupported live visual placement')
        app=self.app
        if app.reviewing:return app.update_status('Return to Programme to queue a physical input.')
        if kind!='camera' and not isinstance(device,dict):raise ValueError('Screen or window descriptor required')
        from instrument_model import voice
        if voice(app.project,role).locked:return app.update_status('Unlock channel '+role+' first.')
        device=copy.deepcopy(device);pid=app.project.id
        from multi_live import ChannelLiveInputs
        key=ChannelLiveInputs.camera_key(device)
        if key in self._pending:return app.update_status('That input is already being prepared.')
        self._pending.add(key)
        app.update_status('Preparing '+kind+' for '+role+' · queue unchanged until ready')
        def work():
            try:
                cap=app.live.acquire_camera(device)
                deadline=time.monotonic()+7
                while cap.state=='starting' and time.monotonic()<deadline and not app.closing:time.sleep(.03)
                if cap.state!='live':raise RuntimeError(cap.error or 'No live frames received')
                def ready():
                    self._pending.discard(key)
                    if app.closing or app.project.id!=pid:
                        if not app.closing:app.release_unassigned_cameras()
                        return
                    from sequencer_model import add_asset
                    try:
                        from instrument_model import voice
                        if voice(app.project,role).locked:raise ValueError('Channel locked while preparing source')
                        asset=next((a for a in app.project.assets.values() if a.kind==kind and a.metadata.get('device')==device),None)
                        if asset is None:
                            asset=app.transaction('Register chosen '+kind,lambda:add_asset(app.project,path='live:'+kind,kind=kind,
                               name=('Camera' if kind=='camera' else 'Screen' if kind=='screen' else 'Window')+' · '+str(device.get('name',device) if isinstance(device,dict) else device),
                               duration=0,metadata={'device':copy.deepcopy(device),'sequence_preferences':{'clip_min':10.,'fit':'cover'}}))
                        if asset is not None:
                            app.place_media([asset.id],role,action=action)
                            app.update_status(kind.title()+' placed in '+role+' · live input will stop when no longer assigned')
                    except (ValueError,RuntimeError,KeyError) as exc:
                        app.update_status('Source not queued: '+str(exc)+' · previous playback preserved')
                        app.release_unassigned_cameras()
                app.events.put(('call',ready))
            except Exception as exc:
                def failed(message=str(exc)):
                    self._pending.discard(key)
                    app.update_status(kind.title()+' could not be prepared: '+message+' · queue unchanged')
                app.events.put(('call',failed))
        app.camera_task('Queue live '+kind,work)

class AudioCueQueue:
    """AUDIO queue route cues run against the programme clock; they do not decode as files."""
    KEY='ux23_audio_input_cues'
    def __init__(self,app):self.app=app;self.fired=set();self.project_id=None
    def items(self):return list(self.app.project.extra.get(self.KEY,[]))
    def enqueue(self,device,label,action):
        if action not in ('now','next','queue'):raise ValueError('Unsupported audio placement')
        import uuid
        app=self.app
        if getattr(app,'reviewing',False):return app.update_status('Audio capture is only available in Programme.')
        now=app.programme_time() if app.playing else app.playhead
        existing=self.items()
        soundtrack=app.project.extra.get('sound_events',[])
        def end(event):return float(event.get('start',0.))+float(event.get('duration',0.))
        currently=[e for e in soundtrack if float(e.get('start',0))<=now<end(e)]
        if action=='now':position=now
        elif action=='next':position=max([now]+[end(e) for e in currently])
        else:position=max([now]+[end(e) for e in soundtrack]+[float(c['start'])+.1 for c in existing])
        cue={'id':'acue-'+uuid.uuid4().hex[:12],'start':position,'label':str(label),'device':copy.deepcopy(device),'react_only':True}
        def edit():app.project.extra.setdefault(self.KEY,[]).append(cue)
        app.transaction('Cue live reaction input',edit)
        if action=='now':self.step(force=True)
        return cue
    def step(self,force=False):
        app=self.app
        if self.project_id!=app.project.id:
            self.project_id=app.project.id;self.fired.clear()
        if app.reviewing or (not app.playing and not force):return
        now=app.programme_time() if app.playing else app.playhead
        for cue in sorted(self.items(),key=lambda c:float(c.get('start',0))):
            if cue['id'] not in self.fired and float(cue['start'])<=now+1e-6:
                self.fired.add(cue['id'])
                app.start_sound_source(copy.deepcopy(cue['device']),cue['label'],react_only=True)
    def remove(self,cue_id):
        def edit():self.app.project.extra[self.KEY]=[c for c in self.items() if c['id']!=cue_id]
        self.app.transaction('Remove queued audio input cue',edit)
        self.fired.discard(cue_id)
