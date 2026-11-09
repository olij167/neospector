"""Native Tk layout review; no network, real devices, or user profile is used."""
from __future__ import annotations
import json, os, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app_source'))
from PIL import ImageGrab
from neospector_console import NeospectorApp


def main():
    output=ROOT/'evidence/r5/screenshots';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='neospector-r5-ui-') as profile:
        os.environ['OMNE_SEQUENCER_SANDBOX']=profile
        app=NeospectorApp(test_mode=True);errors=[];checks=[]
        app.report_callback_exception=lambda *args:errors.append(repr(args))
        def pump(seconds):
            end=time.monotonic()+seconds
            while time.monotonic()<end:app.update();time.sleep(.005)
        def shot(name):
            app.lift();pump(.35)
            x,y=app.winfo_rootx(),app.winfo_rooty();w,h=app.winfo_width(),app.winfo_height()
            buttons=[app.play_button,app.stop_button,app.randomise_button,*app.deck.primary_actions]
            clipped=[str(b.cget('text')) for b in buttons if not b.winfo_ismapped() or b.winfo_rootx()<x or b.winfo_rootx()+b.winfo_width()>x+w or b.winfo_rooty()+b.winfo_height()>y+h]
            ImageGrab.grab(bbox=(x,y,x+w,y+h)).save(output/(name+'.png'))
            checks.append({'image':name+'.png','size':[w,h],'clipped_primary_controls':clipped})
        try:
            app.geometry('1440x940+0+0');pump(.7);shot('r5-empty')
            app.open_example();pump(1.0);app.new_treatment();pump(.9);shot('r5-instrument')
            app.open_randomise('queues',app.queue_deck);pump(.2);shot('r5-queue-randomise');app.randomise_popup.destroy()
            app.open_randomise('rack',app.deck.randomise_button);pump(.2);shot('r5-rack-randomise');app.randomise_popup.destroy()
            app.overview.layer.set('Effects');app.overview.invalidate();pump(.2);shot('r5-effects-overview')
            app.overview.layer.set('Clips');app.overview.invalidate()
            app.source_strip.toggle_camera_details();pump(.2)
            assert app.source_strip.camera_window.winfo_ismapped()
            app.source_strip.camera_window.withdraw()
            app.geometry('1080x740+0+0');app.load_layout({});pump(.6);shot('r5-small')
            app.apply_theme('Space Funk',save=False);app.geometry('1440x940+0+0');app.load_layout({});pump(.5);shot('r5-space-funk')
            app.tk.call('tk','scaling',2.0);app.geometry('1440x1000+0+0');app.load_layout({});pump(.5);shot('r5-scaled')
            report={'checks':checks,'callback_errors':errors,'phase_errors':app.playback_diagnostics().get('phase_errors',[]),'environment':'native Tk under Xvfb; no physical input or audible-output validation'}
            (output/'review.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report,indent=2))
            return int(bool(errors) or any(c['clipped_primary_controls'] for c in checks) or bool(report['phase_errors']))
        finally:app.close(force=True)

if __name__=='__main__':raise SystemExit(main())
