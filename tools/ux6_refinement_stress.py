#!/usr/bin/env python3
"""UX6 measured stress. Generated local media/signals, not physical hardware."""
from __future__ import annotations
import argparse,copy,gc,json,os,subprocess,sys,tempfile,time,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app_source'))

def run():
    import numpy as np
    from PIL import Image
    from types import SimpleNamespace
    from neospector_console import NeospectorApp
    from instrument_model import new_instrument,assign_source
    from sequencer_model import add_asset,project_to_dict,_encode
    from module_library import catalogue_rows
    from media_engine import probe_media
    import composition_queue as cues
    report={'status':'FAIL','scope':'Linux/Tk/Xvfb; generated file, microphone and colour sources. No physical-device or multi-hour soak claim.','errors':[]}
    started=time.monotonic();app=None
    try:
        rows=catalogue_rows(SimpleNamespace(catalog=SimpleNamespace(ingredients=lambda:[])))
        t=time.monotonic()
        for seed in range(2500):
            p=new_instrument();before=_encode(p.master_rack);cues.append_generated(p,rows,seed=seed)
            assert _encode(p.master_rack)==before,'Preparation replaced output'
        report['headless_preparations']=2500;report['headless_seconds']=round(time.monotonic()-t,3)
        with tempfile.TemporaryDirectory(prefix='ux6-native-stress-') as td:
            os.environ['OMNE_SEQUENCER_SANDBOX']=td;os.environ['SDL_AUDIODRIVER']='dummy'
            app=NeospectorApp(test_mode=True);a=app;errors=[];a.report_callback_exception=lambda *e:errors.append(str(e));a.geometry('1080x740')
            def pump(seconds=.04):
                end=time.monotonic()+seconds
                while time.monotonic()<end:a.update();time.sleep(.003)
                assert not errors,errors
            def wait(predicate,seconds=20):
                until=time.monotonic()+seconds
                while not predicate() and time.monotonic()<until:pump()
                assert predicate(),a.status.get()
            asset=add_asset(a.project,path='',kind='colour',name='UX6 generated colour',metadata={'colour':'#355b7b'})
            assign_source(a.project,'A',asset.id,duration=180);a.project.width=96;a.project.height=64;a.project.fps=12;a.project.duration=180
            a.project.conductor.extra.update(evolve_sources=False,evolve_sound=False,evolve_treatment=True)
            cues.configure(a.project,dict(pool_mode='selected',pool_ids=['base:invert','base:contrast','base:hue'],count=2,hold=.3,fade=.2,continuous=True))
            for _ in range(3):a.conductor.queue_view.generate()
            a.conductor.queue_view.take_next();a.project.master_rack[0].extra['locked']=True;locked=_encode(a.project.master_rack[0])
            a.changed();a.refresh_all();pump(.15)
            panels={k:id(v) for k,v in a.shell.frames.items()};controls=(id(a.conductor.queue_view.tree),id(a.conductor.controls),id(a.live),id(a.background_worker))
            a.start_sound_source('test','UX6 synthetic microphone');wait(lambda:any(s.get('state')=='live' for s in a.live.source_states().values()))
            if not a.playing:a.toggle_play()
            wait(lambda:a.playback_diagnostics()['presented_frames']>8)
            a.recording_settings.update(directory=td,name='UX6 autonomy',profile='web',resolution='Programme',fps=12)
            a.record_programme();assert a.output_recording is not None,a.status.get();recorder=id(a.output_recording)
            a.conductor.toggle_power();assert a.evolve.get();t=time.monotonic();initial=a.playback_diagnostics()['presented_frames'];operations=0;manual_randomised=False
            while time.monotonic()-t<18:
                name=('Live','Sequence','Conduct','Build','Studio')[operations%5];a.switch_workspace(name)
                if operations%7==0:a.conductor.toggle_details()
                if operations%11==0:a.shell.toggle('Library')
                if operations>=20 and not manual_randomised:
                    a.deck.scope.set('Master');a.apply_rack_randomise({'module_count':2,'variation':.4});manual_randomised=True
                pump(.08);operations+=1
                assert id(a.output_recording)==recorder,'Recorder replaced by a presentation operation'
            report['native_autonomy_seconds']=round(time.monotonic()-t,3);report['presentation_operations']=operations
            report['performed_transitions']=len(a.project.extra.get('master_transitions',[]))
            report['presented_frames']=a.playback_diagnostics()['presented_frames']-initial
            assert report['performed_transitions']>=8,report
            assert report['presented_frames']>25,report
            assert any(_encode(f)==locked for f in a.project.master_rack),'Explicitly locked module changed'
            assert manual_randomised
            assert panels=={k:id(v) for k,v in a.shell.frames.items()}
            assert controls==(id(a.conductor.queue_view.tree),id(a.conductor.controls),id(a.live),id(a.background_worker))
            report['retained_panels_controls_playback']=True;report['manual_randomise_while_powered']=True;report['explicit_lock_preserved']=True
            a.conductor.toggle_power();before=project_to_dict(a.project);a.advance_composition_queue(5000);assert before==project_to_dict(a.project)
            a.record_programme();wait(lambda:not a.output_busy,40)
            output=Path(td)/'UX6 autonomy.mp4';info=probe_media(output);assert info['has_audio']
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(output),'-vn','-ac','1','-ar','12000','-f','f32le','-'])
            pcm=np.frombuffer(raw,dtype='<f4');rms=float(np.sqrt(np.mean(pcm*pcm)));assert rms>.01,rms
            report['recording']={'has_audio':True,'rms':rms,'duration':info['duration'],'bytes':output.stat().st_size}
            a.commands.invoke('transport.stop')
            for sid in list(a.live.source_states()):
                if sid in a.project.extra.get('sound_routes',{}):a.set_sound_source_enabled(sid,False)
            folder=Path(td)/'import sources';folder.mkdir()
            for n in range(260):Image.new('RGB',(24,16),(n%255,(n*3)%255,(n*7)%255)).save(folder/f'Frame {n:04}.png')
            a.open_import_browser([str(folder)]);w=a.import_window
            wait(lambda:not w.scanning and len(w.model.items)==260 and all(r.state!='pending' for r in w.model.items.values()),40)
            checked=set(w.model.checked);assert len(checked)==260
            cache_peak=0
            for n in range(30):
                w.browser.view.set('List' if n%2 else 'Grid');w.browser.turn_page(1 if n%6<3 else -1);pump(.06)
                cache_peak=max(cache_peak,len(w.photos));assert len(w.photos)<=w.THUMBNAIL_LIMIT
                assert set(w.model.checked)==checked
            w.cancel_scan();w.show_basket();pump(.12);assert len(w.model.checked)==260
            report['browser']={'inspected_files':260,'view_page_changes':30,'basket_preserved':True,'thumbnail_peak':cache_peak,'thumbnail_limit':w.THUMBNAIL_LIMIT,'queued_thumbnails':w.thumb_jobs.qsize()}
            assert w.thumb_jobs.qsize()<=w.browser.PAGE_SIZE
            w.destroy();pump(.1);assert len(list(folder.glob('*.png')))==260
            report['callback_errors']=errors;report['status']='PASS'
    except Exception as exc:
        import traceback
        report['errors'].append(str(exc));report['traceback']=traceback.format_exc()
    finally:
        if app:
            try:app.close(force=True)
            except Exception as exc:report['errors'].append('Close: '+str(exc));report['status']='FAIL'
        app=None;gc.collect()
    report['elapsed_seconds']=round(time.monotonic()-started,3);return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report=run();text=json.dumps(report,indent=2);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text+'\n');print(text)
    raise SystemExit(0 if report['status']=='PASS' else 1)
