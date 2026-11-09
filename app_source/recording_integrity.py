"""Recording integrity contract for Programme capture.

Sound, React and Monitor are independent.  Programme recording may flatten the
picture, but any external audio route that is audible or drives reaction must be
retained.  Reaction-only retention never grants audibility.
"""
from __future__ import annotations
import copy, json, math, os, tempfile
from pathlib import Path
from sound_routes import BUILTINS, contribution, route_at, external_route_intervals

SCHEMA='neospector/recording-integrity-v1'


def active_external_requirements(project,t):
    """Return contributing external routes at *t*, with independent purposes."""
    t=float(t);routes=project.extra.get('sound_routes',{});history=project.extra.get('sound_route_history',[])
    ids=sorted((set(routes)|{e.get('id') for e in history if isinstance(e,dict)})-set(BUILTINS))
    out=[]
    for rid in ids:
        route=copy.deepcopy(route_at(project,rid,t));purposes=[p for p in ('sound','react') if contribution(route,p)>0]
        if purposes:out.append({'id':rid,'label':route.get('label',rid),'purposes':purposes,'route':route})
    return out


def _probe_destination(target):
    """Fail before recording if the destination cannot accept a new artifact pair."""
    target=Path(target)
    if target.exists():raise FileExistsError('Recording destination already exists; choose a new recording name.')
    target.parent.mkdir(parents=True,exist_ok=True)
    try:
        fd,name=tempfile.mkstemp(prefix='.neospector-recording-probe-',dir=target.parent)
        os.close(fd);Path(name).unlink(missing_ok=True)
    except OSError as exc:
        raise OSError('Recording destination is not writable: '+str(exc)) from exc


def preflight_recording(project,live,target,t):
    """Validate all currently contributing live routes before Programme capture."""
    _probe_destination(target)
    requirements=active_external_requirements(project,t);states=live.source_states() if live is not None else {}
    for item in requirements:
        state=states.get(item['id'],{})
        if state.get('state')!='live':
            purposes=' + '.join(p.title() for p in item['purposes'])
            detail=state.get('error') or 'source is not live'
            raise ValueError(f"Cannot record: {item['label']} contributes to {purposes}, but {detail}. Start the input in Inputs or turn that route off before recording.")
    # File-backed Programme Sound must still exist when the final bus is resolved.
    from audio_bus import sound_events
    for event in sound_events(project):
        asset=project.asset(event.get('asset_id'))
        if asset is None:raise ValueError('Cannot record: Programme Sound references a missing asset.')
        if asset.kind in ('audio','video') and (not asset.path or not Path(asset.path).is_file()):
            raise FileNotFoundError(f'Cannot record: {asset.name} is missing. Relink it before recording.')
    return {'time':float(t),'target':str(Path(target)),'external':requirements,'needs_retention':bool(requirements)}


def validate_live_state(project,live,t):
    """Return an actionable failure if a contributing source disappears mid-take."""
    requirements=active_external_requirements(project,t);states=live.source_states() if live is not None else {}
    for item in requirements:
        state=states.get(item['id'],{})
        if state.get('state')!='live':
            purposes=' + '.join(p.title() for p in item['purposes'])
            return f"{item['label']} stopped while contributing to {purposes}. The incomplete recording will not be published."
    recording=getattr(live,'recording',None)
    if requirements and recording is None:
        return 'Retained audio stopped while Sound/React still depended on a live source. The incomplete recording will not be published.'
    if requirements and recording and recording.get('error'):
        return 'Retained audio input failed: '+str(recording['error'])
    if requirements and getattr(live,'record_fault',''):
        return 'Retained audio mix failed: '+str(live.record_fault)
    return ''


def _covers(intervals,start,end,tolerance=.12):
    cursor=float(start)
    for a,b in sorted((float(a),float(b)) for a,b in intervals):
        if b<=cursor:continue
        if a>cursor+tolerance:return False
        cursor=max(cursor,b)
        if cursor>=end-tolerance:return True
    return cursor>=end-tolerance


def _analysis_span(segment,key):
    data=segment.get(key) or {}
    if not data:return None
    start=float(data.get('offset',segment.get('start',0)))
    return (start,start+float(data.get('duration',segment.get('duration',0))))


