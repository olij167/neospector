"""Safe, on-demand hardware choice enumeration for Welcome and Preferences.

Discovery never opens an input. Previously selected but disconnected devices
remain represented so a session can be configured with hardware unplugged.
"""
from __future__ import annotations


def available_input_defaults(app, discover=None):
    if discover is None:
        from live_sources import enumerate_devices
        discover=enumerate_devices
    try:
        found=discover() or {}
    except (OSError, RuntimeError, ValueError):
        found={}
    selections={}
    for kind,selected in (('camera',app.last_camera_device),('microphone',app.last_microphone_device)):
        candidates=[str(selected),*map(str,found.get(kind,()))]
        if kind=='microphone':
            # Pulse/PipeWire outputs are monitor streams, not microphone defaults.
            candidates=[v for v in candidates if v==str(selected) or not v.endswith('.monitor')]
        selections[kind]=tuple(dict.fromkeys(v for v in candidates if v))
    return selections
