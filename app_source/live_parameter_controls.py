"""Shared policies and gesture ownership for live parameter controls."""
from __future__ import annotations

import copy, math

from rack_editing import update_parameter


REACTION_SOURCES = (
    ("reaction_mix", "All audio"),
    ("song", "Music"),
    ("microphone", "Mic"),
)
REACTION_BANDS = (
    ("full", "Full"),
    ("bass", "Bass"),
    ("mid", "Mid"),
    ("high", "High"),
    ("onset", "Hits"),
)
RESPONSE_PRESETS = {
    "Punch": {"attack": .018, "release": .14, "threshold": .01},
    "Smooth": {"attack": .18, "release": .65, "threshold": .02},
    "Swell": {"attack": .65, "release": 1.4, "threshold": .05},
}

_NON_EDIT_RELEASES = {
    "Return", "KP_Enter", "Escape", "Tab", "ISO_Left_Tab",
    "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    "Meta_L", "Meta_R", "Caps_Lock", "Num_Lock",
}


def should_debounce_key(event):
    """True only when a key release can have changed editable text."""
    return getattr(event, "keysym", "") not in _NON_EDIT_RELEASES


def _media_route_cache_key(project):
    events = project.extra.get("sound_events", ())
    takes = project.extra.get("audio_takes", ())
    layers = tuple((id(layer), id(layer.clips), len(layer.clips),
                    id(layer.extra.get("queue_history")), len(layer.extra.get("queue_history", ())))
                   for layer in project.layers)
    return (id(project), project.modified_at, id(events), len(events), id(takes), len(takes),
            id(project.analysis), id(project.waveform), project.audio_asset_id, layers)


