"""Additive source intentions; actual clips and soundtrack events stay canonical."""
from __future__ import annotations
import copy,hashlib,json,math
from pathlib import Path
from music_queue import items
from queue_model import mode_at

MODES={'auto','fixed','live','off'}

def load_intent(project):
    saved=project.extra.get('playable_intent')
    if saved:
        value=copy.deepcopy(saved)
    else:
        sounds=items(project)
        populated=[l.extra.get('voice') for l in project.layers if l.enabled and l.clips and l.extra.get('voice') in ('A','B','C','D')]
        value={'version':1,'music':{'mode':'fixed' if sounds else 'auto','asset_id':sounds[0]['asset_id'] if len(sounds)==1 else None,'album_id':None},
               'visuals':{'mode':'auto','album_id':None},'enabled_roles':populated or ['A'],
               'duration_mode':'song' if sounds else 'continuous','global_randomise_scope':'all'}
    for key in ('music','visuals'):
        value.setdefault(key,{'mode':'auto'})
        if value[key].get('mode') not in MODES:value[key]['mode']='off'
    value.setdefault('enabled_roles',['A']);value.setdefault('duration_mode','song');value.setdefault('global_randomise_scope','all')
    return value

def eligible_assets(project,choice,kind,role=None):
    pool=choice.get('pool_ids')
    if choice.get('mode')=='fixed' and choice.get('asset_id'):pool=[choice['asset_id']]
    aliases=project.extra.get('asset_aliases',{})
    if pool is not None:pool={aliases.get(i,i) for i in pool}
    result=[]
    for a in project.assets.values():
        if a.id in project.extra.get('library_hidden',[]) or a.id in project.extra.get('library_removed',[]):continue
        pref=a.metadata.get('sequence_preferences',{})
        if not pref.get('enabled',True) or float(pref.get('weight',1))<=0:continue
        if pool is not None and a.id not in pool:continue
        if kind=='music':
            if a.kind!='audio' and not a.metadata.get('has_audio'):continue
            if a.duration<=0:continue
        else:
            if a.kind not in ('video','image','colour','shape','text'):continue
            if role and role not in pref.get('roles',['A','B','C','D']):continue
        if a.kind in ('audio','video','image') and not Path(a.path).is_file():continue
        result.append(a)
    return sorted(result,key=lambda a:(a.name.casefold(),a.id))

def fingerprint(project,intent):
    pools={k:[(a.id,a.path,a.duration,a.metadata.get('sequence_preferences',{})) for a in eligible_assets(project,intent[k],k)] for k in ('music','visuals')}
    return hashlib.sha256(json.dumps(pools,sort_keys=True).encode()).hexdigest()

def prepare_source_pools(project,intent,catalog=None,*,only_role=None):
    """Resolve choices into a detached generation snapshot, never the open project."""
    from source_pool import source_pool_choice,resolve_source_pool
    prepared=copy.deepcopy(project);resolved_intent=copy.deepcopy(intent);tokens={}
    for kind in ('music','visuals'):
        mode=intent[kind].get('mode')
        scoped_fixed_music=kind=='music' and only_role=='Music' and mode=='fixed'
        if mode in ('off','live') or (mode=='fixed' and not scoped_fixed_music):continue
        choice=source_pool_choice(project,kind)
        result=resolve_source_pool(project,choice,kind,catalog=catalog)
        for asset in result['assets']:
            prepared.assets.setdefault(asset.id,copy.deepcopy(asset))
        ids=set(result['ids'])
        # Legacy album selection remains an explicit additional constraint.
        legacy=intent[kind].get('pool_ids')
        if legacy is not None:ids.intersection_update(legacy)
        if scoped_fixed_music:
            resolved_intent[kind]['mode']='auto'
            resolved_intent[kind].pop('asset_id',None)
        resolved_intent[kind]['pool_ids']=sorted(ids)
        tokens[kind]={'choice':choice,'token':result['token']}
    return prepared,resolved_intent,tokens

def used_candidate_assets(project):
    """Only occurrences bring a previously imported file into this project."""
    used={c.asset_id for l in project.layers for c in l.clips if c.asset_id}
    used.update(e['asset_id'] for e in items(project) if e.get('asset_id'))
    return used

def plan_randomise(project,intent,scope,*,now,playing,live_state):
    if scope not in ('queues','effects','all'):raise ValueError('Choose Queues, Effects or All')
    now=max(0.,float(now));sounds=items(project);roles=[];blocked=[];pools={}
    music_action='keep';music=intent['music'];visuals=intent['visuals']
    if scope!='effects':
        if music['mode'] in ('off','live'):music_action=music['mode']
        elif music['mode']=='auto':
            pool=eligible_assets(project,music,'music');pools['Music']=[a.id for a in pool]
            if pool:music_action='replace_future' if sounds else 'fill'
            elif not sounds:blocked.append('Music: choose a song, album or Live audio')
        if visuals['mode'] not in ('off','live'):
            for l in project.layers:
                role=l.extra.get('voice')
                if role not in intent.get('enabled_roles',[]) or not l.enabled or l.locked or l.extra.get('playable_empty') or mode_at(l,now)['mode']!='queue':continue
                pool=eligible_assets(project,visuals,'visuals',role)
                if pool:roles.append(role);pools[role]=[a.id for a in pool]
                elif not l.clips:blocked.append(role+': choose a visual album, Import or Camera')
    finish=max((e['start']+e['duration'] for e in sounds),default=0.)
    if intent.get('duration_mode')=='song' and finish>now:end=finish
    elif intent.get('duration_mode')=='duration':end=max(now+.1,float(intent.get('duration_seconds',30)))
    else:end=now+45.
    if not math.isfinite(end) or end-now>21600:raise ValueError('Preparation is limited to six hours; use a shorter finite queue')
    return {'scope':scope,'queue_roles':roles,'music_action':music_action,'effect_targets':['master'] if scope in ('effects','all') else [],
            'interval':(now,end),'pools':pools,'keep_ids':[e['id'] for e in sounds if e['start']<=now],
            'blocked':blocked,'fingerprint':fingerprint(project,intent),
            'summary':('Keeps your song · ' if music['mode']=='fixed' else '')+('varies treatment' if scope=='effects' else 'varies eligible future'+(' + treatment' if scope=='all' else '')),
            'seed_domains':{'music':101,'visuals':211,'effects':307}}
