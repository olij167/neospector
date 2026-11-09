"""Project-derived import destinations shared by both browser surfaces.

Labels remain compatible with saved and in-flight import requests. A destination
is validated again at commit, because the project's channel set may have changed
while a browser was open.
"""
from __future__ import annotations
from visual_channels import channels

LIBRARY='Library only'
SOUND='Add to sound queue'

def visual_roles(project):
    return tuple(layer.extra['voice'] for layer in channels(project))

def choices(project):
    roles=visual_roles(project)
    return (LIBRARY,*(f'Add to {role} queue' for role in roles),SOUND,
            *(f'Video + Sound → {role}' for role in roles))

def destination(project,label):
    """Return (action, role), rejecting stale or fabricated channel labels."""
    if label==LIBRARY:return 'library',None
    if label==SOUND:return 'sound',None
    for role in visual_roles(project):
        if label==f'Add to {role} queue':return 'visual',role
        if label==f'Video + Sound → {role}':return 'visual_sound',role
    raise ValueError('Import destination is no longer available. Choose a current channel.')

def apply(app,ids,label):
    try:action,role=destination(app.project,label)
    except ValueError as exc:
        app.update_status(str(exc));return False
    if action=='library':return True
    if action=='sound':app.queue_sound_selected(ids);return True
    # Keep the existing all-or-nothing compatibility check: audio-only items
    # never masquerade as picture queue entries.
    eligible=[i for i in ids if app.project.asset(i).kind!='audio']
    if not eligible:
        app.update_status('This destination needs a picture or video. Choose the sound queue for audio.');return False
    app.queue_selected(role,asset_ids=eligible)
    if action=='visual_sound':
        app.edit_sound_route('voice:'+role,{'enabled':True,'muted':False,'sound':True,'react':True,'monitor':True})
        app.prepare_sound_analysis()
        if not app.playing and not app.reviewing:app.toggle_play()
    return True
