"""Guarded direct-edit commands. The UI records one history snapshot per gesture."""
from __future__ import annotations
import copy
from sequencer_model import Clip, Layer, Project, Transition, clamp, new_id


def editable(project:Project,clip_id:str,*,timing:bool=False):
    found=project.clip(clip_id)
    if not found:raise ValueError('Clip no longer exists')
    l,c=found
    if l.locked or c.locked or (timing and c.timing_locked):raise ValueError('Unlock the target before editing it')
    return l,c


def reconcile_transitions(layer:Layer):
    clips={c.id:c for c in layer.clips};kept=[]
    for tr in layer.transitions:
        a=clips.get(tr.from_clip);b=clips.get(tr.to_clip)
        if not a or not b:continue
        s=max(a.start,b.start);e=min(a.end,b.end)
        if e>s+1e-6:tr.start=s;tr.duration=e-s;kept.append(tr)
    layer.transitions=kept


def split_clip(project:Project,clip_id:str,t:float) -> Clip:
    l,c=editable(project,clip_id,timing=True);frame=1/project.fps
    if t<c.start+frame-1e-6 or t>c.end-frame+1e-6:raise ValueError('Split inside the clip, at least one frame from either edge')
    if any(tr.locked and clip_id in (tr.from_clip,tr.to_clip) and tr.start<t<tr.end for tr in l.transitions):raise ValueError('The split intersects a locked transition')
    right=copy.deepcopy(c);right.id=new_id('clp');right.start=t;right.duration=c.end-t;right.in_point=c.in_point+(t-c.start)*c.playback_rate
    c.duration=t-c.start;c.fade_out=0;right.fade_in=0;c.manual=right.manual=True
    for tr in l.transitions:
        if tr.from_clip==c.id and tr.start>=t:tr.from_clip=right.id
        if tr.to_clip==c.id and tr.start>=t:tr.to_clip=right.id
    l.clips.append(right);l.clips.sort(key=lambda x:(x.start,x.channel));reconcile_transitions(l);project.touch();return right


def trim_clip(project:Project,clip_id:str,start:float,end:float,*,ripple:bool=False):
    l,c=editable(project,clip_id,timing=True);start=max(0.,float(start));end=float(end)
    if end-start<1/project.fps-1e-6:raise ValueError('A clip must contain at least one frame')
    old_start,old_end=c.start,c.end;delta=end-old_end
    followers=[other for other in l.clips if other.id!=c.id and other.start>=old_end-1e-5 and other.channel==c.channel] if ripple else []
    if any(other.locked or other.timing_locked for other in followers):raise ValueError('Ripple would move a locked clip')
    if any(tr.locked and c.id in (tr.from_clip,tr.to_clip) for tr in l.transitions):raise ValueError('Unlock the attached transition before trimming')
    new_in=max(0.,c.in_point+(start-old_start)*c.playback_rate)
    c.start=start;c.duration=end-start;c.in_point=new_in;c.manual=True
    for other in followers:other.start=max(0.,other.start+delta);other.manual=True
    reconcile_transitions(l);project.duration=max(project.duration,c.end);project.touch()


def slip_clip(project:Project,clip_id:str,delta:float):
    l,c=editable(project,clip_id)
    c.in_point=max(0.,c.in_point+delta);c.manual=True;project.touch()


def replace_clip_media(project:Project,clip_id:str,asset_id:str):
    l,c=editable(project,clip_id)
    a=project.asset(asset_id)
    if not a or a.kind=='audio':raise ValueError('Choose a visual source')
    c.asset_id=asset_id;c.in_point=min(c.in_point,max(0.,a.duration-1/project.fps)) if a.kind=='video' else 0.
    c.manual=True;project.touch()


def duplicate_clip(project:Project,clip_id:str) -> Clip:
    l,c=editable(project,clip_id);new=copy.deepcopy(c);new.id=new_id('clp');new.start=c.end;new.manual=True;new.locked=False;new.timing_locked=False
    l.clips.append(new);project.duration=max(project.duration,new.end);project.touch();return new


def move_clip(project:Project,clip_id:str,start:float,layer_id:str|None=None,channel:str|None=None):
    old,c=editable(project,clip_id,timing=True)
    dest=next((l for l in project.layers if l.id==layer_id),old) if layer_id else old
    if dest.locked:raise ValueError('Destination layer is locked')
    if any(tr.locked and c.id in (tr.from_clip,tr.to_clip) for tr in old.transitions):raise ValueError('Unlock the attached transition before moving')
    c.start=max(0.,start);c.channel=channel if channel in {'A','B'} else c.channel;c.manual=True
    if dest is not old:old.clips.remove(c);dest.clips.append(c)
    reconcile_transitions(old)
    if dest is not old:reconcile_transitions(dest)
    project.duration=max(project.duration,c.end);project.touch()


