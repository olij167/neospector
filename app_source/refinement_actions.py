"""Direct source, queue, rack and sound commands for the instrument shell.

These methods use the existing transaction/history API. Hardware preparation is
asynchronous and only the final ready assignment is committed on Tk's thread.
"""
from __future__ import annotations
import copy,json,math,sys,threading,time,random
from pathlib import Path
import tkinter as tk
from tkinter import ttk,simpledialog
from sequencer_model import add_asset,new_id,_encode
from instrument_model import voice
from queue_model import ordered,current,mode_at,queue_position,switch_source,hold_current,take_next,append_assets,reorder,set_duration,remove
from sound_routes import ensure_route,update_route,use_only,source_id,default_route,primary_route_changes,BUILTINS
from module_engine import randomise_rack,compile_rack
from sequence_edit import replace_clip_media,add_transition
from audio_bus import sound_events,add_sound

class RefinementActions:
    def configure_sound_sources(self):
        if hasattr(self.live,'configure'):
            t=self.programme_time() if getattr(self,'playing',False) and not getattr(self,'reviewing',False) else getattr(self,'playhead',0.)
            self.live.configure(self.programme_project().extra.get('sound_routes',{}),t)
    def _recording_route_guard(self,rid,candidate):
        """Prepare an external Sound/React route before it can affect a take."""
        if self.reviewing or not self.output_recording or rid in BUILTINS:return True
        from sound_routes import contribution
        if contribution(candidate,'sound')<=0 and contribution(candidate,'react')<=0:return True
        state=self.live.source_states().get(rid,{})
        if state.get('state')!='live':
            self.update_status('Recording route blocked · start '+candidate.get('label',rid)+' before enabling Sound/React.')
            return False
        if not self.live.recording:
            self.output_auto_retention=getattr(self,'output_auto_retention',False) or not bool(self.retain_armed.get())
            self.retain_armed.set(True);self.toggle_retention()
            if not self.live.recording:
                self.update_status('Recording route blocked · retained audio could not be armed.')
                return False
        return True
    def edit_sound_route(self,rid,changes,gesture=False):
        now=self.programme_time() if self.playing and not self.reviewing else self.playhead
        # Validate against a detached candidate so a rejected edit cannot create
        # or alter a route as a side effect of the guard itself.
        current=self.project.extra.get('sound_routes',{}).get(rid)
        candidate=copy.deepcopy(current if current is not None else default_route(rid));candidate.update(changes)
        if not self._recording_route_guard(rid,candidate):return False
        if gesture:
            update_route(self.project,rid,changes,now);self.changed()
        else:self.transaction('Sound source '+rid,lambda:update_route(self.project,rid,changes,now))
        self.configure_sound_sources()
        # Real-time PCM analysis is fed by the bus while playing. Debounce the
        # offline analysis so dragging a fader does not repeatedly render a song.
        if rid in BUILTINS:
            if getattr(self,'route_analysis_job',None):
                try:self.after_cancel(self.route_analysis_job)
                except tk.TclError:pass
            self.route_analysis_job=self.after(800,lambda:(setattr(self,'route_analysis_job',None),self.prepare_sound_analysis()))
    def only_sound_source(self,rid):
        now=self.programme_time() if self.playing and not self.reviewing else self.playhead
        current=self.project.extra.get('sound_routes',{}).get(rid)
        candidate=copy.deepcopy(current if current is not None else default_route(rid));candidate.update(enabled=True,muted=False)
        if not self._recording_route_guard(rid,candidate):return False
        self.transaction('Use only this sound source',lambda:use_only(self.project,rid,now));self.configure_sound_sources();return True
    def set_sound_source_enabled(self,rid,enabled,device=None,label=None):
        """One product-level ON/OFF action for a mixer input.

        External inputs own both their physical capture lifetime and their route;
        built-in queue/video sources only own routing.  Default ON means Sound +
        React, while an explicitly customized Advanced Routing combination is
        preserved across later OFF/ON toggles.
        """
        enabled=bool(enabled);current=self.project.extra.get('sound_routes',{}).get(rid)
        route=copy.deepcopy(current if current is not None else default_route(rid,label or ''))
        if rid in BUILTINS:
            return self.edit_sound_route(rid,primary_route_changes(route,enabled))
        state=self.live.source_states().get(rid,{})
        if not enabled:
            if current is None:return False
            return self.stop_sound_source(rid)
        if state.get('state') in ('starting','live'):
            return self.edit_sound_route(rid,primary_route_changes(route,True))
        device=copy.deepcopy(device if device is not None else route.get('device'))
        if device is None:
            self.update_status('Choose or refresh this input before turning it on.');return False
        return self.start_sound_source(device,label or route.get('label',rid))
    def start_sound_source(self,device,label='Microphone',*,react_only=False):
        if self.reviewing:return self.update_status('Return to Programme before enabling a physical input. Review uses retained material.')
        pid=self.project.id;self.update_status('Starting '+label+' · existing sources remain active')
        def work():
            try:
                # Stage the physical source silent until the project route has passed
                # the recording guard and is committed. This closes the sub-frame
                # window where a new source could otherwise influence React first.
                sid=self.live.add_audio(device,label,staged=True)
                until=time.monotonic()+7
                while self.live.source_states().get(sid,{}).get('state')=='starting' and time.monotonic()<until:time.sleep(.03)
                state=self.live.source_states().get(sid,{})
                if state.get('state')!='live':raise RuntimeError(state.get('error') or 'Input did not become ready. Check its device and permission.')
                def ready():
                    if self.closing:self.live.stop_audio(sid);return
                    if self.project.id!=pid:return self.stop_sound_source(sid)
                    if self.output_recording and not self.live.recording:
                        self.output_auto_retention=getattr(self,'output_auto_retention',False) or not bool(self.retain_armed.get())
                        self.retain_armed.set(True);self.toggle_retention()
                        if not self.live.recording:
                            self.live.stop_audio(sid);self.update_status('Input not added · recording retention could not be armed.');return
                    def apply():
                        now=self.programme_time() if self.playing and not self.reviewing else self.playhead
                        route=self.project.extra.get('sound_routes',{}).get(sid,default_route(sid,label))
                        changes=dict(device=copy.deepcopy(device),label=label,kind=device.get('kind','microphone') if isinstance(device,dict) else 'microphone',muted=False)
                        changes.update(primary_route_changes(route,True))
                        if react_only:changes.update(sound=False,react=True,monitor=False)
                        update_route(self.project,sid,changes,now)
                    self.transaction('Add live sound source',apply);self.configure_sound_sources()
                    if not isinstance(device,dict) or device.get('kind')=='microphone':self.last_microphone_device=copy.deepcopy(device)
                    if not self.playing:self.toggle_play()
                    self.update_status(label+(' ON · React only' if react_only else ' ON · Sound + React'))
                self.events.put(('call',ready))
            except Exception as exc:self.events.put(('status','Input could not start: '+str(exc)))
        threading.Thread(target=work,name='Start sound source',daemon=True).start()
    def quick_microphone(self,device=None):
        device=device if device is not None else getattr(self,'last_microphone_device','default' if sys.platform.startswith('linux') else '0')
        sid=source_id(device);state=self.live.source_states().get(sid,{})
        if state.get('state') in ('starting','live'):self.stop_sound_source(sid);return
        self.start_sound_source(device,'Microphone' if not isinstance(device,dict) else device.get('label','Device audio'))
    def stop_sound_source(self,sid):
        if self.reviewing:return self.update_status('Return to Programme to change running devices.')
        self.edit_sound_route(sid,{'enabled':False})
        threading.Thread(target=lambda:self.live.stop_audio(sid),name='Stop sound input',daemon=True).start()
    def stop_inputs(self):
        if self.reviewing:return self.update_status('Return to Programme to stop the performance inputs.')
        self.retain_armed.set(False)
        def work():
            try:
                with self.retention_lock:
                    if self.live.recording:self.recorded_segments.append(self.live.stop_recording())
                    self.live.stop_all()
                self.events.put(('status','All physical inputs stopped. Retained recordings are preserved.'))
            except Exception as exc:self.events.put(('status','Stop inputs: '+str(exc)))
        threading.Thread(target=work,name='Stop instrument inputs',daemon=True).start()
    def quick_camera(self,role='A',device=None):
        if self.reviewing:return self.update_status('Return to Programme to enable a camera. Review never substitutes fresh input.')
        layer=voice(self.project,role)
        if layer.locked:return self.update_status('Unlock the voice before switching sources.')
        now=self.programme_time() if self.playing else self.playhead
        if device is None and mode_at(layer,now)['mode']=='camera':return self.queue_source(role,'queue')
        device=device or getattr(self,'last_camera_device','/dev/video0' if sys.platform.startswith('linux') else '0');pid=self.project.id
        def commit_ready():
            if self.closing:return
            if self.project.id!=pid:return self.update_status('Camera prepared; original session is no longer active. Stop inputs in Sources.')
            def apply():
                a=next((a for a in self.project.assets.values() if a.kind=='camera' and a.metadata.get('device')==device),None)
                if a is None:a=add_asset(self.project,path='live:camera',kind='camera',name='Camera',metadata={'device':device})
                now=self.programme_time() if self.playing else self.playhead;switch_source(voice(self.project,role),'camera',now,camera_id=a.id)
                self.selected_layer_id=voice(self.project,role).id;self.deck.scope.set('Layer');self.last_camera_device=device
            self.transaction('Camera on '+role+' · queue preserved',apply)
            if not self.playing:self.toggle_play()
            self.update_status('Camera on '+role+' · switch back to Queue to resume its held position')
        if self.live.camera and self.live.camera.device==device and self.live.camera.state=='live':commit_ready();return
        if getattr(self,'camera_starting',False):return self.update_status('Camera is preparing…')
        self.camera_starting=True;self.update_status('Preparing camera · current output stays valid')
        def work():
            try:
                self.live.start_camera(device);until=time.monotonic()+7
                while self.live.camera and self.live.camera.state=='starting' and time.monotonic()<until:time.sleep(.03)
                if not self.live.camera or self.live.camera.state!='live':raise RuntimeError(getattr(self.live.camera,'error','') or 'Camera did not become ready. Check permission and device.')
                self.events.put(('call',commit_ready))
            except Exception as exc:self.events.put(('status','Camera: '+str(exc)))
            finally:self.camera_starting=False
        threading.Thread(target=work,name='Prepare shared camera',daemon=True).start()
    def queue_source(self,role,mode):
        if mode=='camera':
            device=voice(self.project,role).extra.get('camera_device')
            if isinstance(device,dict) and device.get('kind') in ('screen','window'):
                return self.open_visual_source(role)
            return self.quick_camera(role)
        now=self.programme_time() if self.playing and not self.reviewing else self.playhead
        self.transaction('Resume '+role+' queue',lambda:switch_source(voice(self.project,role),'queue',now))
    def set_queue_policy(self,role,policy):
        from queue_policies import set_music_policy,set_visual_policy
        now=self.programme_time() if self.playing and not self.reviewing else 0.
        self.transaction('Queue end policy',lambda:set_music_policy(self.project,policy,now) if role=='Music' else set_visual_policy(voice(self.project,role),policy,now))
    def hold_queue(self,role):
        now=self.programme_time() if self.playing and not self.reviewing else self.playhead
        self.transaction('Hold/resume queue item',lambda:hold_current(voice(self.project,role),now))
    def queue_next(self,role,clip_id=None):
        now=self.programme_time() if self.playing and not self.reviewing else self.playhead
        self.transaction('Take queue item',lambda:take_next(voice(self.project,role),now,clip_id))
        if not self.playing and not self.reviewing:self.toggle_play()
    def queue_selected(self,role='A',before=None,after=None,asset_ids=None):
        ids=asset_ids or list(self.library.selection()) or ([self.selected_asset_id] if self.selected_asset_id else [])
        if not ids:return self.update_status('Select media in the Library, then Add to '+role+'.')
        visual=[aid for aid in ids if self.project.asset(aid) and self.project.asset(aid).kind!='audio']
        if not visual:
            self.queue_sound_selected(ids)
            return self.update_status('Audio belongs to Music Queue · added there instead of a picture channel.')
        self.transaction('Add selected media to '+role,lambda:append_assets(self.project,voice(self.project,role).id,visual,before=before,after=after));self.focus_voice(role)
        if len(visual)!=len(ids):self.update_status('Visual sources added to '+role+'. Select Add to Music Queue for the sound files.')
    def queue_sound_selected(self,asset_ids=None):
        ids=asset_ids or list(self.library.selection()) or ([self.selected_asset_id] if self.selected_asset_id else [])
        eligible=[i for i in ids if self.project.asset(i) and (self.project.asset(i).kind=='audio' or self.project.asset(i).metadata.get('has_audio'))]
        if not eligible:return self.update_status('Select audio files or videos with sound in the Library.')
        def apply():
            r=ensure_route(self.project,'soundtrack');r.update(enabled=True,sound=True,react=True,monitor=True)
            for aid in eligible:
                events=[e for e in sound_events(self.project) if e.get('route_id')=='soundtrack'];end=max((e['start']+e['duration'] for e in events),default=self.playhead)
                add_sound(self.project,aid,start=end,fade=0.)
        self.transaction('Add to audio queue',apply);self.prepare_sound_analysis();self.configure_sound_sources()
    def queue_move(self,role,cid,index):self.transaction('Reorder '+role+' queue',lambda:reorder(self.project,voice(self.project,role).id,cid,index))
    def queue_duration(self,cid,duration):self.transaction('Set occurrence duration',lambda:set_duration(self.project,cid,duration))
    def queue_remove(self,role,cid):
        if cid:
            # A queued camera/screen is a real live resource. Releasing the
            # final reference must stop it rather than leaving capture running.
            from instrument_model import voice
            layer=voice(self.project,role) if role in ('A','B') else None
            clip=next((c for c in layer.clips if c.id==cid),None) if layer else None
            asset=self.project.asset(clip.asset_id) if clip else None
            live=bool(asset and asset.kind in ('camera','screen','window'))
            now=self.programme_time() if self.playing and not self.reviewing else self.playhead
            self.transaction('Remove queue occurrence',lambda:remove(self.project,cid,now=now))
            if live:self.release_unassigned_cameras()
    def replace_queue_clip(self,role,cid):
        if not self.selected_asset_id:return self.update_status('Choose replacement media in the Library first.')
        self.transaction('Replace media, preserve treatment',lambda:replace_clip_media(self.project,cid,self.selected_asset_id))
    def queue_transition(self,role,cid):
        layer=voice(self.project,role);items=ordered(layer);i=next((i for i,c in enumerate(items) if c.id==cid),-1)
        if i<0 or i+1>=len(items):return self.update_status('Add another queue item before creating this transition.')
        tr=next((tr for tr in layer.transitions if tr.from_clip==cid and tr.to_clip==items[i+1].id),None)
        if tr is None:tr=self.transaction('Create transition bridge',lambda:add_transition(self.project,layer.id,cid,'dissolve',min(.6,items[i].duration*.4,items[i+1].duration*.4)))
        if tr:self.selected_layer_id=layer.id;self.selected_transition_id=tr.id;self.deck.scope.set('Transition');self.deck.refresh(True)
    def generate_queue(self,role):
        self.focus_voice(role);self.conductor.scope.set('layer');self.mutate(scope='layer')
    def toggle_precision(self):
        value=not self.precision_visible.get();self.precision_visible.set(value)
        if value:self.timeline.grid();self.timeline.zoom_fit()
        else:self.timeline.grid_remove()
        self.precision_button.configure(text='Hide timing' if value else 'Timing ▾')
    def randomise_current_rack(self,seed=None,selected=None,rebuild=False):
        scope=self.deck.scope.get();l,c=self.get_edit_target()
        if scope=='Master':owner=self.project;rack=owner.master_rack
        else:
            owner=c if scope=='Clip' else self.deck.owner if scope=='Layer' and getattr(self.deck,'history_proxy',None) else l
            if owner is None:return self.update_status('Select a voice or an occurrence for its rack.')
            rack=owner.rack
        if not self.can_edit(owner):return
        if seed is None:seed=int(self.project.extra.get('rack_seed',730))+1
        def apply():
            # Validate on a copy so invalid imported modules cannot partially vary.
            trial=copy.deepcopy(rack);randomise_rack(trial,seed,selected=selected,rebuild=rebuild)
            changed=randomise_rack(rack,seed,selected=selected,rebuild=rebuild);self.project.extra['rack_seed']=int(seed);return changed
        count=self.transaction('Randomise reactive rack',apply)
        if count:self.update_status('Reactive rack varied · sources, queue timing, capture and locked work are unchanged. Keep or Undo to compare.')
    def main_browser_visible(self,ids):
        for aid in ids:
            a=self.project.asset(aid)
            if a is None:continue
            if aid in self.thumbnails:self.library.item(aid,image=self.thumbnails[aid])
            else:self.request_thumbnail(a)
    def quick_guide_refined(self):
        from help_browser import show
        return show(self)
