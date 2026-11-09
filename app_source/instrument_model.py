"""Persistent visual channels, replayable treatment history and non-destructive takes.

This module has no Tk/device dependencies. Legacy projects remain ordinary layer
compositions. A capture keeps original project time, so automation and media offsets
are never silently rebased. Its marked range identifies the export interval.
"""
from __future__ import annotations
import copy, math
from dataclasses import fields
from sequencer_model import (Project, Layer, Clip, Asset, Effect, ProgrammableParameter,
    Keyframe, new_id, project_to_dict, project_from_dict, _encode, _fields, _parameter_from, _effect_from, Mask)

VOICES=('A','B')
STYLE_FIELDS=('name','opacity','mix','blend_mode','enabled','solo','effects','rack','mask','mixer_mode')

def new_instrument() -> Project:
    p=Project(name='Untitled Instrument',instrument_mode=True)
    p.layers=[Layer(new_id('voice'),name,generated=True,expanded=False,extra={'voice':name,'queue_policy':'repeat'}) for name in VOICES]
    p.conductor.max_layers=4
    p.extra.update(instrument_version=3,session_mode='perform',sound_events=[],music_queue_policy='repeat')
    # The crossfader is voice_mix; layer opacity remains independent and full-strength.
    p.voice_mix.value=.5
    p.voice_mixer_mode='crossfade'
    from sound_routes import migrate_route_semantics
    migrate_route_semantics(p)
    return p

def voice(p:Project,name:str) -> Layer:
    l=next((l for l in p.layers if l.extra.get('voice')==name),None)
    if l is None:raise ValueError(f'Voice {name} is not present in this project')
    return l

def assign_source(p:Project,name:str,asset_id:str,t:float=0.,*,performing=False,duration=None) -> Clip:
    l=voice(p,name);a=p.asset(asset_id)
    if a is None or a.kind=='audio':raise ValueError('Choose a visual source; use Sound for audio')
    if l.locked:raise ValueError('Unlock this voice before replacing its source')
    t=max(0.,float(t));duration=float(duration or max(1.,p.max_end()-t))
    if performing:
        future=[c for c in l.clips if c.end>t]
        if any(c.locked or c.timing_locked for c in future):raise ValueError('The current/future source is locked')
        for c in list(l.clips):
            if c.start>=t:l.clips.remove(c)
            elif c.end>t:c.duration=t-c.start
        ids={c.id for c in l.clips};l.transitions=[tr for tr in l.transitions if tr.end<=t and tr.from_clip in ids and tr.to_clip in ids]
    else:
        if any(c.locked for c in l.clips):raise ValueError('This voice contains locked occurrences')
        l.clips=[];l.transitions=[]
    c=Clip(new_id('clp'),asset_id,start=t,duration=max(1/p.fps,duration),manual=True,
           in_point=float(a.metadata.get('sequence_preferences',{}).get('source_in',0)),
           source_policy=a.metadata.get('sequence_preferences',{}).get('source_policy','loop'),fit='cover')
    pref=a.metadata.get('sequence_preferences',{})
    if 'source_out' in pref:c.extra['source_window']=[float(pref.get('source_in',0)),float(pref['source_out'])]
    l.clips.append(c);l.enabled=True;p.duration=max(p.duration,c.end);p.touch();return c

def style_dict(l:Layer) -> dict:
    d=_encode(l)
    return {k:d[k] for k in STYLE_FIELDS}

def style_from(raw:dict,l:Layer) -> Layer:
    # Reuse the canonical parser rather than let a second schema drift.
    d={'id':l.id,**copy.deepcopy(raw),'clips':[],'transitions':[]}
    return project_from_dict({'layers':[d]}).layers[0]

def style_at(l:Layer,t:float) -> Layer:
    for event in reversed(l.extra.get('treatment_history',[])):
        if event['start']<=t<event['end']:
            return style_from(event['style'],l)
    return l

def store_style(l:Layer,t:float,style:Layer):
    for event in reversed(l.extra.get('treatment_history',[])):
        if event['start']<=t<event['end']:
            event['style']=style_dict(style);return
    if style is not l:
        for name in STYLE_FIELDS:setattr(l,name,copy.deepcopy(getattr(style,name)))

