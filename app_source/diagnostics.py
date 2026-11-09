"""Explicit user-controlled diagnostics: no source media, credentials, or telemetry."""
from __future__ import annotations
import json,os,platform,sys,zipfile
from pathlib import Path
from media_engine import FFMPEG,FFPROBE,FFPLAY
from process_tools import run_process
from sequencer_model import project_to_dict
from release_identity import VERSION

def export_diagnostics(project,output,session_log=None,render_report=None,live_state=None,playback=None):
    tools={}
    for name,exe in [('ffmpeg',FFMPEG),('ffprobe',FFPROBE),('ffplay',FFPLAY)]:
        try:
            cp=run_process([str(exe),'-version'],timeout=8);tools[name]={'path':exe,'version':cp.stdout.decode('utf-8','replace')[:10000]}
        except Exception as exc:tools[name]={'path':exe,'error':str(exc)}
    import PIL,numpy,tkinter
    data={'app':'Neospector','version':VERSION,'python':sys.version,'platform':platform.platform(),'pillow':PIL.__version__,'numpy':numpy.__version__,'tk':tkinter.TkVersion,'tools':tools,'capture':live_state or {},'playback':playback or {},'privacy':'Includes local paths and project metadata. Does NOT embed media or upload anything.'}
    output=Path(output);tmp=output.with_name(output.name+'.tmp')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('README.txt','Review filenames and local paths before sharing. This report is created locally and is not uploaded automatically.\n')
        z.writestr('environment.json',json.dumps(data,indent=2));z.writestr('project.omne-sequence.json',json.dumps(project_to_dict(project),indent=2))
        if session_log and Path(session_log).is_file():z.writestr('session.log',Path(session_log).read_bytes()[-2_000_000:])
        if render_report and Path(render_report).is_dir():
            for path in Path(render_report).iterdir():
                if path.is_file() and path.suffix in {'.json','.txt','.log','.ffgraph'} and path.stat().st_size<20_000_000:z.write(path,'export/'+path.name)
    tmp.replace(output);return output
