"""Purpose-first finite export descriptors, independent of rendering and devices."""
import math
from music_queue import items

def seconds(value):
    if isinstance(value,str) and ':' in value:
        parts=value.strip().split(':')
        if len(parts)!=2:raise ValueError('Use seconds or minutes:seconds')
        minutes=float(parts[0]);part=float(parts[1])
        if minutes<0 or not minutes.is_integer() or not 0<=part<60:raise ValueError('Use minutes:seconds, with seconds below 60')
        value=minutes*60+part
    n=float(value)
    if not math.isfinite(n) or not 0<n<=21600:raise ValueError('Choose a finite duration between 0 and 6 hours')
    return n

def export_visual_project(project,context='finite'):
    """Materialise performed queue clocks without changing the live sequence."""
    capture=project.extra.get('capture_range') if context=='take' else None
    lo=float(capture[0]) if capture else float(project.extra.get('history_start',0))
    if any(l.extra.get('source_switches') or l.extra.get('queue_policy') in ('repeat','hold') or l.extra.get('queue_history') for l in project.layers):
        from queue_model import materialize
        hi=float(capture[1]) if capture else max(lo+.01,project.max_end())
        return materialize(project,lo,hi)
    return project

def resolve_export_range(project,scope,*,now,current_event_id=None,duration=None,start_mode='beginning',context='finite',layer_id=None,occurrence_id=None):
    now=float(now)
    if not math.isfinite(now) or now<0:raise ValueError('Invalid playhead')
    events=items(project);capture=project.extra.get('capture_range') if context=='take' else None
    lo=float(capture[0]) if capture else float(project.extra.get('history_start',0))
    prepared_pass=context!='take' and scope in ('sequence','music','visual','queue')
    if prepared_pass:
        validate_prepared_sources(project,now);lo=0.
    visual_project=project if prepared_pass else export_visual_project(project,context)
    endpoints=[c.end for l in visual_project.layers if l.enabled for c in l.clips]
    prepared=max([e['start']+e['duration'] for e in events]+endpoints+[0.])
    hi=float(capture[1]) if capture else prepared
    result={'source_context':context,'source_project_id':project.id,'occurrence_id':None,'action':'render','coverage_state':'preflight_required','scope':scope,'clock_domain':'prepared' if prepared_pass else 'session','reference_time':now}
    if scope=='song':
        active=[e for e in events if e['start']<=now<e['start']+e['duration']]
        selected=next((e for e in active if e['id']==current_event_id),None) or (active[-1] if active else None)
        if selected is None:return dict(result,start=None,end=None,label='No current song · choose Duration',action='unavailable')
        start=selected['start'];end=start+selected['duration'];a=project.asset(selected['asset_id'])
        result.update(occurrence_id=selected['id'],label='Current song · '+(a.name if a else 'Missing source'))
    elif scope in ('sequence','music','visual','clip','track'):
        clips=[(l,c) for l in visual_project.layers if l.enabled for c in l.clips]
        if scope=='sequence':
            scheduled=[(c.start,c.end) for l,c in clips]+[(e['start'],e['start']+e['duration']) for e in events]
            if capture:scheduled=[tuple(map(float,capture))]
            label='Whole captured Draft' if capture else 'Whole prepared sequence · one pass' if prepared_pass else 'Whole prepared sequence'
        elif scope=='music':
            scheduled=[(e['start'],e['start']+e['duration']) for e in events];label='Music queue · one pass' if prepared_pass else 'Music queue'
        elif scope=='visual':
            layer=next((l for l in visual_project.layers if l.id==layer_id),None)
            if layer is None:raise ValueError('Choose an available visual queue')
            scheduled=[(c.start,c.end) for l,c in clips if l.id==layer_id]
            label='Visual queue · '+layer.name+(' · one pass' if prepared_pass else '');result['layer_id']=layer_id
        elif scope=='track':
            event=next((e for e in events if e['id']==occurrence_id),None)
            if event is None:raise ValueError('Choose an available track occurrence')
            scheduled=[(event['start'],event['start']+event['duration'])]
            asset=project.asset(event['asset_id']);label='Track · '+(asset.name if asset else 'Missing source')
            result['occurrence_id']=event['id']
        else:
            exact=[(l,c) for l,c in clips if c.id==occurrence_id]
            candidates=exact or [(l,c) for l,c in clips if c.extra.get('original_queue_id')==occurrence_id]
            if not candidates:raise ValueError('Choose a performed or prepared clip occurrence from an enabled queue')
            # Original IDs may have several performed/repeated spans. The explicit
            # materialised ID selects exactly one; an original selection prefers
            # the current span, then the next, then the most recent performed span.
            l,c=min(candidates,key=lambda pair:(0 if pair[1].start<=now<pair[1].end else 1 if pair[1].start>=now else 2,abs(pair[1].start-now)))
            scheduled=[(c.start,c.end)];asset=project.asset(c.asset_id)
            label='Clip · '+(asset.name if asset else 'Missing source')
            result.update(occurrence_id=occurrence_id,materialized_occurrence_id=c.id,
                          original_occurrence_id=c.extra.get('original_queue_id',c.id),layer_id=l.id)
        scheduled=[(max(a,lo),min(b,hi)) for a,b in scheduled if b>lo and a<hi]
        if not scheduled:return dict(result,start=None,end=None,label='No media in this scope · choose another queue or duration',action='unavailable')
        start=min(a for a,b in scheduled);end=max(b for a,b in scheduled);result['label']=label
    elif scope=='queue':
        if capture:start,end=map(float,capture);label='Complete captured take'
        else:
            scheduled=events if events else [dict(start=c.start,duration=c.duration) for l in visual_project.layers if l.enabled for c in l.clips]
            if context=='continuous' and not prepared_pass:scheduled=[e for e in scheduled if e['start']+e['duration']>now]
            if not scheduled:return dict(result,start=None,end=None,label='No prepared queue · choose Duration / Record next',action='unavailable')
            start=min(e['start'] for e in scheduled);end=max(e['start']+e['duration'] for e in scheduled)
            label=('One prepared pass · '+('Music queue' if events else 'visual sequence') if prepared_pass else 'Current + prepared Upcoming · finite snapshot' if context=='continuous' else 'Full scheduled Music queue' if events else 'Full materialised visual sequence')
        result['label']=label
    elif scope=='duration':
        length=seconds(duration)
        if start_mode=='record_next':
            return dict(result,start=now,end=now+length,label='Record the next '+f'{length:g}s',action='capture_first',coverage_state='future_live')
        if start_mode=='beginning':start=lo
        elif start_mode=='playhead':start=now
        elif start_mode=='recent':start=now-length
        else:raise ValueError('Choose beginning, playhead, recent history or Record next')
        end=start+length;result['label']='Duration · '+f'{length:g}s'
    else:raise ValueError('Choose a sequence, queue, clip, track or duration')
    if not 0<=start<end or not all(math.isfinite(x) for x in (start,end)):raise ValueError('Requested interval is not available; choose a shorter or later range')
    if start<lo-.0001:raise ValueError(f'Request begins before retained history / take ({lo:g}s). Choose a later range.')
    repeating=project.extra.get('music_queue_policy')=='repeat' or any(l.enabled and l.extra.get('queue_policy')=='repeat' for l in project.layers)
    if end>hi+.0001 and not (scope=='duration' and repeating and not capture):raise ValueError(f'Request ends beyond prepared media ({hi:g}s). Prepare more media, or use Record for live Programme.')
    if end-start>21600:raise ValueError('Export scope is limited to six hours')
    result.update(start=float(start),end=float(end),duration=float(end-start));return result


