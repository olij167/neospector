"""UX30 visible workbench contracts and live Tk geometry."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX30Tk(unittest.TestCase):
    def setUp(self):
        self.sandbox=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.sandbox.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.a=NeospectorApp(test_mode=True);self.a.geometry('1600x920+0+0');self.pump()
    def pump(self):
        for _ in range(8):self.a.update()
    def tearDown(self):
        try:self.a.close(force=True)
        finally:self.env.stop();self.sandbox.cleanup()
    def test_preview_toolbar_has_one_top_level_home(self):
        a=self.a
        self.assertIs(a.visual_mix.master,a.top_row)
        self.assertTrue(a.visual_mix.winfo_viewable())
        self.assertLess(a.record_button.winfo_rooty(),a.viewport.canvas.winfo_rooty())
        self.assertTrue(a.source_capture_buttons['A'].winfo_viewable())
    def test_unavailable_pipewire_application_is_readonly_row(self):
        a=self.a;a.sidebar.open_browser('Music','sources');self.pump()
        shelf=a.sidebar.source_shelf
        shelf.populate_sources([{'kind':'application','label':'App · Spotify · setup needed','device':{'kind':'application','backend':'pipewire','node':19},'capture_available':False,'capture_hint':'Install pulseaudio-utils'}],['Setup required'])
        iid=shelf.source_list.get_children()[0]
        self.assertEqual(shelf.source_list.item(iid,'values'),('','',''))
        shelf.place_source('now',iid)
        self.assertIn('pulseaudio-utils',shelf.source_status.get())

    def test_mixer_includes_mic_and_vertical_faders(self):
        a=self.a;music=a.queue_deck.pages['Music'];music.show_audio_view('mixer');self.pump()
        from sound_routes import source_id
        mixer=music.audio_mixer
        self.assertTrue(mixer.winfo_viewable())
        self.assertIn('soundtrack',mixer.rows)
        self.assertIn(source_id(a.last_microphone_device),mixer.rows)
        self.assertEqual(mixer.rows['soundtrack']['fader'].cget('orient'),'vertical') if 'fader' in mixer.rows['soundtrack'] else self.fail('Missing fader handle')
        self.assertLessEqual(mixer.winfo_rootx()+mixer.winfo_width(),a.winfo_rootx()+a.winfo_width()+2)
    def test_module_library_has_exit_and_group_variation_actions(self):
        a=self.a;a.toggle_main_effects();self.pump();a.toggle_module_library(True);self.pump()
        lib=a.module_library
        self.assertTrue(lib.close_button.winfo_viewable())
        self.assertTrue(lib.group_button.winfo_viewable())
        self.assertTrue(lib.variation_button.winfo_viewable())
        lib.close_button.invoke();self.pump()
        self.assertFalse(a.library_open)
    def test_narrow_width_top_toolbar_stays_within_window(self):
        a=self.a;a.geometry('1050x790+0+0');a.sidebar.open_browser('A','sources');self.pump()
        self.assertLessEqual(a.visual_mix.winfo_rootx()+a.visual_mix.winfo_width(),a.winfo_rootx()+a.winfo_width()+6)
        self.assertLessEqual(a.source_switches.winfo_rootx()+a.source_switches.winfo_width(),a.winfo_rootx()+a.winfo_width()+6)
        self.assertTrue(a.visual_mix.react_button.winfo_viewable())

if __name__=='__main__':unittest.main()
