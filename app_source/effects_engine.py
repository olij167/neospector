"""Implemented visual operations and their discoverable parameter registry.

Compositing uses display-referred SDR RGB with straight-alpha storage and
premultiplied interpolation. This is not an HDR or scene-linear grading engine.
"""
from __future__ import annotations
import functools
import hashlib
import io
import math
from dataclasses import dataclass
import numpy as np
from PIL import Image,ImageChops,ImageColor,ImageDraw,ImageEnhance,ImageFilter,ImageOps
from sequencer_model import Effect,ProgrammableParameter,new_id

BLEND_MODES=('normal','add','screen','multiply','overlay','soft_light','hard_light','difference','exclusion','darken','lighten')


@dataclass(frozen=True)
class EffectSpec:
    label: str
    group: str
    params: dict                       # name -> (default, min, max, unit)
    temporal: bool = False
    note: str = ''
    priority: tuple[str, ...] = ('amount',)


EFFECTS={
    'brightness':EffectSpec('Brightness','Adjust',{'amount':(0,-1,1,'')}),
    'contrast':EffectSpec('Contrast','Adjust',{'amount':(1,0,3,'×')}),
    'gamma':EffectSpec('Gamma','Adjust',{'amount':(1,.2,3,'')}),
    'saturation':EffectSpec('Saturation','Adjust',{'amount':(1,0,3,'×')}),
    'hue':EffectSpec('Hue','Adjust',{'amount':(0,-180,180,'°')}),
    'sharpness':EffectSpec('Sharpness','Adjust',{'amount':(0,0,3,'')}),
    'blur':EffectSpec('Blur','Adjust',{'amount':(0,0,20,'px @720p')}),
    'invert':EffectSpec('Invert','Colour',{'amount':(1,0,1,'')}),
    'posterize':EffectSpec('Posterise','Colour',{'amount':(.5,0,1,'')}),
    'threshold':EffectSpec('Threshold','Colour',{'amount':(.5,0,1,'')}),
    'pixelate':EffectSpec('Mosaic','Texture',{'amount':(.25,0,1,'')}),
    'scanlines':EffectSpec('Compact Scan','Texture',{'amount':(.35,0,1,''),'spacing':(4,2,16,'px @720p')},priority=('amount','spacing')),
    'chroma_shift':EffectSpec('Chroma Bleed','Texture',{'amount':(.2,0,1,'')}),
    'grain':EffectSpec('Grain','Texture',{'amount':(.15,0,1,'')}),
    'vignette':EffectSpec('Vignette','Light',{'amount':(.4,0,1,'')}),
    'mirror':EffectSpec('Mirror','Spatial',{'amount':(1,0,1,'')}),
    'tile':EffectSpec('Tile','Spatial',{'columns':(3,1,12,''),'rows':(2,1,12,'')},priority=('columns','rows')),
    'liquid':EffectSpec('Liquid Drift','Spatial',{'amount':(.2,0,1,''),'speed':(1,0,4,'×'),'waves':(3,1,10,'')},priority=('amount','speed')),
    'jpeg_loss':EffectSpec('Generation Loss','Texture',{'amount':(.45,0,1,'')},note='Spatial JPEG round-trip; not inter-frame codec corruption.'),
    'echo':EffectSpec('CCD Afterglow','Time',{'amount':(.35,0,.9,''),'delay':(.12,.02,1,'s'),'taps':(2,1,4,'')},True,'Finite, timestamped history; repeatable after seeking.',('amount','delay')),
    'frame_blend':EffectSpec('Frame Blend','Time',{'amount':(.35,0,1,''),'delay':(.04,.01,.3,'s')},True,'Blends earlier frames. Not optical-flow interpolation.',('amount','delay')),
}


