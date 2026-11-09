"""Queue intent over the existing occurrence model; no duplicate timeline authority.

Source switches are timestamped. Camera holds queue time without deleting events;
returning resumes that clock. Persistent racks remain in session time. Capture can
materialise these mappings into ordinary, independently editable occurrences.
"""
from __future__ import annotations
import copy, math, hashlib
from sequencer_model import Clip, Transition, new_id
from sequence_edit import editable, reconcile_transitions

def ordered(layer):return sorted(layer.clips,key=lambda c:(c.start,c.id))

def mode_at(layer,t):
    return next((s for s in reversed(layer.extra.get('source_switches',[])) if s['start']<=t),{'start':0.,'mode':'queue','position':0.})

def queue_position(layer,t):
    from queue_policies import visual_state_at
    layer=visual_state_at(layer,t)
    s=mode_at(layer,t);pos=float(s.get('position',s['start']))
    if s['mode'] in ('camera','pause'):return pos
    if s['mode']=='hold':
        c=next((c for c in layer.clips if c.id==s.get('clip_id')),None)
        if c:return c.start+(pos-c.start+max(0,t-s['start']))%max(.001,c.duration)
        return pos
    q=max(0.,pos+t-s['start']);policy=layer.extra.get('queue_policy','finish')
    if policy=='repeat' and layer.clips:
        end=max(c.end for c in layer.clips)
        if q>=end and end>0:q=q%end
    elif policy=='hold' and layer.clips:q=min(q,max(c.end for c in layer.clips)-1e-5)
    return q

def current(layer,t):
    from queue_policies import visual_state_at
    layer=visual_state_at(layer,t);q=queue_position(layer,t)
    return max((c for c in layer.clips if c.start<=q<c.end),key=lambda c:c.start,default=None)

def append_switch(layer,t,mode,position,**extra):
    if not math.isfinite(t) or t<0:raise ValueError('Invalid source switch time')
    switches=layer.extra.setdefault('source_switches',[])
    # Editing the past requires a take, not two competing events at the same time.
    switches[:]=[s for s in switches if s['start']<t]
    switches.append({'start':float(t),'mode':mode,'position':float(position),**extra})

def switch_source(layer,mode,t,*,camera_id=''):
    if layer.locked:raise ValueError('Unlock this voice before changing its source')
    if mode not in ('camera','queue'):raise ValueError('Choose Queue or Camera')
    pos=queue_position(layer,t)
    if mode=='camera' and not camera_id:raise ValueError('A ready camera source is required')
    from queue_policies import activate_visual_state,preserve_visual_history
    activate_visual_state(layer,t);preserve_visual_history(layer,t)
    append_switch(layer,t,mode,pos,camera_id=camera_id)

def toggle_pause(layer,t):
    """Freeze/resume this lane's source clock without pausing the programme.

    Preserve the previous queue/hold mode, keep its queue position intact and
    retain performed state so the action is reversible as a single transaction.
    """
    if layer.locked:raise ValueError('Unlock this visual channel first')
    from queue_policies import activate_visual_state,preserve_visual_history
    active=mode_at(layer,t)
    if active['mode']=='camera':raise ValueError('Live capture cannot be paused as a media queue')
    position=queue_position(layer,t)
    activate_visual_state(layer,t);preserve_visual_history(layer,t)
    if active['mode']=='pause':
        previous=active.get('resume_mode','queue')
        append_switch(layer,t,previous,position,**({'clip_id':active['clip_id']} if previous=='hold' and 'clip_id' in active else {}))
    else:
        append_switch(layer,t,'pause',position,resume_mode=active['mode'],**({'clip_id':active['clip_id']} if active['mode']=='hold' and 'clip_id' in active else {}))
    return mode_at(layer,t)['mode']=='pause'

def hold_current(layer,t):
    if layer.locked:raise ValueError('Unlock this voice first')
    from queue_policies import activate_visual_state,preserve_visual_history
    activate_visual_state(layer,t);preserve_visual_history(layer,t)
    s=mode_at(layer,t)
    if s['mode']=='hold':append_switch(layer,t,'queue',queue_position(layer,t));return
    if s['mode']=='camera':return
    c=current(layer,t)
    if c:append_switch(layer,t,'hold',queue_position(layer,t),clip_id=c.id)

