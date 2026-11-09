from __future__ import annotations

import array
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from sequencer_model import Asset, Clip, Layer, Project

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover
    Image = ImageDraw = ImageFont = None


VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mts", ".m2ts", ".webm"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}


def find_tool(name: str) -> str | None:
    exe = name + ".exe" if os.name == "nt" else name
    base = Path(__file__).resolve().parent
    candidates = [base / "tools" / exe, base / exe]
    meipass = getattr(__import__("sys"), "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "tools" / exe)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which(name)


FFMPEG = find_tool("ffmpeg") or "ffmpeg"
FFPROBE = find_tool("ffprobe") or "ffprobe"
FFPLAY = find_tool("ffplay")


def ffplay_audio_command(path: str | Path, start: float = 0.0, *, executable: str | None = None) -> list[str]:
    """Build the argument-vector for local transport audio playback.

    The editor never invokes a shell, so user filenames remain ordinary argv
    data. ffplay is bundled in native builds when transport audio is enabled.
    """
    player = executable or FFPLAY
    if not player:
        raise RuntimeError("ffplay is unavailable; transport will remain visual-only")
    return [
        str(player), "-hide_banner", "-loglevel", "quiet",
        "-nodisp", "-autoexit", "-ss", f"{max(0.0, float(start)):.3f}", str(path),
    ]


def kind_for_path(path: str | Path) -> str | None:
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    return None


def _rate(value: str | float | int | None) -> float:
    try:
        if isinstance(value, str) and "/" in value:
            a, b = value.split("/", 1)
            return float(a) / float(b)
        return float(value or 0.0)
    except Exception:
        return 0.0


def probe_media(path: str | Path) -> dict:
    target = str(Path(path).expanduser())
    cp = subprocess.run(
        [FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", target],
        capture_output=True, text=True, timeout=20,
    )
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or "ffprobe failed").strip())
    data = json.loads(cp.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    duration = 0.0
    for source in (video, audio, fmt):
        try:
            duration = max(duration, float(source.get("duration") or 0.0))
        except Exception:
            pass
    return {
        "duration": duration,
        "width": int((video or {}).get("width") or 0),
        "height": int((video or {}).get("height") or 0),
        "fps": _rate((video or {}).get("avg_frame_rate") or (video or {}).get("r_frame_rate")),
        "has_video": video is not None,
        "has_audio": audio is not None,
        "codec": (video or audio or {}).get("codec_name", ""),
        "colour_transfer": (video or {}).get("color_transfer", ""),
        "pixel_format": (video or {}).get("pix_fmt", ""),
    }


# v0.2: video is evaluated by the same Programme compositor and streamed as frames.
# The encoder argument vector is bounded; only the small audio graph lives in a file.
EXPORT_PROFILES={
    'web':{'label':'Web · H.264 / AAC','extension':'.mp4','video':['-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p'],'audio':['-c:a','aac','-b:a','192k']},
    'small':{'label':'Small file · H.264 / AAC','extension':'.mp4','video':['-c:v','libx264','-preset','fast','-crf','25','-pix_fmt','yuv420p'],'audio':['-c:a','aac','-b:a','128k']},
    'master':{'label':'Lossless master · FFV1 / PCM','extension':'.mkv','video':['-c:v','ffv1','-level','3','-pix_fmt','bgra'],'audio':['-c:a','pcm_s16le']},
    'alpha':{'label':'Transparent · PNG / PCM','extension':'.mov','video':['-c:v','png','-pix_fmt','rgba'],'audio':['-c:a','pcm_s16le']},
}


def analyze_audio(path,waveform_points=1200):
    from signal_engine import analyze_file
    info=analyze_file(path,ffmpeg=FFMPEG)
    return info['duration'],info['waveform'],info['onsets']


def extract_frame(path,t,width=900):
    from process_tools import run_process
    cmd=[FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{max(0.,t):.6f}','-i',str(path),'-frames:v','1','-vf',f'scale=min({width}\\,iw):-2','-threads','1','-f','image2pipe','-vcodec','png','pipe:1']
    return run_process(cmd,timeout=20).stdout


def _run(cmd,progress=None,cancel=None):
    from process_tools import run_process
    if progress:progress('Running media process…')
    return run_process(cmd,cancel=cancel,timeout=600)


def _all_parameters(project,*,active_only=False,editable_only=False,start=0.,end=None):
    """Enumerate actual parameter owners; optional range/lock filtering is explicit."""
    end=project.max_end() if end is None else end
    def rack_parameters(rack):
        if active_only:
            from module_engine import compile_rack
            rack=compile_rack(rack)
        for fx in rack:
            if not active_only or fx.enabled:yield from fx.params.values()
    if project.instrument_mode:yield project.voice_mix
    yield from rack_parameters(project.master_rack)
    solo=any(l.solo and l.enabled for l in project.layers)
    for l in project.layers:
        if editable_only and l.locked:continue
        if active_only and (not l.enabled or (solo and not l.solo)):continue
        yield l.opacity;yield l.mix;yield from l.effects.values()
        yield from rack_parameters(l.rack)
        for c in l.clips:
            if editable_only and c.locked:continue
            if active_only and not (c.end>start and c.start<end):continue
            for name in ('opacity','scale','x','y','rotation'):yield getattr(c,name)
            yield from c.effects.values()
            yield from rack_parameters(c.rack)


def preflight_export(project,output,*,overwrite=False,start=0.,end=None):
    output=Path(output).expanduser().resolve()
    if output.exists() and not overwrite:raise FileExistsError('Destination already exists. Choose another name or explicitly approve replacement.')
    sources=[Path(a.path).expanduser().resolve() for a in project.assets.values() if a.path and a.kind in {'video','image','audio'}]
    if output in sources:raise ValueError('Export cannot overwrite source media')
    if output.is_dir():raise ValueError('Choose an output filename, not a folder')
    if end is None:end=project.max_end()
    if not 0<=start<end<=project.max_end()+1e-5:raise ValueError('Export range must be inside the sequence')
    from effects_engine import BLEND_MODES,EFFECTS
    needed=set();effects=list(project.master_rack)
    solo=any(l.solo and l.enabled for l in project.layers)
    for l in project.layers:
        if not l.enabled or (solo and not l.solo):continue
        if l.blend_mode not in BLEND_MODES:raise ValueError(f'Unsupported blend mode: {l.blend_mode}')
        effects.extend(l.rack)
        for c in l.clips:
            if c.end>start and c.start<end:needed.add(c.asset_id);effects.extend(c.rack)
    if project.extra.get('audio_bus_enabled'):
        from audio_bus import sound_events
        needed.update(e['asset_id'] for e in sound_events(project))
    elif project.audio_asset_id:needed.add(project.audio_asset_id)
    for track in project.extra.get('audio_takes',[]):
        if track.get('enabled'):needed.add(track['asset_id'])
    for aid in needed:
        a=project.asset(aid)
        if a is None:raise ValueError('A clip references a missing asset; relink it before export')
        if a.kind in ('camera','screen','window'):raise ValueError('Live visual input is not replayable. Retain or record its cropped frames before offline export.')
        if a.kind in {'video','image','audio'} and not Path(a.path).is_file():raise FileNotFoundError(f'Missing media: {a.name}. Relink it before export.')
        transfer=str(a.metadata.get('colour_transfer',''))
        if transfer in {'smpte2084','arib-std-b67'}:raise ValueError(f'{a.name} is HDR. Prepare an SDR derivative before using this SDR compositor.')
    from module_engine import compile_rack
    # Validate each top-level rack separately: their temporal budgets are local.
    for rack in [project.master_rack,*[l.rack for l in project.layers],*[c.rack for l in project.layers for c in l.clips]]:
        compile_rack(rack)
    from sound_routes import external_reaction_active,external_intervals
    if external_intervals(project,'sound',start,end) and not project.extra.get('capture_range'):
        raise ValueError('Live Sound must be retained and captured before offline export. Capture Recent, then export the take.')
    if external_reaction_active(project) and not project.extra.get('capture_range'):
        for param in _all_parameters(project,active_only=True,start=start,end=end):
            if param.mode=='react' and param.source=='reaction_mix':raise ValueError('Mixed live reaction must be retained and captured before offline export. Capture Recent, then export the take.')
    from queue_model import mode_at
    for layer in project.layers:
        moments=[start]+[sw['start'] for sw in layer.extra.get('source_switches',[]) if start<sw['start']<end]
        if layer.enabled and any(mode_at(layer,t)['mode']=='camera' for t in moments):raise ValueError('Live visual input must be retained and captured before offline export.')
    for p in _all_parameters(project,active_only=True,start=start,end=end):
        if p.mode=='react' and p.source in {'microphone','mix','device'}:raise ValueError('An effect still uses live microphone input. Record the reaction, then select Recorded Take as its signal source before export.')
        if p.mode=='react' and p.source=='recorded_mix' and not project.extra.get('recorded_mix_analysis'):raise ValueError('Recorded reaction mix is missing. Reopen a retained take.')
        if p.mode=='react' and p.source in {'recorded','song_recorded'} and not (project.extra.get('recorded_analyses',{}).get(p.extra.get('recorded_take_id')) or project.recorded_analysis):raise ValueError('Recorded reaction data is missing. Select Song or record a microphone take.')
    return output


def _dimensions(project,preview=False,size=None):
    if size:w,h=size
    elif preview:
        factor=min(1.,640/project.width,640/project.height);w,h=round(project.width*factor),round(project.height*factor)
    else:w,h=project.width,project.height
    return max(16,int(w)//2*2),max(16,int(h)//2*2)


def build_render_command(project,output,*,preview=False,temp_dir=None,start=0.,end=None,profile='web',size=None,cancel=None,progress=None):
    import math
    from sequencer_model import project_to_dict
    temp=Path(temp_dir or tempfile.mkdtemp(prefix='omne-sequencer-export.'));temp.mkdir(parents=True,exist_ok=True)
    spec=EXPORT_PROFILES['small' if preview else profile];w,h=_dimensions(project,preview,size);fps=float(project.fps)
    end=project.max_end() if end is None else end;frames=max(1,math.ceil((end-start)*fps-1e-8));duration=frames/fps
    cmd=[FFMPEG,'-y','-hide_banner','-loglevel','warning','-threads','2','-f','rawvideo','-pixel_format','rgba','-video_size',f'{w}x{h}','-framerate',f'{fps:.9f}','-i','pipe:0']
    audio=[]
    main=project.asset(project.audio_asset_id)
    if main:audio.append({'asset':main,'start':0.,'gain':1.})
    for tr in project.extra.get('audio_takes',[]):
        a=project.asset(tr.get('asset_id'))
        if a and tr.get('enabled',False):audio.append({'asset':a,'start':float(tr.get('start',0)),'gain':float(tr.get('gain',1))})
    if project.extra.get('audio_bus_enabled'):
        from audio_bus import sound_events,render_audio
        if sound_events(project):
            mixed=temp/'soundtrack.wav';render_audio(project,mixed,start,start+duration,cancel=cancel,progress=progress)
            from sequencer_model import Asset
            audio=[{'asset':Asset('mixed',str(mixed),'audio','Prepared soundtrack',duration=duration),'start':start,'gain':1.}]
        else:audio=[]
    if len(audio)>16:raise ValueError('This build supports up to 16 mixed audio sources')
    filters=[];labels=[]
    for i,track in enumerate(audio,1):
        offset=track['start'];seek=max(0.,start-offset);delay=max(0.,offset-start)
        cmd+=['-ss',f'{seek:.9f}','-i',track['asset'].path]
        label=f'a{i}'
        filters.append(f'[{i}:a:0]aresample=48000,asetpts=PTS-STARTPTS,volume={track["gain"]:.6f},adelay={round(delay*1000)}:all=1,apad,atrim=duration={duration:.9f}[{label}]')
        labels.append(f'[{label}]')
    cmd+=['-map','0:v:0']
    if filters:
        if len(labels)>1:filters.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0:duration=longest,alimiter=limit=0.98,atrim=duration={duration:.9f}[audio]')
        else:filters.append(f'{labels[0]}anull[audio]')
        graph=temp/'audio.ffgraph';graph.write_text(';\n'.join(filters)+'\n',encoding='utf-8')
        cmd+=['-filter_complex_script',str(graph),'-map','[audio]']+spec['audio']
    cmd+=spec['video']+['-threads','2','-t',f'{duration:.9f}']
    if profile in {'web','small'} or preview:cmd+=['-movflags','+faststart']
    cmd+=[str(output)]
    (temp/'project.omne-sequence.json').write_text(json.dumps(project_to_dict(project),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (temp/'command.json').write_text(json.dumps(cmd,ensure_ascii=False,indent=2),encoding='utf-8')
    plan={'renderer':'shared CPU Programme compositor','version':'0.3.3-r3','start':start,'end':end,'frame_count':frames,'duration':duration,'fps':fps,'width':w,'height':h,'profile':profile,'audio':bool(audio),'argv_bytes':sum(len(s.encode())+1 for s in cmd)}
    (temp/'render-plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    return cmd,temp


class RenderFailure(RuntimeError):
    def __init__(self,message,diagnostics):
        super().__init__(f'{message}\n\nDiagnostics: {diagnostics}')
        self.diagnostics=str(diagnostics)


def render_project(project,output,*,preview=False,progress=None,cancel=None,temp_dir=None,start=0.,end=None,profile='web',size=None,overwrite=False,diagnostics_dir=None):
    import math,time,uuid,traceback,copy
    from process_tools import EncoderPipe,run_process,Cancelled
    from programme_renderer import ProgrammeRenderer
    if cancel is not None and cancel.is_set():raise Cancelled('Export cancelled')
    project=copy.deepcopy(project)
    preflight_export(project,output,overwrite=overwrite,start=start,end=end)
    output=Path(output).expanduser().resolve();output.parent.mkdir(parents=True,exist_ok=True)
    report=Path(temp_dir or diagnostics_dir or (output.parent/(output.stem+'.diagnostics')))
    report.mkdir(parents=True,exist_ok=True)
    temporary=output.with_name('.'+output.stem+'.render-'+uuid.uuid4().hex[:8]+output.suffix)
    renderer=None;sink=None;started=time.monotonic();success=False
    try:
        cmd,report=build_render_command(project,temporary,preview=preview,temp_dir=report,start=start,end=end,profile=profile,size=size,cancel=cancel,progress=progress)
        plan=json.loads((report/'render-plan.json').read_text(encoding='utf-8'))
        renderer=ProgrammeRenderer();sink=EncoderPipe(cmd,report/'ffmpeg.stderr.log',cancel=cancel)
        frames=plan['frame_count'];fps=plan['fps'];size=(plan['width'],plan['height']);last=-1.;frames_started=time.monotonic()
        for i in range(frames):
            if cancel is not None and cancel.is_set():raise Cancelled('Export cancelled')
            image=renderer.render(project,start+i/fps,size,transparent=(profile=='alpha'))
            sink.write(image.tobytes())
            now=time.monotonic()
            if progress and (now-last>.2 or i==frames-1):
                elapsed=now-frames_started;eta=elapsed/max(1,i+1)*(frames-i-1)
                estimate=f'about {eta:.0f}s remaining' if i>=5 else 'measuring frame timings…'
                progress(f'Rendering {100*(i+1)/frames:.1f}% · frame {i+1}/{frames} · {estimate}');last=now
        sink.finish();sink=None;renderer.close();renderer=None
        if progress:progress('Validating video and audio…')
        info=probe_media(temporary)
        if not info['has_video'] or (plan['audio'] and not info['has_audio']):raise RuntimeError('Export validation: expected video/audio stream is absent')
        if abs(info['duration']-plan['duration'])>max(.25,3/fps):raise RuntimeError(f'Export duration mismatch: {info["duration"]:.3f}s rather than {plan["duration"]:.3f}s')
        validation=[FFMPEG,'-v','error','-i',str(temporary),'-f','null','-']
        cp=run_process(validation,cancel=cancel,timeout=max(120,plan['duration']*3))
        (report/'validation.log').write_bytes(cp.stderr)
        if output.exists() and not overwrite:raise FileExistsError('Destination appeared during rendering; original output was preserved')
        temporary.replace(output);success=True
        result={**plan,'status':'complete','output':str(output),'elapsed_seconds':round(time.monotonic()-started,3),'output_bytes':output.stat().st_size,'probe':info}
        (report/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        if progress:progress('Ready · '+output.name)
        return output
    except Cancelled:
        (report/'result.json').write_text(json.dumps({'status':'cancelled','output':str(output)},indent=2),encoding='utf-8');raise
    except Exception as exc:
        (report/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        (report/'result.json').write_text(json.dumps({'status':'failed','message':str(exc),'output':str(output)},indent=2),encoding='utf-8')
        raise RenderFailure(str(exc),report) from exc
    finally:
        if sink:sink.close()
        if renderer:renderer.close()
        if temporary.exists():
            try:temporary.unlink()
            except OSError:pass
