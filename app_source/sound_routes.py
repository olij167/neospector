"""Named source contributions with historical gain/route changes.

View visibility is deliberately absent. A mute removes all contributions but
preserves level and assignment. Local monitoring never grants export permission.
"""
from __future__ import annotations
import copy, hashlib, json, math
import numpy as np

BUILTINS=('soundtrack','voice:A','voice:B','voice:C','voice:D')
ROUTING_SEMANTICS_VERSION=2

def source_id(device):
    return 'live:'+hashlib.sha256(json.dumps(device,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]

def default_route(route_id,label=''):
    file_source=route_id=='soundtrack'
    # A route's purpose defaults describe what ON means; ``enabled`` describes
    # whether it is currently participating.  Physical inputs and channel-video
    # sound therefore start OFF, but one explicit enable gives the useful product
    # default: audible Programme Sound + audiovisual React + automatic recording.
    # Monitor remains separate to avoid microphone feedback.
    return dict(
        id=route_id,
        label=label or {'soundtrack':'Audio queue',**{f'voice:{r}':f'{r} · video sound' for r in ('A','B','C','D')}}.get(route_id,'Microphone' if route_id=='mic' else route_id),
        enabled=file_source,
        muted=False,
        gain=1.,
        sound=True,
        react=True,
        monitor=file_source,
        routing_custom=False,
    )

def migrate_route_semantics(project):
    """Deterministic UX1 -> UX1R1 route migration.

    UX1's unmarked physical-input default was React-only. That exact unmarked
    shape is promoted to the new normal-use Sound+React default. Other old
    combinations are treated as deliberate advanced routing and preserved.
    Historical route snapshots keep their audible meaning unchanged.
    """
    extra=project.extra
    if int(extra.get('sound_route_semantics_version',0) or 0)>=ROUTING_SEMANTICS_VERSION:return 0
    changed=0
    for rid,route in extra.get('sound_routes',{}).items():
        if not isinstance(route,dict):continue
        if 'routing_custom' not in route:
            if rid not in BUILTINS and route.get('sound',False) is False and route.get('react',False) is True and route.get('monitor',False) is False:
                route['sound']=True;route['routing_custom']=False;changed+=1
            else:
                expected=(True,True,False)
                route['routing_custom']=(bool(route.get('sound',False)),bool(route.get('react',False)),bool(route.get('monitor',False)))!=expected
        else:route['routing_custom']=bool(route['routing_custom'])
    for event in extra.get('sound_route_history',[]):
        route=event.get('route') if isinstance(event,dict) else None
        if isinstance(route,dict) and 'routing_custom' not in route:
            route['routing_custom']=True  # preserve historical purpose semantics exactly
    extra['sound_route_semantics_version']=ROUTING_SEMANTICS_VERSION
    return changed

def primary_route_changes(route,enabled):
    """Changes for the single artist-facing ON/OFF control.

    The first/default enable means Programme Sound + React; Programme Sound is
    what the recorder captures, so there is no second recording-arm decision.
    Once the operator deliberately edits Advanced Routing we preserve that custom
    combination across ordinary OFF/ON toggles (for example React-only).
    """
    enabled=bool(enabled);changes={'enabled':enabled}
    if enabled and not bool((route or {}).get('routing_custom',False)):
        changes.update(sound=True,react=True)
    return changes

def ensure_route(project,route_id,label=''):
    routes=project.extra.setdefault('sound_routes',{})
    if route_id not in routes:routes[route_id]=default_route(route_id,label)
    return routes[route_id]

def route_at(project,route_id,t):
    route=project.extra.get('sound_routes',{}).get(route_id)
    if route is None:return default_route(route_id)
    for event in reversed(project.extra.get('sound_route_history',[])):
        if event['id']==route_id and event['start']<=t<event['end']:return event['route']
    return route

def contribution(route,purpose):
    if not route.get('enabled',True) or route.get('muted',False):return 0.
    if not route.get(purpose,False):return 0.
    return float(route.get(purpose+'_gain',route.get('gain',1.)))

def route_gain(project,route_id,t,purpose='sound'):
    return contribution(route_at(project,route_id,t),purpose)

def gain_curve(project,route_id,times,purpose):
    values=np.ones(len(times),dtype=np.float32)*contribution(project.extra.get('sound_routes',{}).get(route_id,default_route(route_id)),purpose)
    for event in project.extra.get('sound_route_history',[]):
        if event['id']==route_id:
            mask=(times>=event['start'])&(times<event['end']);values[mask]=contribution(event['route'],purpose)
    return values

def update_route(project,route_id,changes,t=0.):
    # Validate the whole change before touching the document.
    if not math.isfinite(t) or t<0:raise ValueError('Invalid source edit time')
    allowed={'label','enabled','muted','gain','sound','react','monitor','sound_gain','react_gain','monitor_gain','device','kind','routing_custom'}
    if set(changes)-allowed:raise ValueError('Unsupported sound source property')
    for key in ('gain','sound_gain','react_gain','monitor_gain'):
        if key in changes and (not isinstance(changes[key],(int,float)) or not math.isfinite(changes[key]) or not 0<=changes[key]<=2):raise ValueError('Source level must be between 0 and 2×')
    routes=project.extra.setdefault('sound_routes',{});existed=route_id in routes
    old=copy.deepcopy(ensure_route(project,route_id));history=project.extra.setdefault('sound_route_history',[])
    # An external route created after Programme time zero did not contribute
    # before it existed. Record that inactive interval explicitly so a take does
    # not demand retained Sound/React coverage from before the device was added.
    if not existed and route_id not in BUILTINS:old['enabled']=False
    origin=max((e['end'] for e in history if e['id']==route_id),default=0.)
    if t>origin:history.append(dict(id=route_id,start=origin,end=float(t),route=old))
    project.extra['sound_routes'][route_id].update(changes);return project.extra['sound_routes'][route_id]

def use_only(project,route_id,t=0.):
    ensure_route(project,route_id)
    for key in tuple(project.extra['sound_routes']):update_route(project,key,{'enabled':key==route_id,'muted':False if key==route_id else project.extra['sound_routes'][key].get('muted',False)},t)

def linked_events(project):
    """Video sound follows its occurrence clock, independent of visual opacity."""
    from queue_model import materialize
    mapped=None;events=[]
    for layer in project.layers:
        role=layer.extra.get('voice');rid='voice:'+str(role)
        if role not in ('A','B','C','D'):continue
        route=project.extra.get('sound_routes',{}).get(rid)
        history=[e for e in project.extra.get('sound_route_history',[]) if e['id']==rid]
        if route is None and not history:continue
        if layer.extra.get('source_switches') or layer.extra.get('queue_policy')=='repeat':
            if mapped is None:mapped=materialize(project,0.,max(.01,project.max_end()))
            layer=next(l for l in mapped.layers if l.id==layer.id)
        for c in layer.clips:
            a=project.asset(c.asset_id)
            if not a or not a.metadata.get('has_audio') or a.kind!='video':continue
            lo,hi=c.extra.get('source_window',[0.,a.duration])
            events.append(dict(id='linked-'+c.id,asset_id=a.id,start=c.start,duration=c.duration,in_point=c.in_point,gain=1.,enabled=True,fade_in=c.fade_in,fade_out=c.fade_out,curve='equal_power',route_id=rid,playback_rate=c.playback_rate,source_policy=c.source_policy,source_lo=lo,source_hi=hi,fade_start=c.extra.get('fade_start',c.start),fade_end=c.extra.get('fade_end',c.end)))
    return events

def external_reaction_active(project):
    return any(k not in BUILTINS and contribution(v,'react')>0 for k,v in project.extra.get('sound_routes',{}).items())


def external_route_intervals(project,purpose,start,end):
    """Per-source external contribution intervals for recording integrity."""
    start,end=float(start),float(end)
    if end<=start:return {}
    routes=project.extra.get('sound_routes',{});history=project.extra.get('sound_route_history',[])
    ids=(set(routes)|{e.get('id') for e in history if isinstance(e,dict)})-set(BUILTINS);result={}
    for rid in sorted(ids):
        points=sorted({start,end,*[max(start,min(end,float(e[k]))) for e in history if e.get('id')==rid for k in ('start','end')]})
        spans=[]
        for a,b in zip(points,points[1:]):
            if b>a and contribution(route_at(project,rid,a),purpose)>0:
                if spans and a<=spans[-1][1]:spans[-1]=(spans[-1][0],max(b,spans[-1][1]))
                else:spans.append((a,b))
        if spans:result[rid]=spans
    return result

def external_intervals(project,purpose,start,end):
    """Merged intervals with any routed external contribution."""
    spans=[span for route_spans in external_route_intervals(project,purpose,start,end).values() for span in route_spans]
    merged=[]
    for a,b in sorted(spans):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    return merged


class LinkedEventClock:
    """Cached video-audio templates mapped over a requested session-time window.

    A mixer owns one clock for its immutable project snapshot. History is decoded
    once at construction; blocks only split at source switches and local wraps.
    Camera and timed gaps contribute no queue audio. Hold-current repeats its
    clip; an end-policy held still frame contributes silence after its source end.
    """
    def __init__(self,project):
        from queue_policies import visual_state_at
        self.layers=[]
        for layer in project.layers:
            role=layer.extra.get('voice');rid='voice:'+str(role)
            if role not in ('A','B','C','D'):continue
            if rid not in project.extra.get('sound_routes',{}) and not any(e['id']==rid for e in project.extra.get('sound_route_history',[])):continue
            history=layer.extra.get('queue_history',[]);versions=[];cuts=set()
            for record in history:
                state=visual_state_at(layer,record['start']);versions.append((record['start'],record['end'],state));cuts.update((record['start'],record['end']))
            versions.append((history[-1]['end'] if history else 0.,float('inf'),layer))
            compiled=[]
            for lo,hi,state in versions:
                templates=[]
                for c in state.clips:
                    asset=project.asset(c.asset_id)
                    if c.extra.get('queue_gap') or not asset or asset.kind!='video' or not asset.metadata.get('has_audio'):continue
                    lower,upper=c.extra.get('source_window',[0.,asset.duration])
                    templates.append(dict(id='linked-'+c.id,asset_id=asset.id,start=c.start,duration=c.duration,in_point=max(0.,c.in_point),gain=1.,enabled=True,fade_in=c.fade_in,fade_out=c.fade_out,curve='equal_power',route_id=rid,playback_rate=c.playback_rate,source_policy=c.source_policy,source_lo=lower,source_hi=upper,fade_start=c.extra.get('fade_start',c.start),fade_end=c.extra.get('fade_end',c.end),_clip_id=c.id))
                for template in templates:
                    clip=next(c for c in state.clips if c.id==template['_clip_id'])
                    if clip.extra.get('captured_queue_seam'):template['_queue_seam']=clip.extra['captured_queue_seam']
                switches=state.extra.get('source_switches',[])
                cuts.update(s['start'] for s in switches if lo<s['start']<hi)
                compiled.append((lo,hi,state,templates,max((c.end for c in state.clips),default=0.)))
            self.layers.append((compiled,sorted(cuts)))

    def events(self,start,end):
        from bisect import bisect_right
        from queue_model import queue_position,mode_at
        result=[]
        for versions,cuts in self.layers:
            lo=float(start)
            while lo<end-1e-10:
                version=next((v for v in reversed(versions) if v[0]<=lo<v[1]),None)
                if version is None:break
                _,version_end,state,templates,queue_end=version
                ci=bisect_right(cuts,lo+1e-9);hi=min(float(end),version_end,cuts[ci] if ci<len(cuts) else end)
                source=mode_at(state,lo);q=queue_position(state,lo)
                if source['mode']=='camera':lo=hi;continue
                pool=templates
                if source['mode']=='hold':
                    held=next((c for c in state.clips if c.id==source.get('clip_id')),None)
                    if held is None:lo=hi;continue
                    hi=min(hi,lo+held.end-q);pool=[e for e in templates if e['_clip_id']==held.id]
                elif state.extra.get('queue_policy')=='repeat' and queue_end>0:
                    hi=min(hi,lo+queue_end-q)
                elif state.extra.get('queue_policy')=='hold' and queue_end>0:
                    # The visual end Hold is a still frame, not an audio loop.
                    if q>=queue_end-2e-5:lo=hi;continue
                    hi=min(hi,lo+queue_end-q)
                if hi<=lo+1e-10:break
                delta=lo-q
                from queue_seams import active_seam
                seam=active_seam(sorted(state.clips,key=lambda c:(c.start,c.id)),state.extra.get('queue_seam'))
                for original in pool:
                    event_start=original['start']+delta
                    if event_start>=hi-1e-10 or event_start+original['duration']<=lo+1e-10:continue
                    e=dict(original);e['start']=event_start;e['fade_start']=original['fade_start']+delta;e['fade_end']=original['fade_end']+delta;e['_segment']=(lo,hi)
                    if seam:e['_queue_seam']={'seam':seam,'length':queue_end,'origin':delta}
                    elif original.get('_queue_seam'):e['_queue_seam']=dict(original['_queue_seam'],origin=original['_queue_seam']['origin']+delta)
                    result.append(e)
                lo=hi
        return result
