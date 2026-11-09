"""Read-only, stable temporal projections of the existing performance histories."""
from __future__ import annotations
import copy, hashlib, json
from sequencer_model import _encode,new_id

def treatment_spans(project,start,end):
    result=[]
    owners=[('Master',project.extra.get('master_history',[]),project.master_rack)]
    owners += [(l.extra.get('voice',l.name),l.extra.get('treatment_history',[]),l.rack) for l in project.layers]
    for role,history,rack in owners:
        for event in history:
            if event['end']<=start or event['start']>=end:continue
            raw=copy.deepcopy(event.get('style',{'rack':event.get('rack',[])}))
            signature=hashlib.sha256(json.dumps([role,event['start'],event['end'],raw],sort_keys=True).encode()).hexdigest()[:20]
            result.append(dict(id='history_'+signature,role=role,start=event['start'],end=event['end'],historical=True,style=raw,rack=raw.get('rack',[])))
        boundary=max([0.]+[float(e['end']) for e in history])
        if boundary<end:
            raw=_encode(rack)
            result.append(dict(id='current_'+role,role=role,start=boundary,end=end,historical=False,style={'rack':raw},rack=raw))
    return result

def record_decision(project,*,now,seed,scope,automatic):
    """Record only an accepted operation; never infer past events for old files."""
    event=dict(id=new_id('decision'),time=float(now),seed=int(seed),scope=scope,automatic=bool(automatic),policy=_encode(project.conductor))
    project.extra['conductor_decisions']=[*project.extra.get('conductor_decisions',[]),event][-128:]
    return event