EFFECTS.update({
    'exposure':EffectSpec('Exposure','Light',{'amount':(0,-3,3,'EV')}),
    'temperature':EffectSpec('Temperature','Colour',{'amount':(0,-1,1,'')},note='Warm/cool channel balance; not calibrated white balance.'),
    'tint':EffectSpec('Tint','Colour',{'amount':(0,-1,1,'')},note='Green/magenta channel balance.'),
    'solarize':EffectSpec('Solarise','Colour',{'amount':(.45,0,1,'')},note='Thresholded inversion with a controllable treatment mix.'),
    'edge':EffectSpec('Edge Trace','Texture',{'amount':(.7,0,1,'')},note='Luminance edge overlay; preserves source alpha.'),
    'emboss':EffectSpec('Emboss','Texture',{'amount':(.5,0,1,'')}),
    'duotone':EffectSpec('Duotone','Colour',{'amount':(.6,0,1,''),'hue':(210,-180,360,'°')},note='Two-colour luminance mapping; amount blends with the original.',priority=('amount','hue')),
})

# The reveal field is a transition-only compositing stage, not an image filter.
# It uses the same programmable Effect and grouped macro editing as other FX.
EFFECTS['transition_reveal']=EffectSpec('Reveal Field','Transition',{'amount':(1,0,1,''),'angle':(0,0,360,'°'),'softness':(.12,.002,.5,'')},note='Reveal the incoming channel along an adjustable directional field.',priority=('angle','softness'))
# Each transition operator is a real module with parameters that participate
# in group macros, project serialization, undo, rack randomisation and reaction.
EFFECTS.update({
    'transition_timing':EffectSpec('Timing Curve','Transition',{'start':(0,0,.9,''),'end':(1,.1,1,''),'curve':(0,-1,1,''),'smooth':(.5,0,1,'')},note='Animate transition progress with start/end, acceleration and smoothness.',priority=('start','end','curve')),
    'transition_iris':EffectSpec('Iris Field','Transition',{'amount':(1,0,1,''),'center_x':(.5,0,1,''),'center_y':(.5,0,1,''),'softness':(.08,.002,.5,''),'reverse':(0,0,1,'')},note='Adjustable radial reveal; move the centre or invert the expansion.',priority=('center_x','center_y','softness')),
    'transition_pixels':EffectSpec('Pixel Field','Transition',{'amount':(1,0,1,''),'cell':(24,4,96,'px @720p'),'randomness':(.9,0,1,''),'softness':(.08,.002,.5,'')},note='Stable per-cell reveal field. Cell size and randomness are editable.',priority=('cell','randomness','softness')),
    'transition_glitch':EffectSpec('Tear Field','Transition',{'amount':(1,0,1,''),'bands':(16,2,80,''),'displace':(.18,0,.5,''),'noise':(.2,0,1,''),'softness':(.06,.002,.5,'')},note='Deterministic scan-band displacement and texture noise.',priority=('bands','displace','noise')),
    'transition_slide':EffectSpec('Slide Motion','Transition',{'amount':(1,0,1,''),'angle':(0,0,360,'°'),'travel':(1,.2,1,'')},note='Translate both channel images in opposite directions across the transition.',priority=('angle','travel','amount')),
})


LOOKS={
    'Clean':[],
    'Generation Loss':[('jpeg_loss',{'amount':.48}),('saturation',{'amount':.9}),('grain',{'amount':.06})],
    'Compact Scan':[('scanlines',{'amount':.5,'spacing':4}),('contrast',{'amount':1.12}),('chroma_shift',{'amount':.08})],
    'CCD Afterglow':[('echo',{'amount':.3,'delay':.1,'taps':2}),('brightness',{'amount':.025}),('saturation',{'amount':.85})],
    'Chroma Bleed':[('chroma_shift',{'amount':.23}),('blur',{'amount':.5}),('saturation',{'amount':1.2})],
    'Liquid Motion':[('liquid',{'amount':.18,'speed':.8,'waves':3}),('frame_blend',{'amount':.18,'delay':.035})],
    'River Memory':[('liquid',{'amount':.13,'speed':.6,'waves':2}),('echo',{'amount':.26,'delay':.16,'taps':2}),('hue',{'amount':8})],
}


def make_effect(kind,values=None):
    if kind not in EFFECTS:raise ValueError(f'Effect not implemented: {kind}')
    spec=EFFECTS[kind]
    return Effect(new_id('fx'),kind,params={k:ProgrammableParameter((values or {}).get(k,v[0]),v[1],v[2]) for k,v in spec.params.items()})


def make_look(name):
    if name not in LOOKS:raise ValueError('Unknown Look')
    return [make_effect(k,v) for k,v in LOOKS[name]]