def take_next(layer,t,clip_id=None):
    if layer.locked:raise ValueError('Unlock this voice first')
    from queue_policies import activate_visual_state,preserve_visual_history,visual_state_at
    active=visual_state_at(layer,t)
    use_prepared=clip_id is not None and not any(c.id==clip_id for c in active.clips)
    items=ordered(layer if use_prepared else active);q=queue_position(layer,t)
    c=next((c for c in items if c.id==clip_id),None) if clip_id else next((c for c in items if c.start>q+1e-6),items[0] if items and layer.extra.get('queue_policy')=='repeat' else None)
    if c is None:raise ValueError('There is no next queue item')
    activate_visual_state(layer,t,prepared=use_prepared);preserve_visual_history(layer,t)
    append_switch(layer,t,'queue',c.start)

def _reflow(project,layer,items,*,fixed_prefix=0):
    transitions={(tr.from_clip,tr.to_clip):tr for tr in layer.transitions};positions=[];cursor=min((c.start for c in layer.clips),default=0.)
    for i,c in enumerate(items):
        tr=transitions.get((items[i-1].id,c.id)) if i else None
        overlap=min(tr.duration,items[i-1].duration*.49,c.duration*.49) if tr else 0.
        start=c.start if i<fixed_prefix else cursor-overlap
        if (layer.locked or c.locked or c.timing_locked) and abs(start-c.start)>1e-6:raise ValueError('This queue edit would move locked material')
        positions.append(start);cursor=start+c.duration
    kept=[]
    pairs={(items[i-1].id,c.id) for i,c in enumerate(items) if i}
    if any(tr.locked and (tr.from_clip,tr.to_clip) not in pairs for tr in layer.transitions):raise ValueError('This edit would remove a locked transition')
    for i,c in enumerate(items):
        tr=transitions.get((items[i-1].id,c.id)) if i else None
        if tr and tr.locked and (abs(tr.start-positions[i])>1e-6 or abs(tr.duration-(positions[i-1]+items[i-1].duration-positions[i]))>1e-6):raise ValueError('This edit would alter a locked transition')
    for i,(c,start) in enumerate(zip(items,positions)):
        c.start=start
        if i>=fixed_prefix:c.manual=True
    for i,c in enumerate(items):
        tr=transitions.get((items[i-1].id,c.id)) if i else None
        if tr:tr.start=c.start;tr.duration=items[i-1].end-c.start;kept.append(tr)
    layer.clips=items;layer.transitions=kept;project.duration=max(project.duration,cursor);project.touch()

def reorder(project,layer_id,clip_id,index):
    layer=next(l for l in project.layers if l.id==layer_id);items=ordered(layer);c=next(c for c in items if c.id==clip_id);editable(project,clip_id,timing=True)
    items.remove(c);items.insert(max(0,min(len(items),int(index))),c);_reflow(project,layer,items)

def set_duration(project,clip_id,duration):
    layer,c=editable(project,clip_id,timing=True);duration=float(duration)
    if not math.isfinite(duration) or duration<1/project.fps:raise ValueError('Duration must be at least one frame')
    old=c.duration;c.duration=duration
    try:_reflow(project,layer,ordered(layer))
    except Exception:c.duration=old;raise

