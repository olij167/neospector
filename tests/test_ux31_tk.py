"""UX31 live Tk checks for sparse fader desk and shared advanced authoring."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
class UX31Tk(unittest.TestCase):
    def setUp(self):
        self.sandbox=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.sandbox.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'});self.env.start()
        from neospector_console import NeospectorApp
        self.a=NeospectorApp(test_mode=True);self.a.geometry('1500x920+0+0');self.pump()
    def pump(self):
        for _ in range(7):self.a.update()
    def tearDown(self):
        try:self.a.close(force=True)
        finally:self.env.stop();self.sandbox.cleanup()
    def test_mixer_omits_disconnected_and_unused_inputs(self):
        music=self.a.queue_deck.pages['Music'];music.show_audio_view('mixer');self.pump()
        self.assertTrue(music.audio_mixer.winfo_viewable())
        self.assertNotIn('voice:A',music.audio_mixer.rows)
        self.assertFalse(any(x.startswith('live:') for x in music.audio_mixer.rows))
        self.assertTrue(music.audio_mixer.empty_status.winfo_viewable())
    def test_empty_mixer_uses_compact_height_and_active_uses_fader_height(self):
        a=self.a;music=a.queue_deck.pages['Music'];music.show_audio_view('mixer');self.pump()
        frame=a.sidebar.sections['Music']['frame']
        self.assertLess(frame.winfo_height(),180)
        self.assertTrue(music.audio_mixer.empty_status.winfo_viewable())
        # Simulate a real live source state (not an invented fader row); the
        # same source_states interface feeds the meter and source discovery.
        from sound_routes import source_id
        mic=source_id(a.last_microphone_device)
        with patch.object(a.live,'source_states',return_value={mic:{'state':'live','level':.3}}):
            music.audio_mixer.refresh(True)
            a.sidebar.request_fit();self.pump()
            self.assertIn(mic,music.audio_mixer.rows)
            self.assertGreaterEqual(a.sidebar.requested_height('Music'),300)
            self.assertGreaterEqual(frame.winfo_height(),220)
            self.assertLessEqual(frame.winfo_rooty()+frame.winfo_height(),a.viewport.canvas.winfo_rooty()+a.viewport.canvas.winfo_height()+6)
    def test_advanced_editor_switches_modes_without_editing_other_scope(self):
        from creative_controls import open_creative_controls
        a=self.a;before=dict(a.project.extra.get('ux16_transition',{}))
        editor=a.visual_mix.open_transition_menu();self.pump()
        self.assertTrue(editor.transition.winfo_viewable())
        editor.effect.set('invert');editor.strength.set('50');editor.save_transition();self.pump()
        self.assertEqual(a.project.extra['ux16_transition']['effect'],'invert')
        e=open_creative_controls(a,'rack');self.pump()
        self.assertIs(e,editor);self.assertTrue(e.rack.winfo_viewable())
        self.assertEqual(a.project.extra['ux16_transition']['effect'],'invert')
        old=a.project.extra.get('randomise_settings',{}).copy()
        e.count.set('3');self.assertTrue(e.save_rack_options());self.pump()
        self.assertEqual(a.project.extra['randomise_settings']['module_count'],3)
        self.assertEqual(a.deck.random_count.get(),'3')
        self.assertEqual(a.project.extra['ux16_transition']['effect'],'invert')
        editor.destroy()
    def test_library_variation_opens_shared_editor(self):
        a=self.a;a.toggle_main_effects();a.toggle_module_library(True);self.pump()
        a.module_library.open_variation_tools();self.pump()
        self.assertEqual(a._creative_controls.mode.get(),'rack')
        self.assertTrue(a._creative_controls.rack.winfo_viewable())
        a._creative_controls.destroy()
if __name__=='__main__':unittest.main()
