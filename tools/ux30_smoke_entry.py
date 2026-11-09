"""Exercise the shipped entry script unchanged; a harness timer closes its UI."""
import gc,json,os,runpy,sys,tempfile,time
from pathlib import Path
import tkinter as tk
root=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(root/'app_source'));sys.argv=[str(root/'app_source/neospector.py')]
original=tk.Misc.mainloop;report={'entry':'app_source/neospector.py','errors':[],'clean_close':False}

def loop(self,n=0):
    self.report_callback_exception=lambda *args:report['errors'].append(repr(args))
    def example():
        report['fresh_workspace']=self.shell.state.name
        report['fresh_visible_panels']=sorted(self.shell.visible_ids())
        report['fresh_live_sources']=self.live.source_states()
        if self.startup_window and self.startup_window.winfo_exists():self.startup_window.destroy();self.startup_window=None
        self.open_example()
        self.after(400,lambda: self.toggle_play() if not self.playing else None)
    def stop():
        report['version']=__import__('family_chrome').VERSION
        report['title']=self.title()
        report['playback']=self.playback_diagnostics()
        report['library_visible']=bool(self.library.winfo_ismapped())
        report['visuals_visible']=bool(self.queue_deck.winfo_ismapped())
        report['visible_panels']=sorted(self.shell.visible_ids())
        report['panel_ids']=sorted(self.panels.ids())
        controls=(self.application_button,self.master_fx_button,self.media_sources_button,self.record_button,self.visual_mix.transition_display,self.visual_mix.react_button,*self.source_capture_buttons.values())
        report['performance_controls_visible']=all(w.winfo_ismapped() for w in controls)
        self.close(force=True);report['clean_close']=True
    self.after(600,example);self.after(4200,stop)
    return original(self,n)

tk.Misc.mainloop=loop
with tempfile.TemporaryDirectory(prefix='neospector-shipped-entry-') as profile:
    os.environ['OMNE_SEQUENCER_SANDBOX']=profile
    runpy.run_path(str(root/'app_source/neospector.py'),run_name='__main__')
    gc.collect()
report['status']='PASS' if report['clean_close'] and not report['errors'] and report['fresh_workspace']=='Live' and 'panel.programme' in report['fresh_visible_panels'] and not report['fresh_live_sources'] and not report['library_visible'] and not report['visuals_visible'] and report['performance_controls_visible'] and 'panel.module-library' not in report['panel_ids'] and report['playback']['presented_frames']>=8 and not report['playback']['phase_errors'] else 'FAIL'
report['scope']='UX30 visible performance controls and unchanged application entry under Xvfb. No physical-audio device acceptance.'
output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
raise SystemExit(0 if report['status']=='PASS' else 1)
