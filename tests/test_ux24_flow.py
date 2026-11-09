"""UX24 queue-first navigation and unambiguous mixer controls."""
import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app_source'))

class UX24Tk(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.temp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True)
        self.app.geometry('1440x900+0+0');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.temp.cleanup()
    def test_media_is_one_click_from_main_toolbar_not_behind_channel_add(self):
        a=self.app
        self.assertTrue(a.media_sources_button.winfo_viewable())
        self.assertIn('Media',a.media_sources_button.cget('text'))
        self.assertFalse(a.sidebar._browser_open)
        a.media_sources_button.invoke();a.update()
        self.assertTrue(a.sidebar._browser_open)
        self.assertTrue(a.sidebar.source_shelf.winfo_viewable())
        self.assertFalse(a.sidebar.browser_frame.master is a.sidebar.pane)
        self.assertEqual((),a.sidebar.open_roles())
        a.media_sources_button.invoke();a.update()
        self.assertFalse(a.sidebar._browser_open)
    def test_record_and_output_are_inside_preview_mixer_beside_focus(self):
        a=self.app;mix=a.visual_mix
        self.assertIs(a.record_button.master,mix.preview_actions)
        self.assertIs(a.output_viewer_button.master,mix.preview_actions)
        self.assertIs(mix.focus_button.master,mix.preview_actions)
        self.assertTrue(a.record_button.winfo_viewable())
        self.assertTrue(a.output_viewer_button.winfo_viewable())
    def test_empty_queue_keeps_current_context_and_direct_media_discovery(self):
        a=self.app;a.sidebar.set_open('A',True);a.update()
        p=a.queue_deck.pages['A']
        self.assertTrue(p.current_canvas.winfo_viewable())
        self.assertFalse(p.browse_button.winfo_viewable())
        self.assertTrue(p.source_shortcuts.winfo_viewable())
        self.assertEqual({'files','camera','screen'},set(p.shortcut_buttons))
        p.shortcut_buttons['files'].invoke();a.update()
        self.assertEqual('A',a.sidebar.source_shelf.destination)
        p.shortcut_buttons['camera'].invoke();a.update()
        self.assertEqual('camera',a.sidebar.source_shelf.mode)
    def test_transition_popovers_close_on_outside_click_escape_and_reopen(self):
        a=self.app;m=a.visual_mix
        m.open_transition_menu();a.update()
        self.assertTrue(m._choice_popup.winfo_exists())
        a.viewport.canvas.event_generate('<ButtonPress-1>',x=4,y=4);a.update()
        self.assertIsNone(m._choice_popup)
        m.open_band_menu() if a.project.voice_mix.mode=='react' else m.open_transition_menu()
        a.update();self.assertIsNotNone(m._choice_popup)
        a.event_generate('<Escape>');a.update()
        self.assertIsNone(m._choice_popup)
        m.open_transition_menu();a.update()
        self.assertIsNotNone(m._choice_popup)
        m.open_transition_menu();a.update()
        self.assertIsNone(m._choice_popup)
    def test_transition_selection_and_band_selector_do_not_leave_stale_popup(self):
        a=self.app;m=a.visual_mix
        m.open_transition_menu();a.update()
        option=m._choice_popup.winfo_children()[0].winfo_children()[1]
        option.invoke();a.update()
        self.assertIsNone(m._choice_popup)
        self.assertNotEqual('dissolve',a.project.extra.get('ux16_transition',{}).get('kind'))
        m.set_reactive(True);m.open_band_menu();a.update()
        self.assertIsNotNone(m._choice_popup)
        option=m._choice_popup.winfo_children()[0].winfo_children()[1]
        option.invoke();a.update()
        self.assertIsNone(m._choice_popup)
        self.assertEqual('bass',a.project.voice_mix.react_band)
    def test_preview_actions_and_right_sources_fit_1024_with_all_docks(self):
        a=self.app;a.geometry('1024x768+0+0');a.update()
        a.media_sources_button.invoke();a.toggle_main_effects()
        for r in ('A','B','Music'):a.sidebar.set_open(r,True)
        for _ in range(6):a.update()
        m=a.visual_mix
        for b in (a.record_button,a.output_viewer_button,m.focus_button):
            self.assertTrue(b.winfo_viewable(),b)
            self.assertLessEqual(b.winfo_rootx()+b.winfo_width(),a.viewport.winfo_rootx()+a.viewport.winfo_width()+2,b)
        self.assertTrue(a.sidebar.source_shelf.winfo_viewable())
        self.assertTrue(a.queue_deck.pages['A'].winfo_viewable())
    def test_depth_is_not_refreshed_during_pointer_gesture(self):
        m=self.app.visual_mix;m.set_reactive(True);self.app.update()
        m._depth_dragging=True;m.react_depth.set(.37)
        for _ in range(8):m.refresh();self.app.update_idletasks()
        self.assertAlmostEqual(.37,m.react_depth.get(),places=2)
        m.finish_depth_drag();self.app.update()
        self.assertAlmostEqual(.37,abs(self.app.project.voice_mix.react_amount),places=2)

if __name__=='__main__':unittest.main()
