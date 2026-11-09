"""Explicit, pinned authority for one visible treatment owner."""
from conductor_targets import DEFAULTS
from dataclasses import dataclass

@dataclass
class OwnerRackAdapter:
    app: object
    project: object
    owner: object
    scope: str
    parent: object = None

    def target(self):
        if self.app.project is not self.project:return None,None
        if self.scope=='Master':return self.project.master_rack,self.project
        if self.scope=='Transition':return self.project.transition_rack,self.project
        if not any(layer is (self.parent if self.scope=='Clip' else self.owner) for layer in self.project.layers):return None,None
        if self.scope=='Clip':
            state=getattr(self,'queue_state',self.parent)
            if state is not self.parent:
                from queue_policies import visual_state_at
                if visual_state_at(self.parent,getattr(self.app,'playhead',0)) is not state:return None,None
            if not any(clip is self.owner for clip in state.clips):return None,None
        editing=getattr(self,'edit_owner',None) or self.owner
        return editing.rack,editing

    @property
    def key(self):return self.scope,getattr(self.owner,'id',None)

    @property
    def title(self):
        if self.scope=='Master':return 'Whole picture'
        if self.scope=='Transition':return 'A/B Transition'
        if self.scope=='Layer':return self.owner.extra.get('voice',self.owner.name)
        asset=self.project.asset(self.owner.asset_id)
        return 'Clip · '+(asset.name if asset else 'Missing source')

    def state(self):
        rack,owner=self.target()
        if rack is None:return 'Unavailable'
        from module_engine import compile_rack
        count=len(compile_rack(rack)) if getattr(owner,'enabled',True) else 0;parts=[f'FX {count} on']
        if self.scope=='Layer':
            state,clips,mode=current_sources(self.owner,getattr(self.app,'playhead',0))
            assets=[self.project.asset(mode.get('camera_id'))] if mode['mode']=='camera' else [self.project.asset(clip.asset_id) for clip in clips]
            names=list(dict.fromkeys(asset.name for asset in assets if asset))
            parts.append(('Camera · ' if mode['mode']=='camera' else '')+(', '.join(names) if names else 'No current source'))
        if self.scope=='Master':parts.append('Final output')
        if self.scope=='Transition':parts.append('A/B bridge only · endpoints unchanged')
        eligible_owner=self.scope=='Layer'
        allowed=eligible_owner and bool(self.project.conductor.extra.get('evolve_treatment',DEFAULTS['evolve_treatment']))
        locked=bool(getattr(owner,'locked',False))
        protected=bool(getattr(owner,'manual',False))
        eligible=not locked and (not rack or any(f.enabled and not f.extra.get('locked') and any(not p.extra.get('conductor_locked') and (not p.keyframes or p.extra.get('conductor_generated')) for p in f.params.values()) for f in rack))
        running=bool(getattr(self.app,'playing',False)) and bool(getattr(self.app,'evolve',None) and self.app.evolve.get())
        parts.append('Conductor ● active' if allowed and eligible and running else 'Conductor ○ allowed' if allowed and eligible else 'Conductor protected' if allowed else 'Conductor off')
        if locked:parts.append('Locked')
        if protected or any(p.extra.get('conductor_locked') for f in rack for p in f.params.values()):parts.append('Manual')
        return ' · '.join(parts)


def current_sources(layer,t):
    """Return every occurrence rendered at the queue clock, including overlaps."""
    from queue_policies import visual_state_at
    from queue_model import queue_position,mode_at
    state=visual_state_at(layer,t);mode=mode_at(state,t)
    if mode['mode']=='camera':return state,[],mode
    position=queue_position(state,t)
    clips=[clip for clip in sorted(state.clips,key=lambda c:(c.start,c.channel,c.id)) if clip.start-1e-7<=position<clip.end-1e-7]
    if mode['mode']=='hold':clips=[clip for clip in clips if clip.id==mode.get('clip_id')]
    return state,clips,mode


CLIP_TREATMENT_FIELDS=('opacity','scale','x','y','rotation','rack','effects','mask','fit')

def preserve_clip_treatment_history(before,project,t):
    """Archive changed occurrence treatment without replacing live owner objects.

    Transactions and completed gestures already own a before snapshot. Reuse its
    affected layer only, and leave intervals preserved by live controls alone.
    """
    import copy
    from dataclasses import fields
    from sequencer_model import Layer,_encode
    t=float(t)
    if t<=0:return
    old_layers={layer['id']:layer for layer in before.get('layers',[])}
    model_fields={field.name for field in fields(Layer)}
    for layer in project.layers:
        old=old_layers.get(layer.id)
        if old is None:continue
        old_clips={clip['id']:clip for clip in old.get('clips',[])}
        changed=any(clip.id in old_clips and any(_encode(getattr(clip,key))!=old_clips[clip.id].get(key) for key in CLIP_TREATMENT_FIELDS) for clip in layer.clips)
        if not changed:continue
        history=layer.extra.get('queue_history',[])
        if any(float(record['start'])<t and float(record['end'])>=t-1e-7 for record in history):continue
        start=max((float(record['end']) for record in history if float(record['end'])<=t),default=0.)
        if t<=start+1e-7:continue
        extra={**old.get('extra',{}),**{key:value for key,value in old.items() if key not in model_fields}}
        extra.pop('queue_history',None)
        state={'id':old['id'],'name':old['name'],'clips':copy.deepcopy(old.get('clips',[])),
               'transitions':copy.deepcopy(old.get('transitions',[])),'extra':copy.deepcopy(extra)}
        history=layer.extra.setdefault('queue_history',[])
        history.append({'start':start,'end':t,'state':state});history.sort(key=lambda record:record['start'])