def _rgba(array):return Image.fromarray(np.clip(np.rint(array*255),0,255).astype(np.uint8),'RGBA')


def blend_images(back:Image.Image,front:Image.Image,mode='normal',opacity=1.):
    if mode not in BLEND_MODES:raise ValueError(f'Blend mode is not supported: {mode}')
    if opacity<=0:return back
    if mode=='normal' and opacity>=.999999:
        return Image.alpha_composite(back,front)
    b=np.asarray(back,dtype=np.float32)/255;s=np.asarray(front,dtype=np.float32)/255
    cb=b[:,:,:3];cs=s[:,:,:3];ab=b[:,:,3:4];a=s[:,:,3:4]*max(0.,min(1.,opacity))
    if mode=='normal':mixed=cs
    elif mode=='add':mixed=np.minimum(1.,cb+cs)
    elif mode=='screen':mixed=1-(1-cb)*(1-cs)
    elif mode=='multiply':mixed=cb*cs
    elif mode=='overlay':mixed=np.where(cb<=.5,2*cb*cs,1-2*(1-cb)*(1-cs))
    elif mode=='hard_light':mixed=np.where(cs<=.5,2*cb*cs,1-2*(1-cb)*(1-cs))
    elif mode=='soft_light':
        d=np.where(cb<=.25,((16*cb-12)*cb+4)*cb,np.sqrt(cb))
        mixed=np.where(cs<=.5,cb-(1-2*cs)*cb*(1-cb),cb+(2*cs-1)*(d-cb))
    elif mode=='difference':mixed=np.abs(cb-cs)
    elif mode=='exclusion':mixed=cb+cs-2*cb*cs
    elif mode=='darken':mixed=np.minimum(cb,cs)
    else:mixed=np.maximum(cb,cs)
    alpha=a+ab*(1-a)
    prem=(1-a)*ab*cb+(1-ab)*a*cs+ab*a*mixed
    rgb=np.divide(prem,alpha,out=np.zeros_like(prem),where=alpha>1e-7)
    return _rgba(np.concatenate([rgb,alpha],axis=2))


def crossfade(a,b,mix):
    if np.isscalar(mix):
        if mix<=0:return a
        if mix>=1:return b
    aa=np.asarray(a,dtype=np.float32)/255;bb=np.asarray(b,dtype=np.float32)/255
    m=np.asarray(mix,dtype=np.float32)
    if m.ndim==2:m=m[:,:,None]
    alpha=aa[:,:,3:4]*(1-m)+bb[:,:,3:4]*m
    prem=aa[:,:,:3]*aa[:,:,3:4]*(1-m)+bb[:,:,:3]*bb[:,:,3:4]*m
    rgb=np.divide(prem,alpha,out=np.zeros_like(prem),where=alpha>1e-7)
    return _rgba(np.concatenate([rgb,alpha],axis=2))


@functools.lru_cache(maxsize=16)
def coordinates(size):
    w,h=size
    # Separable coordinates retain O(width+height), not two O(width*height) maps.
    x=np.arange(w,dtype=np.float32)[None,:];y=np.arange(h,dtype=np.float32)[:,None]
    x.flags.writeable=False;y.flags.writeable=False
    return x,y