def archive_styles(before:Project,after:Project,t:float):
    """Freeze previous treatment for already-played time, never reinterpret it.

Numerical performance gestures are stored as parameter keyframes. Structural edits
(rack replacement/reorder, toggles, driver mode changes) use these sparse style spans.
"""
    if t<=0:return
    by_id={l.id:l for l in before.layers}
    for l in after.layers:
        old=by_id.get(l.id)
        if old is None or style_dict(old)==style_dict(l):continue
        events=l.extra.setdefault('treatment_history',[])
        start=float(events[-1]['end']) if events else 0.
        if t>start+1e-6:events.append({'start':start,'end':t,'style':style_dict(old)})
    if _encode(before.master_rack)!=_encode(after.master_rack):
        prior={e.get('id') for e in before.extra.get('master_transitions',[])}
        for event in after.extra.get('master_transitions',[]):
            if event.get('id') in prior and event['start']<t<event['end']:
                # Retain the original denominator so a manual interruption cannot
                # accelerate/reinterpret the already performed part of a fade.
                event.setdefault('fade_end',event['end']);event['end']=t
        entries=after.extra.setdefault('master_history',[]);start=entries[-1]['end'] if entries else 0.
        if t>start+1e-6:entries.append({'start':start,'end':t,'rack':_encode(before.master_rack)})
    if (_encode(before.voice_mix),before.voice_blend,before.voice_mixer_mode)!=(_encode(after.voice_mix),after.voice_blend,after.voice_mixer_mode):
        entries=after.extra.setdefault('mixer_history',[]);start=entries[-1]['end'] if entries else 0.
        if t>start+1e-6:entries.append({'start':start,'end':t,'mix':_encode(before.voice_mix),'mode':before.voice_mixer_mode,'blend':before.voice_blend})

def walk_parameters(p:Project,include_history=True):
    from media_engine import _all_parameters
    yield p.voice_mix
    yield from _all_parameters(p)

def map_live_reaction(p:Project):
    """Bind every nested module and historical mapping to retained signals."""
    from sound_routes import external_reaction_active
    def mapped(source):
        if source=='reaction_mix':
            if p.extra.get('recorded_mix_analysis'):return 'recorded_mix'
            if external_reaction_active(p):raise ValueError('Mixed live reaction was not retained')
            return 'song'
        if source in ('microphone','mix','device'):
            if not p.recorded_analysis:raise ValueError('Live reaction is not retained. Record input reaction before capturing this interval.')
            return 'song_recorded' if source=='mix' else 'recorded'
        return source
    for param in walk_parameters(p):
        if param.mode=='react':param.source=mapped(param.source);param.extra.pop('recorded_take_id',None)
    def visit(raw):
        if isinstance(raw,dict):
            if raw.get('mode')=='react':raw['source']=mapped(raw.get('source','song'));raw.get('extra',{}).pop('recorded_take_id',None)
            for v in raw.values():visit(v)
        elif isinstance(raw,list):
            for v in raw:visit(v)
    for l in p.layers:
        visit(l.extra.get('treatment_history',[]))
        visit(l.extra.get('queue_history',[]))
        for fx in l.rack:visit(fx.extra)
        for c in l.clips:
            for fx in c.rack:visit(fx.extra)
    for fx in p.master_rack:visit(fx.extra)
    visit(p.extra.get('master_history',[]));visit(p.extra.get('master_transitions',[]));visit(p.extra.get('mixer_history',[]))

def capture_interval(p:Project,start:float,end:float) -> Project:
    if not all(math.isfinite(v) for v in (start,end)) or not 0<=start<end:raise ValueError('Choose a valid captured interval')
    q=copy.deepcopy(p)
    for l in q.layers:
        for c in l.clips:
            a=q.asset(c.asset_id)
            if c.start<end and c.end>start and a and a.kind=='camera':
                raise ValueError('Camera media is not retained. Arm input history or record a raw take before capture.')
    for l in q.layers:l.extra['treatment_history']=[e for e in l.extra.get('treatment_history',[]) if e['start']<end and e['end']>start]
    for key in ('master_history','master_transitions','mixer_history'):q.extra[key]=[e for e in q.extra.get(key,[]) if e['start']<end and e['end']>start]
    map_live_reaction(q)
    q.id=new_id('take');q.name=p.name+' · captured take';q.duration=max(end,.1)
    # Keep original times and source mappings; export only the marked interval.
    for l in q.layers:
        # Queue clips use local time. A later captured loop still needs its
        # original occurrences, as do frozen queues used by previous cycles.
        if l.extra.get('queue_policy')=='repeat' or l.extra.get('queue_history'):
            continue
        l.clips=[c for c in l.clips if c.start<end and c.end>start]
        ids={c.id for c in l.clips};l.transitions=[tr for tr in l.transitions if tr.end>start and tr.start<end and tr.from_clip in ids and tr.to_clip in ids]
    q.extra['capture_range']=[float(start),float(end)]
    q.extra['capture_origin']={'session_id':p.id,'time_basis':'original project seconds','editable':True}
    q.extra['session_mode']='review';return q

