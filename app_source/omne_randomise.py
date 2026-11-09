"""Bounded, portable randomisation settings. Pure operations never start devices."""
from __future__ import annotations
import copy
import math
import random
from module_engine import randomise_rack, compile_rack, children
from neospector_catalog import FACTORY_GROUPS, build_group

DEFAULTS = dict(queue_mode='items', queue_count=8, queue_seconds=60.,
                module_count=1, variation=1.0, mutation_variation=.55, conductor_variation=.2)

def normalise_settings(data=None):
    result = {**DEFAULTS, **(data or {})}
    if result['queue_mode'] not in ('items','seconds','song'):
        raise ValueError('Queue length must be Items, Seconds or Song.')
    for key,lo,hi,integer in (('queue_count',1,128,True),('queue_seconds',1,3600,False),
                             ('module_count',1,12,True),('variation',0,1,False),
                             ('conductor_variation',0,1,False),('mutation_variation',0,1,False)):
        try: value=float(result[key])
        except (ValueError,TypeError): raise ValueError(f'{key.replace("_"," ").title()} must be a number.') from None
        if not math.isfinite(value) or not lo<=value<=hi or (integer and not value.is_integer()):
            raise ValueError(f'{key.replace("_"," ").title()}: choose {lo}–{hi}'+(' (whole numbers).' if integer else '.'))
        result[key]=int(value) if integer else value
    return result

from rack_protection import composition_locked as protected, conductor_protected

def _interpolate(before, after, amount):
    """Blend a sampled valid parameter with its baseline, retaining authored motion."""
    for old,new in zip(before,after):
        if protected(old):continue
        for key,p in old.params.items():
            q=new.params.get(key)
            if q is None:continue
            p.value=max(p.minimum,min(p.maximum,p.value+(q.value-p.value)*amount))
            p.react_amount += (q.react_amount-p.react_amount)*amount
            p.attack += (q.attack-p.attack)*amount;p.release += (q.release-p.release)*amount;p.threshold += (q.threshold-p.threshold)*amount
            if amount>0 and not p.keyframes:
                p.mode=q.mode;p.source=q.source;p.react_band=q.react_band
                p.extra.update(q.extra)
        # Factory groups expose macros; their original children remain portable.

def vary_rack(rack, *, seed, variation, selected=None):
    amount=normalise_settings({'variation':variation})['variation']
    if not amount:return 0
    candidate=copy.deepcopy(rack)
    randomise_rack(candidate,seed,source='reaction_mix',selected=selected,rebuild=False,purpose='manual')
    eligible=[i for i,f in enumerate(rack) if not protected(f) and (selected is None or f.id in selected)]
    for i in eligible:_interpolate([rack[i]],[candidate[i]],amount)
    compile_rack(rack)
    return len(eligible)

def _rack_identity(rack,protect=protected):
    """Visible chain identity used only to prevent a no-op Randomise."""
    return tuple(f.extra.get('factory_group') or f.extra.get('name') or f.kind for f in rack if not protect(f))

def make_rack(rack, *, seed, count, variation, purpose='composition'):
    options=normalise_settings({'module_count':count,'variation':variation})
    protect=conductor_protected if purpose=='conductor' else protected
    protected_slots=[(i,copy.deepcopy(f)) for i,f in enumerate(rack) if protect(f)]
    # Lock means chain position as well as value protection. A requested module
    # count is a target, never permission to collapse protected slots together.
    if rack and len(protected_slots)==len(rack):return [copy.deepcopy(f) for f in rack]
    highest=max((i for i,_ in protected_slots),default=-1)
    total=max(options['module_count'],highest+1,len(protected_slots))
    generated_count=max(0,total-len(protected_slots));before=_rack_identity(rack,protect)
    chosen=None
    # Sequential deterministic seeds can legitimately start with the same shuffled
    # factory group. Randomise must still look like Randomise, so deterministically
    # probe alternate streams until the unlocked visible chain differs.
    attempts=max(2,min(len(FACTORY_GROUPS),12))
    for attempt in range(attempts):
        trial=[];names=list(FACTORY_GROUPS)
        # With one requested module, Randomise is an explicit request for a
        # different instrument. Exclude the current unlocked factory identity
        # outright; larger racks may legitimately retain some modules while the
        # overall chain changes.
        if total==1 and len(before)==1 and before[0] in names:names.remove(before[0])
        random.Random(seed+attempt*104729).shuffle(names)
        for i in range(generated_count):
            fx=build_group(names[i%len(names)])
            vary_rack([fx],seed=seed+101+attempt*1543+i*7919,variation=options['variation'])
            trial.append(fx)
        chosen=trial
        identity=tuple(f.extra.get('factory_group') or f.kind for f in trial)
        if not before or identity!=before:break
    generated=iter(chosen or [])
    fixed={i:f for i,f in protected_slots};result=[]
    for i in range(total):result.append(fixed[i] if i in fixed else next(generated))
    compile_rack(result)
    return result

def vary_conductor(recipe, *, seed, variation):
    amount=normalise_settings({'conductor_variation':variation})['conductor_variation']
    rng=random.Random(seed)
    for key in ('intensity','reaction','layering','transition_usage','variation'):
        value=getattr(recipe,key)
        setattr(recipe,key,max(0.,min(1.,value+rng.uniform(-amount,amount))))
    # Power, target flags, seed, timing and explicit links are not collateral edits.
    return recipe
