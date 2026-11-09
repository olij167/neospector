"""Portable Conductor cue queue and sparse, replayable rack transitions.

Preparing a cue never changes the live rack. Taking it preserves Conductor
protected slots and writes one bounded transition event; no per-frame model or
widget mutation is needed. Module templates are snapshots, not live references.
"""
from __future__ import annotations
import copy, math, random
from sequencer_model import _encode, _effect_from, new_id
from module_engine import compile_rack, children
from rack_protection import conductor_protected

MAX_ITEMS=64
DEFAULTS=dict(version=1,items=[],active_id=None,active_name='Manual rack',next_id=None,
              due_at=None,hold=12.,fade=2.,loop=True,continuous=False,
              count=2,pool_mode='all',pool_ids=[],reaction='full',reaction_source='reaction_mix')
REACTIONS=('none','full','bass','mid','high','onset')
SOURCES=('reaction_mix','song','microphone','device')
CONFIG=('hold','fade','loop','continuous','count','pool_mode','pool_ids','reaction','reaction_source')


def state(project):
    raw=project.conductor.extra.get('composition_queue')
    return raw if isinstance(raw,dict) else copy.deepcopy(DEFAULTS)


def _prepared(project):
    s={**copy.deepcopy(DEFAULTS),**copy.deepcopy(state(project))}
    if s.get('version')!=1:raise ValueError('This composition queue version is not supported; keep the original project.')
    if not isinstance(s['items'],list) or len(s['items'])>MAX_ITEMS:raise ValueError('Composition queue exceeds its 64-cue limit.')
    return s


def _number(value,lo,hi,label,integer=False):
    try:value=float(value)
    except (ValueError,TypeError):raise ValueError(f'{label}: choose {lo}–{hi}.') from None
    if not math.isfinite(value) or not lo<=value<=hi or (integer and not value.is_integer()):raise ValueError(f'{label}: choose {lo}–{hi}'+(' whole numbers.' if integer else '.'))
    return int(value) if integer else value


def configure(project,changes):
    s=_prepared(project)
    if any(k not in CONFIG for k in changes):raise ValueError('Unknown composition queue setting.')
    s.update(copy.deepcopy(changes))
    s['hold']=_number(s['hold'],.25,3600,'Hold');s['fade']=_number(s['fade'],0,60,'Transition');s['count']=_number(s['count'],1,12,'Module count',True)
    if s['reaction'] not in REACTIONS or s['reaction_source'] not in SOURCES:raise ValueError('Choose a supported reaction and audio source.')
    if s['pool_mode'] not in ('all','selected'):raise ValueError('Choose All or Selected modules.')
    if not isinstance(s['pool_ids'],list) or len(s['pool_ids'])>1000 or any(not isinstance(i,str) for i in s['pool_ids']):raise ValueError('Choose a valid module pool.')
    s['pool_ids']=list(dict.fromkeys(s['pool_ids']))
    for k in ('loop','continuous'):
        if not isinstance(s[k],bool):raise ValueError('Choose On or Off for '+k)
    project.conductor.extra['composition_queue']=s
    return s


def append_snapshot(project,rack=None,*,name=None,hold=None,fade=None,generated=False):
    s=_prepared(project)
    if len(s['items'])>=MAX_ITEMS:raise ValueError('The composition queue is full (64 cues). Remove a cue before adding another.')
    hold=_number(s['hold'] if hold is None else hold,.25,3600,'Hold');fade=_number(s['fade'] if fade is None else fade,0,60,'Transition')
    name=str(name or ('Generated' if generated else 'Captured rack')).strip()
    if not name or len(name)>120:raise ValueError('Use a cue name of 1–120 characters.')
    rack=copy.deepcopy(project.master_rack if rack is None else rack);compile_rack(rack)
    item=dict(id=new_id('cue'),name=name,rack=_encode(rack),hold=hold,fade=fade,generated=bool(generated))
    s['items'].append(item)
    if not s['next_id']:s['next_id']=item['id']
    project.conductor.extra['composition_queue']=s
    return item


def append_generated(project,rows,*,seed):
    from module_library import effect_from_row
    from omne_randomise import vary_rack
    s=_prepared(project);selected=set(s['pool_ids'])
    candidates=[r for r in rows if s['pool_mode']=='all' or r['id'] in selected]
    if s['pool_mode']=='all':candidates=[r for r in candidates if r['type']=='Group'] or candidates
    if not candidates:raise ValueError('No selected modules are available. Choose modules in Library or select All.')
    rng=random.Random(int(seed));rack=[];names=[]
    for i in range(int(s['count'])):
        row=rng.choice(candidates);fx=effect_from_row(row)
        vary_rack([fx],seed=int(seed)+i*7919,variation=project.conductor.intensity)
        def apply_reaction(effect):
            for param in effect.params.values():
                if s['reaction']=='none':param.mode='static';param.react_amount=0.
                elif param.mode=='react':
                    param.react_band=s['reaction'];param.source=s['reaction_source'];param.react_amount*=project.conductor.reaction
            if effect.kind=='module':
                nested=children(effect)
                for child in nested:apply_reaction(child)
                effect.extra['children']=_encode(nested)
        apply_reaction(fx)
        rack.append(fx);names.append(row['name'])
    return append_snapshot(project,rack,name=(' + '.join(names))[:120],generated=True)


