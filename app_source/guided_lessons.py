"""Short, observable lessons over the real workspace model.

Descriptions are inert data.  Only the fixed condition vocabulary below reads
the live application; a project cannot install callbacks through lesson content.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    instruction: str
    condition: str
    target: str
    hint: str


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str
    area: str
    steps: tuple[Step, ...]


def lesson(identifier, title, area, *rows):
    return Lesson(identifier, title, area, tuple(Step(*row) for row in rows))


LESSONS = (
    lesson('library.import', 'Put a picture in a queue', 'Library',
           ('Show Library and choose an image or video. Library access alone does not add it to this project.', 'panel.library', 'panel.library.toggle', 'Use Import media or browse an existing album.'),
           ('Include a picture in this project.', 'visual.asset', 'project.import-media', 'Choose a local image or video in Library.'),
           ('Queue that picture in A or B; selecting a tile only previews it.', 'visual.queue', 'panel.queues.toggle', 'Use Add to A or B in Library.')),
    lesson('queues.play', 'Play a visual queue', 'Queues',
           ('Open Queues and find A or B.', 'panel.queues', 'panel.queues.toggle', 'Choose Visual A or Visual B in the Media desk. Playback continues.'),
           ('Put a picture into a visual queue.', 'visual.queue', 'project.import-media', 'Import a picture and use its Add to channel action.'),
           ('Start Programme playback; Play now on a queue is a separate choice.', 'playing', 'transport.play', 'Press Space outside a text field or use Play.')),
    lesson('rack.effect', 'Play with an effect', 'Module Rack',
           ('Choose Visual A, Visual B or Final Output above the rack.', 'panel.rack', 'panel.rack.toggle', 'The breadcrumb above the modules names exactly what you are editing.'),
           ('Add an effect from Library → Modules.', 'rack.effect', 'rack.add-module', 'Press + Module on the rack you want to change, then choose a module from Library.'),
           ('Move one control and watch the Programme change.', 'parameter.edited', 'rack.add-module', 'Use a large control on the module face; Undo restores it.')),
    lesson('rack.react', 'Make an effect react to sound', 'React / Keys',
           ('Add or find an effect in the rack.', 'rack.effect', 'rack.add-module', 'Pick a module from Library.'),
           ('Choose React on one control; this does not turn a microphone on.', 'parameter.react', 'panel.rack.toggle', 'The per-control React button opens its attached response controls.'),
           ('Adjust that control’s response amount or timing.', 'parameter.edited', 'panel.rack.toggle', 'Use the controls inside that module to choose a reaction input.')),
    lesson('rack.keys', 'Animate a control', 'React / Keys',
           ('Find a module with a control to animate.', 'rack.effect', 'rack.add-module', 'Use Add from Library → Modules.'),
           ('Set a keyframe in its control editor.', 'parameter.keys', 'panel.rack.toggle', 'Open the control companion and choose Keys.'),
           ('Move to a new time and change the keyframed value.', 'parameter.keycount', 'timing.precision', 'Precise timing gives finer placement.')),
    lesson('rack.group', 'Build a reusable module', 'Modules',
           ('Place at least two modules in one rack.', 'rack.two', 'rack.add-module', 'Add another effect from Library → Modules.'),
           ('Select adjacent modules and Group them.', 'rack.group', 'rack.group', 'Use the contextual Group action; internal parameters remain editable.'),
           ('Save the group to Library → Modules.', 'module.saved', 'panel.library.toggle', 'Open the group menu and choose Save to Library.')),
    lesson('conductor.cue', 'Prepare and take a composition', 'Conductor',
           ('Open Conductor.', 'panel.conductor', 'panel.conductor.toggle', 'Use the Conductor edge tab.'),
           ('Capture the current rack or Generate + a new cue.', 'cue.prepared', 'panel.conductor.toggle', 'Preparing a cue does not change the live picture.'),
           ('Take Next when ready to hear and see the new composition.', 'cue.taken', 'panel.conductor.toggle', 'Next takes the prepared cue; Loop and Auto-new govern later cues.')),
    lesson('audio.route', 'Set a sound input', 'Audio',
           ('Open Audio.', 'panel.audio', 'panel.audio.toggle', 'The Audio panel keeps Sound, React and Monitor purposes separate.'),
           ('Enable a source deliberately.', 'audio.enabled', 'panel.audio.toggle', 'Choose a file, microphone or available input and turn it on.'),
           ('Confirm its Sound or React purpose in the route controls.', 'audio.routed', 'panel.audio.toggle', 'Monitor alone does not enter Programme recordings.')),
    lesson('visual.capture', 'Bring another application on screen', 'Screen / Window',
           ('Open the visual source chooser from a channel.', 'visual.chooser', 'input.visual.choose', 'Choose Screen / Window in A or B; no sharing begins yet.'),
           ('Preview, crop and choose Use in channel.', 'visual.assigned', 'panel.queues.toggle', 'Only the selected crop is retained; pair audio separately.'),
           ('Stop sharing from the channel or top control.', 'visual.stopped', 'panel.queues.toggle', 'This keeps the queue and closes the capture.')),
    lesson('output.viewer', 'See the clean Programme', 'Programme',
           ('Open Output Viewer.', 'output.open', 'output.viewer', 'The viewer shows Programme without the editing controls.'),
           ('Start playback and compare it to the preview.', 'playing', 'transport.play', 'Preview quality and output settings are separate.'),
           ('Stop playback when you are done.', 'stopped', 'transport.stop', 'The output stays available for the next performance.')),
    lesson('record.result', 'Record and replay a result', 'Record / Export',
           ('Review Record Settings before starting.', 'record.settings', 'record.settings', 'Choose a destination and profile.'),
           ('Start a recording yourself.', 'record.started', 'record.toggle', 'Recording never starts from a lesson automatically.'),
           ('Stop recording and find the finalized take in Drafts.', 'record.finished', 'project.drafts', 'Wait for finalization before switching projects.')),
    lesson('workspace.shape', 'Arrange your workspace', 'Workspaces',
           ('Choose a task workspace such as Live or Sequence.', 'workspace.switched', 'workspace.switch', 'Use the workspace selector.'),
           ('Show or hide a panel with its edge tab.', 'panel.changed', 'panel.library.toggle', 'Hiding a panel does not turn off its source.'),
           ('Save your arrangement as a custom workspace.', 'workspace.saved', 'workspace.save-as', 'Name it from the workspace menu.')),
    lesson('precision.timing', 'Fine tune a sequence', 'Precision',
           ('Open Precise timing.', 'timing.open', 'timing.precision', 'This is a focused view of the same project.'),
           ('Place a picture in a queue to give it an occurrence.', 'visual.queue', 'panel.queues.toggle', 'A Library asset and its queue occurrence have different settings.'),
           ('Make a timing edit and use Undo if needed.', 'project.edited', 'timing.precision', 'Timing changes use normal project history.')),
)

BY_ID = {item.id: item for item in LESSONS}
RECIPES = {
    'Quick live setup': ('visual.capture', 'audio.route', 'rack.effect', 'conductor.cue', 'output.viewer', 'record.result'),
    'Quick video sequence': ('library.import', 'queues.play', 'precision.timing', 'rack.react', 'record.result'),
    'First reusable module': ('rack.effect', 'rack.group'),
    'Use another application': ('visual.capture', 'rack.effect', 'record.result'),
}


def _effects(app):
    p = app.project
    return [fx for rack in [p.master_rack] + [layer.rack for layer in p.layers] for fx in rack]


def _parameters(app):
    from module_engine import children
    def walk(fx):
        yield from fx.params.values()
        if fx.kind == 'module':
            for child in children(fx):yield from walk(child)
    for fx in _effects(app):yield from walk(fx)


def snapshot(app):
    """Fixed observable state; no help text or project payload is evaluated."""
    from composition_queue import state as cue_state
    from queue_model import mode_at
    p = app.project
    parameters = list(_parameters(app))
    effects = _effects(app)
    visual = [a for a in p.assets.values() if a.kind in ('image', 'video')]
    live_visual = []
    for layer in p.layers:
        source = mode_at(layer, app.programme_time() if app.playing else app.playhead)
        asset = p.asset(source.get('camera_id', '')) if source.get('mode') == 'camera' else None
        if asset and asset.kind in ('screen', 'window'):
            live_visual.append(asset)
    sharing = any(source.camera and source.camera.state in ('starting', 'live')
                  for key,source in app.live.camera_sources.items()
                  if '"kind": "screen"' in key or '"kind": "window"' in key)
    routes = list(p.extra.get('sound_routes', {}).values())
    cue = cue_state(p)
    return {
        'project.id':p.id, 'project.revision':app.revision,
        'visual.asset':len(visual)>0,
        'visual.queue':any(layer.clips for layer in p.layers if layer.extra.get('voice')),
        'rack.effect':bool(effects), 'rack.two':any(len(rack)>=2 for rack in [p.master_rack]+[layer.rack for layer in p.layers]),
        'rack.group':any(fx.kind=='module' for fx in effects),
        'parameter.signature':tuple((id(par), round(float(par.value), 6), par.mode, len(par.keyframes),
                                     str(par.source), round(float(par.react_amount), 6)) for par in parameters),
        'parameter.react':any(par.mode=='react' for par in parameters),
        'parameter.keys':any(par.keyframes for par in parameters),
        'parameter.keycount':sum(len(par.keyframes) for par in parameters),
        'cue.prepared':bool(cue['items']), 'cue.active':cue.get('active_id'),
        'audio.enabled':any(isinstance(r,dict) and r.get('enabled') and
                            (r.get('id')!='soundtrack' or bool(p.audio_asset_id)) for r in routes),
        'audio.routed':any(isinstance(r,dict) and r.get('enabled') and (r.get('sound') or r.get('react')) and
                           (r.get('id')!='soundtrack' or bool(p.audio_asset_id)) for r in routes),
        'visual.assigned':bool(live_visual), 'visual.sharing':sharing,
        'visual.chooser':bool(getattr(app,'visual_source_window',None) and app.visual_source_window.winfo_exists()),
        'playing':bool(app.playing), 'output.open':bool(app.output_window and app.output_window.winfo_exists()),
        'record.settings':bool(app.record_settings_window and app.record_settings_window.winfo_exists()),
        'record.active':bool(app.output_recording),
        'record.takes':len(getattr(app,'takes',())),
        'workspace.name':app.workspace_name.get(),
        'workspace.names':tuple(app.workspace_controller.names()),
        'panel.states':tuple(sorted(app.panel_states.items())),
        'timing.open':bool(app.precision_visible.get()),
        'module.saved':sum(1 for item in app.catalog.ingredients() if item.get('kind')=='rack' and
                           (item.get('payload') or {}).get('scope')=='module'),
        **{'panel.'+slug:bool(app.panel_states.get(name)) for slug,name in
           (('library','Library'),('queues','Queues'),('rack','Rack'),('conductor','Conductor'),('audio','Audio'))},
        'panel.rack':bool(app.panel_states.get('Queues') and (app.whole_rack.expanded or any(page.rack_section.expanded for page in app.queue_deck.pages.values() if hasattr(page,'rack_section')))) if getattr(app,'inline_rack_mode',False) else bool(app.panel_states.get('Rack')),
    }


def satisfied(condition, now, start, history):
    """Completion requires a real observable result, including for stop steps."""
    if condition=='parameter.edited':return now['parameter.signature']!=start['parameter.signature']
    if condition=='parameter.keycount':return now['parameter.keycount']>start['parameter.keycount']
    if condition=='module.saved':return now['module.saved']>start['module.saved']
    if condition=='cue.taken':return bool(now['cue.active'] and now['cue.active']!=start['cue.active'])
    if condition=='visual.stopped':return bool(history.get('visual.sharing') and not now['visual.sharing'])
    if condition=='record.started':return bool(history.get('record.active'))
    if condition=='record.finished':return bool(history.get('record.active') and not now['record.active'] and now['record.takes']>start['record.takes'])
    if condition=='workspace.switched':return now['workspace.name']!=start['workspace.name']
    if condition=='workspace.saved':return len(now['workspace.names'])>len(start['workspace.names'])
    if condition=='panel.changed':return now['panel.states']!=start['panel.states']
    if condition=='project.edited':return now['project.revision']>start['project.revision']
    if condition=='stopped':return bool(history.get('playing') and not now['playing'])
    return bool(now.get(condition))


class LessonSession:
    def __init__(self, lesson_id, app):
        self.lesson=BY_ID[lesson_id];self.project_id=app.project.id
        self.start=snapshot(app);self.step_start=dict(self.start);self.last=dict(self.start)
        self.history=dict(self.start);self.index=0;self.paused=False;self.skipped=set()

    def poll(self, app):
        now=snapshot(app)
        self.last=now
        if now['project.id']!=self.project_id:
            self.paused=True;return 'project-changed'
        for key in ('visual.sharing','record.active','playing'):
            self.history[key]=self.history.get(key,False) or now[key]
        if self.paused:return 'paused'
        while self.index<len(self.lesson.steps) and satisfied(self.lesson.steps[self.index].condition,now,self.step_start,self.history):
            self.index+=1;self.step_start=dict(now)
        return 'done' if self.index==len(self.lesson.steps) else 'active'

    def skip(self):
        if self.index<len(self.lesson.steps):
            self.skipped.add(self.index);self.index+=1;self.step_start=dict(self.last)
