"""Future-only operations. Never run the whole Music queue through zero reflow."""
import copy,random
from collections import defaultdict
from music_queue import items,store
from instrument_model import voice
from queue_model import queue_position

def performed_visual_ids(layer,now):
    """Occurrences touched by any performed source-clock interval, not wall time."""
    if now<=0:return set()
    if layer.extra.get('queue_policy')=='repeat':
        q=queue_position(layer,now)
        return {c.id for c in layer.clips if c.start<=q}
    switches=[{'start':0.,'mode':'queue','position':0.}]+layer.extra.get('source_switches',[])
    result=set()
    for index,s in enumerate(switches):
        lo=s['start'];hi=min(now,switches[index+1]['start'] if index+1<len(switches) else now)
        if hi<=lo or s['mode']=='camera':continue
        if s['mode']=='hold':
            result.add(s.get('clip_id'));continue
        a=float(s.get('position',lo));b=a+hi-lo
        result.update(c.id for c in layer.clips if c.start<=b and c.end>a)
    return result

def pin_occurrence(project,role,occurrence_id,pinned):
    if role=='Music':
        events=items(project)
        for e in events:
            if e['id']==occurrence_id:e['pinned']=bool(pinned)
        store(project,events)
    else:
        for c in voice(project,role).clips:
            if c.id==occurrence_id:c.extra['playable_pin']=bool(pinned)

def shuffle_future(project,role,*,now,seed):
    """Permute compatible future timing slots, preserving every current/locked edge.

    Durations, fades and transition geometry belong to their slots. Only slots
    with matching geometry exchange occurrences; unequal slots remain untouched.
    This deliberately avoids retiming an authored neighbour during performance.
    """
    rng=random.Random(seed);groups=defaultdict(list);changed=0
    if role=='Music':
        events=items(project)
        repeating=project.extra.get('music_queue_policy')=='repeat' and now>0
        cutoff=-1. if repeating else now
        protected=[e for e in events if e['start']<=cutoff or e.get('queue_gap') or not e.get('playable_auto') or e.get('pinned') or e.get('locked')]
        for e in events:
            if e in protected:continue
            if any(e['start']<q['start']+q['duration'] and e['start']+e['duration']>q['start'] for q in protected):continue
            groups[(round(e['duration'],6),e.get('fade_in',0),e.get('fade_out',0))].append(e)
        for group in groups.values():
            starts=[e['start'] for e in group];rng.shuffle(starts)
            for e,start in zip(group,starts):changed+=e['start']!=start;e['start']=start
        if changed and repeating:
            from queue_policies import next_music_cycle,preserve_music_history,set_music_origin
            at=next_music_cycle(project,now);preserve_music_history(project,at);set_music_origin(project,at)
        store(project,sorted(events,key=lambda e:(e['start'],e['id'])))
    else:
        layer=voice(project,role)
        if layer.locked:return 0
        repeating=layer.extra.get('queue_policy')=='repeat' and now>0
        performed=set() if repeating else performed_visual_ids(layer,now+.5);qnow=-1. if repeating else queue_position(layer,now+.5)
        archived=False
        endpoints={cid for tr in layer.transitions for cid in (tr.from_clip,tr.to_clip)}
        for c in layer.clips:
            if c.extra.get('queue_gap') or c.start<=qnow or c.id in performed or c.locked or c.timing_locked or c.manual or c.extra.get('playable_pin') or c.id in endpoints:continue
            groups[(round(c.duration,6),c.channel)].append(c)
        for group in groups.values():
            starts=[c.start for c in group];rng.shuffle(starts)
            for c,start in zip(group,starts):
                if c.start!=start and repeating and not archived:
                    from queue_policies import next_visual_cycle,preserve_visual_history
                    from queue_model import append_switch
                    at=next_visual_cycle(layer,now);preserve_visual_history(layer,at);append_switch(layer,at,'queue',0.);archived=True
                changed+=c.start!=start;c.start=start
        layer.clips.sort(key=lambda c:(c.start,c.channel,c.id))
    return changed