def next_entry(project):
    s=state(project);items=s.get('items',[])
    if not items:return None
    found=next((e for e in items if e['id']==s.get('next_id')),None)
    if found:return found
    return items[0] if s.get('loop',True) else None


def move(project,entry_id,offset):
    s=_prepared(project);items=s['items'];i=next((i for i,e in enumerate(items) if e['id']==entry_id),None)
    if i is None:raise ValueError('The selected composition is no longer in the queue.')
    # Before the first take, queue order is the scheduling order.
    j=max(0,min(len(items)-1,i+int(offset)));items.insert(j,items.pop(i))
    if not s['active_id']:s['next_id']=items[0]['id']
    project.conductor.extra['composition_queue']=s


def remove(project,entry_id):
    s=_prepared(project);items=s['items'];i=next((i for i,e in enumerate(items) if e['id']==entry_id),None)
    if i is None:return
    items.pop(i)
    if s['next_id']==entry_id:s['next_id']=items[i]['id'] if i<len(items) else None
    project.conductor.extra['composition_queue']=s


def update_entry(project,entry_id,*,name=None,hold=None,fade=None):
    s=_prepared(project);item=next((e for e in s['items'] if e['id']==entry_id),None)
    if item is None:raise ValueError('The selected composition is no longer in the queue.')
    if name is not None:
        name=str(name).strip()
        if not name or len(name)>120:raise ValueError('Use a cue name of 1–120 characters.')
        item['name']=name
    if hold is not None:
        previous=item['hold'];item['hold']=_number(hold,.25,3600,'Hold')
        if entry_id==s.get('active_id') and s.get('due_at') is not None:s['due_at']+=item['hold']-previous
    if fade is not None:item['fade']=_number(fade,0,60,'Transition')
    project.conductor.extra['composition_queue']=s


def protected_rack(current,proposal):
    fixed={i:copy.deepcopy(f) for i,f in enumerate(current) if conductor_protected(f)}
    ids={f.id for f in fixed.values()};pool=[copy.deepcopy(f) for f in proposal if f.id not in ids]
    total=max(len(pool)+len(fixed),max(fixed,default=-1)+1);result=[];cursor=iter(pool)
    for i in range(total):
        if i in fixed:result.append(fixed[i])
        else:
            candidate=next(cursor,None)
            if candidate is None:candidate=copy.deepcopy(current[i])
            result.append(candidate)
    compile_rack(result);return result


def active_transition(project,now):
    return next((e for e in reversed(project.extra.get('master_transitions',[])) if e['start']<=now<e['end']),None)


def take(project,entry_id=None,*,now,immediate=False):
    from instrument_model import archive_styles
    now=_number(now,0,1e12,'Programme time')
    if active_transition(project,now):raise ValueError('Finish the current transition before taking the next composition.')
    s=_prepared(project);item=next((e for e in s['items'] if e['id']==entry_id),None) if entry_id else next_entry(project)
    if not item:raise ValueError('Add or generate a composition first.')
    fade=0. if immediate else _number(item['fade'],0,60,'Transition');hold=_number(item['hold'],.25,3600,'Hold')
    proposal=[_effect_from(f) for f in copy.deepcopy(item['rack'])];rack=protected_rack(project.master_rack,proposal)
    before=copy.deepcopy(project);project.master_rack=rack;archive_styles(before,project,now)
    if fade>0 and _encode(before.master_rack)!=_encode(rack):
        project.extra.setdefault('master_transitions',[]).append(dict(id=new_id('rackfade'),start=now,end=now+fade,**{'from':_encode(before.master_rack),'to':_encode(rack)}))
    index=next(i for i,e in enumerate(s['items']) if e['id']==item['id'])
    s.update(active_id=item['id'],active_name=item['name'],next_id=s['items'][index+1]['id'] if index+1<len(s['items']) else None,due_at=now+fade+hold)
    project.conductor.extra['composition_queue']=s
    return item


def replenish(project,rows,*,seed):
    """Continuous mode retains authored cues and the active generated cue.

    Old generated cue *templates* can be retired; their performed output remains
    in immutable master history/transition events. Never discard authored cues.
    """
    s=_prepared(project)
    if len(s['items'])>=MAX_ITEMS:
        retire=next((e for e in s['items'] if e.get('generated') and e['id'] not in (s['active_id'],s['next_id'])),None)
        if retire:s['items'].remove(retire)
        else:raise ValueError('The composition queue is full of retained cues. Remove one before continuing generation.')
    # Generate in an isolated project so failure cannot retire a cue.
    trial=copy.deepcopy(project);trial.conductor.extra['composition_queue']=s
    item=append_generated(trial,rows,seed=seed);project.conductor.extra['composition_queue']=trial.conductor.extra['composition_queue']
    return item
