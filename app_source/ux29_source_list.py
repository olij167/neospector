"""Live source discovery for one browser list. Never starts a device on browse."""
from __future__ import annotations

def list_all_sources():
    from live_sources import enumerate_devices
    from visual_capture import list_sources
    from system_audio import discover_audio_sources
    found=[];notes=[]
    try:
        hardware=enumerate_devices()
        for item in hardware.get('camera',()):
            found.append({'kind':'camera','label':'Camera · '+str(item),'device':item})
        for item in hardware.get('microphone',()):
            if item!='test':found.append({'kind':'microphone','label':'Mic · '+str(item),'device':item})
    except Exception as exc:notes.append('Devices: '+str(exc))
    try:
        for item in list_sources():
            if item.get('kind') in ('screen','window'):
                found.append({'kind':item['kind'],'label':('Window · ' if item['kind']=='window' else 'Display · ')+item.get('name','Screen'),'device':item})
    except Exception as exc:notes.append('Screen listing: '+str(exc))
    try:
        audio,details=discover_audio_sources()
        notes.extend(details)
        for item in audio:
            if item.get('kind') in ('system','application'):
                found.append({'kind':item['kind'],'label':item.get('label','Audio input'),'device':item})
    except Exception as exc:notes.append('Audio listing: '+str(exc))
    # A stable row identifier is per scan. Avoid merging two distinct apps that
    # happen to display the same title; their stream/device metadata differs.
    return found,notes
