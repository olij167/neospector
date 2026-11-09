"""Declarative modules made from supported effect primitives, not executable code.

Grouping is an editing abstraction, compiled into the same ordered rack. Macros
have one explicit owner and linear mappings. Compiled bindings are runtime-only.
"""
from __future__ import annotations
import copy, math, random
from sequencer_model import Effect, ProgrammableParameter, Keyframe, new_id, _encode, _effect_from
from effects_engine import EFFECTS, make_effect

MAX_DEPTH=4
MAX_EFFECTS=64
MAX_HISTORY_WORK=128
NEUTRAL={'exposure':0,'temperature':0,'tint':0,'solarize':0,'edge':0,'emboss':0,'duotone':0,'brightness':0,'contrast':1,'gamma':1,'saturation':1,'hue':0,'sharpness':0,'blur':0,'invert':0,'posterize':0,'pixelate':0,'scanlines':0,'chroma_shift':0,'grain':0,'vignette':0,'mirror':0,'liquid':0,'jpeg_loss':0,'echo':0,'frame_blend':0}
USEFUL={'hue':(-100,120),'saturation':(.45,2.25),'contrast':(.75,1.7),'brightness':(-.14,.18),'gamma':(.65,1.55),'blur':(.45,5.0),'sharpness':(.2,1.0),'chroma_shift':(.12,.78),'scanlines':(.25,.9),'grain':(.045,.22),'liquid':(.14,.7),'echo':(.28,.75),'frame_blend':(.2,.78),'vignette':(.22,.78),'pixelate':(.08,.52),'jpeg_loss':(.28,.88),'posterize':(.28,.82),'mirror':(.32,.92),'invert':(.22,.9),'threshold':(.2,.8)}
CURATED=(('chroma_shift','saturation','scanlines'),('hue','contrast','vignette'),('pixelate','hue','grain'),('liquid','saturation'),('echo','chroma_shift'),('posterize','gamma','scanlines'))

class MacroParameter:
    def __init__(self,macro,low,high):self.macro=macro;self.low=float(low);self.high=float(high)
    def render_value(self,evaluator,t,signal_time=None):
        span=self.macro.maximum-self.macro.minimum;f=0 if span==0 else (evaluator.value(self.macro,t,signal_time)-self.macro.minimum)/span
        return self.low+(self.high-self.low)*max(0.,min(1.,f))
    def bake(self):
        p=self.macro.bake() if isinstance(self.macro,MacroParameter) else copy.deepcopy(self.macro);lo,hi=p.minimum,p.maximum;span=max(1e-12,hi-lo)
        def value(v):return self.low+(v-lo)/span*(self.high-self.low)
        p.value=value(p.value);p.keyframes=[Keyframe(k.time,value(k.value)) for k in p.keyframes]
        p.minimum=min(self.low,self.high);p.maximum=max(self.low,self.high)
        if self.high<self.low:p.react_amount=-p.react_amount
        return p
    def __getattr__(self,key):return getattr(object.__getattribute__(self,'macro'),key)
    def __deepcopy__(self,memo):return MacroParameter(copy.deepcopy(self.macro,memo),self.low,self.high)

def label(effect):return effect.extra.get('name','Custom module') if effect.kind=='module' else EFFECTS[effect.kind].label if effect.kind in EFFECTS else effect.kind

def children(effect):return [_effect_from(raw) for raw in effect.extra.get('children',[])]

def priority_keys(effect):
    """Declared face controls; group order is the saved promotion order."""
    if effect.kind=='module':return list(effect.params)[:2]
    return [key for key in EFFECTS[effect.kind].priority if key in effect.params]

def parameter_descriptions(effect):
    """The entire editable parameter inventory, independent of face selection."""
    spec=EFFECTS.get(effect.kind)
    result={}
    for key,param in effect.params.items():
        title=effect.extra.get('labels',{}).get(key) or (spec.label if key=='amount' and spec else key.replace('_',' ').title())
        unit=spec.params[key][3] if spec and key in spec.params else ''
        purpose=(spec.note if spec and spec.note else f'Changes {title.lower()} in the picture.')
        result[key]={'label':title,'unit':unit,'help':f'{purpose} Drag or type a value; Controls opens reaction and keys.'}
    return result

