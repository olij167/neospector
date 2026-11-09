"""Small, serialisable channel/mixer operations. No device or widget ownership."""
from __future__ import annotations
import math
import numpy as np
from PIL import Image
from sequencer_model import Layer,new_id

ROLES=('A','B')
MAX_CHANNELS=2

def channels(project):
    return sorted((l for l in project.layers if l.extra.get('voice') in ROLES),key=lambda l:l.extra['voice'])

def add_channel(project):
    existing={l.extra.get('voice') for l in project.layers}
    role=next((r for r in ROLES if r not in existing),None)
    if role is None:raise ValueError('UX10 has exactly two visual channels (A/B).')
    layer=Layer(new_id('voice'),role,enabled=True,generated=True,expanded=False,extra={'voice':role})
    index=next((i for i,l in enumerate(project.layers) if l.extra.get('voice')=='Camera'),len(project.layers))
    project.layers.insert(index,layer)
    intent=project.extra.get('playable_intent')
    if intent is not None:intent['enabled_roles']=list(dict.fromkeys([*intent.get('enabled_roles',[]),role]))
    project.touch();return layer

def strength_values(project,t,evaluator=None):
    """Return pre-master, pre-visibility channel strengths; legacy A/B stays truthful."""
    def value(p):return evaluator.value(p,t) if evaluator else p.animated_value(t)
    result={l.extra['voice']:max(0.,min(1.,value(l.opacity))) if l.enabled else 0. for l in channels(project)}
    if t<float(project.extra.get('channel_mix_since',float('inf'))):
        if result.get('A',0)>0 and result.get('B',0)>0:
            mix=max(0.,min(1.,value(project.voice_mix)))
            result['A']*=1-mix;result['B']*=mix
    return result

def strongest_channel(project,t,evaluator=None):
    enabled=[l for l in channels(project) if l.enabled]
    if not enabled:raise ValueError('Enable a visual channel before playing media into Programme.')
    values=strength_values(project,t,evaluator)
    return min(enabled,key=lambda l:(-round(values[l.extra['voice']],9),l.extra['voice'])).extra['voice']

def adopt_channel_mix(project,t,evaluator=None):
    if 'channel_mix_since' in project.extra:return
    levels=strength_values(project,t,evaluator)
    project.extra['channel_mix_since']=float(t)
    # This explicit takeover is reversible. archive_styles retains the old opacity
    # at the transaction boundary, while channel_mix_since preserves old A/B time.
    for layer in channels(project):
        layer.opacity.mode='static';layer.opacity.value=levels[layer.extra['voice']]
        layer.opacity.keyframes=[]

def master_at(project,kind,t):
    if kind not in ('audio','visual'):raise ValueError('Unknown master bus')
    events=project.extra.get(kind+'_master_events',[])
    return next((float(e['value']) for e in reversed(events) if e['time']<=t),1.)

def set_master(project,kind,value,t):
    if kind not in ('audio','visual'):raise ValueError('Unknown master bus')
    value=float(value);t=float(t)
    if not math.isfinite(value) or not 0<=value<=1 or not math.isfinite(t) or t<0:raise ValueError('Master level is 0–100%; time must be finite and nonnegative.')
    events=project.extra.setdefault(kind+'_master_events',[])
    events[:]=[e for e in events if e['time']<t]
    if events and abs(events[-1]['value']-value)<1e-8:return
    events.append({'time':t,'value':value});project.touch()

def master_curve(project,kind,times):
    out=np.ones(len(times),dtype=np.float32)
    for event in project.extra.get(kind+'_master_events',[]):out[times>=event['time']]=event['value']
    return out

def mix_images(images,levels,size):
    """Premultiplied, headroom-limited blend, not order-dependent opaque layering.

    Layer images already contain their alpha/gain. Multiple full-strength images
    share headroom; below a summed strength of one, lowering faders fades to black.
    Empty channels consume no headroom; all ordinary A-D visual channels share the same mix.
    """
    pairs=[(image,level) for image,level in zip(images,levels) if level>0 and image.getchannel('A').getbbox()]
    if not pairs:return Image.new('RGBA',size)
    divisor=max(1.,sum(level for _,level in pairs))
    accum=np.zeros((size[1],size[0],4),np.float32)
    for image,_ in pairs:
        data=np.asarray(image,dtype=np.float32)/255.;alpha=data[:,:,3:4]
        accum[:,:,:3]+=data[:,:,:3]*alpha;accum[:,:,3:4]+=alpha
    accum/=divisor
    alpha=np.clip(accum[:,:,3:4],0,1)
    rgb=np.divide(accum[:,:,:3],alpha,out=np.zeros_like(accum[:,:,:3]),where=alpha>1e-8)
    return Image.fromarray(np.uint8(np.clip(np.concatenate((rgb,alpha),axis=2),0,1)*255+.5))
