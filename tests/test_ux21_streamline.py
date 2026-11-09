"""UX21 user-contract: one FX entry, source pairs, and a single clean mixer."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX21Streamline(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True);self.app.geometry('1500x900+0+0');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()
    def test_single_fx_entry_uses_current_rack(self):
        a=self.app
        self.assertEqual('Effects',a.master_fx_button.cget('text'))
        self.assertFalse(a.output_fx_button.winfo_viewable())
        self.assertFalse(a.shell.rack_open)
        a.master_fx_button.invoke();a.update()
        self.assertTrue(a.shell.rack_open)
        a.rack_target_buttons['B'].invoke();a.update()
        self.assertIn('CHANNEL B',a.rack_owner_title.get())
        a.master_fx_button.invoke();a.update()
        self.assertFalse(a.shell.rack_open)
        a.master_fx_button.invoke();a.update()
        self.assertTrue(a.shell.rack_open)
        self.assertEqual('B',a.edit_target_role)
    def test_sources_are_in_global_toolbar_with_live_toggle_pairs(self):
        a=self.app
        self.assertEqual(a.source_switches.master,a.top_source_host)
        self.assertTrue(a.source_tab_buttons['A'].winfo_viewable())
        self.assertTrue(a.source_tab_buttons['B'].winfo_viewable())
        self.assertTrue(a.source_tab_buttons['Music'].winfo_viewable())
        for w in (a.preview_camera,a.preview_camera_b,a.preview_microphone):
            self.assertTrue(w.winfo_viewable())
        self.assertGreater(a.source_switches.winfo_rootx(),a.record_button.winfo_rootx())
    def test_preview_header_unmounted_and_mix_controls_ordered(self):
        a=self.app
        self.assertFalse(a.programme_toolbar.winfo_viewable())
        m=a.visual_mix
        self.assertTrue(m.focus_button.winfo_viewable())
        self.assertLess(m.transition_group.winfo_rooty(),m.fader.winfo_rooty())
        self.assertGreater(m.focus_button.winfo_rootx(),m.transition_group.winfo_rootx())
    def test_no_clip_fx_buttons_or_auto_selection_of_clip_rack(self):
        a=self.app
        for role in ('A','B'):
            page=a.queue_deck.pages[role]
            self.assertFalse(page.fx_button.winfo_viewable())
            self.assertFalse(page.item_effects_button.winfo_viewable())
    def test_file_menu_owns_save_export_and_top_has_clear_output_view(self):
        a=self.app
        self.assertFalse(a.save_project_button.winfo_viewable())
        self.assertFalse(a.export_project_button.winfo_viewable())
        self.assertIn('Output',a.output_viewer_button.cget('text'))
        outputs=[x for x in a.global_toolbar.items if getattr(x['widget'],'command_id','')=='output.viewer']
        self.assertEqual(1,len(outputs))
        self.assertLessEqual(len(a.preview_camera.cget('text')),3)
        self.assertLessEqual(len(a.preview_microphone.cget('text')),3)
        names=[a.application_menu.entrycget(i,'label') for i in range(a.application_menu.index('end')+1) if a.application_menu.type(i)!='separator']
        self.assertTrue(any('Save' in name for name in names))
        self.assertTrue(any('Export' in name for name in names))
        for w in (a.master_fx_button,a.record_button,a.output_viewer_button):
            self.assertTrue(w.winfo_viewable())
        heights=[w.winfo_height() for w in (a.master_fx_button,a.record_button,a.output_viewer_button)]
        self.assertLessEqual(max(heights)-min(heights),2)
    def test_compact_header_keeps_primary_toggles_visible(self):
        a=self.app;a.geometry('1024x768+0+0');a.sidebar.set_open('Music',True);a.open_effects_context('Master');a.update()
        for w in (a.source_tab_buttons['A'],a.source_tab_buttons['B'],a.source_tab_buttons['Music'],a.preview_camera,a.preview_camera_b,a.preview_microphone,a.master_fx_button,a.record_button):
            self.assertTrue(w.winfo_viewable(),str(w))
            self.assertLessEqual(w.winfo_rootx()+w.winfo_width(),a.winfo_rootx()+a.winfo_width()+1)