def append_assets(project,layer_id,asset_ids,*,before=None,after=None):
    layer=next(l for l in project.layers if l.id==layer_id)
    if layer.locked:raise ValueError('Unlock the voice first')
    items=ordered(layer);idx=len(items)
    if before:idx=next(i for i,c in enumerate(items) if c.id==before)
    if after:idx=next(i for i,c in enumerate(items) if c.id==after)+1
    fixed_prefix=idx;created=[]
    for aid in asset_ids:
        a=project.asset(aid)
        if not a or a.kind=='audio':continue
        pref=a.metadata.get('sequence_preferences',{});dur=float(pref.get('clip_min',min(a.duration or 5.,5.)))
        c=Clip(new_id('clp'),aid,start=max((x.end for x in items),default=0.),duration=max(1/project.fps,dur),in_point=float(pref.get('source_in',0)),source_policy=pref.get('source_policy','loop'),fit=pref.get('fit','cover'),playback_rate=float(pref.get('playback_rate',1)),manual=True)
        if 'default_rack' in pref:
            from media_settings_model import default_rack
            c.rack=default_rack(a)
        if 'source_out' in pref:c.extra['source_window']=[c.in_point,float(pref['source_out'])]
        items.insert(idx,c);created.append(c);idx+=1
    if not created:raise ValueError('Select visual media for this queue')
    _reflow(project,layer,items,fixed_prefix=fixed_prefix);return created

def remove(project,clip_id,*,now=None):
    layer,c=editable(project,clip_id,timing=True)
    held=now is not None and mode_at(layer,now).get('mode')=='hold' and mode_at(layer,now).get('clip_id')==clip_id
    next_id=None
    if held:
        items=ordered(layer);index=next(i for i,item in enumerate(items) if item.id==clip_id)
        survivors=[item for item in items if item.id!=clip_id]
        if survivors:next_id=survivors[index%len(survivors)].id
    if now is not None:
        from queue_policies import activate_visual_state,preserve_visual_history
        # Keep the performed interval, then let the authored future own all later
        # cycles. A pending historical version must not restore this occurrence.
        activate_visual_state(layer,now,prepared=True)
        preserve_visual_history(layer,now)
    _reflow(project,layer,[x for x in ordered(layer) if x.id!=c.id])
    if held:
        successor=next((item for item in layer.clips if item.id==next_id),None)
        append_switch(layer,now,'queue',successor.start if successor else 0.)

