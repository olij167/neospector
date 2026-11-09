"""Seeded, scope-aware generation. Recipes never mutate existing edits implicitly."""
from __future__ import annotations
import copy
import hashlib
import random
import math
from sequencer_model import Clip, Effect, Layer, ProgrammableParameter, Project, Transition, clamp, new_id

PREFERENCE_WEIGHTS={'prefer':4.,'allow':1.,'avoid':.15,'exclude':0.}
TRANSITIONS=('dissolve','fade_colour','wipe_left','wipe_right','wipe_up','wipe_down','iris_open','iris_close','slide_left','slide_right','pixel_dissolve')
SCOPES=('sequence','range','layer','channel','media','transitions','motion','effects')


def stream(seed:int,name:str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256(f'{seed}:{name}'.encode()).digest()[:8],'big'))


def weighted_choice(rng,preferences,allowed=None,default=None):
    choices=[(k,PREFERENCE_WEIGHTS.get(v,1)) for k,v in preferences.items() if v!='exclude' and (allowed is None or k in allowed)]
    choices=[(k,w) for k,w in choices if w>0]
    if not choices:return default
    return rng.choices([k for k,w in choices],[w for k,w in choices],k=1)[0]


def protected(clip:Clip,layer:Layer,timing=True) -> bool:
    return layer.locked or clip.locked or clip.manual or clip.extra.get('playable_pin',False) or (timing and clip.timing_locked)


def gap_ranges(start,end,clips):
    cursor=start
    for a,b in sorted((max(start,c.start),min(end,c.end)) for c in clips if c.end>start and c.start<end):
        if a>cursor+1e-5:yield cursor,a
        cursor=max(cursor,b)
    if cursor<end-1e-5:yield cursor,end


def _chosen_assets(project,role=None):
    assets=[a for a in project.assets.values() if a.kind in ({'video','image','colour','shape','text','camera'} if project.instrument_mode else {'video','image'}) and a.metadata.get('sequence_preferences',{}).get('enabled',True) and a.id not in project.extra.get('library_hidden',[]) and a.id not in project.extra.get('library_removed',[])]
    # Stable source/name order, not random UUID or dictionary iteration order.
    if role:assets=[a for a in assets if role in a.metadata.get('sequence_preferences',{}).get('roles',['A','B','C','D'])]
    pool=project.conductor.extra.get('pool_ids')
    if pool is not None:assets=[a for a in assets if a.id in pool]
    return sorted(assets,key=lambda a:(a.name.casefold(),a.path))


def _select_asset(rng,assets,recent,gap):
    available=[a for a in assets if a.id not in recent[-gap:]] if gap else assets
    if not available:available=[a for a in assets if not recent or a.id!=recent[-1]] or assets
    weights=[max(0.,min(1000.,float(a.metadata.get('sequence_preferences',{}).get('weight',1)))) for a in available]
    if not any(weights):raise ValueError('All eligible media have zero probability; raise a source weight')
    chosen=rng.choices(available,weights=weights,k=1)[0];recent.append(chosen.id);return chosen


def _style_clip(project,clip,asset,rng,scope='all'):
    r=project.conductor
    prefs=asset.metadata.get('sequence_preferences',{})
    intensity=clamp(prefs.get('intensity',r.intensity),0,1)
    effect_preferences={**r.effect_preferences,**prefs.get('effect_preferences',{})}
    reaction_preferences={**r.reaction_preferences,**prefs.get('reaction_preferences',{})}
    if scope in {'all','motion'}:
        clip.scale.value=1+(.02+rng.random()*.08)*intensity
        for name in ('x','y'):getattr(clip,name).value=0
        for name in ('scale','x','y'):getattr(clip,name).mode='static'
        reaction=weighted_choice(rng,reaction_preferences,allowed={'scale','x','y','saturation','brightness'})
        if reaction in {'scale','x','y'} and r.reaction>0:
            p=getattr(clip,reaction);p.mode='react';p.source='reaction_mix';p.react_band='full';p.react_amount=max(.55,r.reaction);p.attack=.025;p.release=.16;p.threshold=.01;p.extra['react_full_range']=True
    if scope in {'all','effects'}:
        clip.rack=[]
        effect=weighted_choice(rng,effect_preferences)
        if intensity>0 and effect:
            if effect in {'contrast','saturation'}:
                value=1+intensity*(.1+rng.random()*.3)
                clip.rack=[Effect(new_id('fx'),effect,params={'amount':ProgrammableParameter(value,0,3)})]
            else:
                clip.rack=[Effect(new_id('fx'),effect,params={'amount':ProgrammableParameter(intensity*.22,0,1)})]
        reaction=weighted_choice(rng,reaction_preferences,allowed={'saturation','brightness'})
        if reaction and r.reaction>0:
            base=1. if reaction=='saturation' else 0.
            p=ProgrammableParameter(base,0 if reaction=='saturation' else -1,3 if reaction=='saturation' else 1,mode='react',source='reaction_mix',react_band='full',react_amount=max(.55,r.reaction),attack=.025,release=.16,threshold=.01,extra={'react_full_range':True})
            clip.rack.append(Effect(new_id('fx'),reaction,params={'amount':p}))

    if scope in {'all','effects'}:
        for i,fx in enumerate(clip.rack):fx.extra['seed']=f'{project.mutation_seed}:{asset.name}:{clip.start:.6f}:{i}'

