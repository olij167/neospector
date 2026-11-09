"""Portable, renderer-independent sequencing data and snapshot history.

v0.1 documents migrate on load. Unknown fields are retained, live device handles
are never serialized, and manually edited material is protected from mutation.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

FORMAT_VERSION = "1.3.0"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def clamp(value: float, lo: float, hi: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Numeric values must be finite")
    return max(lo, min(hi, value))


@dataclass
class Keyframe:
    time: float
    value: float


@dataclass
class ProgrammableParameter:
    value: float
    minimum: float
    maximum: float
    mode: str = "static"
    keyframes: list[Keyframe] = field(default_factory=list)
    react_band: str = "full"
    react_amount: float = 0.0
    attack: float = 0.08
    release: float = 0.22
    source: str = "song"                 # song | microphone | mix | recorded
    interpolation: str = "linear"       # linear | smooth | hold
    combine_animation: bool = False
    threshold: float = 0.0
    extra: dict = field(default_factory=dict)

    def normalized(self) -> "ProgrammableParameter":
        if not math.isfinite(self.minimum) or not math.isfinite(self.maximum) or self.minimum > self.maximum:
            raise ValueError("Invalid parameter bounds")
        self.value = clamp(self.value, self.minimum, self.maximum)
        if self.mode not in {"static", "animate", "react"}:
            raise ValueError(f"Unsupported parameter mode: {self.mode}")
        ks = {max(0.,float(k.time)): clamp(k.value,self.minimum,self.maximum) for k in self.keyframes}
        self.keyframes = [Keyframe(t,v) for t,v in sorted(ks.items())]
        self.react_amount = clamp(self.react_amount,-1,1)
        self.attack = clamp(self.attack,0,4)
        self.release = clamp(self.release,0,8)
        self.threshold = clamp(self.threshold,0,.99)
        return self

    def animated_value(self, t: float) -> float:
        ks = self.keyframes
        if not ks: return self.value
        if t <= ks[0].time: return ks[0].value
        if t >= ks[-1].time: return ks[-1].value
        # Keyframes are normally short; callers may cache curves for long records.
        import bisect
        i = bisect.bisect_right([k.time for k in ks],t)-1
        a,b = ks[i],ks[i+1]
        if self.interpolation == "hold": return a.value
        f = (t-a.time)/max(1e-9,b.time-a.time)
        if self.interpolation == "smooth": f=f*f*(3-2*f)
        return a.value+(b.value-a.value)*f

    def evaluate(self, t: float, reactive_value: float = 0.) -> float:
        base=self.value
        if self.mode == "animate" or (self.mode == "react" and self.combine_animation):
            base=self.animated_value(t)
        if self.mode == "react":
            v=clamp((reactive_value-self.threshold)/max(.001,1-self.threshold),0,1)
            base += v*self.react_amount*(self.maximum-self.minimum)*(1.0 if self.extra.get('react_full_range') else .5)
        return clamp(base,self.minimum,self.maximum)

    def add_keyframe(self, t: float, value: float | None = None) -> None:
        k=Keyframe(max(0.,float(t)),clamp(self.value if value is None else value,self.minimum,self.maximum))
        self.keyframes=[old for old in self.keyframes if abs(old.time-k.time)>1e-5]+[k]
        self.keyframes.sort(key=lambda x:x.time)
        self.mode="animate"


@dataclass
class Effect:
    id: str
    kind: str
    enabled: bool = True
    params: dict[str,ProgrammableParameter] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)


@dataclass
class Mask:
    kind: str = "none"                  # none | rectangle | ellipse | luma | alpha
    layer_id: str = ""                 # alpha/luma references an earlier layer
    width: float = .7
    height: float = .7
    x: float = 0.
    y: float = 0.
    feather: float = .02
    invert: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class Asset:
    id: str
    path: str
    kind: str
    name: str
    duration: float = 0.
    width: int = 0
    height: int = 0
    metadata: dict[str,Any] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)


@dataclass
class Clip:
    id: str
    asset_id: str
    channel: str = "A"
    start: float = 0.
    duration: float = 3.
    in_point: float = 0.
    fade_in: float = 0.
    fade_out: float = 0.
    opacity: ProgrammableParameter = field(default_factory=lambda:ProgrammableParameter(1,0,1))
    scale: ProgrammableParameter = field(default_factory=lambda:ProgrammableParameter(1,.05,3))
    x: ProgrammableParameter = field(default_factory=lambda:ProgrammableParameter(0,-1.5,1.5))
    y: ProgrammableParameter = field(default_factory=lambda:ProgrammableParameter(0,-1.5,1.5))
    locked: bool = False
    rotation: ProgrammableParameter = field(default_factory=lambda:ProgrammableParameter(0,-180,180))
    manual: bool = False
    timing_locked: bool = False
    source_policy: str = "hold"         # hold | loop
    playback_rate: float = 1.
    fit: str = "contain"                # contain | cover | stretch
    rack: list[Effect] = field(default_factory=list)
    effects: dict[str,ProgrammableParameter] = field(default_factory=lambda:adjustment_parameters())
    mask: Mask = field(default_factory=Mask)
    extra: dict = field(default_factory=dict)

    @property
    def end(self) -> float: return self.start+self.duration


def adjustment_parameters() -> dict[str,ProgrammableParameter]:
    return {
        "brightness":ProgrammableParameter(0,-1,1),
        "contrast":ProgrammableParameter(1,0,3),
        "gamma":ProgrammableParameter(1,.2,3),
        "saturation":ProgrammableParameter(1,0,3),
        "hue":ProgrammableParameter(0,-180,180),
        "sharpness":ProgrammableParameter(0,0,3),
        "blur":ProgrammableParameter(0,0,20),
    }


@dataclass
class Transition:
    id: str
    from_clip: str
    to_clip: str
    kind: str = "dissolve"
    start: float = 0.
    duration: float = .5
    softness: float = .04
    easing: str = "smooth"
    colour: str = "#000000"
    locked: bool = False
    manual: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def end(self) -> float: return self.start+self.duration


@dataclass
class Layer:
    id: str
    name: str
    clips: list[Clip] = field(default_factory=list)
    opacity: ProgrammableParameter = field(default_factory=lambda:ProgrammableParameter(1,0,1))
    mix: ProgrammableParameter = field(default_factory=lambda:ProgrammableParameter(.5,0,1))
    blend_mode: str = "normal"
    enabled: bool = True
    locked: bool = False
    generated: bool = False
    effects: dict[str,ProgrammableParameter] = field(default_factory=adjustment_parameters)
    transitions: list[Transition] = field(default_factory=list)
    mixer_mode: str = "auto"            # auto | crossfade | over | matte
    solo: bool = False
    expanded: bool = True
    rack: list[Effect] = field(default_factory=list)
    mask: Mask = field(default_factory=Mask)
    extra: dict = field(default_factory=dict)


@dataclass
class Conductor:
    energy: float = .5
    intensity: float = .35
    clip_min: float = 3.
    clip_max: float = 7.
    transition_usage: float = .8
    transition_min: float = .35
    transition_max: float = .85
    reaction: float = .3
    layering: float = .2
    max_layers: int = 3
    variation: float = .65
    beat_sync: bool = False
    bpm: float = 120.
    beat_offset: float = 0.
    repeat_gap: int = 2
    energy_links: list[str] = field(default_factory=lambda:["intensity","reaction","layering"])
    transition_preferences: dict[str,str] = field(default_factory=lambda:{
        "dissolve":"prefer","wipe_left":"allow","wipe_right":"allow",
        "wipe_up":"avoid","wipe_down":"avoid","iris_open":"allow",
        "iris_close":"allow","slide_left":"avoid","slide_right":"avoid",
        "fade_colour":"allow","pixel_dissolve":"avoid"})
    effect_preferences: dict[str,str] = field(default_factory=lambda:{
        "saturation":"prefer","contrast":"allow","grain":"avoid",
        "scanlines":"avoid","chroma_shift":"allow","liquid":"avoid","vignette":"allow"})
    reaction_preferences: dict[str,str] = field(default_factory=lambda:{
        "scale":"prefer","x":"avoid","y":"avoid","saturation":"allow","brightness":"avoid"})
    extra: dict = field(default_factory=dict)

    def normalized(self) -> "Conductor":
        for name in ("energy","intensity","reaction","layering","variation","transition_usage"):
            setattr(self,name,clamp(getattr(self,name),0,1))
        self.clip_min=clamp(self.clip_min,.1,120)
        self.clip_max=clamp(self.clip_max,self.clip_min,240)
        self.transition_min=clamp(self.transition_min,.04,8)
        self.transition_max=clamp(self.transition_max,self.transition_min,12)
        self.bpm=clamp(self.bpm,20,300)
        self.max_layers=int(clamp(self.max_layers,1,8))
        self.repeat_gap=int(clamp(self.repeat_gap,0,50))
        return self

    def set_energy(self,value:float) -> None:
        self.energy=clamp(value,0,1)
        mapping={"intensity":self.energy*.75,"reaction":self.energy*.65,"layering":self.energy*.5}
        for name in self.energy_links:
            if name in mapping:setattr(self,name,mapping[name])


@dataclass
class Project:
    name: str = "Untitled Sequence"
    id: str = field(default_factory=lambda:new_id("seq"))
    format_version: str = FORMAT_VERSION
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)
    duration: float = 30.
    width: int = 1280
    height: int = 720
    fps: float = 30.
    audio_asset_id: str | None = None
    assets: dict[str,Asset] = field(default_factory=dict)
    layers: list[Layer] = field(default_factory=list)
    beats: list[float] = field(default_factory=list)
    waveform: list[float] = field(default_factory=list)
    mutation_seed: int = 1
    mutation_complexity: float = .5       # preserved legacy field; no ambiguous UI slider
    conductor: Conductor = field(default_factory=Conductor)
    analysis: dict = field(default_factory=dict)
    recorded_analysis: dict = field(default_factory=dict)
    markers: list[dict] = field(default_factory=list)
    master_rack: list[Effect] = field(default_factory=list)
    transition_rack: list[Effect] = field(default_factory=list)  # A/B-only transient treatment
    background: str = "#000000"
    # Additive schema: legacy documents retain their original layer semantics.
    instrument_mode: bool = False
    voice_mix: ProgrammableParameter = field(default_factory=lambda:ProgrammableParameter(.35,0,1))
    voice_mixer_mode: str = "blend"
    voice_blend: str = "screen"
    extra: dict = field(default_factory=dict)

    def touch(self) -> None: self.modified_at=time.time()
    def ensure_layer(self) -> Layer:
        if not self.layers:self.layers.append(Layer(new_id("lyr"),"Layer 1"))
        return self.layers[0]
    def asset(self,asset_id:str|None) -> Asset|None: return self.assets.get(asset_id or "")
    def clip(self,clip_id:str|None) -> tuple[Layer,Clip]|None:
        for layer in self.layers:
            for clip in layer.clips:
                if clip.id==clip_id:return layer,clip
        return None
    def transition(self,tid:str|None) -> tuple[Layer,Transition]|None:
        for l in self.layers:
            for tr in l.transitions:
                if tr.id==tid:return l,tr
        return None
    def max_end(self) -> float:
        return max([self.duration]+[c.end for l in self.layers for c in l.clips])


@dataclasses.dataclass
class _ConductorCheckpoint:
    """Transient undo entry; never part of a saved project or renderer state."""
    recipe: object


class ProjectHistory:
    def __init__(self,project:Project,limit:int=60):
        self.limit=limit; self.undo_stack=[]; self.redo_stack=[]; self.current=project
    def checkpoint(self) -> None:
        self.checkpoint_snapshot(project_to_dict(self.current))
    def checkpoint_snapshot(self,snapshot:dict) -> None:
        """Take ownership of a freshly serialized, immutable-by-convention snapshot.

        Gesture and transaction callers already require this same before-state.
        Sharing it avoids a second complete serialization on Tk's input thread.
        Undo/redo decode rather than mutate stored snapshots.
        """
        self.undo_stack.append(snapshot)
        if len(self.undo_stack)>self.limit:self.undo_stack.pop(0)
        self.redo_stack.clear()
    def checkpoint_conductor(self,before) -> None:
        self.undo_stack.append(_ConductorCheckpoint(copy.deepcopy(before)))
        if len(self.undo_stack)>self.limit:self.undo_stack.pop(0)
        self.redo_stack.clear()
    def _restore_conductor(self,source,destination) -> Project:
        entry=source.pop();destination.append(_ConductorCheckpoint(copy.deepcopy(self.current.conductor)))
        # Explicit undo may copy the document; high-frequency gesture commits do not.
        self.current=copy.deepcopy(self.current);self.current.conductor=copy.deepcopy(entry.recipe)
        return self.current
    def undo(self) -> Project|None:
        if not self.undo_stack:return None
        if isinstance(self.undo_stack[-1],_ConductorCheckpoint):return self._restore_conductor(self.undo_stack,self.redo_stack)
        self.redo_stack.append(project_to_dict(self.current));self.current=project_from_dict(self.undo_stack.pop());return self.current
    def redo(self) -> Project|None:
        if not self.redo_stack:return None
        if isinstance(self.redo_stack[-1],_ConductorCheckpoint):return self._restore_conductor(self.redo_stack,self.undo_stack)
        self.undo_stack.append(project_to_dict(self.current));self.current=project_from_dict(self.redo_stack.pop());return self.current


def _encode(value):
    if dataclasses.is_dataclass(value):
        result=copy.deepcopy(getattr(value,"extra",{}))
        result.update({f.name:_encode(getattr(value,f.name)) for f in dataclasses.fields(value) if f.name!="extra"})
        return result
    if isinstance(value,dict):return {str(k):_encode(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [_encode(v) for v in value]
    return value


def project_to_dict(project:Project) -> dict:
    data=_encode(project);data["kind"]="omne/sequence";return data


def _finite_tree(value,depth=0):
    if depth>40:raise ValueError("Project nesting is too deep")
    if isinstance(value,float) and not math.isfinite(value):raise ValueError("Project contains a non-finite number")
    if isinstance(value,dict):
        for v in value.values():_finite_tree(v,depth+1)
    elif isinstance(value,list):
        if len(value)>1_000_000:raise ValueError("Project collection exceeds limits")
        for v in value:_finite_tree(v,depth+1)


def _fields(cls,raw,exclude=()):
    names={f.name for f in dataclasses.fields(cls)}
    out={k:copy.deepcopy(v) for k,v in raw.items() if k in names and k not in exclude and k!="extra"}
    out['extra']={**copy.deepcopy(raw.get('extra',{})),**{k:copy.deepcopy(v) for k,v in raw.items() if k not in names and k not in ('kind',)}}
    return out


def _parameter_from(raw,default):
    if raw is None:return copy.deepcopy(default)
    if not isinstance(raw,dict):raise ValueError("Parameter must be an object")
    kw=_fields(ProgrammableParameter,raw,('keyframes',))
    kw.setdefault('value',default.value);kw.setdefault('minimum',default.minimum);kw.setdefault('maximum',default.maximum)
    kw['keyframes']=[Keyframe(float(k['time']),float(k['value'])) for k in raw.get('keyframes',[])]
    return ProgrammableParameter(**kw).normalized()


def _effect_from(raw):
    kw=_fields(Effect,raw,('params',));kw['params']={k:_parameter_from(v,ProgrammableParameter(0,0,1)) for k,v in raw.get('params',{}).items()}
    return Effect(**kw)


def normalise_instrument_roles(project:Project) -> int:
    """Remove the retired special Foreground voice without losing legacy work.

    Standard legacy instruments had A/B/Foreground, so Foreground becomes the
    first free ordinary channel (normally C). If all A-D roles already exist, the
    layer remains intact as an ordinary named layer with no special voice role.
    """
    if not project.instrument_mode:return 0
    roles={'A','B','C','D'};used={l.extra.get('voice') for l in project.layers if l.extra.get('voice') in roles};changed=0
    replacements={}
    for layer in project.layers:
        if layer.extra.get('voice')!='Foreground':continue
        role=next((r for r in ('C','D') if r not in used),None)
        layer.extra.pop('voice',None)
        if role:
            layer.extra['voice']=role;used.add(role);layer.name=role;replacements['Foreground']=role
        elif layer.name.strip().lower()=='foreground':layer.name='Additional visual layer'
        changed+=1
    intent=project.extra.get('playable_intent')
    if isinstance(intent,dict) and isinstance(intent.get('enabled_roles'),list):
        mapped=[]
        for role in intent['enabled_roles']:
            role=replacements.get(role,role)
            if role!='Foreground' and role not in mapped:mapped.append(role)
        intent['enabled_roles']=mapped
    # Preserve legacy video-audio routing when the retired visual role moves.
    target=replacements.get('Foreground')
    if target:
        routes=project.extra.get('sound_routes')
        old_id,new_id='voice:Foreground',f'voice:{target}'
        if isinstance(routes,dict) and old_id in routes:
            route=routes.pop(old_id)
            if new_id in routes:
                project.extra.setdefault('retired_sound_route_conflicts',{})[new_id]=copy.deepcopy(routes[new_id])
            if isinstance(route,dict):
                route['id']=new_id;route['label']=f'{target} · video sound'
            routes[new_id]=route
        history=project.extra.get('sound_route_history')
        if isinstance(history,list):
            for event in history:
                if not isinstance(event,dict) or event.get('id')!=old_id:continue
                event['id']=new_id
                route=event.get('route')
                if isinstance(route,dict):route['id']=new_id;route['label']=f'{target} · video sound'
    if changed:project.extra['visual_role_version']=2
    return changed

def normalise_effect_surface(project:Project) -> int:
    """Move legacy simple adjustments into the visible module rack.

    Older projects stored seven adjustment parameters beside ``rack``. They were
    rendered before rack modules but could not be accounted for from the rack UI.
    Prepending equivalent rack modules preserves that signal order and makes every
    active treatment visible. The conversion is idempotent because migrated native
    parameters are reset to their neutral defaults.
    """
    from effects_engine import EFFECTS,make_effect
    defaults=adjustment_parameters();moved=0
    for owner in [*project.layers,*[clip for layer in project.layers for clip in layer.clips]]:
        migrated=[]
        for name,neutral in defaults.items():
            param=owner.effects.get(name)
            if param is None or name not in EFFECTS:continue
            if dataclasses.asdict(param)==dataclasses.asdict(neutral):continue
            fx=make_effect(name);fx.params['amount']=copy.deepcopy(param)
            fx.extra['migrated_native_adjustment']=True;migrated.append(fx);owner.effects[name]=copy.deepcopy(neutral);moved+=1
        if migrated:owner.rack[:0]=migrated
    if moved:project.extra['effects_surface_version']=2
    return moved


def project_from_dict(data:dict) -> Project:
    if not isinstance(data,dict) or data.get('kind','omne/sequence')!='omne/sequence':raise ValueError('Not an OmN-e Sequence project')
    _finite_tree(data)
    version=str(data.get('format_version','1.0.0-poc.1'))
    if version.split('.')[0]!='1':raise ValueError(f'Unsupported project schema {version}; original file is unchanged')
    kw=_fields(Project,data,('assets','layers','conductor','master_rack','transition_rack','voice_mix'))
    kw['format_version']=FORMAT_VERSION
    p=Project(**kw)
    p.voice_mix=_parameter_from(data.get('voice_mix'),p.voice_mix)
    p.duration=clamp(p.duration,.05,86400);p.width=int(clamp(p.width,16,8192));p.height=int(clamp(p.height,16,8192));p.fps=clamp(p.fps,1,120)
    p.conductor=Conductor(**_fields(Conductor,data.get('conductor',{}))).normalized()
    p.master_rack=[_effect_from(v) for v in data.get('master_rack',[])]
    p.transition_rack=[_effect_from(v) for v in data.get('transition_rack',[])]
    for aid,raw in data.get('assets',{}).items():
        kw=_fields(Asset,raw);kw.setdefault('id',aid);kw.setdefault('name',Path(str(raw.get('path','asset'))).name)
        p.assets[aid]=Asset(**kw)
    for raw in data.get('layers',[]):
        kw=_fields(Layer,raw,('clips','opacity','mix','effects','rack','mask','transitions'))
        l=Layer(**kw);l.opacity=_parameter_from(raw.get('opacity'),l.opacity);l.mix=_parameter_from(raw.get('mix'),l.mix)
        # v0.1 A/B semantics were B-over-A, not a crossfader; retain that intention.
        if 'mixer_mode' not in raw and 'conductor' not in data:l.mixer_mode='over'
        l.effects={k:_parameter_from(raw.get('effects',{}).get(k),v) for k,v in adjustment_parameters().items()}
        for k,v in raw.get('effects',{}).items():
            if k not in l.effects:l.effects[k]=_parameter_from(v,ProgrammableParameter(0,0,1))
        l.rack=[_effect_from(v) for v in raw.get('rack',[])]
        l.mask=Mask(**_fields(Mask,raw.get('mask',{})))
        l.transitions=[Transition(**_fields(Transition,v)) for v in raw.get('transitions',[])]
        for r in raw.get('clips',[]):
            c=Clip(**_fields(Clip,r,('opacity','scale','x','y','rotation','mask','rack','effects')))
            for key in ('opacity','scale','x','y','rotation'):setattr(c,key,_parameter_from(r.get(key),getattr(c,key)))
            c.effects={k:_parameter_from(r.get('effects',{}).get(k),v) for k,v in adjustment_parameters().items()}
            c.mask=Mask(**_fields(Mask,r.get('mask',{})));c.rack=[_effect_from(v) for v in r.get('rack',[])]
            c.channel='B' if c.channel=='B' else 'A';c.start=max(0.,float(c.start));c.duration=clamp(c.duration,1/p.fps,86400);c.playback_rate=clamp(c.playback_rate,.1,4)
            l.clips.append(c)
        p.layers.append(l)
    p.ensure_layer()
    normalise_instrument_roles(p)
    normalise_effect_surface(p)
    from sound_routes import migrate_route_semantics
    migrate_route_semantics(p)
    from module_engine import compile_rack
    from ux16_transitions import validate_transition_rack
    validate_transition_rack(p.transition_rack)
    for rack in [p.master_rack,*[l.rack for l in p.layers],*[c.rack for l in p.layers for c in l.clips]]:
        if any(e.kind=='module' for e in rack):compile_rack(rack)
    return p


def save_project(project:Project,path:str|Path) -> Path:
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    project.touch();tmp=target.with_name(target.name+'.tmp')
    text=json.dumps(project_to_dict(project),indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n'
    tmp.write_text(text,encoding='utf-8');tmp.replace(target);return target


def load_project(path:str|Path) -> Project:
    path=Path(path)
    if path.stat().st_size>100*1024*1024:raise ValueError('Project exceeds 100 MB; source media belongs beside the project, not inside its JSON')
    p=project_from_dict(json.loads(path.read_text(encoding='utf-8')))
    for a in p.assets.values():
        if a.kind in {'image','video','audio'} and a.path and not Path(a.path).is_absolute():a.path=str((path.parent/a.path).resolve())
    from media_identity import reconcile_asset_records
    reconcile_asset_records(p)
    return p


def add_asset(project:Project,*,path:str,kind:str,name:str|None=None,duration:float=0.,width:int=0,height:int=0,metadata:dict|None=None) -> Asset:
    existing=next((a for a in project.assets.values() if a.path==path and a.kind==kind and path and (kind not in ('camera','screen','window') or a.metadata.get('device')==(metadata or {}).get('device'))),None)
    if existing:return existing
    a=Asset(new_id('ast'),path,kind,name or Path(path).name,duration,width,height,metadata or {})
    project.assets[a.id]=a;project.touch();return a


def add_clip(project:Project,layer:Layer,asset:Asset,channel:str,start:float,duration:float|None=None) -> Clip:
    if layer.locked:raise ValueError('Unlock the layer before adding material')
    dur=duration if duration is not None else (asset.duration if asset.duration>0 else 4.)
    c=Clip(new_id('clp'),asset.id,'B' if channel=='B' else 'A',max(0.,start),max(1/project.fps,dur),manual=True)
    layer.clips.append(c);project.duration=max(project.duration,c.end);project.touch();return c


def mutate_project(project:Project,seed:int|None=None,complexity:float|None=None,**kwargs) -> int:
    # Late import avoids a model -> UI/renderer dependency.
    from conductor import generate
    if complexity is not None:project.mutation_complexity=clamp(complexity,0,1)
    return generate(project,project.mutation_seed if seed is None else int(seed),**kwargs)
