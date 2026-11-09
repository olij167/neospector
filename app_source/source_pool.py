"""Detached source pool resolution. Browsing/resolving never imports candidates.

Choices: {'mode': 'project'|'albums'|'all', 'albums': [{'id': str,
'revision': 'original'|'project:<id>', 'snapshot': optional album revision dict}]}
The optional snapshot pins an explicitly chosen working revision. Assets already
in this project always retain their project's processing. Missing sources remain
in the catalogue but are counted separately, never selected for generation.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
from sequencer_model import project_from_dict, _encode

LABELS={'This project':'project','Selected albums…':'albums','Selected albums':'albums','All imports':'all'}

def normalize_choice(choice):
    if isinstance(choice,str):choice={'mode':LABELS.get(choice,choice)}
    choice=copy.deepcopy(choice or {'mode':'project'})
    mode=LABELS.get(choice.get('mode'),choice.get('mode','project'))
    if mode not in ('project','albums','all'):raise ValueError('Choose This project, Selected albums or All imports.')
    albums=[]
    for entry in choice.get('albums',[]):
        entry={'id':entry} if isinstance(entry,str) else copy.deepcopy(entry)
        if not entry.get('id'):continue
        entry.setdefault('revision','original');albums.append(entry)
    return {'mode':mode,'albums':albums}

def source_pool_choice(project,kind):
    return normalize_choice(project.conductor.extra.get('source_pools',{}).get(kind))

def set_source_pool(project,kind,choice):
    if kind not in ('visuals','music'):raise ValueError('Pool kind must be visuals or music')
    value=normalize_choice(choice);project.conductor.extra.setdefault('source_pools',{})[kind]=value
    return copy.deepcopy(value)

def resolve_source_pool(project,choice,kind,catalog=None):
    """Return assets, ids, token, eligible/excluded/unavailable counts and reason.

    `kind` is visuals or music. Optional choice role filters visual eligibility.
    All returned Asset objects are detached. No project/catalogue mutation, probes,
    hashing of source files, decoding or analysis occurs here. Caller freezes the
    token for a job and checks again before acceptance. Call on pool/generation
    changes, not pointer motion; catalogue scopes perform one metadata read.
    """
    if kind not in ('visuals','music'):raise ValueError('Pool kind must be visuals or music')
    role=choice.get('role') if isinstance(choice,dict) else None
    selection=normalize_choice(choice);mode=selection['mode'];missing_revisions=[]
    if mode=='project':candidates=copy.deepcopy(project.assets)
    else:
        raw={a['id']:a for a in catalog.assets()} if catalog else {};chosen={}
        if mode=='all':chosen=raw
        else:
            for entry in selection['albums']:
                try:
                    revision=entry.get('snapshot') or (catalog.album_revision(entry['id'],entry['revision']) if catalog else None)
                    if revision is None:raise KeyError(entry['id'])
                    for aid in revision['ids']:
                        value=revision.get('assets',{}).get(aid,raw.get(aid))
                        if value:chosen.setdefault(aid,value)
                except KeyError:missing_revisions.append(entry['id'])
        candidates=project_from_dict({'assets':chosen}).assets
        for aid in candidates:
            if aid in project.assets:candidates[aid]=copy.deepcopy(project.assets[aid])
    hidden=set(project.extra.get('library_hidden',[]))|set(project.extra.get('library_removed',[]))
    eligible=[];excluded=0;unavailable=0;states=[]
    for aid,asset in sorted(candidates.items()):
        musical=(asset.kind=='audio' or bool(asset.metadata.get('has_audio'))) and asset.duration>0
        if (kind=='music' and not musical) or (kind=='visuals' and asset.kind not in ('image','video','colour','shape','text')):continue
        prefs=asset.metadata.get('sequence_preferences',{})
        disabled=(aid in hidden or not prefs.get('enabled',True) or float(prefs.get('weight',1))<=0
                  or (role and role not in prefs.get('roles',[role])))
        missing=asset.kind in ('audio','video','image') and not Path(asset.path).is_file()
        status='excluded' if disabled else 'unavailable' if missing else 'eligible'
        states.append((aid,status,_encode(asset)))
        if disabled:excluded+=1
        elif missing:unavailable+=1
        else:eligible.append(asset)
    token=hashlib.sha256(json.dumps([selection,kind,role,states,missing_revisions],sort_keys=True,default=str).encode()).hexdigest()
    reason='' if eligible else 'No eligible sources. Choose another pool or include available media.'
    if missing_revisions:reason='A selected album revision is unavailable. Choose its revision again.'
    return {'assets':eligible,'ids':[a.id for a in eligible],'token':token,'eligible':len(eligible),
            'excluded':excluded,'unavailable':unavailable+len(missing_revisions),'reason':reason,'choice':selection}
