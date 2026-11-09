"""A/B mix transitions: a distinct time-bound effect using the existing FX registry.

Transition shape remains associated with the A/B crossfade. A separate authored
Transition module rack uses the same grouping and parameter language as visual
racks, without modifying either source or inventing a second playback engine.
"""
from __future__ import annotations
import math
import hashlib
import numpy as np
from PIL import Image
from types import SimpleNamespace
from effects_engine import crossfade,transition_image,make_effect,apply_effect,coordinates
from module_engine import compile_rack

STYLES={
 'dissolve':'Mix','wipe_left':'Wipe ←','wipe_right':'Wipe →',
 'wipe_up':'Wipe ↑','pixel_dissolve':'Pixels','glitch_wipe':'Glitch',
}
# Re-use tested, non-temporal module FX. Time-history effects require a frame
# provider and therefore deliberately remain in the ordinary module rack.
TRANSITION_EFFECTS={'none':'No effect','invert':'Invert','pixelate':'Mosaic',
                    'grain':'Grain','chroma_shift':'Chroma bleed','duotone':'Duotone',
                    'edge':'Edge trace','saturation':'Saturation','contrast':'Contrast'}
EASING={'linear':'Linear','smooth':'Smooth','ease_in':'Ease in','ease_out':'Ease out'}
DEFAULT=dict(kind='dissolve',softness=.09,easing='linear',effect='none',effect_strength=0.)

def validated_spec(data):
    spec={**DEFAULT,**(data or {})}
    if spec['kind'] not in STYLES:raise ValueError('Unknown A/B transition style')
    if spec['effect'] not in TRANSITION_EFFECTS:raise ValueError('Unsupported transition effect')
    if spec['easing'] not in EASING:raise ValueError('Unsupported transition easing')
    for key,lo,hi in (('softness',.001,.5),('effect_strength',0.,1.)):
        try:v=float(spec[key])
        except (TypeError,ValueError):raise ValueError('Invalid transition '+key) from None
        if not math.isfinite(v) or not lo<=v<=hi:raise ValueError('Transition '+key+' must be within '+str((lo,hi)))
        spec[key]=v
    return {key:spec[key] for key in DEFAULT}

def configure_transition(project,kind,**changes):
    # Changing a style must not silently reset the artist's custom effect.
    merged={**project.extra.get('ux16_transition',{}),**changes,'kind':kind}
    spec=validated_spec(merged)
    project.extra['ux16_transition']=spec
    project.voice_mixer_mode='crossfade'
    return spec

def _eased(value,kind):
    if kind=='smooth':return value*value*(3-2*value)
    if kind=='ease_in':return value*value
    if kind=='ease_out':return 1-(1-value)*(1-value)
    return value

def validate_transition_rack(rack):
    """Use the shared rack/group compiler, excluding effects needing frame history.

    Modules and nested groups share the ordinary module model, parameters,
    ownership and preset library. Temporal echo/trails require a frame-history
    provider which the instant A/B bridge deliberately does not own.
    """
    operations=compile_rack(rack)
    if len(operations)>32:raise ValueError('Transition rack: use no more than 32 effects')
    if any(fx.kind in ('echo','frame_blend') for fx in operations):
        raise ValueError('Transition modules cannot use frame history (Echo or Frame Blend).')
    return operations


def random_transition_rack(current,seed,count,variation):
    """Randomise the Transition rack with a real animation operator by default.

    Respect protected slots and a bounded module budget; never substitute an
    image-only effect chain for an animation when a slot can be authored.
    """
    import copy,random
    from rack_protection import composition_locked
    from module_engine import randomise_rack
    from effects_engine import EFFECTS
    rng=random.Random(seed)
    animation=('transition_reveal','transition_iris','transition_pixels','transition_glitch','transition_slide')
    choices=[key for key in EFFECTS if key not in ('echo','frame_blend')]
    fixed={i:copy.deepcopy(f) for i,f in enumerate(current) if composition_locked(f)}
    count=max(int(count),max(fixed,default=-1)+1)
    has_animation=any(f.kind in animation for f in fixed.values())
    result=[]
    for i in range(count):
        if i in fixed:result.append(fixed[i]);continue
        if not has_animation:
            kind=rng.choice(animation);has_animation=True
        else:
            kind=rng.choice(choices)
        fx=make_effect(kind)
        randomise_rack([fx],seed+7919*i,source='reaction_mix',rebuild=False,purpose='manual')
        baseline=make_effect(fx.kind)
        for name,param in fx.params.items():
            neutral=baseline.params[name]
            param.value=neutral.value+(param.value-neutral.value)*variation
        result.append(fx)
    validate_transition_rack(result)
    return result

