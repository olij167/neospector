import sys,os,tempfile,time,statistics,json,gc
from pathlib import Path
source=Path(sys.argv[1]);sys.path.insert(0,str(source/'app_source'))
from neospector_console import NeospectorApp
from sequencer_model import add_asset,add_clip
from instrument_model import voice
from unittest.mock import patch
with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':td,'SDL_AUDIODRIVER':'dummy'}):
    a=NeospectorApp(test_mode=True);errors=[];a.report_callback_exception=lambda *e:errors.append(str(e));a.geometry('1440x940')
    def pump(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:a.update();time.sleep(.005)
    asset=add_asset(a.project,path='',kind='colour',name='Benchmark colour',metadata={'colour':'#345678'})
    layer=voice(a.project,'A')
    for n in range(512):add_clip(a.project,layer,asset,'A',n*2,2)
    a.project.width=160;a.project.height=90;a.project.fps=12;a.refresh_all();pump(.35)
    callbacks=[];begins=[];ends=[];c=a.conductor
    for trial in range(3):
        t=time.perf_counter();c.begin('variation');begins.append((time.perf_counter()-t)*1000)
        for n in range(40):
            v=.2+(n%31)/50+.003*trial;t=time.perf_counter();c.values['variation'].set(v);c.changed('variation',v);callbacks.append((time.perf_counter()-t)*1000)
        t=time.perf_counter();c.end();ends.append((time.perf_counter()-t)*1000);pump(.1)
    report={'source':source.name,'environment':'Linux container / Xvfb / Python '+sys.version.split()[0], 'project_clips':512,'gestures':3,'updates_per_gesture':40,
            'callback_p50_ms':statistics.median(callbacks),'callback_p95_ms':sorted(callbacks)[int(.95*(len(callbacks)-1))],
            'gesture_begin_median_ms':statistics.median(begins),'gesture_end_median_ms':statistics.median(ends),'callback_errors':errors,
            'scope':'Paused synthetic project. Direct callbacks, not end-to-end pointer or physical hardware latency.'}
    a.close(force=True);a=None;gc.collect();print(json.dumps(report,indent=2))
