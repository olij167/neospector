"""Queue clocks and immutable performed versions, independent of generation.

History stores queue-local state only; no project/assets/catalogue snapshots.
Serialized histories survive project reopen. Decoding is cached by record identity.
"""
from __future__ import annotations
import copy, math
from collections import OrderedDict
from sequencer_model import _encode, project_from_dict

_CACHE=OrderedDict()

def _time(t):
    t=float(t)
    if not math.isfinite(t) or t<0:raise ValueError('Use finite nonnegative Programme time.')
    return t

def _policy(policy):
    if policy not in ('repeat','finish','hold'):raise ValueError('Choose Loop, Finish or Hold.')
    return policy

def initialise_queue_policies(project, *, is_new=False):
    default='repeat' if is_new else 'finish'
    project.extra.setdefault('music_queue_policy',default)
    for layer in project.layers:layer.extra.setdefault('queue_policy',default)
    return project

def visual_state_at(layer,t):
    for record in reversed(layer.extra.get('queue_history',[])):
        if record['start']<=t<record['end']:
            key=id(record);cached=_CACHE.get(key)
            if cached is None or cached[0] is not record:
                state=project_from_dict({'layers':[record['state']]}).layers[0]
                _CACHE[key]=(record,state)
                while len(_CACHE)>128:_CACHE.popitem(last=False)
            else:state=cached[1]
            return state
    return layer

def preserve_visual_history(layer,t):
    t=_time(t);history=layer.extra.setdefault('queue_history',[])
    start=history[-1]['end'] if history else 0.
    if t<=start+1e-8:return
    # Exclude previous history to keep growth linear instead of recursive.
    extra={k:v for k,v in layer.extra.items() if k in ('source_switches','queue_policy','queue_seam','camera_layer','treatment_history')}
    state={'id':layer.id,'name':layer.name,'clips':_encode(layer.clips),'transitions':_encode(layer.transitions),'extra':_encode(extra)}
    history.append({'start':start,'end':t,'state':state})

def next_visual_cycle(layer,now):
    from queue_model import queue_position
    state=visual_state_at(layer,now);end=max((c.end for c in state.clips),default=0.)
    return float(now)+max(0.,end-queue_position(layer,now))

def set_visual_policy(layer,policy,t=0.):
    from queue_model import queue_position,append_switch
    t=_time(t);policy=_policy(policy);position=queue_position(layer,t)
    if layer.locked:raise ValueError('Unlock this queue first.')
    activate_visual_state(layer,t);preserve_visual_history(layer,t);layer.extra['queue_policy']=policy
    append_switch(layer,t,'queue',position)
    return policy

def _music_state(project):
    return {'events':project.extra.get('sound_events',[]),'policy':project.extra.get('music_queue_policy','finish'),'origins':project.extra.get('music_queue_origins',[]),'seam':project.extra.get('music_queue_seam')}

def music_state_at(project,t):
    return next((r['state'] for r in reversed(project.extra.get('music_queue_history',[])) if r['start']<=t<r['end']),None) or _music_state(project)

def preserve_music_history(project,t):
    t=_time(t);history=project.extra.setdefault('music_queue_history',[]);start=history[-1]['end'] if history else 0.
    if t>start+1e-8:history.append({'start':start,'end':t,'state':copy.deepcopy(_music_state(project))})

def music_position(project,t):
    state=music_state_at(project,t)
    origin=next((s for s in reversed(state['origins']) if s['start']<=t),{'start':0.,'position':0.})
    q=max(0.,origin['position']+t-origin['start'])
    end=max((e['start']+e['duration'] for e in state['events'] if e.get('route_id','soundtrack')=='soundtrack'),default=0.)
    if state['policy']=='repeat' and end>0:return q%end
    if state['policy']=='hold' and end>0:return min(q,max(0.,end-1e-7))
    return q