def reveal_field(a,b,progress,angle,softness):
    """An authored directional reveal; a full 360° angle is editable on-pedal."""
    w,h=a.size
    x,y=coordinates(a.size)
    radians=math.radians(angle)
    cx,cy=math.cos(radians),math.sin(radians)
    span=max(.0001,abs(cx)+abs(cy))
    projected=(cx*(x/max(1,w-1)-.5)+cy*(y/max(1,h-1)-.5))/span
    mask=np.clip((progress-.5-projected)/max(.002,softness)+.5,0.,1.)
    return crossfade(a,b,mask)

def _phase(progress, params, eval_, time):
    start=max(0.,min(.9,eval_.value(params['start'],time)))
    end=max(start+.001,min(1.,eval_.value(params['end'],time)))
    phase=max(0.,min(1.,(progress-start)/(end-start)))
    curve=max(-1.,min(1.,eval_.value(params['curve'],time)))
    if curve>=0:phase=phase**(1.+3.*curve)
    else:phase=1.-(1.-phase)**(1.-3.*curve)
    smooth=eval_.value(params['smooth'],time)
    return phase*(1.-smooth)+(phase*phase*(3.-2.*phase))*smooth


def _seed_bytes(seed):
    return int.from_bytes(hashlib.sha256(str(seed).encode('utf-8')).digest()[:8],'big')


