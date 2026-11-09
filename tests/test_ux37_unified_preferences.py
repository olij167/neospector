"""UX37: one live selection, reversible Appearance preview, inline canvas controls."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX37Tk(unittest.TestCase):
    def setUp(self):
        self.home=tempfile.TemporaryDirectory(prefix='ux37-')
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.home.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True);self.app.geometry('1450x900+0+0');self.pump()
    def pump(self):
        for _ in range(3):self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.home.cleanup()
    def test_welcome_theme_select_rethemes_existing_welcome_and_persists(self):
        from builtin_themes import BUILTIN_THEMES
        a=self.app;w=a.show_startup_window(True);self.pump()
        w.theme_var.set('Beth Funk');w.theme_combo.event_generate('<<ComboboxSelected>>');self.pump()
        self.assertEqual(a.theme_name.get(),'Beth Funk')
        self.assertEqual(a.ui_chrome['background'],BUILTIN_THEMES['Beth Funk']['background'])
        self.assertEqual(w.theme_combo.get(),'Beth Funk')
        self.assertEqual(w.welcome_canvas.cget('bg'),BUILTIN_THEMES['Beth Funk']['panel_bg'])
        self.assertEqual(w.brand_heading.cget('fg'),BUILTIN_THEMES['Beth Funk']['accent'])
        a.test_mode=False
        a.save_preferences()
        a.test_mode=True
        self.assertEqual(a.read_preferences()['theme_name'],'Beth Funk')
    def test_preview_shares_theme_name_then_cancel_reverts_in_both_locations(self):
        a=self.app;w=a.show_startup_window(True);p=a.open_preferences('appearance')
        p.theme_editor.base.set('Space Funk');p.theme_editor.load_base();self.pump()
        self.assertEqual(w.theme_combo.get(),'Space Funk')
        self.assertEqual(a.theme_name.get(),'Space Funk')
        p.close();self.pump()
        self.assertEqual(w.theme_combo.get(),'Pungent Funk')
        self.assertEqual(a.theme_name.get(),'Pungent Funk')
    def test_welcome_choice_while_preferences_open_is_applied_not_reverted(self):
        a=self.app;w=a.show_startup_window(True);p=a.open_preferences('appearance');self.pump()
        w.theme_var.set('Mik Funk');w.theme_combo.event_generate('<<ComboboxSelected>>');self.pump()
        self.assertEqual(p.theme_editor.base.get(),'Mik Funk')
        p.close();self.pump()
        self.assertEqual(a.theme_name.get(),'Mik Funk')
    def test_all_six_published_themes_appear_and_match_exact_palette(self):
        from builtin_themes import BUILTIN_THEMES,PUBLISHED_THEME_ORDER
        w=self.app.show_startup_window(True);self.pump()
        for name in PUBLISHED_THEME_ORDER:
            w.theme_var.set(name);w.theme_combo.event_generate('<<ComboboxSelected>>');self.pump()
            self.assertEqual(self.app.ui_chrome['background'],BUILTIN_THEMES[name]['background'])
            self.assertEqual(self.app.ui_chrome['accent'],BUILTIN_THEMES[name]['accent'])
            self.assertEqual(w.brand_heading.cget('fg'),BUILTIN_THEMES[name]['accent'])
    def test_preferences_footer_remains_visible_at_small_window_height(self):
        from tkinter import ttk
        p=self.app.open_preferences('appearance');p.geometry('760x540+10+10');self.pump()
        foot=p.footer_frame
        self.assertTrue(foot.winfo_ismapped())
        self.assertGreaterEqual(foot.winfo_height(),24)
        self.assertLessEqual(foot.winfo_rooty()+foot.winfo_height(),p.winfo_rooty()+p.winfo_height()+2)
        p.select('output');self.pump()
        self.assertLessEqual(foot.winfo_rooty()+foot.winfo_height(),p.winfo_rooty()+p.winfo_height()+2)

    def test_output_advanced_controls_are_inline_and_no_popup_button(self):
        p=self.app.open_preferences('output');self.pump()
        text=[x.cget('text') for x in self._desc(p.pages['output']) if 'text' in x.keys()]
        self.assertNotIn('Advanced canvas and sequence settings…',text)
        for field in ('project_name','duration','background','output_preset'):
            self.assertIn(field,p.vars)
        self.assertIn('Canvas & sequence',text)
    def test_inline_output_apply_is_one_transaction_and_keeps_project(self):
        a=self.app;p=a.open_preferences('output');self.pump()
        p.vars['project_name'].set('My show');p.vars['duration'].set('33')
        p.vars['background'].set('#456ABC');p.vars['width'].set('1280');p.vars['height'].set('720')
        self.assertTrue(p.apply());self.pump()
        self.assertEqual(a.project.name,'My show');self.assertEqual(a.project.duration,33)
        self.assertEqual(a.project.background,'#456ABC')
        self.assertIs(a.sequence_settings(),p)
        self.assertEqual(p.active_page(),'output')
    def test_welcome_has_single_preferences_entry_not_redundant_shortcuts(self):
        w=self.app.show_startup_window(True);self.pump()
        text=[x.cget('text') for x in self._desc(w) if 'text' in x.keys()]
        self.assertIn('Preferences…',text)
        self.assertNotIn('Output Settings…',text)
        self.assertNotIn('Recording Settings…',text)
    @staticmethod
    def _desc(root):
        out=[root]
        for child in root.winfo_children():out.extend(UX37Tk._desc(child))
        return out
