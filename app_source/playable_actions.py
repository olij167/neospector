"""Bounded orchestration over the existing generator, rack and event engines."""
from __future__ import annotations
from conductor_targets import DEFAULTS
import copy,random,threading,time
from dataclasses import fields
from sequencer_model import Clip,project_to_dict,new_id
from instrument_model import voice,archive_styles
from playable_intent import load_intent,plan_randomise,fingerprint
from music_queue import items,store
from audio_bus import add_sound
from conductor import generate,stream
from neospector_catalog import FACTORY_GROUPS,build_group
from module_engine import randomise_rack,compile_rack,children
from queue_model import queue_position,mode_at,append_switch
from playable_queues import performed_visual_ids

class Superseded(Exception):pass

from rack_protection import composition_locked, conductor_protected as rack_protected

def prepare_candidate(project,intent,scope,*,seed,now,playing,live_state,cancel=lambda:False,only_role=None,automatic=False,settings=None):
    deadline=time.monotonic()+8.;p=copy.deepcopy(project);plan=plan_randomise(p,intent,scope,now=now,playing=playing,live_state=live_state)
    from omne_randomise import normalise_settings,make_rack
    options=normalise_settings(settings) if settings is not None else None
    start,end=plan['interval'];first_change=float('inf');original_duration=p.duration
    count_limit=options['queue_count'] if options and options['queue_mode']=='items' else None
    if options and options['queue_mode']=='seconds':end=now+options['queue_seconds']
    if options and options['queue_mode']=='song':
        events=items(p);active=next((e for e in reversed(events) if e['start']<=now<e['start']+e['duration']),None)
        end=active['start']+active['duration'] if active else max([now+options['queue_seconds']]+[e['start']+e['duration'] for e in events])
    # An explicit Music request may fill its pool while still preserving the chosen current song.
    if only_role=='Music' and intent['music']['mode'] not in ('off','live'):
        from playable_intent import eligible_assets
        choice=copy.deepcopy(intent['music']);choice['mode']='auto';choice.pop('asset_id',None)
        plan['pools']['Music']=[a.id for a in eligible_assets(p,choice,'music')]
        plan['music_action']='replace_future' if items(p) else 'fill'
    if only_role=='Visuals':plan['music_action']='keep'

    if automatic:
        if not p.conductor.extra.get('evolve_sources',DEFAULTS['evolve_sources']):plan['queue_roles']=[]
        if not p.conductor.extra.get('evolve_sound',DEFAULTS['evolve_sound']):plan['music_action']='keep'
        if not p.conductor.extra.get('evolve_treatment',DEFAULTS['evolve_treatment']):plan['effect_targets']=[]
    if cancel():raise Superseded()
    if only_role is not None and only_role!='Visuals':
        plan['queue_roles']=[r for r in plan['queue_roles'] if r==only_role]
        if only_role!='Music':plan['music_action']='keep'
    if plan['music_action'] in ('fill','replace_future'):
        events=items(p);rng=stream(seed,'playable-music');pool=plan['pools'].get('Music',[])
        music_cycle=None
        if events and p.extra.get('music_queue_policy')=='repeat' and (playing or now>0):
            from queue_policies import next_music_cycle,preserve_music_history,set_music_origin
            music_cycle=next_music_cycle(p,now)
            if automatic and p.extra.get('music_generation_at',0)>now:
                pool=[]
            elif pool:
                preserve_music_history(p,music_cycle);set_music_origin(p,music_cycle)
                p.extra['music_generation_at']=music_cycle
        # Preserve manual events, pins, history and both active crossfade participants.
        keep=[e for e in events if not pool or not e.get('playable_auto') or e.get('pinned') or e.get('locked') or e.get('queue_gap') or (music_cycle is None and (playing or now>0) and e['start']<=now+.5)]
        music_end=max(.1,end-start) if music_cycle is not None else end
        future_start=max([0. if music_cycle is not None else start]+[e['start']+e['duration'] for e in keep]);replacement=[];cursor=future_start
        count=0
        if count_limit and pool:music_end=max(music_end,cursor+count_limit*max(p.asset(a).duration for a in pool)+1)
        while pool and cursor<music_end-.01 and count<(count_limit or 256):
            if cancel():raise Superseded()
            weights=[max(0.,float(p.asset(i).metadata.get('sequence_preferences',{}).get('weight',1.))) for i in pool]
            if not any(weights):break
            aid=rng.choices(pool,weights=weights,k=1)[0];a=p.asset(aid);pref=a.metadata.get('sequence_preferences',{});source_in=max(0.,float(pref.get('source_in',0)))
            speed=float(pref.get('playback_rate',1.));dur=max(.01,(min(a.duration,float(pref.get('source_out',a.duration)))-source_in)/speed)
            if dur<=.01:break
            replacement.append(dict(id=new_id('snd'),asset_id=aid,start=cursor,duration=dur,in_point=source_in,gain=float(pref.get('sound_gain',1.)),playback_rate=speed,source_lo=source_in,source_hi=min(a.duration,float(pref.get('source_out',a.duration))),enabled=True,fade_in=0.,fade_out=0.,curve='equal_power',route_id='soundtrack',playable_auto=True))
            cursor+=dur;count+=1
            if not options and intent.get('duration_mode')=='song' and not events:break
        store(p,keep+replacement)
        if replacement:first_change=min(first_change,(music_cycle or 0.)+replacement[0]['start'])
        if (not options or options['queue_mode']=='song') and intent.get('duration_mode')=='song' and (keep or replacement):end=max(e['start']+e['duration'] for e in keep+replacement)
    if scope!='effects':
        if not items(project) and not any(l.clips for l in project.layers) and intent.get('duration_mode')=='song':p.duration=end
        else:p.duration=max(p.duration,end)
    for ordinal,role in enumerate(plan['queue_roles']):
        if cancel():raise Superseded()
        layer=voice(p,role);old=copy.deepcopy(layer.clips);old_ids={c.id for c in old}
        if mode_at(layer,now)['mode'] in ('hold','camera'):continue
        cycle=None
        if old and layer.extra.get('queue_policy')=='repeat' and (playing or now>0):
            if automatic and layer.extra.get('queue_generation_at',0)>now:continue
            from queue_policies import next_visual_cycle,preserve_visual_history
            cycle=next_visual_cycle(layer,now);preserve_visual_history(layer,cycle)
            append_switch(layer,cycle,'queue',0.);layer.extra['queue_generation_at']=cycle
            qnow=0.;qstart=0.;qend=max(.1,end-start)
            protected=set()
        else:
            qnow=queue_position(layer,now);qstart=qnow+max(0.,start-now);qend=qnow+max(0.,end-now)
            protected=performed_visual_ids(layer,now+(.5 if playing else 0.))
        protected.update(c.id for c in old if c.locked or c.manual or c.timing_locked or c.extra.get('playable_pin') or c.extra.get('queue_gap'))
        for tr in layer.transitions:
            if tr.locked or tr.manual or tr.from_clip in protected or tr.to_clip in protected:protected.update((tr.from_clip,tr.to_clip))
        boundary=max([qstart]+[c.end for c in old if c.id in protected and c.start<=qstart<c.end])
        if count_limit:
            maximum=max([p.conductor.clip_max]+[float(p.asset(aid).metadata.get('sequence_preferences',{}).get('clip_max',p.conductor.clip_max)) for aid in plan['pools'][role]])
            qend=max([boundary]+[c.end for c in old if c.id in protected])+count_limit*min(240,max(.1,maximum))+.1
        if boundary>=qend:continue
        original_transitions=copy.deepcopy(layer.transitions)
        for c in layer.clips:
            if c.id in protected:c.locked=True
        previous_pool=p.conductor.extra.get('pool_ids');had_pool='pool_ids' in p.conductor.extra
        p.conductor.extra['pool_ids']=plan['pools'][role]
        saved_duration=p.duration;p.duration=max(p.duration,qend)
        if options or cycle is not None:
            # Replace only disposable future material; don't leave a stale tail after a smaller request.
            layer.clips=[c for c in layer.clips if c.id in protected or c.end<=qstart]
            retained={c.id for c in layer.clips}
            layer.transitions=[tr for tr in layer.transitions if tr.from_clip in retained and tr.to_clip in retained]
        cursor=boundary;chunk=0
        while cursor<qend-1e-6:
            if cancel():raise Superseded()
            if time.monotonic()>deadline or sum(len(l.clips) for l in p.layers)>6000:raise ValueError('Preparation limit reached. Choose a shorter queue or longer clips; current work is unchanged.')
            stop=qend if count_limit else min(qend,cursor+45.)
            generate(p,seed+ordinal*7919+chunk*104729,scope='layer',layer_id=layer.id,time_range=(cursor,stop),max_new_clips=count_limit)
            cursor=stop;chunk+=1
        p.duration=saved_duration
        originals={c.id:c for c in old if c.id in protected}
        layer.clips=[originals.get(c.id,c) for c in layer.clips]
        prior_transitions={tr.id:tr for tr in original_transitions if tr.locked or tr.manual or tr.from_clip in protected or tr.to_clip in protected}
        layer.transitions=[prior_transitions.get(tr.id,tr) for tr in layer.transitions]
        kept_ids={c.id for c in layer.clips}
        for c in old:
            if c.id not in kept_ids:first_change=min(first_change,cycle if cycle is not None else now+c.start-qnow)
        if had_pool:p.conductor.extra['pool_ids']=previous_pool
        else:p.conductor.extra.pop('pool_ids',None)
        for c in layer.clips:
            if c.id in old_ids:continue
            c.extra['playable_auto']=True;first_change=min(first_change,(cycle+c.start) if cycle is not None else now+c.start-qnow)
            if scope=='queues':
                # New occurrences inherit the nearest recipe; no source-side rack reroll.
                source=min(old,key=lambda x:abs(x.start-c.start)) if old else Clip('template',c.asset_id)
                for key in ('rack','effects','opacity','scale','x','y','rotation','blend_mode','mask'):
                    if hasattr(source,key):setattr(c,key,copy.deepcopy(getattr(source,key)))
    if live_state.get('camera')=='live':
        old_ids={c.id for l in project.layers for c in l.clips}
        for l in p.layers:
            if l.extra.get('voice') not in plan['queue_roles']:continue
            for c in l.clips:
                if c.id not in old_ids and not c.locked and not c.opacity.extra.get('conductor_locked'):c.opacity.value=min(c.opacity.value,.65)
    if plan['effect_targets'] and only_role is None:
        protect=rack_protected if automatic else composition_locked
        protected=[f for f in p.master_rack if protect(f)]
        # A wholly protected existing rack is a no-op, not permission to add past it.
        if not p.master_rack or len(protected)!=len(p.master_rack):
            if options:p.master_rack=make_rack(p.master_rack,seed=seed+307,count=options['module_count'],variation=options['variation'],purpose='conductor' if automatic else 'composition')
            else:p.master_rack=make_rack(p.master_rack,seed=seed+307,count=max(1,len(protected)+1),variation=1.,purpose='conductor' if automatic else 'composition')
    old_transitions={tr.id:tr for l in project.layers for tr in l.transitions}
    for layer in p.layers:layer.transitions=[copy.deepcopy(old_transitions.get(tr.id,tr)) for tr in layer.transitions]
    if options:
        p.extra['randomise_settings']=copy.deepcopy(options)
        p.duration=max([original_duration]+[c.end for l in p.layers for c in l.clips]+[e['start']+e['duration'] for e in items(p)])
        plan['summary']+=' · '+(str(count_limit)+' new items per eligible queue' if count_limit else 'length by '+options['queue_mode'])
    p.extra['playable_intent']=copy.deepcopy(intent);p.mutation_seed=seed
    plan['first_structural_change']=first_change
    before=project_to_dict(project);after=project_to_dict(p)
    plan['changed']=any(before.get(k)!=after.get(k) for k in ('layers','master_rack','sound_events','duration'))
    return p,plan