def _field(a,b,fx,progress,time,eval_,seed):
    """Turn authored transition parameters into a stable spatial compositor.

    A spatial stage always operates on A/B originals. Animated progression
    comes from the rack's Timing Curve; it does not depend on wall time.
    """
    def p(k):return eval_.value(fx.params[k],time)
    kind=fx.kind;w,h=a.size;x,y=coordinates(a.size)
    xn=x/max(1,w-1);yn=y/max(1,h-1)
    if kind=='transition_reveal':
        return reveal_field(a,b,progress,p('angle'),p('softness'))
    if kind=='transition_iris':
        cx=p('center_x');cy=p('center_y')
        corners=[math.hypot(u-cx,v-cy) for u in (0,1) for v in (0,1)]
        radius=max(.01,max(corners));dist=np.sqrt((xn-cx)**2+(yn-cy)**2)/radius
        if p('reverse')>=.5:dist=1.-dist
        softness=max(.002,p('softness'))
        mask=np.clip((progress*(1+softness)-dist)/softness+.5,0,1)
        return crossfade(a,b,mask)
    if kind=='transition_pixels':
        cell=max(2,round(p('cell')*h/720))
        cols=max(1,(w+cell-1)//cell);rows=max(1,(h+cell-1)//cell)
        rng=np.random.default_rng(_seed_bytes(f'{seed}:{fx.id}'))
        grid=rng.random((rows,cols),dtype=np.float32)
        # Blend between spatial scan and per-cell random order.
        yidx,xidx=np.indices((rows,cols),dtype=np.float32)
        ordered=(xidx+.5)/cols
        amount=max(0.,min(1.,p('randomness')))
        dist=ordered*(1.-amount)+grid*amount
        dist=np.repeat(np.repeat(dist,cell,axis=0),cell,axis=1)[:h,:w]
        soft=max(.002,p('softness'))
        mask=np.clip((progress*(1+soft)-dist)/soft+.5,0.,1.)
        return crossfade(a,b,mask)
    if kind=='transition_glitch':
        bands=max(2,round(p('bands')))
        rng=np.random.default_rng(_seed_bytes(f'{seed}:{fx.id}'))
        displacement=rng.uniform(-1,1,(bands,1)).astype(np.float32)
        band_rows=np.minimum(bands-1,(np.arange(h,dtype=np.int32)*bands//max(1,h)))
        bandfield=displacement[band_rows]
        texture=rng.uniform(-1,1,(max(1,(h+11)//12),max(1,(w+15)//16))).astype(np.float32)
        noise=np.repeat(np.repeat(texture,12,axis=0),16,axis=1)[:h,:w]
        dist=np.clip(xn+p('displace')*bandfield+p('noise')*.16*noise,0.,1.)
        soft=max(.002,p('softness'))
        mask=np.clip((progress*(1+soft)-dist)/soft+.5,0.,1.)
        return crossfade(a,b,mask)
    if kind=='transition_slide':
        theta=math.radians(p('angle'));travel=p('travel');f=progress
        dx=math.cos(theta);dy=math.sin(theta)
        # A and B move as two pieces of one image; unfilled areas retain
        # the ordinary crossfade rather than showing a transparent canvas.
        canvas=crossfade(a,b,f)
        a_offset=(-round(w*dx*f*travel),-round(h*dy*f*travel))
        b_offset=(round(w*dx*(1.-f)*travel),round(h*dy*(1.-f)*travel))
        layer=Image.new('RGBA',a.size,(0,0,0,0))
        layer.alpha_composite(a,a_offset);layer.alpha_composite(b,b_offset)
        return Image.alpha_composite(canvas,layer)
    raise ValueError('Unsupported transition composer: '+kind)


ANIMATION_MODULES=frozenset({'transition_reveal','transition_iris','transition_pixels','transition_glitch','transition_slide'})


def transition_treatment(project,a,b,base,mix,t=0.,evaluator=None):
    """An ordered, authored A/B animation and treatment chain.

    Timing modules set the shared transition clock; spatial stages reveal or
    move the original sources. Image effects apply after their preceding stage.
    Groups compile to the same primitive sequence as individual modules.
    """
    rack=getattr(project,'transition_rack',())
    if not rack or project.extra.get('transition_rack_bypassed',False):return base
    operations=validate_transition_rack(rack)
    if not operations:return base
    strength=max(0.,min(1.,4.*mix*(1.-mix)))
    if strength<=0:return base
    if evaluator is None:
        class StaticEvaluator:
            def value(self,param,time,signal_time=None):
                return param.render_value(self,time) if hasattr(param,'render_value') else param.animated_value(time)
        evaluator=StaticEvaluator()
    eval_=evaluator
    clock=mix
    # Timing can be placed anywhere within a group, without making sequencing
    # depend on the library's default insertion position.
    for fx in operations:
        if fx.kind=='transition_timing':clock=_phase(clock,fx.params,eval_,t)
    has_animation=any(fx.kind in ANIMATION_MODULES or fx.kind=='transition_timing' for fx in operations)
    image=crossfade(a,b,clock) if has_animation else base
    for fx in operations:
        if fx.kind in ANIMATION_MODULES:
            amount=max(0.,min(1.,eval_.value(fx.params['amount'],t)))
            if amount:
                rendered=_field(a,b,fx,clock,t,eval_,project.id)
                image=crossfade(image,rendered,amount)
        elif fx.kind=='transition_timing':
            continue
        else:
            treated=apply_effect(image,fx,t,eval_)
            image=crossfade(image,treated,strength)
    return image

def composited_mix(project,a,b,mix,t=0.,evaluator=None):
    spec=validated_spec(project.extra.get('ux16_transition',{}))
    m=max(0.,min(1.,float(mix)))
    if m<=0:return a
    if m>=1:return b
    f=_eased(m,spec['easing'])
    kind=spec['kind']
    if kind=='dissolve':base=crossfade(a,b,f)
    else:
        transition=SimpleNamespace(id='ux16-mix',start=0.,duration=1.,kind=kind,
                                   easing='linear',softness=spec['softness'],
                                   extra={'seed':project.id})
        base=transition_image(a,b,transition,f)
    if getattr(project,'transition_rack',None):
        return transition_treatment(project,a,b,base,f,t,evaluator)
    effect=spec['effect'];strength=spec['effect_strength']
    if effect=='none' or strength<=0:return base
    # The effect belongs only to the transition, peaking at its centre.
    envelope=min(1.,max(0.,4*f*(1-f)))
    amount=strength*envelope
    fx=make_effect(effect)
    fx.extra['seed']=project.id
    if 'amount' in fx.params:
        v=fx.params['amount'];neutral={'contrast':1.,'saturation':1.}.get(effect,0.)
        chosen={'contrast':2.1,'saturation':.1}.get(effect,1.)
        v.value=neutral+(chosen-neutral)*strength
    evaluator=SimpleNamespace(value=lambda param,t:param.value)
    treated=apply_effect(base,fx,0.,evaluator)
    return crossfade(base,treated,amount)