def set_boundary(project,layer_id,from_id,to_id,kind,seconds,*,now=None,curve=None):
    """Change one boundary atomically, retaining the prefix and clip durations.

    The following suffix moves as a unit, so its authored gaps/overlaps survive.
    A performed source-clock interval can never be changed during playback.
    """
    from queue_transitions import VISUAL_KINDS
    seconds=float(seconds)
    if curve is not None and curve not in ('linear','smooth','ease_in','ease_out'):raise ValueError('Choose a supported curve.')
    if not math.isfinite(seconds) or seconds<0:raise ValueError('Use finite, nonnegative seconds.')
    if kind not in VISUAL_KINDS:raise ValueError('Choose a supported visual transition.')
    if kind=='cut':seconds=0.
    layer=next((l for l in project.layers if l.id==layer_id),None)
    if layer is None:raise ValueError('This queue is no longer available.')
    entries=ordered(layer);i=next((i for i,c in enumerate(entries) if c.id==from_id),-1)
    if i<0 or i+1>=len(entries) or entries[i+1].id!=to_id:raise ValueError('These items are no longer neighbours. Reopen the boundary.')
    a,b=entries[i:i+2];tr=next((t for t in layer.transitions if (t.from_clip,t.to_clip)==(from_id,to_id)),None)
    if layer.locked or any(c.locked or c.timing_locked or c.extra.get('playable_pin') for c in (a,b)) or (tr and tr.locked):raise ValueError('Unlock or unpin both items and their transition first.')
    if seconds and (seconds<1/project.fps or seconds>min(a.duration,b.duration)*.49):raise ValueError('Use at least one frame, up to 49% of the shorter item.')
    delta=a.end-seconds-b.start
    if abs(delta)<1e-8 and ((not seconds and tr is None and not a.fade_out and not b.fade_in) or (tr and tr.kind==kind and abs(tr.duration-seconds)<1e-8 and (curve is None or tr.easing==curve))):return tr or True
    shifted=entries[i+1:] if abs(delta)>1e-8 else []
    if any(c.locked or c.timing_locked or c.extra.get('playable_pin') for c in shifted):raise ValueError('This duration would move a locked or pinned upcoming item.')
    if now is not None:
        now=float(now)
        if not math.isfinite(now) or now<0:raise ValueError('Invalid Programme time.')
        from queue_policies import next_visual_cycle
        cutoff=queue_position(layer,now)
        old_edge=min(b.start,a.end-float(a.fade_out or 0))
        new_edge=a.end-seconds
        effective=max(now,max((r['end'] for r in layer.extra.get('queue_history',[]) if r['start']<=now<r['end']),default=now))
        if min(old_edge,new_edge)<=cutoff+1e-7:
            if layer.extra.get('queue_policy')!='repeat':
                raise ValueError('This overlap has started. Edit a Draft or enable Loop to change the next repeat.')
            effective=max(effective,next_visual_cycle(layer,now))
    else:effective=None
    if any(c.end>b.start+delta+1e-7 for c in entries[:i]):raise ValueError('This overlap would intersect an earlier visual item. Use Timing controls for this composition.')
    suffix={c.id for c in shifted};moved_transitions=[]
    for other in layer.transitions:
        if other is tr:continue
        endpoints={other.from_clip,other.to_clip}
        if endpoints & suffix:
            if not endpoints<=suffix:raise ValueError('An overlapping transition crosses this boundary. Use Timing controls.')
            if other.locked:raise ValueError('This duration would move a locked upcoming transition.')
            moved_transitions.append(other)
    if effective is not None:
        from queue_policies import preserve_visual_history
        preserve_visual_history(layer,effective)
        append_switch(layer,effective,'queue',0. if effective>now+1e-7 else cutoff)
    for c in shifted:c.start+=delta;c.manual=True
    for other in moved_transitions:other.start+=delta
    a.manual=b.manual=True
    if seconds:
        if tr is None:tr=Transition(new_id('tr'),from_id,to_id);layer.transitions.append(tr)
        tr.kind=kind;tr.start=b.start;tr.duration=seconds;tr.manual=True;tr.extra['queue_authored']=True
        if curve is not None:tr.easing=curve
    else:
        if tr:layer.transitions.remove(tr)
        a.fade_out=b.fade_in=0.
    project.duration=max(project.duration,max(c.end for c in entries));project.touch()
    return tr if seconds else True

def _shift_parameters(raw,delta):
    """Rebase clip-local authored automation when a queue becomes session events."""
    if isinstance(raw,dict):
        if 'keyframes' in raw and 'mode' in raw:
            for key in raw.get('keyframes',[]):key['time']=max(0,key['time']+delta)
        for value in raw.values():_shift_parameters(value,delta)
    elif isinstance(raw,list):
        for value in raw:_shift_parameters(value,delta)

