#!/usr/bin/env python3
"""Smoke the unmodified Neospector entry with current UX36 controls, not UX18 ones."""
import gc,json,os,runpy,sys,tempfile
from pathlib import Path
import tkinter as tk
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(root/'app_source'))
sys.argv=[str(root/'app_source/neospector.py')]
original=tk.Misc.mainloop
report={'entry':'app_source/neospector.py','errors':[],'clean_close':False,'scope':'Virtual X display / bundled demo; not physical audio or hardware testing.'}

def loop(app,n=0):
    app.report_callback_exception=lambda *errors:report['errors'].append(repr(errors))
    def start():
        if app.startup_window and app.startup_window.winfo_exists():
            app.startup_window.destroy();app.startup_window=None
        # Verify the actual first-run page is actionable before continuing.
        app.show_startup_window(True)
        if app.startup_window and app.startup_window.winfo_exists():
            w=app.startup_window
            report['welcome_controls']={
                'camera_picker':bool(w.camera_selector.winfo_exists()),
                'mic_picker':bool(w.microphone_selector.winfo_exists()),
                'folder_field':bool(w.folder_entry.winfo_exists()),
                'recent_projects':hasattr(w,'recent_project_actions'),
                'appearance_entry':callable(w.preferences_actions['appearance']),
                'no_first_light':not hasattr(app,'welcome_example'),
                'no_tutorial_section':not hasattr(w,'onboarding_actions'),
            }
            app.startup_window.destroy();app.startup_window=None
        app.open_example()
        app.after(300,lambda:app.toggle_play() if not app.playing else None)
    def finish():
        from release_identity import VERSION
        report['version']=VERSION
        report['playback']=app.playback_diagnostics()
        controls={'record':app.record_button,'output':app.output_viewer_button,
                  'crossfade':app.visual_mix.fader,
                  'camera_a':app.source_capture_buttons['A'],
                  'camera_b':app.source_capture_buttons['B'],
                  'mic':app.source_capture_buttons['Music'],
                  'transition_editor':app.visual_mix.transition_display}
        report['visible_current_controls']={k:bool(w.winfo_ismapped()) for k,w in controls.items()}
        report['legacy_transition_arrows_hidden']=not app.visual_mix.previous_transition.winfo_ismapped() and not app.visual_mix.next_transition.winfo_ismapped()
        app.close(force=True);report['clean_close']=True
    app.after(500,start);app.after(4500,finish)
    return original(app,n)

tk.Misc.mainloop=loop
with tempfile.TemporaryDirectory(prefix='neospector-ux36-smoke-') as home:
    os.environ['OMNE_SEQUENCER_SANDBOX']=home
    os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
    runpy.run_path(str(root/'app_source/neospector.py'),run_name='__main__')
    gc.collect()
report['status']='PASS' if (report['clean_close'] and not report['errors'] and
    report['version']=='0.7.20-ux36' and report['playback']['presented_frames']>=8 and
    not report['playback']['phase_errors'] and report['legacy_transition_arrows_hidden'] and
    all(report['visible_current_controls'].values()) and
    all(report.get('welcome_controls',{}).values())) else 'FAIL'
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2));raise SystemExit(0 if report['status']=='PASS' else 1)
