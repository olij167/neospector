"""UX20 behaviour acceptance: fewer decisions, explicit ownership, one mix strip."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX20Consolidation(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True)
        self.app.geometry('1500x920+0+0');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()
    def test_sources_have_one_named_discoverable_group(self):
        a=self.app
        self.assertTrue(a.sources_heading.winfo_viewable())
        self.assertIn('SOURCES',str(a.sources_heading.cget('text')).upper())
        self.assertIn('AUDIO',a.source_tab_buttons['Music'].cget('text'))
        a.source_tab_buttons['B'].invoke();a.update()
        self.assertIn('▾',a.source_tab_buttons['B'].cget('text'))
        self.assertIn('▸',a.source_tab_buttons['A'].cget('text'))
    def test_rack_ownership_is_explicit_and_switchable_without_source_nav(self):
        a=self.app
        a.open_effects_context('A');a.update()
        self.assertIn('CHANNEL A',a.rack_owner_title.get())
        self.assertTrue(a.rack_target_buttons['A'].winfo_viewable())
        a.rack_target_buttons['B'].invoke();a.update()
        self.assertIn('CHANNEL B',a.rack_owner_title.get())
        self.assertEqual('B',a.edit_target_role)
        a.rack_target_buttons['Master'].invoke();a.update()
        self.assertIn('OUTPUT',a.rack_owner_title.get())
        self.assertEqual('Master',a.edit_target_role)
        self.assertEqual((),a.sidebar.open_roles())
    def test_mixer_is_one_surface_not_disconnected_disclosure_panels(self):
        a=self.app;mix=a.visual_mix
        self.assertTrue(mix.transition_group.winfo_viewable())
        self.assertTrue(mix.audio_group.winfo_viewable())
        self.assertFalse(hasattr(mix,'transition_panel'))
        self.assertFalse(hasattr(mix,'reaction_panel'))
        self.assertIn('Dissolve',mix.transition_display.cget('text'))
        mix.step_transition(1)
        self.assertNotEqual('dissolve',a.project.extra['ux16_transition']['kind'])
        mix.set_reactive(True)
        self.assertEqual('react',a.project.voice_mix.mode)
        self.assertEqual(1,abs(a.project.voice_mix.react_amount))
        self.assertTrue(mix.band_button.winfo_viewable())
        mix.step_band(1)
        self.assertEqual('bass',a.project.voice_mix.react_band)
    def test_rack_uses_single_owner_header_and_direct_fx_power(self):
        a=self.app;a.open_effects_context('Master');a.update()
        self.assertFalse(a.deck.path_label.winfo_viewable())
        self.assertTrue(a.rack_power_control.winfo_viewable())
        self.assertIn('ON',a.rack_power_control.cget('text'))
        a.rack_power_control.invoke();a.update()
        self.assertIn('OFF',a.rack_power_control.cget('text'))
        a.rack_power_control.invoke();a.update()
        self.assertIn('ON',a.rack_power_control.cget('text'))

    def test_compact_preview_preserves_sources_mixer_and_rack_identity(self):
        a=self.app;a.geometry('1024x768+0+0')
        a.sidebar.set_open('Music',True);a.open_effects_context('Master');a.update()
        self.assertTrue(a.sources_heading.winfo_viewable())
        self.assertTrue(a.rack_owner_heading.winfo_viewable())
        self.assertTrue(a.visual_mix.transition_group.winfo_viewable())
        self.assertTrue(a.visual_mix.audio_group.winfo_viewable())
        self.assertTrue(a.visual_mix.fader.winfo_viewable())
        for w in (a.visual_mix.transition_group,a.visual_mix.audio_group):
            self.assertLessEqual(w.winfo_rootx()+w.winfo_width(),a.viewport_frame.winfo_rootx()+a.viewport_frame.winfo_width()+8)