def set_music_origin(project,at,position=0.):
    at=_time(at);position=_time(position);origins=project.extra.setdefault('music_queue_origins',[])
    origins[:]=[s for s in origins if s['start']<at];origins.append({'start':at,'position':position})

def set_music_policy(project,policy,t=0.):
    t=_time(t);policy=_policy(policy);q=music_position(project,t)
    activate_music_state(project,t);preserve_music_history(project,t);project.extra['music_queue_policy']=policy;set_music_origin(project,t,q)
    return policy

def next_music_cycle(project,now):
    state=music_state_at(project,now);end=max((e['start']+e['duration'] for e in state['events'] if e.get('route_id','soundtrack')=='soundtrack'),default=0.)
    return float(now)+max(0.,end-music_position(project,now))

def music_segments(project,start,end):
    """Yield finite (session start, end, local start, state) without per-sample Python."""
    cuts={float(start),float(end)}
    history=project.extra.get('music_queue_history',[])
    for r in history:
        cuts.update(v for v in (r['start'],r['end']) if start<v<end)
    states=[r['state'] for r in history]+[_music_state(project)]
    for state in states:cuts.update(s['start'] for s in state['origins'] if start<s['start']<end)
    cuts=sorted(cuts)
    for lo,hi in zip(cuts,cuts[1:]):
        state=music_state_at(project,lo)
        stop=max((e['start']+e['duration'] for e in state['events'] if e.get('route_id','soundtrack')=='soundtrack'),default=0.)
        while lo<hi-1e-10:
            q=music_position(project,lo+1e-10);finish=min(hi,lo+stop-q) if state['policy']=='repeat' and stop>0 else hi
            if finish<=lo+1e-9:finish=hi
            yield lo,finish,q,state
            lo=finish

def activate_visual_state(layer,t,*,prepared=False):
    """An immediate manual Take/source/policy supersedes a pending next cycle.

    Retain all earlier source history; discard the scheduled version explicitly
    through queue_pending_cancelled_at, consumed by the queue status display.
    """
    t=_time(t);state=visual_state_at(layer,t)
    if state is layer:return False
    history=[dict(r,end=min(t,r['end'])) for r in layer.extra.get('queue_history',[]) if r['start']<t]
    if not prepared:
        layer.clips=copy.deepcopy(state.clips);layer.transitions=copy.deepcopy(state.transitions)
        for key in ('source_switches','queue_policy','queue_seam'):
            if key in state.extra:layer.extra[key]=copy.deepcopy(state.extra[key])
            else:layer.extra.pop(key,None)
    layer.extra['queue_history']=history
    layer.extra['source_switches']=[s for s in layer.extra.get('source_switches',[]) if s['start']<=t]
    layer.extra.pop('queue_generation_at',None);layer.extra.pop('generation_at',None)
    layer.extra['queue_pending_cancelled_at']=t
    return True

def activate_music_state(project,t,*,prepared=False):
    t=_time(t);state=music_state_at(project,t)
    if not any(r['start']<=t<r['end'] for r in project.extra.get('music_queue_history',[])):return False
    history=[dict(r,end=min(t,r['end'])) for r in project.extra.get('music_queue_history',[]) if r['start']<t]
    if not prepared:
        current_other=[e for e in project.extra.get('sound_events',[]) if e.get('route_id','soundtrack')!='soundtrack']
        project.extra['sound_events']=current_other+copy.deepcopy([e for e in state['events'] if e.get('route_id','soundtrack')=='soundtrack'])
        project.extra['music_queue_policy']=state['policy'];project.extra['music_queue_origins']=copy.deepcopy(state['origins'])
        if state.get('seam'):project.extra['music_queue_seam']=copy.deepcopy(state['seam'])
        else:project.extra.pop('music_queue_seam',None)
    project.extra['music_queue_history']=history
    project.extra['music_queue_origins']=[s for s in project.extra.get('music_queue_origins',[]) if s['start']<=t]
    project.extra.pop('music_generation_at',None);project.extra['music_pending_cancelled_at']=t
    return True
