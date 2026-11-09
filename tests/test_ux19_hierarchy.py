"""UX19: a preview-first dock, zero empty sidebar width and semantic source controls."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX19Hierarchy(unittest.TestCase):
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
    def test_preview_uses_full_width_when_all_source_panes_are_closed(self):
        a=self.app
        self.assertEqual((),a.sidebar.open_roles())
        self.assertFalse(a.shell.frames['panel.library'].winfo_viewable())
        self.assertGreater(a.shell.frames['panel.programme'].winfo_width(),a.shell.stage.winfo_width()*.96)
    def test_a_b_and_audio_are_independent_header_actions(self):
        a=self.app
        for role in ('A','B','Music'):
            self.assertTrue(a.source_tab_buttons[role].winfo_viewable())
        a.source_tab_buttons['A'].invoke();a.source_tab_buttons['Music'].invoke();a.update()
        self.assertEqual(('A','Music'),a.sidebar.open_roles())
        self.assertTrue(a.shell.frames['panel.library'].winfo_viewable())
        a.source_tab_buttons['A'].invoke();a.source_tab_buttons['Music'].invoke();a.update()
        self.assertEqual((),a.sidebar.open_roles())
        self.assertFalse(a.shell.frames['panel.library'].winfo_viewable())
    def test_fx_docks_adjacent_not_over_preview(self):
        a=self.app
        a.open_effects_context('Master');a.update()
        rack=a.shell.frames['panel.rack'];preview=a.shell.frames['panel.programme']
        self.assertTrue(rack.winfo_viewable())
        self.assertLessEqual(rack.winfo_rootx()+rack.winfo_width(),preview.winfo_rootx())
        self.assertGreater(preview.winfo_height(),a.shell.stage.winfo_height()*.9)
    def test_fx_and_audio_fit_in_compact_window(self):
        a=self.app
        a.geometry('1024x768+0+0');a.sidebar.set_open('Music',True)
        a.open_effects_context('Master');a.update()
        for pid in ('panel.programme','panel.library','panel.rack'):
            frame=a.shell.frames[pid]
            self.assertTrue(frame.winfo_viewable(),pid)
            self.assertGreater(frame.winfo_width(),250,pid)
        preview=a.shell.frames['panel.programme'];rack=a.shell.frames['panel.rack']
        self.assertLessEqual(rack.winfo_rootx()+rack.winfo_width(),preview.winfo_rootx())
    def test_empty_queue_has_one_clear_browse_action(self):
        a=self.app;a.sidebar.set_open('B',True);a.update()
        b=a.queue_deck.pages['B'];b.refresh(True);a.update()
        self.assertFalse(b.queue_fold.winfo_viewable())
        self.assertTrue(b.browse_button.winfo_viewable())
    def test_compact_header_keeps_camera_mic_and_source_access_visible(self):
        a=self.app
        a.geometry('1024x768+0+0');a.sidebar.set_open('A',True)
        a.open_effects_context('Master');a.update()
        self.assertTrue(a.preview_camera.winfo_viewable())
        self.assertTrue(a.preview_microphone.winfo_viewable())
        self.assertTrue(a.source_tab_buttons['A'].winfo_viewable())
        self.assertTrue(a.source_tab_buttons['Music'].winfo_viewable())
        self.assertLessEqual(a.preview_microphone.winfo_rootx()+a.preview_microphone.winfo_width(),
                             a.viewport_frame.winfo_rootx()+a.viewport_frame.winfo_width())

    def test_radio_only_is_compact_and_docked_bottom_right(self):
        a=self.app;a.sidebar.set_open('Music',True);a.update()
        radio=a.shell.frames['panel.library']
        self.assertTrue(radio.winfo_viewable())
        self.assertLessEqual(radio.winfo_height(),150)
        self.assertGreater(radio.winfo_rooty(),a.shell.stage.winfo_rooty()+a.shell.stage.winfo_height()*.75)

    def test_module_vary_and_delete_have_distinct_semantics(self):
        from effects_engine import make_effect
        a=self.app;fx=make_effect('blur');a.project.master_rack.append(fx)
        a.open_effects_context('Master');a.deck.refresh(True);a.update()
        cell=a.deck.selected_cell();controls=cell.card_controls[fx.id]
        self.assertEqual('UX19.Delete.TButton',controls['delete'].cget('style'))
        shell=cell.card_parts[fx.id][0]
        vary=[w for w in shell.footer.winfo_children() if getattr(w,'cget',lambda x:None)('text')=='Vary']
        self.assertEqual(1,len(vary))
        self.assertEqual('UX19.Vary.TButton',vary[0].cget('style'))

    def test_roles_have_distinct_capture_and_record_hierarchy(self):
        a=self.app
        self.assertNotEqual(a.preview_camera.cget('style'),a.preview_microphone.cget('style'))
        self.assertNotEqual(a.record_button.cget('style'),a.save_project_button.cget('style'))