def snapshot_for_descriptor(snapshot,descriptor):
    """Interpret one prepared pass on an export-owned snapshot, never Programme.

    Caller passes its frozen copy. Session Duration/clip/Draft scopes retain all
    performed versions; prepared scopes use raw queue/source/style state at local
    time zero. Authored parameter keyframes remain intact.
    """
    if not descriptor or descriptor.get('clock_domain')!='prepared':return snapshot
    validate_prepared_sources(snapshot,float(descriptor.get('reference_time',0)))
    for layer in snapshot.layers:
        for key in ('queue_history','source_switches','treatment_history','camera_placement_history'):
            layer.extra.pop(key,None)
        layer.extra['queue_policy']='finish'
    for key in ('music_queue_history','music_queue_origins','master_history','master_transitions','mixer_history','sound_route_history','history_start'):
        snapshot.extra.pop(key,None)
    for kind in ('visual','audio'):
        key=kind+'_master_events';events=snapshot.extra.get(key,[])
        if events:snapshot.extra[key]=[dict(events[-1],time=0.)]
    if 'channel_mix_since' in snapshot.extra:snapshot.extra['channel_mix_since']=0.
    snapshot.extra['music_queue_policy']='finish'
    snapshot.extra['export_clock_domain']='prepared'
    snapshot.duration=float(descriptor['end'])
    return snapshot


def validate_prepared_sources(project,now):
    from queue_policies import visual_state_at
    from queue_model import mode_at
    for layer in project.layers:
        if not layer.enabled:continue
        state=visual_state_at(layer,now)
        if mode_at(state,now)['mode']=='camera' or any(project.asset(c.asset_id) and project.asset(c.asset_id).kind in ('camera','screen','window') for c in layer.clips):
            raise ValueError('A prepared pass cannot reconstruct a live visual source. Choose Record next or a captured Draft.')
