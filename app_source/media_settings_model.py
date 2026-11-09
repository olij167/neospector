"""Capability-aware Library defaults. Validation is pure and preserves unknown data."""
from __future__ import annotations
import copy,math
from sequencer_model import _effect_from,new_id

def tabs_for(asset):
    tabs=['General','Playback']
    if asset.kind!='audio':tabs.append('Effects')
    tabs.append('Conductor')
    if asset.kind=='audio' or asset.metadata.get('has_audio',False):tabs.append('Audio')
    return tabs

def validate_defaults(asset,updates,clip_min=2.,clip_max=8.):
    result=copy.deepcopy(asset.metadata.get('sequence_preferences',{}))
    limits={'clip_min':(.15,240),'clip_max':(.15,240),'source_in':(0,864000),'source_out':(.001,864000),
        'intensity':(0,1),'weight':(0,1000),'playback_rate':(.1,4),'sound_gain':(0,2)}
    for key,value in updates.items():
        if key in limits:
            if value is None or str(value).strip()=='':result.pop(key,None);continue
            try:number=float(value)
            except (ValueError,TypeError):raise ValueError(key.replace('_',' ').title()+' must be a number.') from None
            lo,hi=limits[key]
            if not math.isfinite(number) or not lo<=number<=hi:raise ValueError(f'{key.replace("_"," ").title()}: choose {lo:g}–{hi:g}.')
            result[key]=number
        elif key=='fit':
            if value not in ('cover','contain','stretch'):raise ValueError('Choose Cover, Contain or Stretch.')
            result[key]=value
        elif key=='source_policy':
            if value not in ('loop','hold'):raise ValueError('Choose Loop or Hold.')
            result[key]=value
        elif key=='roles':
            if not isinstance(value,list) or any(v not in ('A','B','C','D','Music') for v in value):raise ValueError('Invalid source role.')
            result[key]=list(dict.fromkeys(value))
        elif key in ('effect_preferences','reaction_preferences'):
            if not isinstance(value,dict) or any(v not in ('prefer','allow','avoid','exclude') for v in value.values()):raise ValueError('Invalid generation preference.')
            result[key]=copy.deepcopy(value)
        elif key=='default_rack':
            if value is None:result.pop(key,None)
            else:
                from module_engine import compile_rack
                if not isinstance(value,list):raise ValueError('Invalid saved treatment.')
                compile_rack([_effect_from(v) for v in value]);result[key]=copy.deepcopy(value)
        elif key=='enabled':result[key]=bool(value)
    if result.get('clip_min',clip_min)>result.get('clip_max',clip_max):raise ValueError('Maximum occurrence must be at least its minimum.')
    end=result.get('source_out',asset.duration or math.inf);start=result.get('source_in',0.)
    if end<=start:raise ValueError('Source end must follow source start.')
    if asset.duration and (end>asset.duration+.001 or start>=asset.duration):raise ValueError('Source window exceeds this file’s duration.')
    return result

def default_rack(asset):
    raw=copy.deepcopy(asset.metadata.get('sequence_preferences',{}).get('default_rack',[]));mapping={}
    def collect(obj):
        if isinstance(obj,dict):
            if 'id' in obj and 'kind' in obj:mapping[obj['id']]=new_id('fx')
            for value in obj.values():collect(value)
        elif isinstance(obj,list):
            for value in obj:collect(value)
    def replace(obj):
        if isinstance(obj,dict):
            for k,v in obj.items():
                if k in ('id','effect') and isinstance(v,str) and v in mapping:obj[k]=mapping[v]
                else:replace(v)
        elif isinstance(obj,list):
            for value in obj:replace(value)
    collect(raw);replace(raw);return [_effect_from(v) for v in raw]

def queue_drop_intent(zone,dwell,before_id=None):
    if zone=='next':return 'next',None
    if zone=='list' and dwell>=1. and before_id:return 'insert',before_id
    return 'append',None