def materialize(project,start,end):
    """Freeze source clocks without opening devices. Existing renderer/export reads it.

Camera intervals become ordinary camera occurrences for the existing retention
mapper. Queue time metadata is kept on each cloned occurrence so trims and reaction
use the correct original time; session-wide racks are never shifted.
"""
    def stable_id(prefix,*parts):return prefix+'_'+hashlib.sha256(repr(parts).encode()).hexdigest()[:20]
    p=copy.deepcopy(project)
    for layer in p.layers:
        switches=layer.extra.get('source_switches',[])
        if not switches and layer.extra.get('queue_policy') not in ('repeat','hold') and not layer.extra.get('queue_history'):continue
        original=copy.deepcopy(layer);boundaries={float(start),float(end),*(s['start'] for s in switches if start<s['start']<end)}
        if original.extra.get('camera_layer'):
            for event in original.extra.get('treatment_history',[]):
                boundaries.update(v for v in (event['start'],event['end']) if start<v<end)
        for record in original.extra.get('queue_history',[]):boundaries.update(v for v in (record['start'],record['end']) if start<v<end)
        cuts=sorted(boundaries)
        clones=[];transitions=[]
        live_original=original
        for lo,hi in zip(cuts,cuts[1:]):
            from queue_policies import visual_state_at
            original=visual_state_at(live_original,lo)
            if original.extra.get('camera_layer'):
                from instrument_model import style_at
                if not style_at(original,lo).enabled:continue
            s=mode_at(original,lo)
            if s['mode']=='camera':
                clones.append(Clip(stable_id('clp',layer.id,'camera',lo,hi),s['camera_id'],start=lo,duration=hi-lo,fit='cover',manual=True));continue
            if s['mode']=='pause':
                qtime=queue_position(original,lo)
                frozen=current(original,lo)
                if frozen is not None:
                    clone=copy.deepcopy(frozen)
                    clone.id=stable_id('clp',frozen.id,'pause',lo,hi)
                    clone.in_point=max(0.,frozen.in_point+(qtime-frozen.start)*frozen.playback_rate)
                    clone.start=lo;clone.duration=hi-lo;clone.playback_rate=0.
                    clone.extra.update(captured_pause=True,original_queue_id=frozen.id)
                    clones.append(clone)
                position=hi
                continue
            position=lo
            while position<hi-1e-7:
                qtime=queue_position(original,position+1e-8);delta=position-qtime
                if original.extra.get('queue_policy')=='hold' and original.clips and qtime>=max(c.end for c in original.clips)-2e-5:
                    from sequencer_model import _encode
                    last=max(original.clips,key=lambda c:c.end)
                    clone=Clip(stable_id('gap',last.id,position,hi),'',start=position,duration=hi-position,manual=True,extra={'queue_gap':{'mode':'hold'},'held_gap_clip':_encode(last),'original_queue_id':last.id})
                    clones.append(clone);position=hi;continue
                # Repeat/hold split at wrap boundaries, not at every frame.
                if s['mode']=='hold':
                    c=next((c for c in original.clips if c.id==s.get('clip_id')),None);finish=min(hi,position+c.end-qtime) if c else hi;pool=[c] if c else []
                else:
                    finish=min(hi,position+max(c.end for c in original.clips)-qtime) if original.extra.get('queue_policy') in ('repeat','hold') and original.clips else hi;pool=original.clips
                if finish<=position+1e-7:break
                ids={}
                for c in pool:
                    a=max(position,c.start+delta);b=min(finish,c.end+delta)
                    if b<=a:continue
                    clone=copy.deepcopy(c);clone.id=stable_id('clp',c.id,round(a,8),round(b,8),round(delta,8));ids[c.id]=clone.id;clone.start=a;clone.duration=b-a;clone.in_point=max(0.,c.in_point+(a-delta-c.start)*c.playback_rate)
                    from queue_seams import active_seam
                    seam=active_seam(ordered(original),original.extra.get('queue_seam'))
                    if seam:clone.extra['captured_queue_seam']={'seam':copy.deepcopy(seam),'length':max(x.end for x in original.clips),'origin':delta}
                    clone.extra.update(captured_queue_offset=delta,fade_start=c.start+delta,fade_end=c.end+delta,original_queue_id=c.id)
                    if c.extra.get('queue_gap',{}).get('mode')=='hold':
                        from sequencer_model import _encode
                        previous=max((x for x in pool if x.end<=c.start+1e-7 and not x.extra.get('queue_gap')),key=lambda x:x.end,default=None)
                        if previous:clone.extra['held_gap_clip']=_encode(previous)
                    # Keep authored time coordinates intact; the renderer applies
                    # this offset separately from source time and signal time.
                    clones.append(clone)
                for tr in original.transitions:
                    if tr.from_clip in ids and tr.to_clip in ids:
                        copytr=copy.deepcopy(tr);copytr.id=stable_id('tr',tr.id,round(delta,8));copytr.from_clip=ids[tr.from_clip];copytr.to_clip=ids[tr.to_clip];copytr.start+=delta
                        if copytr.end>position and copytr.start<finish:transitions.append(copytr)
                position=finish
        layer.clips=clones;layer.transitions=transitions;layer.extra.pop('source_switches',None);layer.extra['queue_policy']='finish';layer.extra.pop('queue_history',None);layer.extra.pop('queue_seam',None)
    return p