class PlayableActions:
    def cancel_pending_play(self):
        self._playable_ticket=getattr(self,'_playable_ticket',0)+1
        self._playable_latest=None;self._playable_play_requested=False
    def randomise_playable(self,scope=None,*,only_role=None,play_after=False,automatic=False,settings=None):
        if self.reviewing and not automatic:return self.update_status('Review is independent. Return to Programme before randomising Programme.')
        if automatic and self.gesture:return
        if self.gesture:self.end_gesture()
        target=self.programme_project() if automatic else self.project
        intent=self.source_intent(target);scope=scope or intent.get('global_randomise_scope','all')
        if not automatic and hasattr(self,'request_media_for_randomise') and self.request_media_for_randomise(scope,only_role,play_after,settings):return
        if play_after:self._playable_play_requested=True
        if not automatic:intent['global_randomise_scope']=scope
        self._playable_ticket=getattr(self,'_playable_ticket',0)+1
        request={'ticket':self._playable_ticket,'project':copy.deepcopy(target),'intent':intent,'scope':scope,
                 'seed':target.mutation_seed+self._playable_ticket,'now':self.programme_time(),'playing':self.playing,
                 'live_state':{'camera':getattr(self.live.camera,'state','stopped')},'revision':self.programme_revision() if automatic else self.revision,'context':id(target),'only_role':only_role,'play_after':play_after,'automatic':automatic,'settings':copy.deepcopy(settings if settings is not None else target.extra.get('randomise_settings'))}
        request['fingerprint']=fingerprint(target,intent)
        self._playable_latest=request
        if not automatic and hasattr(self,'randomise_label'):self.randomise_label.set('Randomise '+scope.title())
        self.update_status('Preparing next variation · current output continues')
        if hasattr(self,'performance_status'):self.performance_status.set('Preparing next variation…')
        if not getattr(self,'_playable_running',False):self._start_playable_request()
    def _start_playable_request(self):
        if self.closing:return
        if self.mutating:
            if not getattr(self,'_playable_waiting',False):
                self._playable_waiting=True
                def retry():
                    self._playable_waiting=False
                    if self._playable_latest:self._start_playable_request()
                self.after(80,retry)
            return
        r=self._playable_latest;self._playable_latest=None;self._playable_running=True;self.mutating=True
        def work():
            try:
                source=r['project'];intent=r['intent'];r['pool_tokens']={}
                if r['scope']!='effects' and getattr(self,'catalog',None) is not None:
                    from playable_intent import prepare_source_pools
                    source,intent,r['pool_tokens']=prepare_source_pools(source,intent,self.catalog,only_role=r['only_role'])
                candidate,plan=prepare_candidate(source,intent,r['scope'],seed=r['seed'],now=r['now'],playing=r['playing'],live_state=r['live_state'],only_role=r['only_role'],automatic=r['automatic'],settings=r.get('settings'),cancel=lambda:self.closing or r['ticket']!=self._playable_ticket)
                from playable_intent import used_candidate_assets
                used=used_candidate_assets(candidate)
                candidate.assets={aid:a for aid,a in candidate.assets.items() if aid in r['project'].assets or aid in used}
                candidate.extra['playable_intent']=copy.deepcopy(r['intent'])
                plan['fingerprint']=r['fingerprint']
                result=(candidate,plan,None)
            except Exception as exc:result=(None,None,exc)
            self.events.put(('call',lambda:self._finish_playable(r,*result)))
        self._playable_thread=threading.Thread(target=work,name='Playable preparation',daemon=True);self._playable_thread.start()
    def _finish_playable(self,r,candidate,plan,error):
        self._playable_running=False;self.mutating=False
        if self.closing:return
        if r['ticket']==self._playable_ticket:
            automatic=r.get('automatic',False);target=self.programme_project() if automatic else self.project
            revision=self.programme_revision() if automatic else self.revision
            valid=((automatic or not self.reviewing) and id(target)==r['context'] and revision==r['revision'])
            if valid and not error:valid=fingerprint(target,self.source_intent(target))==plan['fingerprint']
            pool_message=None
            if valid and not error and r.get('pool_tokens'):
                from source_pool import source_pool_choice,resolve_source_pool
                try:
                    for kind,record in r['pool_tokens'].items():
                        choice=source_pool_choice(target,kind)
                        if choice!=record['choice'] or resolve_source_pool(target,choice,kind,catalog=self.catalog)['token']!=record['token']:
                            valid=False
                            pool_message='Variation discarded: source pool changed or became unavailable. Review the source pool and try again.'
                            break
                except Exception:
                    valid=False
                    pool_message='Variation discarded: source pool could not be validated. Review the source pool and try again.'
            if valid and not error and self.playing:valid=plan['first_structural_change']>=self.programme_time()
            if error and not isinstance(error,Superseded):message='Randomise: '+str(error)
            elif pool_message:message=pool_message
            elif not valid:message='Variation discarded: target or playing boundary changed. Your newer work is preserved.'
            elif candidate:
                if plan['changed']:
                    from omne_timeline_model import record_decision
                    record_decision(candidate,now=r['now'],seed=r['seed'],scope=r['scope'],automatic=automatic)
                def commit():
                    self.project=candidate;self.history.current=candidate
                if automatic and self.reviewing:
                    state=self._review_state;state['history'].checkpoint();state['project']=candidate;state['history'].current=candidate;state['revision']+=1;state['dirty']=True
                else:self.transaction('Randomise '+r['scope'].title(),commit)
                self.audio_bus.update(self.programme_snapshot());self.prepare_sound_analysis(project=self.programme_project())
                message=(plan['summary'] if plan['changed'] else 'No eligible creative change · current/manual/locked work kept')+(' · '+ '; '.join(plan['blocked']) if plan['blocked'] else '')
                if not self.playing:self.viewport.request()
                requested_play=r['play_after'] or getattr(self,'_playable_play_requested',False);self._playable_play_requested=False
                if requested_play and not self.playing:self.toggle_play()
            else:message='No eligible change'
            self.update_status(message)
            if hasattr(self,'performance_status'):self.performance_status.set(message)
            self.refresh_source_choices()
        if self._playable_latest:self._start_playable_request()
    def source_intent(self,project=None):
        intent=load_intent(project if project is not None else self.project)
        for key in ('music','visuals'):
            choice=intent[key];album=choice.get('album_id')
            if album and album!='all':choice['pool_ids']=sorted(self.catalog.member_ids(album))
        return intent
    def use_song(self,asset_id=None):
        aid=asset_id or self.selected_asset_id or next(iter(self.library.selection()),None)
        a=self.project.asset(aid) if aid else None
        if not a or (a.kind!='audio' and not a.metadata.get('has_audio')):return self.update_status('Choose a song in the Library first.')
        def apply():
            now=self.programme_time() if self.playing else 0.
            existing=items(self.project);start=max([now]+[e['start']+e['duration'] for e in existing if e['start']<=now<e['start']+e['duration']]) if self.playing else 0.
            event=add_sound(self.project,aid,start=start)
            if not self.playing and not any(l.clips for l in self.project.layers):self.project.duration=event['duration']
            from sound_routes import update_route
            update_route(self.project,'soundtrack',{'enabled':True},now)
            intent=load_intent(self.project);intent['music']={'mode':'fixed','asset_id':aid,'album_id':None};intent['duration_mode']='song';self.project.extra['playable_intent']=intent
        self.transaction('Use song',apply);self.prepare_sound_analysis();self.refresh_source_choices()
    def use_source_album(self,kind):
        album=self.album.get()
        def apply():
            i=load_intent(self.project);i[kind]={'mode':'auto','album_id':None if album=='all' else album}
            if kind=='music':
                i['duration_mode']='song'
                from sound_routes import update_route
                update_route(self.project,'soundtrack',{'enabled':True},self.programme_time() if self.playing else 0.)
            else:
                if not i['enabled_roles']:i['enabled_roles']=['A']
                for l in self.project.layers:
                    if l.extra.get('voice') in ('A','B','C','D'):l.enabled=l.extra['voice'] in i['enabled_roles']
            self.project.extra['playable_intent']=i
        self.transaction('Use album for '+('Music' if kind=='music' else 'Background'),apply);self.refresh_source_choices()
    def set_source_mode(self,kind,mode):
        def apply():
            i=load_intent(self.project);i[kind]={'mode':mode,'album_id':None}
            if mode=='live':i['duration_mode']='continuous'
            if kind=='music':
                from sound_routes import update_route
                update_route(self.project,'soundtrack',{'enabled':mode not in ('off','live')},self.programme_time() if self.playing else 0)
            else:
                for l in self.project.layers:
                    if l.extra.get('voice') in ('A','B','C','D'):l.enabled=mode not in ('off','live') and l.extra.get('voice') in i['enabled_roles']
            self.project.extra['playable_intent']=i
        self.transaction(kind.title()+' source '+mode,apply);self.refresh_source_choices()
    def set_role_enabled(self,role,enabled):
        def apply():
            l=voice(self.project,role);i=load_intent(self.project);roles=set(i['enabled_roles'])
            if enabled:roles.add(role)
            else:roles.discard(role)
            i['enabled_roles']=[r for r in ('A','B','C','D') if r in roles];l.enabled=bool(enabled);self.project.extra['playable_intent']=i
        self.transaction(('Enable ' if enabled else 'Bypass ')+role,apply)

    def set_sequence_enabled(self,enabled):
        def apply():
            i=load_intent(self.project)
            if not enabled:
                i['sequence_roles']=i.get('enabled_roles',['A']);i['enabled_roles']=[]
            else:i['enabled_roles']=i.get('sequence_roles',['A']);i['visuals']['mode']='auto'
            for l in self.project.layers:
                if l.extra.get('voice') in ('A','B','C','D'):l.enabled=l.extra['voice'] in i['enabled_roles']
            self.project.extra['playable_intent']=i
        self.transaction('Sequence ON' if enabled else 'Sequence bypass · Music continues',apply)
    def reveal_camera(self):
        def apply():
            count=0
            for l in self.project.layers:
                if l.locked or l.extra.get('voice') not in ('A','B','C','D'):continue
                for c in l.clips:
                    if c.manual or c.locked or not c.extra.get('playable_auto') or c.opacity.extra.get('conductor_locked'):continue
                    c.opacity.value=min(c.opacity.value,.65);count+=1
            return count
        count=self.transaction('Reveal Camera through generated clips',apply)
        self.update_status(f'Revealed camera through {count or 0} generated clips. Manual/locked or opaque authored layers need their own opacity control.')