def transition_image(a,b,transition,t):
    f=max(0.,min(1.,(t-transition.start)/max(1e-8,transition.duration)))
    if transition.easing=='smooth':f=f*f*(3-2*f)
    elif transition.easing=='ease_in':f=f*f
    elif transition.easing=='ease_out':f=1-(1-f)*(1-f)
    if f<=1e-8:return a
    if f>=1-1e-8:return b
    kind=transition.kind;w,h=a.size
    if kind=='dissolve':return crossfade(a,b,f)
    if kind=='fade_colour':
        colour=Image.new('RGBA',a.size,ImageColor.getrgb(transition.colour)+(255,))
        return crossfade(a,colour,f*2) if f<.5 else crossfade(colour,b,(f-.5)*2)
    if kind.startswith('slide_'):
        output=Image.new('RGBA',a.size);offset=round(w*f)
        if kind=='slide_left':output.alpha_composite(a,(-offset,0));output.alpha_composite(b,(w-offset,0))
        else:output.alpha_composite(a,(offset,0));output.alpha_composite(b,(offset-w,0))
        return output
    x,y=coordinates(a.size);x=x/max(1,w-1);y=y/max(1,h-1)
    if kind=='wipe_left':dist=1-x
    elif kind=='wipe_right':dist=x
    elif kind=='wipe_up':dist=1-y
    elif kind=='wipe_down':dist=y
    elif kind in {'iris_open','iris_close'}:
        dist=np.sqrt((x-.5)**2+(y-.5)**2)/math.sqrt(.5)
        if kind=='iris_close':dist=1-dist
    elif kind=='glitch_wipe':
        # Deterministic scan-band displacement and coarse pixel tear; bounded
        # to the transition itself. This is a glitch wipe, not codec datamosh.
        seed=int.from_bytes(hashlib.sha256(str(transition.extra.get('seed',transition.id)).encode()).digest()[:4],'big')
        rng=np.random.default_rng(seed)
        horizontal=rng.uniform(-.16,.16,size=(max(1,(h+11)//12),1)).astype(np.float32)
        bands=np.repeat(horizontal,12,axis=0)[:h]
        coarse=rng.uniform(-.06,.06,size=(max(1,(h+11)//12),max(1,(w+31)//32))).astype(np.float32)
        pixels=np.repeat(np.repeat(coarse,12,axis=0),32,axis=1)[:h,:w]
        dist=np.clip(x+bands+pixels,0,1)
    elif kind=='pixel_dissolve':
        # A fixed coarse noise field gives stable spatial identity at all sizes.
        seed=int.from_bytes(hashlib.sha256(str(transition.extra.get('seed',transition.id)).encode()).digest()[:4],'big')
        rng=np.random.default_rng(seed);grid=Image.fromarray((rng.random((36,64))*255).astype(np.uint8))
        dist=np.asarray(grid.resize(a.size,Image.Resampling.NEAREST),dtype=np.float32)/255
    else:raise ValueError(f'Unsupported transition: {kind}')
    soft=max(.0001,min(.5,transition.softness));mask=np.clip((f*(1+soft)-soft*.5-dist)/soft+.5,0,1)
    return crossfade(a,b,mask)


def multiply_alpha(image,amount):
    if np.isscalar(amount) and amount>=.999999:return image
    out=image.copy();alpha=np.asarray(image.getchannel('A'),dtype=np.float32)*amount
    out.putalpha(Image.fromarray(np.clip(alpha,0,255).astype(np.uint8)));return out


def mask_image(image,mask,reference=None):
    if mask.kind=='none':return image
    w,h=image.size
    if mask.kind in {'alpha','luma'}:
        if reference is None:raise ValueError('Mask source must reference an earlier layer')
        m=reference.getchannel('A') if mask.kind=='alpha' else ImageChops.multiply(reference.convert('L'),reference.getchannel('A'))
    else:
        m=Image.new('L',image.size,0);d=ImageDraw.Draw(m)
        cx=w*(.5+mask.x*.5);cy=h*(.5+mask.y*.5);rx=w*max(.01,min(2,mask.width))*.5;ry=h*max(.01,min(2,mask.height))*.5
        if mask.kind=='ellipse':d.ellipse((cx-rx,cy-ry,cx+rx,cy+ry),fill=255)
        elif mask.kind=='rectangle':d.rectangle((cx-rx,cy-ry,cx+rx,cy+ry),fill=255)
        else:raise ValueError(f'Unsupported mask: {mask.kind}')
    if mask.feather>0:m=m.filter(ImageFilter.GaussianBlur(min(w,h)*min(.3,mask.feather)))
    if mask.invert:m=ImageOps.invert(m)
    return multiply_alpha(image,np.asarray(m,dtype=np.float32)/255)


def adjust(image,kind,value):
    v=float(value)
    neutral=1. if kind in {'contrast','gamma','saturation'} else 0.
    if abs(v-neutral)<1e-7:return image
    alpha=image.getchannel('A');rgb=image.convert('RGB')
    if kind=='brightness':
        if abs(v)<1e-6:return image
        rgb=rgb.point([int(max(0,min(255,i+v*255))) for i in range(256)]*3)
    elif kind=='contrast':
        if abs(v-1)<1e-6:return image
        rgb=ImageEnhance.Contrast(rgb).enhance(v)
    elif kind=='gamma':
        if abs(v-1)<1e-6:return image
        rgb=rgb.point([round(255*(i/255)**(1/max(.1,v))) for i in range(256)]*3)
    elif kind=='saturation':
        if abs(v-1)<1e-6:return image
        rgb=ImageEnhance.Color(rgb).enhance(v)
    elif kind=='hue':
        if abs(v)<1e-6:return image
        hsv=np.array(rgb.convert('HSV'));hsv[:,:,0]=((hsv[:,:,0].astype(np.int16)+round(v/360*255))%256).astype(np.uint8);rgb=Image.fromarray(hsv,'HSV').convert('RGB')
    elif kind=='sharpness':
        if v<=1e-6:return image
        rgb=ImageEnhance.Sharpness(rgb).enhance(1+v)
    elif kind=='blur':
        if v<=1e-6:return image
        # An opaque image already is its own premultiplied representation.
        if alpha.getextrema()==(255,255):return image.filter(ImageFilter.GaussianBlur(v*image.height/720))
        # Blur premultiplied colours and alpha together, avoiding coloured fringes.
        a=np.asarray(image,dtype=np.float32)/255;prem=np.concatenate((a[:,:,:3]*a[:,:,3:4],a[:,:,3:4]),axis=2)
        blurred=np.asarray(_rgba(prem).filter(ImageFilter.GaussianBlur(v*image.height/720)),dtype=np.float32)/255
        colour=np.divide(blurred[:,:,:3],blurred[:,:,3:4],out=np.zeros_like(blurred[:,:,:3]),where=blurred[:,:,3:4]>1e-6)
        return _rgba(np.concatenate((colour,blurred[:,:,3:4]),axis=2))
    rgb=rgb.convert('RGBA');rgb.putalpha(alpha);return rgb


def apply_effect(image,effect,t,evaluator,delayed=None):
    if not effect.enabled:return image
    if effect.kind not in EFFECTS:raise ValueError(f'Unknown effect {effect.kind}; it was not silently removed')
    spec=EFFECTS[effect.kind]
    p={k:max(v[1],min(v[2],evaluator.value(effect.params[k],t))) if k in effect.params else v[0] for k,v in spec.params.items()}
    kind=effect.kind;v=p.get('amount',1.);w,h=image.size
    if kind.startswith('transition_'):return image  # The A/B compositor interprets these stages.
    if kind in {'brightness','contrast','gamma','saturation','hue','sharpness','blur'}:return adjust(image,kind,v)
    if kind in {'echo','frame_blend'}:
        if delayed is None:raise ValueError('Temporal effect requires a history provider')
        if v<=0:return image
        if kind=='frame_blend':return crossfade(image,delayed(p['delay']),v)
        out=image
        for i in range(int(round(p['taps'])),0,-1):out=blend_images(delayed(p['delay']*i),out,'normal',1-v**i)
        return out
    alpha=image.getchannel('A');rgb=image.convert('RGB')
    if kind=='exposure':rgb=rgb.point([round(min(255,x*(2**v))) for x in range(256)]*3)
    elif kind in {'temperature','tint'}:
        a=np.asarray(rgb,dtype=np.float32)
        gains=(1+.24*v,1.,1-.24*v) if kind=='temperature' else (1+.13*v,1-.22*v,1+.13*v)
        rgb=Image.fromarray(np.clip(a*np.asarray(gains,dtype=np.float32),0,255).astype(np.uint8))
    elif kind=='solarize':rgb=Image.blend(rgb,ImageOps.solarize(rgb,threshold=128),v)
    elif kind=='edge':rgb=Image.blend(rgb,rgb.convert('L').filter(ImageFilter.FIND_EDGES).convert('RGB'),v)
    elif kind=='emboss':rgb=Image.blend(rgb,rgb.filter(ImageFilter.EMBOSS),v)
    elif kind=='duotone':
        import colorsys
        tone=tuple(round(c*255) for c in colorsys.hsv_to_rgb((p['hue']%360)/360,.7,.98))
        treated=ImageOps.colorize(rgb.convert('L'),(13,12,24),tone)
        rgb=Image.blend(rgb,treated,v)
    elif kind=='invert':rgb=Image.blend(rgb,ImageOps.invert(rgb),v)
    elif kind=='posterize':rgb=ImageOps.posterize(rgb,max(1,round(8-v*6)))
    elif kind=='threshold':rgb=rgb.convert('L').point(lambda x:255 if x>=v*255 else 0).convert('RGB')
    elif kind=='pixelate':
        cell=max(1,round(1+v*60*h/720));image=image.resize((max(1,w//cell),max(1,h//cell)),Image.Resampling.BOX).resize((w,h),Image.Resampling.NEAREST);return image
    elif kind=='scanlines':
        a=np.asarray(rgb,dtype=np.float32);spacing=max(2,round(p['spacing']*h/720));a[::spacing]*=1-v;rgb=Image.fromarray(np.clip(a,0,255).astype(np.uint8))
    elif kind=='chroma_shift':
        a=np.array(rgb);offset=round(v*w*.04)
        if offset:
            a[:,:,0]=np.roll(a[:,:,0],offset,axis=1);a[:,:offset,0]=a[:,offset:offset+1,0]
            a[:,:,2]=np.roll(a[:,:,2],-offset,axis=1);a[:,-offset:,2]=a[:,-offset-1:-offset,2]
        rgb=Image.fromarray(a)
    elif kind=='grain':
        # Noise is deterministic for the project frame, not wall time or playback speed.
        seed=int.from_bytes(hashlib.sha256(f"{effect.extra.get('seed',effect.id)}:{round(t*60)}".encode()).digest()[:4],'big')
        rng=np.random.default_rng(seed);noise=rng.normal(0,v*32,(h,w,1)).astype(np.float32);rgb=Image.fromarray(np.clip(np.asarray(rgb,dtype=np.float32)+noise,0,255).astype(np.uint8))
    elif kind=='vignette':
        x,y=coordinates(image.size);dist=((x/max(1,w)-.5)*2)**2+((y/max(1,h)-.5)*2)**2
        a=np.asarray(rgb,dtype=np.float32)*np.clip(1-dist*v*.7,0,1)[:,:,None];rgb=Image.fromarray(a.astype(np.uint8))
    elif kind=='mirror':
        mirrored=ImageOps.mirror(image);return crossfade(image,mirrored,v)
    elif kind=='tile':
        cols=max(1,int(round(p['columns'])));rows=max(1,int(round(p['rows'])));out=Image.new('RGBA',image.size);cells={}
        for y in range(rows):
            for x in range(cols):
                x0=round(x*w/cols);x1=round((x+1)*w/cols);y0=round(y*h/rows);y1=round((y+1)*h/rows)
                cell_size=(x1-x0,y1-y0)
                if cell_size not in cells:cells[cell_size]=image.resize(cell_size,Image.Resampling.BILINEAR)
                out.alpha_composite(cells[cell_size],(x0,y0))
        return out
    elif kind=='liquid':
        if v<=0:return image
        x,y=coordinates(image.size);phase=t*p['speed']*math.tau;wave=p['waves']
        # Bilinear remapping avoids the block/noise appearance of nearest sampling.
        sx=np.clip(x+np.sin(y/h*math.tau*wave+phase)*v*w*.035,0,w-1);sy=np.clip(y+np.cos(x/w*math.tau*(wave*.7)+phase*.73)*v*h*.035,0,h-1)
        x0=sx.astype(np.int32);y0=sy.astype(np.int32);x1=np.minimum(x0+1,w-1);y1=np.minimum(y0+1,h-1);fx=(sx-x0)[:,:,None];fy=(sy-y0)[:,:,None]
        a=np.asarray(image,dtype=np.float32);out=a[y0,x0]*(1-fx)*(1-fy)+a[y0,x1]*fx*(1-fy)+a[y1,x0]*(1-fx)*fy+a[y1,x1]*fx*fy
        return Image.fromarray(np.clip(out,0,255).astype(np.uint8),'RGBA')
    elif kind=='jpeg_loss':
        if v<=0:return image
        buffer=io.BytesIO();rgb.save(buffer,format='JPEG',quality=max(3,round(97-v*90)),subsampling=2);buffer.seek(0)
        with Image.open(buffer) as result:rgb=result.convert('RGB')
    rgb=rgb.convert('RGBA');rgb.putalpha(alpha);return rgb
