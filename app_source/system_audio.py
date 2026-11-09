"""Opt-in system/application audio adapters. No stream rerouting or driver installs.

Linux monitors are read from PulseAudio or PipeWire's Pulse compatibility server.
Application capture uses parec --monitor-stream, and follows a specific stream ID,
not an inferred window. Windows optional loopback is isolated in a child process.
"""
from __future__ import annotations
import json, os, shutil, sys
from pathlib import Path
from process_tools import run_process


def pulse_choices(sources,sinks,streams,*,parec_available=False):
    result=[];monitors={}
    for s in sinks:monitors[str(s['index'])]=s.get('monitor_source_name') or (s.get('monitor_source') if isinstance(s.get('monitor_source'),str) else None) or s['name']+'.monitor'
    seen=set()
    for s in sources:
        name=s.get('name','');monitor=s.get('monitor_of_sink')
        if name.endswith('.monitor') or (monitor is not None and str(monitor) not in ('4294967295','-1','')):
            if name and name not in seen:
                result.append(dict(kind='system',backend='pulse',device=name,label='PC audio · '+s.get('description',name)));seen.add(name)
    # PipeWire/Pulse servers do not always expose sink monitors in the source
    # listing until they are opened.  Sink metadata is authoritative enough to
    # offer the monitor and makes normal desktop audio discoverable up front.
    for sink in sinks:
        name=monitors.get(str(sink.get('index')))
        if name and name not in seen:
            result.append(dict(kind='system',backend='pulse',device=name,label='PC audio · '+sink.get('description',sink.get('name',name))));seen.add(name)
    if parec_available:
        for s in streams:
            props=s.get('properties',{});name=props.get('application.name') or props.get('application.process.binary') or 'Application'
            if 'omne' in name.lower() or 'sequencer' in name.lower():continue
            monitor=monitors.get(str(s.get('sink')))
            if not monitor:continue
            result.append(dict(kind='application',backend='pulse',stream=int(s['index']),device=monitor,pid=props.get('application.process.id',''),application=name,label=f'App · {name} / {props.get("media.name","audio")} [stream {s["index"]}]'))
    return result

def pipewire_app_choices(nodes):
    """Show named PipeWire playback nodes without pretending they can be tapped.

    pw-dump nodes are *not* Pulse sink-input indexes; passing a node id to
    parec --monitor-stream would capture the wrong target or fail outright.
    """
    result=[]
    for node in nodes:
        if node.get('type')!='PipeWire:Interface:Node':continue
        props=(node.get('info') or {}).get('props') or {}
        if props.get('media.class')!='Stream/Output/Audio':continue
        title=props.get('application.name') or props.get('application.process.binary') or props.get('node.nick') or 'Application'
        if 'omne' in str(title).lower() or 'neospector' in str(title).lower():continue
        media=props.get('media.name','')
        label='App · '+str(title)+((' / '+str(media)) if media and media!=title else '')+' · setup needed'
        result.append(dict(kind='application',backend='pipewire',node=node.get('id'),label=label,
                           application=title,capture_available=False,
                           capture_hint='Install pulseaudio-utils, then Refresh to enable individual application capture.'))
    return result

def discover_audio_sources():
    result=[];notes=[]
    if sys.platform.startswith('linux'):
        pactl=shutil.which('pactl')
        if pactl:
            try:
                def listing(what):return json.loads(run_process([pactl,'-f','json','list',what],timeout=5).stdout.decode('utf-8'))
                result=pulse_choices(listing('sources'),listing('sinks'),listing('sink-inputs'),parec_available=bool(shutil.which('parec')))
                if not shutil.which('parec'):notes.append('Per-application capture needs the existing parec utility; no routing or drivers are changed.')
                if not result:notes.append('No output monitor or playing application was found. Start audio playback, then Refresh.')
            except Exception as exc:notes.append('Device audio listing unavailable: '+str(exc))
        elif shutil.which('wpctl') or shutil.which('pw-cli') or shutil.which('pw-dump'):
            # Identify active applications for orientation while preserving the
            # explicit capture dependency. PipeWire node IDs cannot be passed
            # to parec as Pulse sink-input indexes.
            result.append(dict(kind='system',backend='pulse',device='@DEFAULT_MONITOR@',label='PC audio · Default output (PipeWire)'))
            if shutil.which('pw-dump'):
                try:
                    nodes=json.loads(run_process(['pw-dump'],timeout=5).stdout.decode('utf-8'))
                    result+=pipewire_app_choices(nodes)
                except Exception as exc:notes.append('PipeWire app inspection unavailable: '+str(exc))
            notes.append('Per-app audio unavailable: install pulseaudio-utils (pactl + parec), keep Spotify playing, then Refresh inputs. Whole-PC audio remains available.')
        else:
            notes.append('Device audio listing unavailable: neither pactl nor PipeWire command-line tools were found.')
    elif sys.platform=='win32':
        try:
            # Enumerate in a subprocess: COM ownership must not leak into the UI thread.
            cmd=worker_command({'list':True});cp=run_process(cmd,timeout=10);result=json.loads(cp.stdout)
        except Exception as exc:notes.append('WASAPI loopback needs the optional SoundCard package: '+str(exc))
        notes.append('Per-application Windows capture is not implemented in this build. Device loopback records the selected output mix.')
    else:notes.append('On macOS, select an already-configured loopback/virtual input in Microphone. Native system/app taps are not included in this build.')
    return result,notes

def worker_command(source):
    if getattr(sys,'frozen',False):return [sys.executable,'--audio-loopback-worker',json.dumps(source)]
    return [sys.executable,str(Path(__file__).with_name('system_audio_worker.py')),json.dumps(source)]

def source_command(source,*,rate=24000,ffmpeg='ffmpeg',parec=None):
    if source.get('backend')=='wasapi':return worker_command({**source,'rate':rate})
    if source.get('backend')!='pulse':raise ValueError('Unsupported device audio backend')
    device=str(source.get('device',''))
    if not device:raise ValueError('Select an output monitor')
    if source.get('kind')=='application':
        index=int(source.get('stream',-1))
        if index<0:raise ValueError('Application stream no longer exists')
        tool=parec or shutil.which('parec')
        if not tool:raise ValueError('Application-only capture needs parec (normally supplied by pulseaudio-utils)')
        return [tool,'--record','--raw','--format=float32le','--channels=1',f'--rate={rate}','--latency-msec=50',f'--device={device}',f'--monitor-stream={index}','--client-name=OmN-e Input','--stream-name=OmN-e application reaction']
    return [str(ffmpeg),'-hide_banner','-loglevel','warning','-nostdin','-f','pulse','-i',device,'-vn','-ac','1','-ar',str(rate),'-f','f32le','pipe:1']

def validate_application(source):
    if source.get('kind')!='application':return
    data=json.loads(run_process(['pactl','-f','json','list','sink-inputs'],timeout=5).stdout)
    found=next((s for s in data if int(s.get('index',-1))==int(source.get('stream',-2))),None)
    if found is None:raise ValueError('That application audio stream ended. Refresh and select its new stream.')
    props=found.get('properties',{})
    if source.get('pid') and source['pid']!=props.get('application.process.id'):raise ValueError('Application stream identity changed. Refresh the device list.')
