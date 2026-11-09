"""Music queue commands over the existing soundtrack events (not a second timeline)."""
from __future__ import annotations
import copy, math
from audio_bus import sound_events

def items(project):
    return [e for e in sound_events(project,include_linked=False) if e.get('route_id')=='soundtrack']

def store(project,events):
    rest=[e for e in project.extra.get('sound_events',[]) if e.get('route_id','soundtrack')!='soundtrack']
    project.extra['sound_events']=rest+events;project.extra['audio_bus_enabled']=True
    if events:project.audio_asset_id=next((e['asset_id'] for e in reversed(events) if e.get('asset_id')),None);project.duration=max(project.duration,max(e['start']+e['duration'] for e in events))
    else:project.audio_asset_id=None

def layout(events,start=0.):
    end=start
    for i,e in enumerate(events):
        if e.get('boundary_from') and (not i or e['boundary_from']!=events[i-1]['id']):
            e['fade_in']=0.;e.pop('boundary_from',None);e.pop('boundary_id',None)
        e.pop('fade_start',None);e.pop('fade_end',None)
        e['start']=max(start,end-(min(float(e.get('fade_in',0)),events[i-1]['duration']*.8,e['duration']*.8) if i else 0))
        if not i:e['fade_in']=0.
        end=e['start']+e['duration']
        e['fade_out']=0.
        if i:events[i-1]['fade_out']=max(0.,events[i-1]['start']+events[i-1]['duration']-e['start'])
    return events

def move(project,event_id,index):
    events=items(project);old=next((i for i,e in enumerate(events) if e['id']==event_id),None)
    if old is None:return
    e=events.pop(old);events.insert(max(0,min(index,len(events))),e)
    store(project,layout(events))

def remove(project,event_id):
    store(project,layout([e for e in items(project) if e['id']!=event_id]))

def duration(project,event_id,value):
    value=float(value)
    if not math.isfinite(value) or value<1/project.fps:raise ValueError('Choose a positive duration of at least one frame.')
    events=items(project)
    for e in events:
        if e['id']==event_id:
            if e.get('queue_gap'):e['duration']=value;continue
            a=project.asset(e['asset_id']);available=max(0.,a.duration-e['in_point'])/float(e.get('playback_rate',1))
            if value>available+.02 and e.get('source_policy')!='loop':raise ValueError(f'Only {available:.2f} seconds remain in this source.')
            e['duration']=value
    store(project,layout(events))

def transition(project,event_id,seconds,*,to_id=None,now=None,cut=False,curve=None):
    seconds=float(seconds);events=items(project)
    if not math.isfinite(seconds) or seconds<0:raise ValueError('Use a nonnegative crossfade duration.')
    if curve is not None and curve not in ('linear','equal_power'):raise ValueError('Choose Linear or Equal power.')
    if cut:seconds=0.
    i=next((i for i,e in enumerate(events) if e['id']==event_id),-1)
    if not 0<=i<len(events)-1:raise ValueError('Add a following track before creating a crossfade.')
    a,b=events[i:i+2]
    if to_id is not None and b['id']!=to_id:raise ValueError('These tracks are no longer neighbours. Reopen the boundary.')
    if seconds>min(a['duration'],b['duration'])*.8:raise ValueError('Crossfade is too long for these two tracks.')
    delta=a['start']+a['duration']-seconds-b['start']
    if abs(delta)<1e-8 and a.get('fade_out',0)==seconds and b.get('fade_in',0)==seconds and 'fade_end' not in a and 'fade_start' not in b and not a.get('playable_auto') and not b.get('playable_auto') and (curve is None or (a.get('curve')==curve and b.get('curve')==curve)):return True
    affected=events[i:] if abs(delta)>1e-8 else [a,b]
    if any(e.get('locked') or e.get('timing_locked') or e.get('pinned') for e in affected):raise ValueError('This edit would change a locked or pinned track.')
    if now is not None:
        now=float(now)
        if not math.isfinite(now) or now<0:raise ValueError('Invalid Programme time.')
        from queue_policies import music_position,next_music_cycle,preserve_music_history,set_music_origin
        q=music_position(project,now);at=max(now,max((r['end'] for r in project.extra.get('music_queue_history',[]) if r['start']<=now<r['end']),default=now))
        old_edge=min(b['start'],a['start']+a['duration']-float(a.get('fade_out',0)))
        if min(old_edge,a['start']+a['duration']-seconds)<=q+1e-7:
            if project.extra.get('music_queue_policy')!='repeat':raise ValueError('This overlap has started. Edit a Draft or enable Loop to change the next repeat.')
            at=max(at,next_music_cycle(project,now))
        preserve_music_history(project,at);set_music_origin(project,at,0. if at>now else q)
    # Never reflow from zero: current PCM and all earlier events stay identical.
    for e in events[i+1:]:
        e['start']+=delta
        for key in ('fade_start','fade_end'):
            if key in e:e[key]+=delta
    a['fade_out']=seconds;b['fade_in']=seconds
    if curve is not None:a['curve']=b['curve']=curve
    a.pop('fade_end',None);b.pop('fade_start',None)
    a['manual']=b['manual']=True
    # Both autonomous preparation and shuffle use playable_auto as their
    # eligibility flag. An explicitly authored edge owns both occurrences.
    a['playable_auto']=b['playable_auto']=False
    if seconds:
        from sequencer_model import new_id
        b['boundary_from']=a['id'];b.setdefault('boundary_id',new_id('sndtr'))
    else:b.pop('boundary_from',None);b.pop('boundary_id',None)
    changed={e['id']:e for e in affected}
    raw=project.extra.get('sound_events',[])
    # Retain raw prefix dictionaries, disabled tracks and independent routes.
    stored=[copy.deepcopy(changed.get(e.get('id'),e)) for e in raw]
    known={e.get('id') for e in raw}
    stored.extend(e for e in events if e['id'] not in known)
    project.extra['sound_events']=stored;project.extra['audio_bus_enabled']=True
    project.audio_asset_id=next((e['asset_id'] for e in reversed(events) if e.get('asset_id')),None);project.duration=max(project.duration,max(e['start']+e['duration'] for e in events));project.touch()
    return True

