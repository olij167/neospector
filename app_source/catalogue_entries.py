"""One entry per operation or distinct factory recipe, with composition disclosed."""
import json
from effects_engine import EFFECTS
from neospector_catalog import FACTORY_GROUPS

def entries():
    out=[]
    for key,s in EFFECTS.items():
        out.append(dict(id='base:'+key,name=s.label,type='Base',family=s.group,key=key,
                        detail='Base operation · '+(s.note or s.label+' processing')))
    signatures={}
    for name,(family,recipe) in FACTORY_GROUPS.items():
        signature=json.dumps(recipe,sort_keys=True)
        if signature in signatures:
            signatures[signature]['aliases'].append(name);continue
        row=dict(id='group:'+name,name=name,type='Group',family=family,key=name,aliases=[],
                 detail=f'{len(recipe)}-effect recipe · '+ ' → '.join(EFFECTS[k].label for k,v in recipe))
        signatures[signature]=row;out.append(row)
    return out
