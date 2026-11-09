"""UX39: the live parameter gesture must not rebuild unrelated playback/UI state."""
import os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX39PerformanceTk(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ux39-')
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.temp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.a=NeospectorApp(test_mode=True)
        self.a.geometry('1250x800+0+0')
        self.a.update()
    def tearDown(self):
        try:self.a.close(force=True)
        finally:self.env.stop();self.temp.cleanup()
    def test_fast_gesture_does_not_run_full_queue_and_audio_refresh_per_step(self):
        a=self.a;owner=a.project.layers[0];param=owner.opacity
        a.begin_gesture('program')
        with patch.object(a.queue_deck,'refresh',wraps=a.queue_deck.refresh) as q,patch.object(a,'configure_sound_sources',wraps=a.configure_sound_sources) as sound:
            for i in range(60):a.write_parameter(param,.1+i/100.,owner)
            self.assertAlmostEqual(param.value,.69)
            self.assertEqual(q.call_count,0,'slider motion cannot synchronously rebuild queues')
            self.assertEqual(sound.call_count,0,'slider motion cannot synchronously reconfigure live audio')
            time.sleep(.042);a.update()
            self.assertEqual(q.call_count,0,'the coalesced preview frame must also avoid unrelated queue refresh')
            self.assertEqual(sound.call_count,0)
        a.end_gesture()
        self.assertTrue(a.dirty)
    def test_program_gesture_end_avoids_forced_rack_rebuild(self):
        a=self.a;owner=a.project.layers[0]
        a.begin_gesture('program');a.write_parameter(owner.opacity,.38,owner)
        with patch.object(a.deck,'refresh',wraps=a.deck.refresh) as refreshed:
            a.end_gesture()
            self.assertFalse(any(c.kwargs.get('force') is True or c.args==(True,) for c in refreshed.call_args_list),
                'finishing a value gesture is not a structural rack edit')
    def test_steady_rack_refresh_preserves_selected_owner_variables(self):
        a=self.a
        a.open_effects_context('Transition');a.update()
        d=a.deck
        with patch.object(d.scope,'set',wraps=d.scope.set) as s,patch.object(d.target_name,'set',wraps=d.target_name.set) as n:
            for _ in range(12):d.refresh(False)
            self.assertEqual(s.call_count,0,'unchanged scope must not emit another Tk trace')
            self.assertEqual(n.call_count,0,'unchanged owner title must not trigger toolbar redraw')
    def test_starting_fader_on_already_selected_owner_does_not_relayout(self):
        a=self.a;a.open_effects_context('Transition');a.update()
        d=a.deck;cell=d.selected_cell()
        with patch.object(d,'relayout',wraps=d.relayout) as relayout:
            d.select_owner(cell)
            self.assertEqual(relayout.call_count,0,'fader press must not trigger full rack geometry')
    def test_clock_does_not_poll_entire_rack_during_active_slider_motion(self):
        a=self.a
        a.begin_gesture('program');a._last_controls_at=-1.
        with patch.object(a.deck,'refresh',wraps=a.deck.refresh) as refreshed:
            a._clock_ui()
            self.assertEqual(refreshed.call_count,0)
        a.end_gesture()
    def test_idle_fader_refresh_does_not_reset_unchanged_tk_variable(self):
        from omne_rack import ParameterFader
        a=self.a;owner=a.project.layers[0];param=owner.opacity
        f=ParameterFader(a,a,'Opacity',param,owner)
        f.pack();a.update()
        with patch.object(f.normal,'set',wraps=f.normal.set) as assign,patch.object(f.text,'set',wraps=f.text.set) as label:
            for _ in range(20):f.refresh()
            self.assertEqual(assign.call_count,0,'unchanged fader values should not send 20 Tk redraws')
            self.assertEqual(label.call_count,0,'unchanged value labels should not send 20 Tk redraws')
        param.value=.38;f.refresh()
        self.assertAlmostEqual(f.normal.get(),f.to_normal(.38),places=3)
        f.destroy()

if __name__=='__main__':unittest.main()
