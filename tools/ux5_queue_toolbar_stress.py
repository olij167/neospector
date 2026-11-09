#!/usr/bin/env python3
"""UX5 queue/toolbars retained-widget + long-queue stress gate."""
import os,sys,tempfile,time,threading,resource
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from neospector_console import NeospectorApp
from sequencer_model import add_asset
from instrument_model import voice
from queue_model import append_assets
from queue_gaps import add_visual_gap
from playable_queues import shuffle_future

def widgets(w):
    total=1
    for child in w.winfo_children():total+=widgets(child)
    return total

def pump(app,d=.05):
    end=time.monotonic()+d
    while time.monotonic()<end:app.update();time.sleep(.002)

def main():
    temp=tempfile.TemporaryDirectory();os.environ['OMNE_SEQUENCER_SANDBOX']=temp.name
    app=NeospectorApp(test_mode=True);errors=[];app.report_callback_exception=lambda *e:errors.append(repr(e))
    try:
        asset=add_asset(app.project,path='',kind='colour',name='Stress',metadata={'colour':'#5c46ff','sequence_preferences':{'clip_min':.08}})
        a=voice(app.project,'A');b=voice(app.project,'B')
        append_assets(app.project,a.id,[asset.id]*1200);append_assets(app.project,b.id,[asset.id]*600)
        for c in a.clips+b.clips:c.manual=False;c.extra['playable_auto']=True
        for i in range(18):add_visual_gap(app.project,a.id,.05,index=min(len(a.clips),30+i*50),mode='transparent')
        app.queue_deck.refresh(True);app.geometry('1080x740');app.load_layout({});app.shell.dock('Queues','bottom');pump(app,.4)
        before=widgets(app);threads_before=len(threading.enumerate());rss_before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        start=time.monotonic()
        for i in range(60):
            app.shell.collapse('Queues');app.update();app.shell.show('Queues');app.update()
            if i%6==0:shuffle_future(app.project,'A',now=0.,seed=100+i)
            size=((1080,740),(1366,768),(1920,1080))[i%3];app.geometry(f'{size[0]}x{size[1]}')
            app.queue_deck.hcanvas.xview_moveto((i%10)/10);app.queue_deck.refresh(i%5==0);app.update_idletasks();app.update()
        pump(app,.2)
        after=widgets(app);threads_after=len(threading.enumerate());rss_after=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        primaries=(app.play_button,app.randomise_button,app.global_camera_button,app.global_mic_button,app.record_button,app.visual_master_fader)
        assert all(w.winfo_ismapped() for w in primaries),'Level-1 controls dropped from supported layout'
        assert after<=before+8,(before,after)
        assert threads_after<=threads_before+1,(threads_before,threads_after)
        assert not errors,errors
        print(f'UX5_STRESS_PASS clips={len(a.clips)+len(b.clips)} widgets={before}->{after} threads={threads_before}->{threads_after} rss_kb={rss_before}->{rss_after} seconds={time.monotonic()-start:.3f}')
    finally:
        app.close(force=True);temp.cleanup()
if __name__=='__main__':main()