def mutate_instrument(p:Project,seed:int,*,scope='sequence',layer_id=None,channel=None,time_range=None):
    from conductor import generate
    if not p.instrument_mode:return generate(p,seed,scope=scope,layer_id=layer_id,channel=channel,time_range=time_range)
    chosen=[l for l in p.layers if (not layer_id or l.id==layer_id) and l.extra.get('voice')!='Camera']
    if scope in ('media','effects','motion','transitions'):
        for n,l in enumerate(chosen):generate(p,seed+n*7919,scope=scope,layer_id=l.id,time_range=time_range)
    else:
        for n,l in enumerate(chosen):
            role=l.extra.get('voice')
            if role=='B' and p.conductor.layering<=.01 and not l.clips:continue
            generate(p,seed+n*7919,scope='layer',layer_id=l.id,time_range=time_range)
    p.mutation_seed=seed;p.touch();return seed


def vary_rack(p:Project,seed:int,layer_id=None,*,start=0.,duration=3.):
    """Seeded parameter evolution, independent from clip selection and timing.

    Authored/held parameters stay protected. Generated interpolation begins from
    the evaluated value, retaining the past instead of jumping back to a base.
    """
    from conductor import stream,weighted_choice
    from effects_engine import make_effect,EFFECTS
    rng=stream(seed,'persistent-rack');start=max(0.,float(start));duration=max(.25,float(duration));amount=0
    for layer in p.layers:
        if layer.locked or (layer_id and layer.id!=layer_id):continue
        if not layer.rack:
            kind=weighted_choice(rng,p.conductor.effect_preferences,allowed=EFFECTS)
            if kind:layer.rack.append(make_effect(kind))
        for fx in layer.rack:
            if not fx.enabled or fx.extra.get('locked',False):continue
            for name,param in fx.params.items():
                if param.extra.get('conductor_locked'):continue
                if param.keyframes and not param.extra.get('conductor_generated'):continue
                current=param.animated_value(start) if param.keyframes else param.value
                span=(param.maximum-param.minimum)*p.conductor.intensity*.3
                destination=max(param.minimum,min(param.maximum,current+rng.uniform(-span,span)))
                param.keyframes=[k for k in param.keyframes if k.time<start]
                if not param.keyframes:param.add_keyframe(0.,current)
                param.add_keyframe(start,current);param.add_keyframe(start+duration,destination)
                mode=param.mode;param.interpolation='smooth';param.mode='animate'
                if mode=='react':param.mode='react';param.combine_animation=True
                param.extra['conductor_generated']=True;amount+=1
    p.touch();return amount

# Camera is optional and added lazily: loading an older three-voice session does
# not activate a device or alter its existing channels.
CAMERA_POSITIONS = ('above', 'between', 'below')

def attach_camera_layer(p: Project, asset_id: str, t: float = 0.) -> Layer:
    """Bind a prepared camera to its own layer, preserving every visual queue."""
    from queue_model import switch_source
    asset=p.asset(asset_id)
    if asset is None or asset.kind not in ('camera','screen','window'):raise ValueError('A ready visual source is required')
    if not math.isfinite(t) or t<0:raise ValueError('Invalid camera activation time')
    layer=next((l for l in p.layers if l.extra.get('voice')=='Camera'),None)
    if layer is not None and layer.locked:raise ValueError('Unlock the Camera layer before changing it')
    if layer is None:
        layer=Layer(new_id('camera'), 'Camera', generated=False, expanded=False,
                    extra={'voice':'Camera','camera_position':'below','camera_layer':True})
        p.layers.append(layer)
    switch_source(layer,'camera',t,camera_id=asset_id)
    layer.enabled=True;p.touch();return layer

def camera_placement_at(layer: Layer, t: float) -> str:
    events=layer.extra.get('camera_placement_history',[])
    return next((e['position'] for e in reversed(events) if e['start']<=t),
                layer.extra.get('camera_position','above') if not events else 'above')

def set_camera_placement(p: Project, position: str, t: float = 0.) -> None:
    """Record a z-order change at session time, including subsequent take replay."""
    if position not in CAMERA_POSITIONS:raise ValueError('Choose Above, Between A/B or Below')
    if not math.isfinite(t) or t<0:raise ValueError('Invalid camera placement time')
    layer=voice(p,'Camera')
    if layer.locked:raise ValueError('Unlock the Camera layer before moving it')
    history=layer.extra.setdefault('camera_placement_history',[])
    history[:]=[e for e in history if e['start']<t]
    history.append({'start':float(t),'position':position})
    layer.extra['camera_position']=position;p.touch()
