#!/usr/bin/env python3
"""UX0 repeatable baseline: screenshots plus bounded local performance measurements.

This intentionally uses synthetic sources under Xvfb. Physical-device and 30-minute
owner soaks remain separate release gates; the report labels that limitation.
"""
from __future__ import annotations
import gc,json,os,statistics,sys,tempfile,time,threading
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app_source'))
import psutil
from PIL import ImageGrab
from neospector_console import NeospectorApp
from sequencer_model import add_asset,save_project,load_project
from instrument_model import assign_source

OUT=ROOT/'evidence/ux0';OUT.mkdir(parents=True,exist_ok=True)
P=psutil.Process()

def widgets(root):
    total=1;stack=list(root.winfo_children())
    while stack:
        w=stack.pop();total+=1;stack.extend(w.winfo_children())
    return total

def sample(app,label,seconds=3.0):
    gc.collect();cpu0=sum(P.cpu_times()[:2]);wall0=time.perf_counter();rss0=P.memory_info().rss
    renders=[];end=time.monotonic()+seconds
    while time.monotonic()<end:
        app.update();
        if getattr(app,'_last_render_ms',None) is not None:renders.append(float(app._last_render_ms))
        time.sleep(.006)
    wall=time.perf_counter()-wall0;cpu=sum(P.cpu_times()[:2])-cpu0
    info={'label':label,'seconds':round(wall,3),'cpu_one_core_percent':round(cpu/max(.001,wall)*100,2),
          'rss_mb':round(P.memory_info().rss/1024/1024,2),'rss_delta_mb':round((P.memory_info().rss-rss0)/1024/1024,2),
          'threads':P.num_threads(),'fds':P.num_fds() if hasattr(P,'num_fds') else None,'widgets':widgets(app)}
    if renders:info.update(render_ms_p50=round(statistics.median(renders),3),render_ms_p95=round(sorted(renders)[int(.95*(len(renders)-1))],3))
    return info

def pump(app,seconds=.3):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.006)

def wait(app,predicate,timeout=8):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.update();
        if predicate():return True
        time.sleep(.012)
    return False

with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':td,'SDL_AUDIODRIVER':'dummy'}):
    app=NeospectorApp(test_mode=True);errors=[];app.report_callback_exception=lambda *e:errors.append(repr(e))
    app.project.width=160;app.project.height=90;app.project.fps=12;app.project.duration=60
    a=add_asset(app.project,path='',kind='colour',name='UX0 violet',metadata={'colour':'#6a3b85'});b=add_asset(app.project,path='',kind='colour',name='UX0 amber',metadata={'colour':'#d59c3a'})
    assign_source(app.project,'A',a.id,duration=60);assign_source(app.project,'B',b.id,duration=60);app.refresh_all();pump(app,.4)
    screenshots=[]
    for size in ('1080x740','1440x940','1680x1050'):
        app.geometry(size+'+0+0');app.load_layout({});pump(app,.45);x,y=app.winfo_rootx(),app.winfo_rooty();path=OUT/f'baseline-{size}.png';ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height()),xdisplay=os.environ['DISPLAY']).save(path);screenshots.append(str(path.relative_to(ROOT)))
    metrics=[sample(app,'idle')]
    app.toggle_play();pump(app,.4);metrics.append(sample(app,'playback'))
    # Bounded interaction timings.
    resize=[]
    for size in ('1080x740','1440x940','1240x820','1680x1050','1440x940'):
        t=time.perf_counter();app.geometry(size);app.update_idletasks();app.update();resize.append((time.perf_counter()-t)*1000)
    t=time.perf_counter();app.randomise_playable('all',settings={'queue_items':3,'module_count':3,'variation':.5});pump(app,.35);randomise_ms=(time.perf_counter()-t)*1000
    project_path=Path(td)/'ux0-save.omne-sequence.json';t=time.perf_counter();save_project(app.project,project_path);save_ms=(time.perf_counter()-t)*1000;t=time.perf_counter();load_project(project_path);load_ms=(time.perf_counter()-t)*1000
    # File-only Programme recording start/finalise timing.
    app.recording_settings.update(name='UX0 metric',directory=td,profile='web',resolution='Programme',fps=12)
    t=time.perf_counter();app.record_programme();start_ms=(time.perf_counter()-t)*1000;pump(app,1.1);t=time.perf_counter();app.record_programme();wait(app,lambda:not app.output_busy,20);finalise_ms=(time.perf_counter()-t)*1000
    # Synthetic live camera.
    app.toggle_camera_layer('test');wait(app,lambda:getattr(app.live.camera,'state','')=='live',8);pump(app,.5);metrics.append(sample(app,'live-camera'))
    # Synthetic 110 Hz audio route, React-only by default.
    app.start_sound_source('test','Synthetic audio');wait(app,lambda:any(v.get('state')=='live' for v in app.live.source_states().values()),8);pump(app,.5);metrics.append(sample(app,'camera-audio-react'))
    report={
      'schema':'neospector/ux0-baseline-v1','environment':{'python':sys.version.split()[0],'platform':sys.platform,'display':os.environ.get('DISPLAY'),'measurement':'container/Xvfb synthetic sources'},
      'screenshots':screenshots,'metrics':metrics,'interaction_ms':{'resize_median':round(statistics.median(resize),3),'resize_p95':round(sorted(resize)[int(.95*(len(resize)-1))],3),'randomise_submit_and_settle':round(randomise_ms,3),'save':round(save_ms,3),'load':round(load_ms,3),'record_start':round(start_ms,3),'record_finalize':round(finalise_ms,3)},
      'callback_errors':errors,'phase_errors':app.playback_diagnostics().get('phase_errors',{}),
      'limitations':['Synthetic Xvfb baseline is not physical-device acceptance.','The required 30-minute owner/workstation soak is not represented by this bounded CI measurement and remains pending for later resilience qualification.']
    }
    (OUT/'baseline.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));app.close(force=True)
