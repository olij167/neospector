"""First-class timed queue gaps; no synthetic Library assets."""
import math
from sequencer_model import Clip,new_id

def gap_name(item):
    gap=item.get('queue_gap') if isinstance(item,dict) else item.extra.get('queue_gap')
    return {'transparent':'Gap · transparent','silence':'Gap · silence','hold':'Gap · hold frame','colour':'Gap · colour'}.get((gap or {}).get('mode'),'')

def _duration(project,seconds):
    n=float(seconds)
    if not math.isfinite(n) or n<1/project.fps:raise ValueError('A gap must last at least one frame.')
    return n

def add_visual_gap(project,layer_id,seconds=1.,*,index=None,mode='transparent',colour='#000000',now=None):
    from queue_model import ordered
    from queue_policies import preserve_visual_history,next_visual_cycle
    from queue_model import append_switch,queue_position
    layer=next(l for l in project.layers if l.id==layer_id);entries=ordered(layer);n=_duration(project,seconds)
    if mode not in ('transparent','hold','colour'):raise ValueError('Choose Transparent, Hold frame or Colour.')
    from PIL import ImageColor
    ImageColor.getrgb(colour)
    i=len(entries) if index is None else max(0,min(len(entries),int(index)))
    suffix=entries[i:];start=entries[i-1].end if i else 0.
    before=entries[i-1] if i else None;after=entries[i] if i<len(entries) else None
    removed=[tr for tr in layer.transitions if before and after and tr.from_clip==before.id and tr.to_clip==after.id]
    delta=start+n-(after.start if after else start)
    if layer.locked or any(c.locked or c.timing_locked or c.extra.get('playable_pin') for c in suffix) or any(t.locked for t in removed):raise ValueError('This gap would move locked or pinned material.')
    moved=[tr for tr in layer.transitions if tr not in removed and tr.from_clip in {c.id for c in suffix}]
    if any(tr.locked for tr in moved):raise ValueError('This gap would move a locked transition.')
    if now is not None:
        q=queue_position(layer,now);at=max(now,max((r['end'] for r in layer.extra.get('queue_history',[]) if r['start']<=now<r['end']),default=now))
        if start<=q:
            if layer.extra.get('queue_policy')!='repeat':raise ValueError('Insert after the current item, or edit a Draft.')
            at=max(at,next_visual_cycle(layer,now))
        preserve_visual_history(layer,at);append_switch(layer,at,'queue',0. if at>now else q)
    for c in suffix:c.start+=delta
    for tr in moved:tr.start+=delta
    for tr in removed:layer.transitions.remove(tr)
    if before:before.fade_out=0.
    if after:after.fade_in=0.
    gap=Clip(new_id('gap'),'',start=start,duration=n,manual=True,extra={'queue_gap':{'mode':mode,'colour':colour}})
    entries.insert(i,gap);layer.clips=entries;project.duration=max(project.duration,max(c.end for c in entries));project.touch();return gap

def add_music_gap(project,seconds=1.,*,index=None,now=None):
    from music_queue import items,store,layout
    from queue_policies import music_position,preserve_music_history,next_music_cycle,set_music_origin
    events=items(project);i=len(events) if index is None else max(0,min(len(events),int(index)));n=_duration(project,seconds)
    start=events[i-1]['start']+events[i-1]['duration'] if i else 0.
    if any(e.get('locked') or e.get('timing_locked') or e.get('pinned') for e in events[i:]):raise ValueError('This gap would move locked or pinned tracks.')
    if now is not None:
        q=music_position(project,now);at=max(now,max((r['end'] for r in project.extra.get('music_queue_history',[]) if r['start']<=now<r['end']),default=now))
        if start<=q:
            if project.extra.get('music_queue_policy')!='repeat':raise ValueError('Insert after the current track, or edit a Draft.')
            at=max(at,next_music_cycle(project,now))
        preserve_music_history(project,at);set_music_origin(project,at,0. if at>now else q)
    if i<len(events):events[i]['fade_in']=0.;events[i].pop('boundary_from',None);events[i].pop('boundary_id',None)
    gap={'id':new_id('gap'),'asset_id':'','start':start,'duration':n,'in_point':0.,'gain':0.,'fade_in':0.,'fade_out':0.,'enabled':True,'route_id':'soundtrack','manual':True,'playable_auto':False,'queue_gap':{'mode':'silence'}}
    events.insert(i,gap);store(project,layout(events));project.touch();return gap

def edit_queue(project,role,operation,*args,now=None):
    """Validate a local queue edit before publishing; live reflows use next Loop.

    Candidate copies contain only occurrences, never the full project/assets.
    Existing paused APIs remain compatible; this wraps native card operations.
    """
    import copy
    from instrument_model import voice
    from queue_policies import (preserve_visual_history,next_visual_cycle,
        preserve_music_history,next_music_cycle,set_music_origin,music_position)
    from queue_model import append_switch,queue_position
    candidate=copy.copy(project)
    if role=='Music':
        candidate.extra=dict(project.extra);candidate.extra['sound_events']=copy.deepcopy(project.extra.get('sound_events',[]))
        old=project.extra.get('sound_events',[])
        result=operation(candidate,*args);new=candidate.extra.get('sound_events',[])
        for event in old:
            changed=next((e for e in new if e['id']==event['id']),None)!=event
            if changed and any(event.get(k) for k in ('locked','timing_locked','pinned')):raise ValueError('Unlock or unpin this track first.')
            if changed and now is not None and project.extra.get('music_queue_policy')!='repeat' and event['start']<=music_position(project,now):raise ValueError('Played tracks are protected. Use Loop or edit a Draft.')
        if now is not None:
            at=next_music_cycle(project,now) if project.extra.get('music_queue_policy')=='repeat' else now
            preserve_music_history(project,at);set_music_origin(project,at,0. if at>now else music_position(project,now))
        project.extra['sound_events']=new;project.audio_asset_id=candidate.audio_asset_id
    else:
        layer=voice(project,role);cloned=copy.copy(layer);cloned.clips=copy.deepcopy(layer.clips);cloned.transitions=copy.deepcopy(layer.transitions);cloned.extra=dict(layer.extra)
        candidate.layers=[cloned if l is layer else l for l in project.layers]
        result=operation(candidate,*args)
        for clip in layer.clips:
            after=next((c for c in cloned.clips if c.id==clip.id),None)
            changed=after!=clip
            if changed and (clip.locked or clip.timing_locked or clip.extra.get('playable_pin')):raise ValueError('Unlock or unpin this occurrence first.')
            if changed and now is not None and layer.extra.get('queue_policy')!='repeat' and clip.start<=queue_position(layer,now):raise ValueError('Played occurrences are protected. Use Loop or edit a Draft.')
        from queue_model import remove as remove_occurrence
        if operation is remove_occurrence and now is not None:
            # A deletion is the performer's authored future decision, including
            # the next repeat. Do not schedule a historical snapshot as its owner.
            return remove_occurrence(project,*args,now=now)
        if now is not None:
            at=next_visual_cycle(layer,now) if layer.extra.get('queue_policy')=='repeat' else now
            preserve_visual_history(layer,at);append_switch(layer,at,'queue',0. if at>now else queue_position(layer,now))
        layer.clips=cloned.clips;layer.transitions=cloned.transitions
    project.duration=candidate.duration;project.touch();return result if result is not None else True