def internal_parameters(effect,path=()):
    """Describe every descendant with stable IDs and its actual editing owner."""
    for child in children(effect):
        child_path=(*path,child.id)
        for key,description in parameter_descriptions(child).items():
            owner_path,owner_key=internal_parameter_owner(effect,child_path[len(path):],key)
            yield child_path,key,description,((*path,*owner_path),owner_key)
        if child.kind=='module':
            yield from internal_parameters(child,child_path)

def internal_parameter_owner(group,path,key):
    """Resolve a leaf through every mapping, including an outer promotion."""
    if group.kind!='module' or not path:raise ValueError('Choose an internal parameter')
    subs=children(group);child=next((fx for fx in subs if fx.id==path[0]),None)
    if child is None:raise ValueError('Internal module no longer exists')
    if len(path)==1:
        if key not in child.params:raise ValueError('Internal parameter no longer exists')
        owner_path,owner_key=(),key
    else:owner_path,owner_key=internal_parameter_owner(child,path[1:],key)
    if not owner_path:
        for macro,targets in group.extra.get('mappings',{}).items():
            if any(t.get('effect')==path[0] and t.get('parameter')==owner_key for t in targets):
                return (),macro
    return (path[0],*owner_path),owner_key

def internal_parameter_target(group,path,key):
    owner_path,owner_key=internal_parameter_owner(group,tuple(path),key)
    current=group
    for child_id in owner_path:
        current=next(child for child in children(current) if child.id==child_id)
    return owner_path,owner_key,current.params[owner_key]

def edit_internal_parameter(group,path,key,changes):
    """Atomically persist through stored children, never a compiled wrapper."""
    from rack_editing import update_parameter
    if group.extra.get('locked'):raise ValueError('Unlock this group before editing it')
    trial=copy.deepcopy(group);node=trial
    for child_id in path:
        node=next((child for child in children(node) if child.id==child_id),None)
        if node is None:raise ValueError('Internal module no longer exists')
        if node.extra.get('locked'):raise ValueError('Unlock the internal module before editing it')
    owner_path,owner_key=internal_parameter_owner(trial,tuple(path),key)
    def apply(node,remaining):
        if not remaining:
            update_parameter(node.params[owner_key],changes);return
        subs=children(node);child=next((fx for fx in subs if fx.id==remaining[0]),None)
        if child is None or child.extra.get('locked'):raise ValueError('Unlock the internal module before editing it')
        apply(child,remaining[1:]);node.extra['children']=_encode(subs)
    apply(trial,owner_path);compile_rack([trial])
    # Preserve top-level parameter objects so retained face faders and the
    # attached companion keep their editing authority during a refresh.
    for name,value in trial.params.items():
        if name in group.params:group.params[name].__dict__.update(copy.deepcopy(value.__dict__))
        else:group.params[name]=value
    group.extra=trial.extra
    return owner_path,owner_key

def compile_rack(rack,depth=0):
    if depth>MAX_DEPTH:raise ValueError('Custom modules may nest at most four levels')
    if len(rack)>MAX_EFFECTS:raise ValueError('Module contains too many operations')
    out=[]
    for fx in rack:
        if fx.kind!='module':
            if fx.kind not in EFFECTS:raise ValueError('Unsupported required module: '+fx.kind)
            if fx.enabled:out.append(fx)
            continue
        if fx.extra.get('version',1)!=1:raise ValueError('Unsupported module version')
        subs=children(fx)
        # Validate even a bypassed module. Unknown required data is never hidden.
        mappings=fx.extra.get('mappings',{})
        for name,targets in mappings.items():
            if name not in fx.params:raise ValueError('Module macro is missing: '+name)
            for target in targets:
                child=next((e for e in subs if e.id==target.get('effect')),None)
                if child is None or target.get('parameter') not in child.params:raise ValueError('Module mapping has a missing target')
                low=float(target['low']);high=float(target['high'])
                if not all(math.isfinite(v) for v in (low,high)):raise ValueError('Module mapping must be finite')
                original=child.params[target['parameter']]
                if min(low,high)<original.minimum or max(low,high)>original.maximum:raise ValueError('Macro range exceeds its target bounds')
                child.params[target['parameter']]=MacroParameter(fx.params[name],low,high)
        flat=compile_rack(subs,depth+1)
        if fx.enabled:out.extend(flat)
    if len(out)>MAX_EFFECTS:raise ValueError('A rack can contain at most 64 primitive operations')
    history=1
    for fx in out:
        if fx.kind in ('echo','frame_blend'):
            taps=fx.params.get('taps');count=round(taps.maximum if taps and taps.mode!='static' else taps.value if taps else 1);history*=1+max(1,count)
    if history>MAX_HISTORY_WORK:raise ValueError('Temporal modules exceed the bounded history budget; reduce stacked trails')
    return out