def remove_clip(project:Project,clip_id:str,*,ripple:bool=False):
    l,c=editable(project,clip_id,timing=True)
    following=[other for other in l.clips if other is not c and other.channel==c.channel and other.start>=c.end-1e-5] if ripple else []
    if any(other.locked or other.timing_locked for other in following):raise ValueError('Ripple would move a locked clip')
    if any(tr.locked and c.id in (tr.from_clip,tr.to_clip) for tr in l.transitions):raise ValueError('Unlock attached transition before deleting')
    for other in following:other.start=max(0.,other.start-c.duration);other.manual=True
    l.clips.remove(c);reconcile_transitions(l);project.touch()


def insert_clip(project:Project,layer:Layer,clip:Clip,mode='place'):
    if layer.locked:raise ValueError('Destination layer is locked')
    affected=[c for c in layer.clips if c.channel==clip.channel and (c.end>clip.start if mode=='insert' else c.end>clip.start and c.start<clip.end)]
    if mode in {'insert','overwrite'} and any(c.locked or c.timing_locked for c in affected):raise ValueError('This edit overlaps locked material')
    if mode=='insert':
        for c in list(affected):
            if c.start<clip.start<c.end:
                right=split_clip(project,c.id,clip.start);right.start+=clip.duration
            else:c.start+=clip.duration;c.manual=True
    elif mode=='overwrite':
        for c in list(affected):
            if c.start<clip.start and c.end>clip.end:
                right=split_clip(project,c.id,clip.end);trim_clip(project,c.id,c.start,clip.start)
            elif c.start<clip.start:trim_clip(project,c.id,c.start,clip.start)
            elif c.end>clip.end:trim_clip(project,c.id,clip.end,c.end)
            else:layer.clips.remove(c)
    clip.manual=True;layer.clips.append(clip);reconcile_transitions(layer);project.duration=max(project.duration,clip.end);project.touch()


def set_transition_duration(project:Project,tid:str,duration:float):
    found=project.transition(tid)
    if not found:raise ValueError('Transition no longer exists')
    l,tr=found
    if l.locked or tr.locked:raise ValueError('Transition is locked')
    a=next((c for c in l.clips if c.id==tr.from_clip),None);b=next((c for c in l.clips if c.id==tr.to_clip),None)
    if not a or not b:raise ValueError('Transition endpoint is missing')
    editable(project,a.id,timing=True);editable(project,b.id,timing=True)
    duration=clamp(duration,1/project.fps,min(12,b.duration))
    a.duration=b.start+duration-a.start;a.manual=b.manual=True;tr.start=b.start;tr.duration=duration;tr.manual=True;project.touch()


def add_transition(project:Project,layer_id:str,to_clip_id:str,kind='dissolve',duration=.5) -> Transition:
    l,b=editable(project,to_clip_id,timing=True)
    if l.id!=layer_id:raise ValueError('Select a clip in this layer')
    a=max((c for c in l.clips if c.start<b.start and c.id!=b.id),key=lambda c:c.start,default=None)
    if not a:raise ValueError('A transition needs a preceding clip')
    editable(project,a.id,timing=True)
    duration=clamp(duration,1/project.fps,min(12,b.duration))
    tr=Transition(new_id('tr'),a.id,b.id,kind,b.start,duration,manual=True)
    if any(x.locked and x.to_clip==b.id for x in l.transitions):raise ValueError('The existing transition is locked')
    a.duration=b.start+duration-a.start;a.manual=b.manual=True
    l.transitions=[x for x in l.transitions if x.to_clip!=b.id]+[tr];project.touch();return tr


def snap_time(project:Project,t:float,mode:str,*,pixel_tolerance:float=0.12,exclude_id:str|None=None) -> float:
    if mode=='off':return max(0.,t)
    if mode=='frames':return max(0.,round(t*project.fps)/project.fps)
    if mode=='beats':
        c=project.conductor;step=60/c.bpm;return max(0.,round((t-c.beat_offset)/step)*step+c.beat_offset)
    points=[0.,project.duration]+[float(m.get('time',0)) for m in project.markers]
    if mode=='edges':points += [x for l in project.layers for c in l.clips if c.id!=exclude_id for x in (c.start,c.end)]
    nearest=min(points,key=lambda x:abs(x-t))
    return max(0.,nearest if abs(nearest-t)<=pixel_tolerance else t)
