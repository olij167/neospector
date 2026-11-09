#!/usr/bin/env python3
"""Desktop acceptance runner. Never treats a timer or dummy sound as AV proof."""
import datetime,hashlib,json,os,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path
from verify_source import NativeFixtureResult
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'app_source'),str(ROOT/'tests')]

def main():
    report_dir=ROOT/'verification-runs'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');report_dir.mkdir(parents=True)
    report={'status':'INCOMPLETE','screenshots':[],'physical_sound_confirmed':False,'profile':'isolated temporary profile'}
    def save():
        (report_dir/'native-result.json').write_text(json.dumps(report,indent=2));print('Evidence:',report_dir,flush=True)
    app=None
    with tempfile.TemporaryDirectory(prefix='neospector-r5-verification-') as profile:
        os.environ['OMNE_SEQUENCER_SANDBOX']=profile
        try:
            import tkinter as tk
            probe=tk.Tk();probe.withdraw();probe.update();probe.destroy()
            if os.environ.get('SDL_AUDIODRIVER')=='dummy':raise RuntimeError('Dummy audio cannot verify audible playback. Unset SDL_AUDIODRIVER for this desktop check.')
            suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
            with (report_dir/'tests.log').open('w') as log:result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=NativeFixtureResult).run(suite)
            report['tests']={'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}
            from playable_av_acceptance import run
            run(report_dir/'encoded-av')
            from process_tools import run_process
            from neospector_console import NeospectorApp
            from sequencer_model import add_asset
            from instrument_model import new_instrument
            from builtin_themes import PUBLISHED_THEME_ORDER
            from PIL import ImageGrab,ImageTk
            import numpy as np
            video=Path(profile)/'motion.mp4';audio=Path(profile)/'tone.wav'
            run_process(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=20:duration=30','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-y',str(video)])
            run_process(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=30','-c:a','pcm_s16le','-y',str(audio)])
            app=NeospectorApp(test_mode=True);errors=[];app.report_callback_exception=lambda *e:errors.append(str(e));app.geometry('1240x900+0+0')
            def pump(seconds):
                end=time.monotonic()+seconds
                while time.monotonic()<end:app.update();time.sleep(.01)
            def wait(predicate,seconds=20):
                end=time.monotonic()+seconds
                while not predicate() and time.monotonic()<end:pump(.05)
                if not predicate():raise RuntimeError('UI operation timed out: '+app.status.get())
            p=new_instrument();p.width=320;p.height=180;p.fps=20;p.duration=30
            add_asset(p,path=str(video),kind='video',name='Desktop moving-picture verification',duration=30,width=320,height=180)
            song=add_asset(p,path=str(audio),kind='audio',name='Desktop audible 440 Hz test tone',duration=30)
            app.restore_project(p);app.use_song(song.id);app.randomise_playable('queues')
            wait(lambda:not getattr(app,'_playable_running',False) and not getattr(app,'_playable_latest',None))
            assert app.project.layers[0].clips,'Empty Auto queue was not prepared'
            app.test_mode=False;app.toggle_play();pump(.5)
            hashes=[];times=[];audio_rms=[]
            for n in range(50):
                if n in (5,10,15):app.randomise_playable('effects')
                pump(.1)
                if app.viewport.photo is not None:
                    hashes.append(hashlib.sha256(ImageTk.getimage(app.viewport.photo).tobytes()).hexdigest());times.append(app.viewport.display_time)
                if app.audio_bus.last_block is not None:audio_rms.append(float(np.sqrt(np.mean(app.audio_bus.last_block[1]**2))))
            stats=app.playback_diagnostics();report['playback']={**stats,'distinct_displayed_images':len(set(hashes)),'distinct_displayed_times':len(set(times)),'maximum_audio_bus_rms':max(audio_rms,default=0.),'audio_process_running':bool(app.audio_bus.proc and app.audio_bus.proc.poll() is None)}
            assert app.viewport.canvas.winfo_ismapped() and len(set(hashes))>=8,'No proven sequence of fresh displayed Tk images'
            assert len(set(times))>=8 and (stats['frame_age_seconds'] or 999)<2,'Display freshness failed'
            assert not stats['phase_errors'] and not errors,'UI callback / heartbeat errors'
            assert report['playback']['audio_process_running'] and max(audio_rms,default=0.)>.005 and not app.audio_bus.error,'Audio monitoring process failed'
            app.pause();app.test_mode=True
            def shot(name):
                app.lift();pump(.3);x,y=app.winfo_rootx(),app.winfo_rooty();w,h=app.winfo_width(),app.winfo_height()
                if x<0 or y<0 or x+w>app.winfo_screenwidth() or y+h>app.winfo_screenheight():raise RuntimeError('Desktop is too small for complete screenshot '+name)
                for button in (app.play_button,app.randomise_button,app.global_camera_button,app.global_mic_button,app.record_button,app.visual_master_fader,*app.deck.primary_actions):
                    assert button.winfo_ismapped() and button.winfo_rootx()+button.winfo_width()<=x+w and button.winfo_rooty()+button.winfo_height()<=y+h,'Primary control clipped in '+name
                target=report_dir/(name+'.png');ImageGrab.grab(bbox=(x,y,x+w,y+h)).save(target);report['screenshots'].append(target.name)
            for theme in PUBLISHED_THEME_ORDER:
                app.apply_theme(theme,save=False)
                for size in ('1080x740','1240x900','1440x1000'):
                    app.geometry(size+'+0+0');app.load_layout({});pump(.3);shot(theme.replace(' ','-')+'-'+size)
            app.tk.call('tk','scaling',2.);app.geometry('1440x1000+0+0');app.load_layout({});pump(.5);shot('high-dpi-1440x1000')
            report['ui_callback_errors']=errors
            app.close(force=True);app=None
            if sys.stdin.isatty():report['physical_sound_confirmed']=input('Did you actually hear a continuous tone during the moving-picture test? Type yes only if heard: ').strip().lower()=='yes'
            report['status']='PASS' if result.wasSuccessful() and not result.skipped and report['physical_sound_confirmed'] else 'INCOMPLETE'
        except Exception as exc:
            report['error']=str(exc);(report_dir/'failure.txt').write_text(traceback.format_exc());report['status']='BLOCKED_OR_FAILED'
        finally:
            if app:
                try:app.test_mode=True;app.close(force=True)
                except Exception:pass
            save()
    return 0 if report['status']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