def prepare_recording_integrity(project,start,end,segments):
    """Freeze retained live Sound/React into a recording snapshot and private integrity data.

    External Sound is attached as an already-routed retained mix. External React
    is retained as the full reaction envelope only; it is never attached to Sound.
    """
    from performance_capture import attach_retained_sound,join_analysis
    from sequencer_model import project_to_dict
    start,end=float(start),float(end)
    if not (math.isfinite(start) and math.isfinite(end) and end>start):raise ValueError('Invalid recording interval')
    used=[s for s in segments if float(s.get('start',0))<end and float(s.get('start',0))+float(s.get('duration',0))>start]
    errors=[str(s.get('error')) for s in used if s.get('error')]
    if errors:raise ValueError('Retained input reported an error: '+'; '.join(errors))

    sound_by_route=external_route_intervals(project,'sound',start,end)
    react_by_route=external_route_intervals(project,'react',start,end)

    # Sound is authoritative: no legacy checkbox may add a route that was not Sound.
    attach_retained_sound(project,start,end,used)

    # Preserve both the external-only live envelope and the complete reaction mix.
    # Parameters that explicitly chose microphone/device use recorded_analysis;
    # reaction_mix uses recorded_mix_analysis. This keeps their semantics distinct.
    live_segments=[s for s in used if s.get('analysis')]
    live_analysis=join_analysis(live_segments) if react_by_route else {}
    reaction_segments=[{**s,'analysis':s['reaction_analysis']} for s in used if s.get('reaction_analysis')]
    reaction_spans=[span for s in used for span in [_analysis_span(s,'reaction_analysis')] if span]
    for rid,spans in react_by_route.items():
        for lo,hi in spans:
            if not _covers(reaction_spans,lo,hi):
                label=route_at(project,rid,lo).get('label',rid)
                raise ValueError(f'Reaction from {label} has incomplete retained coverage. The recording will not be published.')
    reaction_analysis=join_analysis(reaction_segments) if react_by_route else {}
    if react_by_route:
        if not reaction_analysis:raise ValueError('External reaction influenced the recording but no reaction envelope was retained.')
        if not live_analysis:raise ValueError('External reaction influenced the recording but no source reaction envelope was retained.')
        project.recorded_analysis=copy.deepcopy(live_analysis)
        project.extra['recorded_mix_analysis']=copy.deepcopy(reaction_analysis)
        # Convert live reaction selectors to the retained deterministic equivalents
        # in the reproducibility snapshot. The flattened Programme frames themselves
        # are unchanged; this only makes a future replay independent of hardware.
        from instrument_model import map_live_reaction
        map_live_reaction(project)

    route_history=[copy.deepcopy(e) for e in project.extra.get('sound_route_history',[]) if isinstance(e,dict) and float(e.get('end',0))>start and float(e.get('start',0))<end]
    raw=[]
    for s in used:
        for item in s.get('raw_sources',[]):
            raw.append({k:copy.deepcopy(v) for k,v in item.items() if k not in ('writer',)})
    return {
        'schema':SCHEMA,
        'contract':'Every audio input that changed Programme Sound or audiovisual React is retained sufficiently to reproduce the recorded result. Monitor alone never grants output inclusion.',
        'start':start,'end':end,
        'route_purposes':{'sound':'audible Programme/output','react':'audiovisual control only','monitor':'local monitoring only'},
        'external_sound_intervals':sound_by_route,
        'external_react_intervals':react_by_route,
        'live_reaction_analysis':live_analysis,
        'reaction_analysis':reaction_analysis,
        'routing_history':route_history,
        'routing_final':copy.deepcopy(project.extra.get('sound_routes',{})),
        'retained_raw_sources':raw,
        'retained_segments':[{'start':s.get('start'),'duration':s.get('duration'),'sound_mix_recorded':bool(s.get('sound_mix_recorded')),'reaction_mix_recorded':bool(s.get('reaction_mix_recorded')),'routing_events':copy.deepcopy(s.get('routing_events',[]))} for s in used],
        # A current-format snapshot keeps file-backed queue/source timing and all
        # parameter/conductor histories. Media remains local-first by reference.
        'project_snapshot':project_to_dict(project),
    }
