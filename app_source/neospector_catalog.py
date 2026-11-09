"""Factory treatments are editable groups of independent registered operators.

Each call creates fresh identities. No render is flattened, no executable preset
code is imported, and the existing 21 operators retain their serialised names.
"""
from effects_engine import make_effect
from module_engine import group_effects, expose_group_front

FACTORY_GROUPS={
 'Directional Wipe':('Transition',[('transition_timing',{'smooth':.7}),('transition_reveal',{'angle':0,'softness':.025})]),
 'Iris Bloom':('Transition',[('transition_timing',{'smooth':.7}),('transition_iris',{'center_x':.5,'center_y':.5,'softness':.12})]),
 'Pixel Scatter':('Transition',[('transition_timing',{'smooth':.15}),('transition_pixels',{'cell':36,'randomness':1,'softness':.02})]),
 'Glitch Tear':('Transition',[('transition_timing',{'smooth':.1}),('transition_glitch',{'bands':32,'displace':.3,'noise':.45}),('chroma_shift',{'amount':.12})]),
 'Moving Slide':('Transition',[('transition_timing',{'smooth':.55}),('transition_slide',{'angle':0,'travel':1})]),
 'Soft Dissolve':('Transition',[('transition_timing',{'smooth':.3}),('transition_reveal',{'angle':0,'softness':.5,'amount':0})]),
 'Chroma Bleed':('Colour',[('chroma_shift',{'amount':.23}),('blur',{'amount':.7}),('saturation',{'amount':1.18})]),
 'CCD Afterglow':('Time',[('echo',{'amount':.32,'delay':.12,'taps':2}),('exposure',{'amount':.12}),('saturation',{'amount':.86})]),
 'Liquid Motion':('Spatial',[('liquid',{'amount':.16,'speed':.6,'waves':3}),('frame_blend',{'amount':.2,'delay':.04})]),
 'Mosaic Print':('Texture',[('pixelate',{'amount':.18}),('posterize',{'amount':.35}),('contrast',{'amount':1.15})]),
 'Compact Scan':('Texture',[('scanlines',{'amount':.4,'spacing':4}),('chroma_shift',{'amount':.12}),('contrast',{'amount':1.15})]),
 'Tape Ghost':('Time',[('chroma_shift',{'amount':.18}),('echo',{'amount':.3,'delay':.13,'taps':2}),('liquid',{'amount':.09,'speed':.4})]),
 'River Memory':('Time',[('liquid',{'amount':.13,'speed':.6,'waves':2}),('echo',{'amount':.26,'delay':.16,'taps':2}),('hue',{'amount':8})]),
 'Generation Loss':('Texture',[('jpeg_loss',{'amount':.5}),('saturation',{'amount':.85}),('grain',{'amount':.045})]),
 'Warm Film':('Colour',[('temperature',{'amount':.4}),('contrast',{'amount':1.1}),('grain',{'amount':.035})]),
 'Cold CRT':('Colour',[('temperature',{'amount':-.55}),('scanlines',{'amount':.32}),('vignette',{'amount':.2})]),
 'Solar Bloom':('Colour',[('solarize',{'amount':.45}),('blur',{'amount':.6}),('hue',{'amount':24})]),
 'Embossed Metal':('Texture',[('emboss',{'amount':.65}),('saturation',{'amount':.2}),('contrast',{'amount':1.2})]),
 'Ink Outline':('Texture',[('edge',{'amount':.7}),('invert',{'amount':.85}),('saturation',{'amount':.15})]),
 'Neon Edge':('Colour',[('edge',{'amount':.7}),('duotone',{'amount':.9,'hue':290}),('exposure',{'amount':.3})]),
 'Duotone Poster':('Colour',[('posterize',{'amount':.25}),('duotone',{'amount':.85,'hue':185})]),
 'Ghost Mirror':('Time',[('mirror',{'amount':.45}),('frame_blend',{'amount':.32,'delay':.12}),('tint',{'amount':.2})]),
 'Prism Grid':('Spatial',[('tile',{'columns':3,'rows':2}),('chroma_shift',{'amount':.16}),('hue',{'amount':25})]),
 'Soft Focus':('Light',[('blur',{'amount':2}),('exposure',{'amount':.2}),('vignette',{'amount':.2})]),
 'Dusty Projector':('Texture',[('grain',{'amount':.06}),('temperature',{'amount':.24}),('vignette',{'amount':.35})]),
 'Moonwash':('Light',[('temperature',{'amount':-.4}),('saturation',{'amount':.45}),('gamma',{'amount':1.2})]),
 'Thermal Signal':('Colour',[('threshold',{'amount':.43}),('duotone',{'amount':.88,'hue':30}),('liquid',{'amount':.06})]),
 'Midnight Grain':('Light',[('exposure',{'amount':-.6}),('tint',{'amount':.18}),('grain',{'amount':.05})]),
 'Acid Print':('Colour',[('solarize',{'amount':.45}),('saturation',{'amount':1.7}),('hue',{'amount':65})]),
 'Paper Screen':('Texture',[('pixelate',{'amount':.06}),('emboss',{'amount':.25}),('temperature',{'amount':.15})]),
}

PRIMARY_LABELS={'chroma_shift':'Separation','echo':'Trail','liquid':'Warp','pixelate':'Cells','scanlines':'Depth','frame_blend':'Ghost','jpeg_loss':'Loss','edge':'Outline','emboss':'Relief','duotone':'Colour mix','tile':'Columns','temperature':'Warm / cool','tint':'Tint','solarize':'Solarise','exposure':'Exposure'}

def build_group(name):
    if name not in FACTORY_GROUPS:raise ValueError('Unknown factory group: '+str(name))
    family,recipe=FACTORY_GROUPS[name]
    rack=[make_effect(kind,values) for kind,values in recipe]
    promote=[]
    for fx in rack[:3]:
        key=next(iter(fx.params))
        promote.append((fx.id,key,PRIMARY_LABELS.get(fx.kind,fx.kind.replace('_',' ').title())))
    group=group_effects(rack,[e.id for e in rack],name,promote)
    group.extra.update(factory_group=name,family=family,recipe_version=1)
    return expose_group_front(group)