def generate(project:Project,seed:int,*,scope:str='sequence',layer_id:str|None=None,channel:str|None=None,time_range:tuple[float,float]|None=None,max_new_clips:int|None=None) -> int:
    if max_new_clips is not None and (not isinstance(max_new_clips,int) or not 1<=max_new_clips<=128):raise ValueError('Choose 1–128 new queue items')
    if scope not in SCOPES:raise ValueError(f'Unknown mutation scope: {scope}')
    role=next((l.extra.get('voice') for l in project.layers if l.id==layer_id),None) if project.instrument_mode else None
    assets=_chosen_assets(project,role)
    if not assets:raise ValueError('Add a video or image to the media pool before Mutate')
    r=project.conductor.normalized();project.mutation_seed=int(seed)
    timing=stream(seed,'timing');media=stream(seed,'media');styling=stream(seed,'style');trans=stream(seed,'transitions')
    asset_by_id={a.id:a for a in assets}
    start,end=(0.,project.duration) if time_range is None else (max(0.,time_range[0]),min(project.max_end(),time_range[1]))
    if end<=start:raise ValueError('Select a non-empty time range')
    if scope=='range' and time_range is None:raise ValueError('Set range In and Out before mutating a range')
    if scope in {'layer','channel'} and not layer_id:raise ValueError('Choose a layer for this scope')
    if scope=='channel' and channel not in {'A','B'}:raise ValueError('Choose A or B for channel mutation')
    candidates=[l for l in project.layers if not layer_id or l.id==layer_id]
    if layer_id and not candidates:raise ValueError('The selected layer no longer exists')
    affected=[]
    if scope in {'media','effects','motion','transitions'}:
        count=0;recent=[]
        for l in candidates:
            if l.locked:continue
            if scope=='transitions':
                for tr in l.transitions:
                    a=next((c for c in l.clips if c.id==tr.from_clip),None);b=next((c for c in l.clips if c.id==tr.to_clip),None)
                    if tr.locked or tr.manual or not a or not b or protected(a,l) or protected(b,l):continue
                    if tr.start<start or tr.end>end:continue
                    kind=weighted_choice(trans,r.transition_preferences,TRANSITIONS)
                    if kind:tr.kind=kind;tr.extra['seed']=f'{seed}:{tr.start:.6f}:{kind}';count+=1
                continue
            for c in l.clips:
                if protected(c,l,timing=False) or c.start<start or c.end>end or (channel and c.channel!=channel):continue
                asset=project.asset(c.asset_id)
                if not asset or asset.kind not in {'video','image'}:continue
                if scope=='media':
                    asset=_select_asset(media,assets,recent,r.repeat_gap);c.asset_id=asset.id
                    pref=asset.metadata.get('sequence_preferences',{});lo=float(pref.get('source_in',0));hi=float(pref.get('source_out',asset.duration));c.in_point=max(lo,min(c.in_point,max(lo,hi-c.duration*c.playback_rate)))
                    if hi>lo:c.extra['source_window']=[lo,hi]
                    else:c.extra.pop('source_window',None)
                else:_style_clip(project,c,asset,styling,scope)
                count+=1
        project.extra['last_mutation']={'scope':scope,'seed':seed,'affected':count}
        project.touch();return seed

    # Reuse the primary generated row; never delete a row containing protected material.
    if scope in {'layer','channel','range'}:
        target=next((l for l in candidates if l.id==layer_id),None) if layer_id else next((l for l in candidates if l.generated),None)
    else:target=next((l for l in candidates if l.generated),None)
    if target is None:target=next((l for l in candidates if not l.clips and not l.locked),None)
    if target is not None and target.locked:
        project.extra['last_mutation']={'scope':scope,'seed':seed,'affected':0};return seed
    if target is None:
        target=Layer(new_id('lyr'),'Directed Sequence',generated=True);project.layers.insert(0,target)
    if not target.clips:target.generated=True
    # Explicit transition locks protect their endpoints against structural mutation.
    endpoint_locks={cid for tr in target.transitions if tr.locked or tr.manual for cid in (tr.from_clip,tr.to_clip)}
    preserve=[];removed=[]
    for c in target.clips:
        outside=c.start<start-1e-5 or c.end>end+1e-5
        wrong_channel=scope=='channel' and c.channel!=channel
        if protected(c,target) or c.id in endpoint_locks or outside or wrong_channel:preserve.append(c)
        else:removed.append(c)
    target.clips=preserve[:]
    keep_ids={c.id for c in preserve}
    target.transitions=[tr for tr in target.transitions if tr.from_clip in keep_ids and tr.to_clip in keep_ids]
    avoid=[c for c in preserve if scope!='channel' or c.channel==channel]
    recent=[];added=[]
    for gap_start,gap_end in gap_ranges(start,end,avoid):
        if max_new_clips is not None and len(added)>=max_new_clips:break
        cursor=gap_start;previous=None;ordinal=0
        while cursor<gap_end-.5/project.fps:
            if max_new_clips is not None and len(added)>=max_new_clips:break
            asset=_select_asset(media,assets,recent,r.repeat_gap)
            own=asset.metadata.get('sequence_preferences',{})
            lo=clamp(own.get('clip_min',r.clip_min),.1,120);hi=clamp(own.get('clip_max',r.clip_max),lo,240)
            dur=timing.uniform(lo,hi)
            if r.beat_sync:
                step=60/r.bpm
                absolute=round((cursor+dur-r.beat_offset)/step)*step+r.beat_offset
                dur=clamp(absolute-cursor,lo,hi)
            # Permit a short final shot only when the remaining time cannot fit the minimum.
            dur=min(dur,gap_end-cursor)
            if 0<gap_end-(cursor+dur)<lo and gap_end-cursor<=hi:dur=gap_end-cursor
            ch=channel if scope=='channel' else ('A' if ordinal%2==0 else 'B')
            c=Clip(new_id('clp'),asset.id,ch,round(cursor,6),round(dur,6),manual=False,source_policy='hold')
            source_start=max(0.,float(own.get('source_in',0)));source_end=min(asset.duration,float(own.get('source_out',asset.duration))) if asset.duration else 0.
            maximum=max(0.,source_end-source_start-dur)
            c.in_point=source_start+(media.random()*maximum*r.variation if maximum>0 else 0.)
            c.source_policy=own.get('source_policy','hold');c.fit=own.get('fit','cover');c.playback_rate=float(own.get('playback_rate',1.))
            if source_end>source_start:c.extra['source_window']=[source_start,source_end]
            _style_clip(project,c,asset,styling)
            if 'default_rack' in own:
                from media_settings_model import default_rack
                c.rack=default_rack(asset)
            target.clips.append(c);added.append(c)
            if previous is not None and c.start<previous.end-1e-4:
                prefs={**r.transition_preferences,**own.get('transition_preferences',{})}
                kind=weighted_choice(trans,prefs,TRANSITIONS,default='dissolve')
                tr=Transition(new_id('tr'),previous.id,c.id,kind,c.start,min(previous.end,c.end)-c.start)
                target.transitions.append(tr)
            remaining=gap_end-c.end
            if remaining<=.5/project.fps:break
            use=trans.random()<r.transition_usage and any(PREFERENCE_WEIGHTS.get(v,1)>0 for v in r.transition_preferences.values())
            overlap=min(trans.uniform(r.transition_min,r.transition_max),dur*.4,lo*.4) if use else 0.
            cursor=c.end-overlap;previous=c;ordinal+=1
            if ordinal>10000:raise ValueError('Generation exceeds 10,000 shots; increase clip duration')

    # Existing accent rows retain protected clips. The density control creates at most
    # max_layers rows, rather than accumulating rows on repeated mutations.
    if scope=='sequence' and layer_id is None:
        accent_layers=[l for l in project.layers if l is not target and l.generated and l.extra.get('conductor_role')=='accent']
        for l in accent_layers:
            if not l.locked:
                l.clips=[c for c in l.clips if protected(c,l)];l.transitions=[]
        desired=min(r.max_layers-1,math.ceil((r.max_layers-1)*r.layering) if r.layering>.05 else 0)
        for n in range(desired):
            l=accent_layers[n] if n<len(accent_layers) else Layer(new_id('lyr'),'Visual accents',generated=True,blend_mode='screen',extra={'conductor_role':'accent'})
            if l not in project.layers:project.layers.append(l)
            if l.locked:continue
            rng=stream(seed,f'accents:{n}');l.opacity.value=.15+r.layering*.35
            for g0,g1 in gap_ranges(0,project.duration,l.clips):
                cursor=g0+rng.uniform(2,6)
                while cursor<g1-.5:
                    asset=_select_asset(media,assets,recent,r.repeat_gap)
                    dur=min(rng.uniform(1.5,3.5),g1-cursor)
                    c=Clip(new_id('clp'),asset.id,'A',cursor,dur,fade_in=min(.35,dur*.25),fade_out=min(.35,dur*.25))
                    c.scale.value=.6+rng.random()*.35;c.x.value=rng.uniform(-.5,.5);c.y.value=rng.uniform(-.3,.3)
                    l.clips.append(c);cursor+=dur+max(1.,(1-r.layering)*16)
        project.layers=[l for l in project.layers if l is target or l.clips or l.locked or not l.generated]
    target.clips.sort(key=lambda c:(c.start,c.channel,c.id));target.generated=True
    for layer in project.layers:
        for tr in layer.transitions:tr.extra.setdefault('seed',f'{seed}:{tr.start:.6f}:{tr.kind}')
    project.extra['last_mutation']={'scope':scope,'seed':seed,'affected':len(added)}
    project.touch();return seed