def group_effects(rack,ids,name,promote=()):
    indices=[i for i,e in enumerate(rack) if e.id in ids]
    if not indices:raise ValueError('Select modules to group')
    if indices!=list(range(min(indices),max(indices)+1)):raise ValueError('Select adjacent modules; grouping must preserve processing order')
    if any(rack[i].extra.get('locked') for i in indices):raise ValueError('Unlock the selected modules first')
    name=str(name).strip()
    if not name or len(name)>80:raise ValueError('Give the module a name of up to 80 characters')
    selected=rack[min(indices):max(indices)+1];g=Effect(new_id('module'),'module',extra={'name':name,'version':1,'children':_encode(selected),'mappings':{},'backend':'cpu-reference','inputs':['image','reaction'],'neutral':'Reset constituent processing; sources are unchanged'})
    for n,(eid,param,title) in enumerate(promote):
        fx=next((e for e in selected if e.id==eid),None)
        if not fx or param not in fx.params:raise ValueError('Promoted parameter no longer exists')
        k='macro_'+str(n+1);p=copy.deepcopy(fx.params[param]);g.params[k]=p;g.extra.setdefault('labels',{})[k]=str(title)[:60];g.extra['mappings'][k]=[{'effect':eid,'parameter':param,'low':p.minimum,'high':p.maximum}]
    compile_rack([g]);rack[min(indices):max(indices)+1]=[g];return g



def expose_group_front(effect):
    """Put the group's entire immediate parameter inventory on its existing face.

    Existing promoted controls retain their IDs, motion and values; missing
    controls become mapped parameters on the group itself. This runs at group
    creation/insertion inside the owning project transaction, never at paint.
    """
    if effect.kind != 'module':return effect
    subs=children(effect)
    for child in subs:
        if child.kind == 'module':expose_group_front(child)
    if subs and any(c.kind=='module' for c in subs):
        effect.extra['children']=_encode(subs)
    mappings=effect.extra.setdefault('mappings',{})
    labels=effect.extra.setdefault('labels',{})
    existing={(target['effect'],target['parameter'])
              for targets in mappings.values() for target in targets}
    ordinal=1
    for child in subs:
        descriptions=parameter_descriptions(child)
        for key,param in child.params.items():
            if (child.id,key) in existing:continue
            while f'macro_{ordinal}' in effect.params:ordinal+=1
            name=f'macro_{ordinal}';ordinal+=1
            effect.params[name]=copy.deepcopy(param)
            labels[name]=(label(child)+' · '+descriptions[key]['label'])[:60]
            mappings[name]=[{'effect':child.id,'parameter':key,'low':param.minimum,'high':param.maximum}]
            existing.add((child.id,key))
    compile_rack([effect])
    return effect


def primary_parameter(effect):
    """Return the most useful front-panel control for one top-level module."""
    if not effect.params:return None
    key=next(iter(priority_keys(effect)),next(iter(effect.params)))
    title=effect.extra.get('labels',{}).get(key)
    if not title:
        title=label(effect) if key=='amount' else label(effect)+' · '+key.replace('_',' ').title()
    return key,str(title)

def automatic_promotions(effects):
    """Promote one useful control per selected member, in signal order."""
    out=[]
    for effect in effects:
        picked=primary_parameter(effect)
        if picked:out.append((effect.id,picked[0],picked[1]))
    return out

def automatic_group_name(effects):
    names=[label(e) for e in effects]
    if not names:return 'Module group'
    if len(names)<=3:text=' + '.join(names)
    else:text=' + '.join(names[:2])+f' + {len(names)-2} more'
    return text[:80].strip() or 'Module group'

