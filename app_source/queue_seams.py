"""Explicit last-to-first fades, split across edges without changing the period."""
import math
import numpy as np
from sequencer_model import new_id


def active_seam(entries,seam):
    if not entries or not seam:return None
    ident=lambda e:e['id'] if isinstance(e,dict) else e.id
    return seam if (seam.get('from_id'),seam.get('to_id'))==(ident(entries[-1]),ident(entries[0])) else None


def seam_gain(position,length,seam):
    q=np.asarray(position,dtype=np.float64)
    if not seam or seam.get('kind')!='seam_fade' or not seam.get('duration'):return np.ones_like(q)
    half=float(seam['duration'])/2
    gain=np.clip(np.minimum(q/half,(float(length)-q)/half),0.,1.)
    curve=seam.get('curve','smooth')
    if curve=='smooth':gain=gain*gain*(3-2*gain)
    elif curve=='ease_in':gain=gain*gain
    elif curve=='ease_out':gain=1-(1-gain)*(1-gain)
    elif curve=='equal_power':gain=np.sin(gain*np.pi/2)
    return gain


def seam_info(project,role,entries,*,layer=None):
    from queue_gaps import gap_name
    music=role=='Music';ident=lambda e:e['id'] if music else e.id
    aid=lambda e:e['asset_id'] if music else e.asset_id
    duration=lambda e:e['duration'] if music else e.duration
    store=project.extra if music else layer.extra;key='music_queue_seam' if music else 'queue_seam'
    seam=active_seam(entries,store.get(key)) or {}
    ends=(entries[-1],entries[0]);names=[gap_name(e) or (project.asset(aid(e)).name if project.asset(aid(e)) else 'Missing source') for e in ends]
    return dict(from_id=ident(ends[0]),to_id=ident(ends[1]),kind=seam.get('kind','cut'),seconds=seam.get('duration',0.),maximum=min(map(duration,ends))*.98,names=names,durations=list(map(duration,ends)),curve=seam.get('curve','equal_power' if music else 'smooth'),compatibility=False,seam=True)


def set_seam(project,role,info,kind,seconds,*,now=None,curve=None):
    from instrument_model import voice
    from queue_model import ordered,append_switch,queue_position
    from music_queue import items
    from queue_policies import (music_position,preserve_music_history,next_music_cycle,set_music_origin,
        preserve_visual_history,next_visual_cycle)
    music=role=='Music';layer=None if music else voice(project,role);entries=items(project) if music else ordered(layer)
    store=project.extra if music else layer.extra;key='music_queue_seam' if music else 'queue_seam';old=active_seam(entries,store.get(key)) or {}
    seconds=float(seconds);curve=curve or old.get('curve','equal_power' if music else 'smooth')
    if kind not in ('cut','seam_fade'):raise ValueError('Choose Cut or Fade through the loop boundary.')
    if curve not in (('linear','equal_power') if music else ('linear','smooth','ease_in','ease_out')):raise ValueError('Choose a supported curve.')
    if not math.isfinite(seconds) or seconds<0:raise ValueError('Use finite nonnegative seam seconds.')
    seconds=0. if kind=='cut' else seconds
    if seconds and not 1/project.fps<=seconds<=info['maximum']:raise ValueError('Use at least one frame, up to 98% of the shorter edge item.')
    ends=(entries[-1],entries[0])
    if music:locked=any(e.get('locked') or e.get('timing_locked') or e.get('pinned') for e in ends)
    else:locked=layer.locked or any(e.locked or e.timing_locked or e.extra.get('playable_pin') for e in ends)
    if locked or old.get('locked'):raise ValueError('Unlock or unpin both loop edge items first.')
    if old.get('kind','cut')==kind and old.get('duration',0)==seconds and old.get('curve',curve)==curve:return True
    if now is not None:
        now=float(now)
        if not math.isfinite(now) or now<0:raise ValueError('Invalid Programme time.')
        q=music_position(project,now) if music else queue_position(layer,now)
        length=max(e['start']+e['duration'] for e in entries) if music else max(e.end for e in entries)
        history=store.get('music_queue_history' if music else 'queue_history',[])
        at=max(now,max((r['end'] for r in history if r['start']<=now<r['end']),default=now))
        half=max(seconds,float(old.get('duration',0)))/2
        if q>=length-half or (0<q<half):
            policy=store.get('music_queue_policy' if music else 'queue_policy','finish')
            if policy!='repeat':raise ValueError('This loop edge has started. Enable Loop or edit a Draft.')
            at=max(at,next_music_cycle(project,now) if music else next_visual_cycle(layer,now))
        if music:preserve_music_history(project,at);set_music_origin(project,at,0. if at>now else q)
        else:preserve_visual_history(layer,at);append_switch(layer,at,'queue',0. if at>now else q)
    seam=dict(id=old.get('id') or new_id('seam'),from_id=info['from_id'],to_id=info['to_id'],kind=kind,duration=seconds,curve=curve)
    store[key]=seam;project.touch();return seam