def _eligible_media_routes(app):
    """Find routes with real media using document metadata, never queue expansion."""
    project = app.project
    key = _media_route_cache_key(project)
    cached = getattr(app, "_reaction_media_routes", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    eligible = set()

    def asset_can_sound(asset_id):
        asset = project.asset(asset_id)
        return asset is not None and (asset.kind == "audio" or bool(asset.metadata.get("has_audio")))

    def usable_event(event, default_route="soundtrack"):
        if not event.get("enabled", True) or event.get("queue_gap") or not asset_can_sound(event.get("asset_id")):
            return
        asset = project.asset(event.get("asset_id"))
        try:
            duration = float(event.get("duration", asset.duration))
        except (TypeError, ValueError):
            return
        if duration > 0:
            eligible.add(event.get("route_id", default_route))

    raw_events = project.extra.get("sound_events", ())
    for event in raw_events:
        usable_event(event)
    if not project.extra.get("audio_bus_enabled") and not raw_events and asset_can_sound(project.audio_asset_id):
        eligible.add("soundtrack")
    for take in project.extra.get("audio_takes", ()):
        usable_event(take, "")

    for layer in project.layers:
        role = layer.extra.get("voice")
        if role not in ("A", "B", "C", "D"):
            continue
        clips = list(layer.clips)
        for record in layer.extra.get("queue_history", ()):
            clips.extend(record.get("state", {}).get("clips", ()))
        for clip in clips:
            asset_id = clip.get("asset_id") if isinstance(clip, dict) else clip.asset_id
            duration = clip.get("duration", 0) if isinstance(clip, dict) else clip.duration
            if duration > 0 and asset_can_sound(asset_id):
                eligible.add("voice:" + str(role))
                break
    result = frozenset(eligible)
    app._reaction_media_routes = (key, result)
    return result


def _has_signal_data(value):
    try:
        return value is not None and len(value) > 0
    except TypeError:
        return bool(value)


def available_reaction_sources(app):
    """Return ready sources without starting or rerouting any of them."""
    from sound_routes import contribution, source_id
    project = app.project
    ready = []
    event_routes = _eligible_media_routes(app)
    song_ready = _has_signal_data(project.analysis) or _has_signal_data(project.waveform) or "soundtrack" in event_routes
    if song_ready:
        ready.append("song")
    try:states = app.live.source_states()
    except Exception:states = {}
    mic = states.get(source_id(getattr(app, "last_microphone_device", "default")), {})
    if mic.get("state") == "live":
        ready.append("microphone")
    routes = project.extra.get("sound_routes", {})
    mixed = any(contribution(route, "react") > 0 and
                ((rid == "soundtrack" and song_ready) or rid in event_routes or
                 states.get(rid, {}).get("state") == "live")
                for rid, route in routes.items())
    if mixed:
        ready.append("reaction_mix")
    return tuple(ready)


class LiveGesture:
    """Own an application gesture for one stable model identity."""
    def __init__(self, app, kind, valid, message=None):
        self.app = app
        self.kind = kind
        self.valid = valid
        self.message = message or (lambda text: None)
        self.token = None
        self.identity = None

    @property
    def active(self):
        return self.token is not None and self.app.gesture is self.token

    def begin(self, identity):
        if self.active:
            return self.identity == identity and self.current()
        if self.app.gesture is not None:
            self.message("Finish the current control gesture first.")
            return False
        if not self.valid(identity):
            return False
        self.app.begin_gesture(self.kind)
        if self.app.gesture is None:
            self.message("This edit could not start.")
            return False
        self.token = self.app.gesture
        self.identity = identity
        return True

    def current(self):
        if not self.active or not self.valid(self.identity):
            self.message("The edit target changed. Reopen its controls.")
            return False
        return True

    def finish(self):
        token = self.token
        self.token = self.identity = None
        if token is not None and self.app.gesture is token:
            self.app.end_gesture()

    def cancel(self):
        token = self.token
        self.token = self.identity = None
        if token is not None and self.app.gesture is token:
            self.app.cancel_gesture()


def initial_reaction_changes(param, source=None, available=None):
    """Return an immediately expressive binding without flattening authored work.

    First-touch React intentionally behaves like an instrument, not a subtle
    inspector default: the whole routed audio mix drives the full spectrum and
    can travel across the entire native parameter range. Fine control remains
    available in the companion panel.
    """
    changes = {"mode": "react"}
    unconfigured = abs(float(param.react_amount)) < 1e-9
    if source is None and unconfigured:
        source = "reaction_mix"
    if source is not None and source != param.source:
        changes["source"] = source
    if unconfigured:
        midpoint = (param.minimum + param.maximum) * .5
        changes.update(react_amount=1.0 if param.value <= midpoint else -1.0,
                       react_band="full", attack=.018, release=.14, threshold=.01,
                       react_full_range=True)
    if param.keyframes and not param.combine_animation:
        changes["combine_animation"] = True
    return changes


def response_name(param):
    current = (param.attack, param.release, param.threshold)
    for name, values in RESPONSE_PRESETS.items():
        expected = (values["attack"], values["release"], values["threshold"])
        if all(abs(a - b) < 1e-7 for a, b in zip(current, expected)):
            return name
    return "Custom"


def source_status(app, source, available=None):
    """Describe availability without changing audible or monitored routing."""
    project = app.project
    available = available_reaction_sources(app) if available is None else available
    if source == "song":
        ready = "song" in available
        level = float(getattr(getattr(app, "audio_bus", None), "levels", {}).get("soundtrack", 0.0))
        return ("Music · " + ("ready" if ready else "waiting for music"), min(1., max(0., level * 4)))
    if source == "microphone":
        try:
            states = app.live.source_states()
        except Exception:
            states = {}
        from sound_routes import source_id
        state = states.get(source_id(getattr(app, "last_microphone_device", "default")), {})
        level = float(state.get("level", 0.))
        return ("Mic · " + ("live" if state.get("state") == "live" else "start an input in Audio"), min(1., max(0., level * 4)))
    if source == "reaction_mix":
        from sound_routes import contribution
        routes = project.extra.get("sound_routes", {})
        active = [(rid, route) for rid, route in routes.items() if contribution(route, "react") > 0]
        try:states = app.live.source_states()
        except Exception:states = {}
        level = max((float(states.get(rid, {}).get("level", 0.)) * contribution(route, "react") for rid, route in active), default=0.)
        ready = "reaction_mix" in available
        detail = f"{len(active)} routed" if ready else ("routed sources need media or input" if active else "no React routes")
        return ("Reaction mix · " + detail, min(1., max(0., level * 4)))
    if source in ("recorded", "recorded_mix", "song_recorded"):
        return ("Recorded reaction · retained take", 0.)
    return (source.replace("_", " ").title() + " · configured", 0.)


class ParameterGesture:
    """Own one live edit while its project/owner/parameter identity remains valid."""
    def __init__(self, app, resolve, message=None, changed=None):
        self.app = app
        self.resolve = resolve
        self.message = message or (lambda text: None)
        self.changed = changed or (lambda: None)
        self.token = None
        self.param = None
        self.owner = None

    @property
    def active(self):
        return self.token is not None and self.app.gesture is self.token

    def begin(self):
        if self.active:
            return True
        target = self.resolve()
        if target is None:
            self.message("This parameter is no longer editable. Reopen its module.")
            return False
        param, owner = target
        if self.app.gesture is not None:
            self.message("Finish the current control gesture first.")
            return False
        if not self.app.can_edit(owner):
            return False
        self.app.begin_gesture("program")
        if self.app.gesture is None:
            self.message("This parameter could not start an edit.")
            return False
        self.token = self.app.gesture
        self.param = param
        self.owner = owner
        return True

    def _current(self):
        if not self.active:
            return None
        target = self.resolve()
        if target is None or target[0] is not self.param or target[1] is not self.owner:
            self.message("The rack target changed. Reopen this parameter.")
            return None
        return target

    def write_base(self, value):
        if not math.isfinite(float(value)):
            raise ValueError("Enter a finite number.")
        if not self.active and not self.begin():
            return False
        if self._current() is None:
            return False
        param = self.param
        value = max(param.minimum, min(param.maximum, float(value)))
        if hasattr(self.app, "write_parameter"):
            self.app.write_parameter(param, value, self.owner)
        elif param.mode == "animate":
            param.add_keyframe(self.app.gesture_time, value)
            if hasattr(self.owner, "manual"):
                self.owner.manual = True
            param.extra["conductor_locked"] = True
            self.app.changed(redraw=False)
        else:
            param.value = value
            if hasattr(self.owner, "manual"):
                self.owner.manual = True
            param.extra["conductor_locked"] = True
            self.app.changed(redraw=False)
        self.changed()
        return True

    def write_field(self, key, value):
        return self.write_fields({key: value})

    def write_fields(self, changes):
        if not self.active and not self.begin():
            return False
        if self._current() is None:
            return False
        values = dict(changes)
        values.setdefault("conductor_locked", True)
        update_parameter(copy.deepcopy(self.param), values)
        if hasattr(self.app, "parameter_edit_clock"):
            self.app.parameter_edit_clock(self.owner, self.app.gesture_time)
        update_parameter(self.param, values)
        if hasattr(self.owner, "manual"):
            self.owner.manual = True
        self.app.changed(redraw=False)
        self.changed()
        return True

    def finish(self):
        token = self.token
        self.token = self.param = self.owner = None
        if token is not None and self.app.gesture is token:
            self.app.end_gesture()

    def cancel(self):
        token = self.token
        self.token = self.param = self.owner = None
        if token is not None and self.app.gesture is token:
            self.app.cancel_gesture()
