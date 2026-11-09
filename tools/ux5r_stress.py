#!/usr/bin/env python3
"""UX5R native retained-panel stress. Uses generated camera/audio, not hardware.

Every transform is painted by Tk while the production playback/recording paths
run. Counts, document integrity, output media and resource growth are checked.
"""
from __future__ import annotations
import argparse, copy, json, os, sys, tempfile, threading, time, resource
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app_source'))

def widget_paths(w):
    result={str(w): w.winfo_class()}
    for child in w.winfo_children():result.update(widget_paths(child))
    return result

def widgets(w):
    return len(widget_paths(w))

def run():
    from neospector_console import NeospectorApp
    from instrument_model import assign_source
    from sequencer_model import add_asset,project_to_dict
    from media_engine import probe_media
    from workspace_system import DEFAULT_WORKSPACES
    from effects_engine import make_effect
    import numpy as np, subprocess
    report={'status':'FAIL','scope':'Tk/Xvfb; production playback/recording with generated microphone and camera', 'errors':[]}
    started=time.monotonic();callbacks=[];latencies=[];frames_before=0
    with tempfile.TemporaryDirectory(prefix='neospector-ux5r-stress-') as td:
        os.environ['OMNE_SEQUENCER_SANDBOX']=td;os.environ['SDL_AUDIODRIVER']='dummy'
        a=NeospectorApp(test_mode=True);a.report_callback_exception=lambda t,e,tb:callbacks.append(f'{t.__name__}: {e}')
        def pump(seconds=.006):
            end=time.monotonic()+seconds
            while time.monotonic()<end:a.update();time.sleep(.001)
        def wait(predicate,timeout=25):
            end=time.monotonic()+timeout
            while not predicate() and time.monotonic()<end:pump(.035)
            if not predicate():raise AssertionError(a.status.get())
        def action(fn):
            t=time.monotonic();fn();pump();latencies.append((time.monotonic()-t)*1000)
        try:
            a.geometry('1080x740+0+0');a.project.width=96;a.project.height=64;a.project.fps=12;a.project.duration=120
            asset=add_asset(a.project,path='',kind='colour',name='Stress colour',metadata={'colour':'#73437c'})
            assign_source(a.project,'A',asset.id,duration=120)
            a.project.master_rack=[make_effect('brightness')];a.changed();a.deck.refresh(True);pump(.15)
            # Warm every retained view, stack and lazy menu before resource counts.
            for name in DEFAULT_WORKSPACES:a.switch_workspace(name);pump(.025)
            a.switch_workspace('Live');a.workspace_controller.reset();pump(.05)
            a.shell.float_panel('Library');pump();a.shell.dock('Library','left');pump()
            a.shell.tab_with('Audio','Conductor');pump();a.workspace_controller.reset();pump()
            before=project_to_dict(a.project);owners={k:id(v) for k,v in a.deck.owner_cells.items()};panels={k:id(v) for k,v in a.shell.frames.items()}
            resources=(id(a.live),id(a.background_worker),id(a.viewport))
            cold_widgets=widgets(a)
            # A live synthetic microphone must remain Sound + React throughout.
            a.start_sound_source('test','UX5R synthetic microphone');wait(lambda:bool(a.live.source_states()) and any(s.get('state')=='live' for s in a.live.source_states().values()),8)
            a.toggle_channel_camera('B','test');wait(lambda:not a.camera_tickets,10)
            if not a.playing:a.toggle_play()
            wait(lambda:a.playback_diagnostics()['presented_frames']>12,10);pump(.2)
            # Source assignment legitimately creates a retained Clip OwnerCell
            # (49 widgets). Warm that owner before comparing presentation-only
            # resource counts; never hide actual per-transform growth in a budget.
            for name in DEFAULT_WORKSPACES:a.switch_workspace(name);pump(.025)
            a.switch_workspace('Live');a.workspace_controller.reset();a.deck.refresh(True);pump(.2)
            baseline_widgets=widgets(a);baseline_paths=widget_paths(a)
            baseline_callbacks=len(a.tk.call('after','info'));baseline_threads=len(threading.enumerate())
            rss_before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            master_cell=next(c for c in a.deck.owner_cells.values() if c.adapter.scope=='Master')
            card=master_cell.card_parts[a.project.master_rack[0].id][0]
            report['source_assignment_widget_warmup']=[cold_widgets,baseline_widgets]
            a.recording_settings.update(directory=td,name='Workspace stress',profile='web',resolution='Programme',fps=12)
            a.record_programme();assert a.output_recording is not None,a.status.get()
            frames_before=a.playback_diagnostics()['presented_frames'];record_clock=a.programme_time();recorder_id=id(a.output_recording)
            # 200 workspace switches while recording, including all three sizes.
            names=tuple(DEFAULT_WORKSPACES)
            for i in range(200):
                if i%8==0:a.geometry(('1080x740+0+0','1366x768+0+0','1920x1080+0+0')[(i//8)%3])
                action(lambda i=i:a.switch_workspace(names[i%5]))
                assert id(a.output_recording)==recorder_id,'Recorder replaced during a workspace switch'
            report['workspace_switches']=200
            # Record through actual drawer and floating-panel moves as well as
            # switches; the recorder must not depend on any editor being visible.
            for _ in range(24):
                action(lambda:a.shell.show('Library'));action(a.shell.dismiss_drawer)
                assert id(a.output_recording)==recorder_id
            for _ in range(12):
                action(lambda:a.shell.float_panel('Queues'));action(lambda:a.shell.dock('Queues','bottom'))
                assert id(a.output_recording)==recorder_id
            report['drawer_cycles_while_recording']=24;report['float_redock_cycles_while_recording']=12
            assert a.playback_diagnostics()['presented_frames']>frames_before
            a.record_programme();wait(lambda:not a.output_busy,40)
            path=Path(td)/'Workspace stress.mp4';assert path.is_file(),a.status.get()
            info=probe_media(path);assert info['has_audio'],'Recorded microphone sound is missing'
            pcm=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-vn','-ac','1','-ar','12000','-f','f32le','-'],check=True,stdout=subprocess.PIPE).stdout
            audio=np.frombuffer(pcm,dtype='<f4');rms=float(np.sqrt(np.mean(audio*audio))) if len(audio) else 0.
            assert rms>.01,('Silent recorded microphone',rms)
            report['recording']={'bytes':path.stat().st_size,'has_audio':info['has_audio'],'duration':info.get('duration'),'audio_rms':rms,'clock_seconds_during_switches':round(a.programme_time()-record_clock,3)}
            # Devices stay live and playback continues through drawer and float cycles.
            a.switch_workspace('Live');a.workspace_controller.reset();pump()
            for i in range(200):
                panel=('Library','Queues','Conductor','Audio')[i%4]
                action(lambda p=panel:a.shell.show(p));action(a.shell.dismiss_drawer)
            report['drawer_cycles']=200
            for i in range(100):
                panel=('Library','Queues','Conductor','Audio')[i%4]
                action(lambda p=panel:a.shell.float_panel(p));action(lambda p=panel:a.shell.dock(p,'bottom' if p=='Queues' else 'left' if p=='Library' else 'right'))
                a.shell.collapse(panel)
            report['float_redock_cycles']=100
            for i in range(120):
                action(lambda:a.shell.maximize('Rack'));action(lambda:a.shell.maximize('Rack'))
            report['maximize_restore_cycles']=120
            report['painted_presentation_operations']=len(latencies)
            assert len(latencies)>=500
            assert panels=={k:id(v) for k,v in a.shell.frames.items()}
            assert owners=={k:id(v) for k,v in a.deck.owner_cells.items()}
            assert resources==(id(a.live),id(a.background_worker),id(a.viewport))
            assert card is master_cell.card_parts[a.project.master_rack[0].id][0]
            report['retained_views_owners_cards_playback_resources']=True
            assert a.playing and a.playback_diagnostics()['presented_frames']>frames_before
            report['presented_frames_during_stress']=a.playback_diagnostics()['presented_frames']-frames_before
            # Stop devices before counting steady-state resources, not while their
            # capture/encoder workers are legitimately alive.
            a.toggle_channel_camera('B');pump(.12)
            for sid in list(a.live.source_states()):
                if sid in a.project.extra.get('sound_routes',{}):a.set_sound_source_enabled(sid,False)
            pump(.5);a.commands.invoke('transport.stop');a.switch_workspace('Live');a.workspace_controller.reset();pump(.3)
            current=project_to_dict(a.project)
            # Separate presentation-only integrity check after explicit media commands.
            snapshot=copy.deepcopy(current)
            for name in names:a.switch_workspace(name);pump(.01)
            a.switch_workspace('Live');a.workspace_controller.reset();pump(.1)
            assert snapshot==project_to_dict(a.project),'Workspace transforms mutated the document'
            after_widgets=widgets(a);after_callbacks=len(a.tk.call('after','info'));after_threads=len(threading.enumerate())
            report['widget_additions']={k:v for k,v in widget_paths(a).items() if k not in baseline_paths};report['widget_removals']={k:v for k,v in baseline_paths.items() if k not in widget_paths(a)};report['widgets']=[baseline_widgets,after_widgets];report['after_callbacks']=[baseline_callbacks,after_callbacks];report['threads']=[baseline_threads,after_threads]
            report['rss_kb']=[rss_before,resource.getrusage(resource.RUSAGE_SELF).ru_maxrss]
            # Strict presentation-only steady-state comparison after source warmup.
            assert after_widgets<=baseline_widgets,report['widgets']
            assert after_callbacks<=baseline_callbacks+5,report['after_callbacks']
            assert after_threads<=baseline_threads+2,report['threads']
            report['transform_p50_ms']=round(float(np.percentile(latencies,50)),2);report['transform_p95_ms']=round(float(np.percentile(latencies,95)),2)
            report['callback_errors']=callbacks;assert not callbacks,callbacks
            report['status']='PASS'
        except Exception as exc:
            report['errors'].append(f'{type(exc).__name__}: {exc}');report['callback_errors']=callbacks
        finally:a.close(force=True)
    report['elapsed_seconds']=round(time.monotonic()-started,3);return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path);args=ap.parse_args();report=run();text=json.dumps(report,indent=2)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text+'\n')
    print(text);return 0 if report['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
