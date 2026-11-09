"""UX41: deterministic, serialisable A/B ping-pong clock.

A single mix curve drives preview, export and the visual fader. This does not
spawn timers, touch live sources, modify parameter keys or change playback.
"""
from __future__ import annotations
import math

KEY='ux41_pingpong'
DEFAULT={'enabled':False,'start':0.,'hold':8.,'fade':2.,'first':'A'}

def validate(settings):
    d={**DEFAULT,**(settings or {})}
    for key,lo,hi in (('start',0.,1e9),('hold',0.,3600.),('fade',.05,600.)):
        try:v=float(d[key])
        except (TypeError,ValueError):raise ValueError('Invalid ping-pong '+key) from None
        if not math.isfinite(v) or not lo<=v<=hi:raise ValueError('Ping-pong '+key+' is outside its allowed range')
        d[key]=v
    if d['first'] not in ('A','B'):raise ValueError('Ping-pong starting channel must be A or B')
    d['enabled']=bool(d['enabled'])
    return d

def configure_pingpong(project,enabled,*,start=None,hold=None,fade=None,first=None):
    old=validate(project.extra.get(KEY))
    values={**old,'enabled':bool(enabled)}
    values.update({k:v for k,v in (('start',start),('hold',hold),('fade',fade),('first',first)) if v is not None})
    project.extra[KEY]=validate(values)
    if enabled:project.voice_mixer_mode='crossfade'
    return project.extra[KEY]

def pingpong_at(project,t):
    raw=project.extra.get(KEY)
    if not raw or not raw.get('enabled'):return None
    config=validate(raw)
    phase=max(0.,float(t)-config['start'])%(2*(config['hold']+config['fade']))
    hold,fade=config['hold'],config['fade']
    if phase<hold:mix=0.
    elif phase<hold+fade:
        x=(phase-hold)/fade;mix=x*x*(3-2*x)
    elif phase<2*hold+fade:mix=1.
    else:
        x=(phase-(2*hold+fade))/fade;mix=1.-x*x*(3-2*x)
    return mix if config['first']=='A' else 1.-mix
