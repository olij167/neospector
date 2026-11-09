"""A bounded, declarative module recipe importer; never evaluates user code.

Format neospector/module-recipe v1. Recipe operations are registry identifiers
plus finite numeric parameters. This can create editable groups, not Python
plugins, filesystem/network access, shaders or arbitrary expression evaluation.
"""
from __future__ import annotations
import json,math
from pathlib import Path
from effects_engine import EFFECTS,make_effect
from module_engine import group_effects,expose_group_front,compile_rack

FORMAT='neospector/module-recipe'
MAX_BYTES=65536
ALLOWED_FAMILIES={'Transition','Colour','Texture','Light','Spatial','Adjust','Time','Custom'}

def parse_recipe(data):
    if not isinstance(data,dict) or set(data)-{'format','version','name','family','tags','operations'}:
        raise ValueError('Unsupported recipe fields')
    if data.get('format')!=FORMAT or type(data.get('version')) is not int or data['version']!=1:
        raise ValueError('Unsupported Neospector recipe format')
    name=data.get('name')
    if not isinstance(name,str) or not 1<=len(name.strip())<=80:raise ValueError('Recipe name must be 1–80 characters')
    family=data.get('family','Custom')
    if family not in ALLOWED_FAMILIES:raise ValueError('Unknown module family')
    tags=data.get('tags',[])
    if not isinstance(tags,list) or len(tags)>8 or any(not isinstance(t,str) or not 1<=len(t.strip())<=24 for t in tags):
        raise ValueError('Use up to eight short tags')
    items=data.get('operations')
    if not isinstance(items,list) or not 1<=len(items)<=16:raise ValueError('Recipe must have 1–16 operations')
    operations=[]
    for item in items:
        if not isinstance(item,dict) or set(item)-{'kind','params'}:raise ValueError('Recipe operation contains unsupported fields')
        kind=item.get('kind');params=item.get('params',{})
        if not isinstance(kind,str) or kind not in EFFECTS:raise ValueError('Unknown required module: '+str(kind))
        if kind in ('echo','frame_blend') and family=='Transition':raise ValueError('Transition cannot use frame history')
        if kind.startswith('transition_') and family!='Transition':raise ValueError('Transition geometry belongs to the Transition family')
        if not isinstance(params,dict) or set(params)-set(EFFECTS[kind].params):raise ValueError('Unknown module parameter')
        for param,value in params.items():
            if type(value) not in (float,int) or not math.isfinite(value):raise ValueError('Module parameters must be finite numbers')
            _,lower,upper,_=EFFECTS[kind].params[param]
            if not lower<=value<=upper:raise ValueError(f'{kind}.{param} exceeds its allowed range')
        operations.append(make_effect(kind,params))
    group=group_effects(operations,{fx.id for fx in operations},name.strip())
    group.extra.update(family=family,tags=[t.strip() for t in tags],imported_recipe=True)
    expose_group_front(group)
    compile_rack([group])
    if family=='Transition':
        from ux16_transitions import validate_transition_rack
        validate_transition_rack([group])
    return group

def read_recipe(path):
    path=Path(path)
    if path.stat().st_size>MAX_BYTES:raise ValueError('Recipe file exceeds 64 KiB')
    return parse_recipe(json.loads(path.read_text(encoding='utf-8')))