def group_selected(rack,ids,name=None):
    """One-action grouping used by the rack surface."""
    ordered=[e for e in rack if e.id in set(ids)]
    group=group_effects(rack,[e.id for e in ordered],name or automatic_group_name(ordered),automatic_promotions(ordered))
    group.extra['generated_name']=not bool(name)
    group.extra.setdefault('family','Custom')
    return group

def reidentify(effect):
    """Clone a reusable module with fresh identities while preserving mappings."""
    cloned=copy.deepcopy(effect)
    if cloned.kind=='module':
        subs=children(cloned);mapping={} ; fresh=[]
        for child in subs:
            old=child.id;new_child=reidentify(child);mapping[old]=new_child.id;fresh.append(new_child)
        for targets in cloned.extra.get('mappings',{}).values():
            for target in targets:
                if target.get('effect') in mapping:target['effect']=mapping[target['effect']]
        cloned.extra['children']=_encode(fresh);cloned.id=new_id('module')
    else:cloned.id=new_id('fx')
    return cloned

def baked_group_children(effect):
    if effect.kind!='module':raise ValueError('Choose a composed module')
    subs=children(effect)
    for name,targets in effect.extra.get('mappings',{}).items():
        macro=effect.params.get(name)
        if macro is None:continue
        for target in targets:
            child=next((e for e in subs if e.id==target.get('effect')),None)
            if child is not None and target.get('parameter') in child.params:
                child.params[target['parameter']]=MacroParameter(macro,target['low'],target['high']).bake()
    return subs

def edit_group(effect,name,promote):
    """Rebuild one group's front panel without changing its signal-order children."""
    if effect.kind!='module':raise ValueError('Choose a composed module')
    if effect.extra.get('locked'):raise ValueError('Unlock this module first')
    subs=baked_group_children(effect);holder=list(subs)
    fresh=group_effects(holder,[e.id for e in subs],str(name).strip(),promote)
    # Promotion keys are public mapping IDs for a containing group. Keep each
    # existing key when its target survives a reorder or rename.
    existing={tuple((t.get('effect'),t.get('parameter')) for t in targets):key
              for key,targets in effect.extra.get('mappings',{}).items()}
    reserved=set(effect.params);used=set();next_index=1
    renamed_params={};renamed_labels={};renamed_mappings={}
    for temporary,targets in fresh.extra['mappings'].items():
        signature=tuple((t.get('effect'),t.get('parameter')) for t in targets)
        stable=existing.get(signature)
        if stable is None:
            while f'macro_{next_index}' in reserved or f'macro_{next_index}' in used:next_index+=1
            stable=f'macro_{next_index}';next_index+=1
        used.add(stable);renamed_params[stable]=fresh.params[temporary]
        renamed_labels[stable]=fresh.extra['labels'][temporary]
        renamed_mappings[stable]=targets
    fresh.params=renamed_params;fresh.extra['labels']=renamed_labels;fresh.extra['mappings']=renamed_mappings
    fresh.id=effect.id;fresh.enabled=effect.enabled
    preserved={k:v for k,v in effect.extra.items() if k not in ('name','children','mappings','labels','generated_name')}
    fresh.extra.update(preserved);fresh.extra['generated_name']=False
    effect.params=fresh.params;effect.extra=fresh.extra
    compile_rack([effect]);return effect

def ungroup(rack,eid):
    idx=next(i for i,e in enumerate(rack) if e.id==eid);g=rack[idx]
    if g.kind!='module':raise ValueError('Choose a composed module')
    if g.extra.get('locked'):raise ValueError('Unlock this module first')
    # Restore one level, preserving bypassed children and nested structure.
    # Promote bindings are baked into the child parameter, not evaluated at a
    # single instant, so the animation and audio mappings survive ungrouping.
    compile_rack([g])
    restored=children(g)
    for name,targets in g.extra.get('mappings',{}).items():
        for target in targets:
            child=next(e for e in restored if e.id==target['effect'])
            child.params[target['parameter']]=MacroParameter(g.params[name],target['low'],target['high']).bake()
    for child in restored:child.enabled=child.enabled and g.enabled
    rack[idx:idx+1]=restored;return restored