def take(project,event_id,now):
    from queue_policies import activate_music_state,music_state_at
    state=music_state_at(project,now)
    use_prepared=not any(e['id']==event_id for e in state['events'])
    if not any(e['id']==event_id for e in items(project)) and use_prepared:return
    activate_music_state(project,now,prepared=use_prepared)
    events=items(project);i=next((i for i,e in enumerate(events) if e['id']==event_id),-1)
    if i<0:return
    if project.extra.get('music_queue_policy')=='repeat' or project.extra.get('music_queue_origins'):
        from queue_policies import preserve_music_history,set_music_origin
        preserve_music_history(project,now);set_music_origin(project,now,events[i]['start']);project.touch();return
    history=[]
    for e in events:
        if e['start']<now:
            e=copy.deepcopy(e)
            if e['start']+e['duration']>now:
                # Truncation stops future output without rewriting the envelope
                # which was already heard before this Take.
                if e.get('fade_out'):e.setdefault('fade_end',e['start']+e['duration'])
                e['duration']=now-e['start']
            history.append(e)
    upcoming=fresh_occurrences(events[i:])
    store(project,history+layout(upcoming,max(0.,now)))

def fresh_occurrences(events):
    """Clone a played/replayed suffix with its internal pair references intact."""
    from sequencer_model import new_id
    copies=copy.deepcopy(events);ids={e['id']:new_id('snd') for e in copies}
    for e in copies:
        e['id']=ids[e['id']]
        predecessor=e.get('boundary_from')
        if predecessor in ids:
            e['boundary_from']=ids[predecessor]
            e['boundary_id']=new_id('sndtr')
        elif predecessor:
            # The old incoming edge has no outgoing member in this suffix.
            e['fade_in']=0.;e.pop('boundary_from',None);e.pop('boundary_id',None)
    return copies

def set_timing(project,event_id,**changes):
    """Precise event edits over the same queue, validated before storage."""
    events=items(project);event=next((e for e in events if e['id']==event_id),None)
    if event is None:raise ValueError('The selected track is no longer in this queue.')
    candidate=copy.deepcopy(event)
    for key,value in changes.items():
        if key not in ('start','duration','in_point','fade_in','fade_out','gain'):raise ValueError('Unsupported audio timing control')
        value=float(value)
        if not math.isfinite(value) or value<0:raise ValueError('Use finite, nonnegative values')
        candidate[key]=value
    if candidate['duration']<1/project.fps:raise ValueError('A track must last at least one frame')
    a=project.asset(candidate['asset_id']);rate=float(candidate.get('playback_rate',1))
    if a is None:raise ValueError('Locate the missing source first')
    if candidate.get('source_policy')!='loop' and candidate['in_point']+candidate['duration']*rate>a.duration+.02:raise ValueError('Timing exceeds the available source. Adjust source in or duration.')
    if candidate.get('gain',1)>4:raise ValueError('Gain exceeds 4×')
    if max(candidate.get('fade_in',0),candidate.get('fade_out',0))>candidate['duration']:raise ValueError('A fade cannot exceed the track duration')
    candidate.pop('fade_start',None);candidate.pop('fade_end',None)
    event.clear();event.update(candidate);store(project,sorted(events,key=lambda e:(e['start'],e['id'])))