def reset_effect(effect):
    if effect.extra.get('locked'):raise ValueError('Unlock this module to reset it')
    if effect.kind=='module':
        subs=children(effect)
        for sub in subs:sub.extra.pop('locked',None);reset_effect(sub)
        effect.extra['children']=_encode(subs)
        # Keep the front-panel mappings when resetting a group. Clearing them
        # used to produce an inexplicably blank pedal after pressing Reset.
        for name,targets in effect.extra.get('mappings',{}).items():
            if not targets:continue
            item=targets[0]
            child=next((c for c in subs if c.id==item.get('effect')),None)
            if child is not None and item.get('parameter') in child.params:
                original=child.params[item['parameter']]
                if name in effect.params:
                    effect.params[name].__dict__.update(copy.deepcopy(original.__dict__))
                else:effect.params[name]=copy.deepcopy(original)
        effect.enabled=True;compile_rack([effect]);return
    if effect.kind not in EFFECTS:raise ValueError('Unsupported module')
    clean=make_effect(effect.kind);effect.params=clean.params;effect.enabled=True
    if effect.kind=='threshold':effect.enabled=False  # no neutral threshold transfer exists
    elif effect.kind=='tile':effect.params['columns'].value=effect.params['rows'].value=1
    elif effect.kind.startswith('transition_'):pass  # Reset restores authored field to its usable default
    elif 'amount' in effect.params:effect.params['amount'].value=NEUTRAL.get(effect.kind,0)

def randomise_rack(rack,seed,*,source='reaction_mix',selected=None,rebuild=False,purpose='conductor'):
    from rack_protection import composition_locked
    rng=random.Random(int(seed));eligible=[fx for fx in rack if (not selected or fx.id in selected) and not composition_locked(fx)]
    if not rack or rebuild:
        preserved=[fx for fx in rack if fx.extra.get('locked')]
        if selected and rack:raise ValueError('Rebuild applies to the rack, not selected parameters')
        rack[:]=preserved+[make_effect(k) for k in rng.choice(CURATED)];eligible=[e for e in rack if e not in preserved]
    changed=0
    for fx in eligible:
        for name,p in fx.params.items():
            if purpose!='manual' and p.extra.get('conductor_locked'):continue
            if purpose!='manual' and p.keyframes and not p.extra.get('conductor_generated'):continue
            if name=='amount':lo,hi=USEFUL.get(fx.kind,(p.minimum+(p.maximum-p.minimum)*.2,p.minimum+(p.maximum-p.minimum)*.65))
            elif name in ('taps','rows','columns'):lo,hi=1,3
            elif name=='delay':lo,hi=.05,.20
            elif name=='speed':lo,hi=.25,1.2
            else:lo,hi=p.minimum+(p.maximum-p.minimum)*.15,p.minimum+(p.maximum-p.minimum)*.6
            lo=max(lo,p.minimum);hi=min(hi,p.maximum);p.value=rng.uniform(lo,hi)
            if name in ('taps','rows','columns','spacing','waves'):p.value=round(p.value)
            # Only meaningful amount/macros react; topology and duration stay fixed.
            # Generated treatments default to the full routed-audio signal and a
            # deliberately broad excursion. This makes Randomise immediately read
            # as an audiovisual instrument; subtlety is an explicit fine-tuning act.
            if name=='amount' or fx.kind=='module':
                p.mode='react';p.source='reaction_mix';p.react_band='full';p.attack=.018;p.release=.14;p.threshold=.01
                # Keep the base visibly processed, but deliberately park it toward
                # one side of the useful range so audio has a large distance to
                # travel. The signal therefore reads immediately as motion rather
                # than a tiny tremble around an already-middle value.
                positive=rng.random()<.72
                width=max(0.,hi-lo)
                if positive:p.value=rng.uniform(lo,lo+width*.28)
                else:p.value=rng.uniform(hi-width*.28,hi)
                p.react_amount=1.0 if positive else -1.0
                p.extra['react_full_range']=True;p.extra['conductor_generated']=True
            changed+=1
    compile_rack(rack);return changed
