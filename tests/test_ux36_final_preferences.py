"""UX36 acceptance of final welcome/preferences/appearance interaction contract."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX36Tk(unittest.TestCase):
    def setUp(self):
        self.home=tempfile.TemporaryDirectory(prefix='ux36-fixture-')
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.home.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.a=NeospectorApp(test_mode=True);self.a.geometry('1390x850+0+0');self.pump()
    def pump(self):
        for _ in range(3):self.a.update()
    def tearDown(self):
        try:self.a.close(force=True)
        finally:self.env.stop();self.home.cleanup()
    @staticmethod
    def descend(root):
        result=[root]
        for c in root.winfo_children():result+=UX36Tk.descend(c)
        return result
    def test_welcome_is_project_and_preferences_not_tutorial(self):
        w=self.a.show_startup_window(True);self.pump()
        texts=[str(x.cget('text')) for x in self.descend(w) if 'text' in x.keys()]
        self.assertNotIn('Open First Light',texts)
        self.assertNotIn('Learn in place',texts)
        self.assertIn('New Project',texts);self.assertIn('Open Project…',texts)
        self.assertEqual(w.brand_heading.cget('text'),'OmN-e')
    def test_welcome_device_choices_are_readonly_and_folder_is_editable(self):
        from tkinter import ttk
        with patch('live_sources.enumerate_devices',return_value={'camera':['/dev/video4','test'],'microphone':['default','alsa_input.usb'],'notes':[]}):
            w=self.a.show_startup_window(True);self.pump()
        self.assertEqual(str(w.camera_selector.cget('state')),'readonly')
        self.assertEqual(str(w.microphone_selector.cget('state')),'readonly')
        self.assertIn('/dev/video4',w.camera_selector.cget('values'))
        self.assertIn('alsa_input.usb',w.microphone_selector.cget('values'))
        self.assertIsInstance(w.folder_entry,ttk.Entry)
        self.assertTrue(w.folder_entry.cget('state')!='readonly')
    def test_devices_preferences_show_detected_options_and_preserve_saved_unplugged(self):
        self.a.last_camera_device='/dev/video31';self.a.last_microphone_device='offline-input'
        with patch('live_sources.enumerate_devices',return_value={'camera':['/dev/video4'],'microphone':['default','alsa_input.usb'],'notes':[]}):
            p=self.a.open_preferences('devices');self.pump()
        self.assertEqual(str(p.device_selectors['camera'].cget('state')),'readonly')
        self.assertEqual(str(p.device_selectors['microphone'].cget('state')),'readonly')
        self.assertIn('/dev/video31',p.device_selectors['camera'].cget('values'))
        self.assertIn('offline-input',p.device_selectors['microphone'].cget('values'))
    def test_updates_and_support_appear_in_general_with_no_extra_tab(self):
        p=self.a.open_preferences('general');self.pump()
        self.assertNotIn('updates',p.pages)
        self.assertEqual(len(p.pages),5)
        labels=[str(x.cget('text')) for x in self.descend(p.pages['general']) if 'text' in x.keys()]
        self.assertIn('Check for updates on website',labels)
        self.assertIn('Support Neospector…',labels)
        self.assertIs(self.a.open_preferences('updates'),p)
        self.assertEqual(p.active_page(),'general')
    def test_appearance_is_theme_studio_not_another_window(self):
        p=self.a.open_preferences('appearance');self.pump()
        self.assertTrue(p.theme_editor.winfo_ismapped())
        self.assertIs(self.a.open_theme_studio(),p)
        self.assertEqual(p.active_page(),'appearance')
        self.assertTrue(p.theme_editor.vars['accent'].get().startswith('#'))
    def test_published_theme_assignments_stable_and_distinct(self):
        from builtin_themes import BUILTIN_THEMES,PUBLISHED_THEME_ORDER,BUILTIN_THEME_APPEARANCE
        from ui_chrome import resolve_theme_preference
        self.assertEqual(len(PUBLISHED_THEME_ORDER),6)
        self.assertEqual(len(set(BUILTIN_THEMES[n]['background'] for n in PUBLISHED_THEME_ORDER)),6)
        for name in PUBLISHED_THEME_ORDER:
            self.assertEqual(resolve_theme_preference(name,{},PUBLISHED_THEME_ORDER),name)
            self.assertEqual(self.a.theme_library[name],BUILTIN_THEMES[name])
            self.a.apply_theme(name,save=False)
            self.assertEqual(self.a.ui_chrome['accent'],BUILTIN_THEMES[name]['accent'])
            self.assertIn(BUILTIN_THEME_APPEARANCE[name],('light','dark'))
    def test_welcome_theme_change_opens_same_appearance_editor(self):
        w=self.a.show_startup_window(True);self.pump()
        p=w.preferences_actions['appearance']();self.pump()
        self.assertIs(p,self.a.open_preferences('appearance'))
        self.assertTrue(p.theme_editor.winfo_ismapped())

    def test_welcome_selected_default_is_saved_without_capture(self):
        with patch('live_sources.enumerate_devices',return_value={'camera':['/dev/video4'],'microphone':['default','alsa_input.usb'],'notes':[]}):
            w=self.a.show_startup_window(True)
        w.camera_default.set('/dev/video4');w.camera_selector.event_generate('<<ComboboxSelected>>');self.pump()
        w.microphone_default.set('alsa_input.usb');w.microphone_selector.event_generate('<<ComboboxSelected>>');self.pump()
        self.assertEqual(self.a.last_camera_device,'/dev/video4')
        self.assertEqual(self.a.last_microphone_device,'alsa_input.usb')
        self.assertFalse(self.a.live.source_states())
    def test_editor_builtin_switch_then_apply_keeps_exact_published_palette(self):
        from builtin_themes import BUILTIN_THEMES
        p=self.a.open_preferences('appearance');p.theme_editor.base.set('Smitzu Funk');p.theme_editor.load_base()
        self.assertEqual(self.a.ui_chrome['background'],BUILTIN_THEMES['Smitzu Funk']['background'])
        self.assertTrue(p.apply())
        self.assertEqual(self.a.theme_name.get(),'Smitzu Funk')
        self.assertEqual(self.a.ui_chrome['accent'],BUILTIN_THEMES['Smitzu Funk']['accent'])
    def test_editing_built_in_creates_separate_custom_theme(self):
        from builtin_themes import BUILTIN_THEMES
        builtin=BUILTIN_THEMES['Pungent Funk']['accent']
        p=self.a.open_preferences('appearance');p.theme_editor.base.set('Pungent Funk');p.theme_editor.load_base()
        p.theme_editor.vars['accent'].set('#2176A7');self.pump()
        self.assertTrue(p.apply())
        self.assertEqual(BUILTIN_THEMES['Pungent Funk']['accent'],builtin)
        self.assertEqual(self.a.theme_name.get(),'Pungent Funk (custom)')
        self.assertEqual(self.a.theme_library['Pungent Funk (custom)']['accent'],'#2176A7')
    def test_import_folder_can_be_blank_without_auto_import(self):
        p=self.a.open_preferences('devices');p.vars['auto_import'].set(False);p.vars['folder'].set('')
        self.assertTrue(p.apply())
        self.assertEqual(self.a.last_import_folder,'')

    def test_cancel_preference_theme_preview_restores_previous_theme(self):
        from builtin_themes import BUILTIN_THEMES
        a=self.a;self.assertEqual(a.theme_name.get(),'Pungent Funk')
        p=a.open_preferences('appearance');p.theme_editor.base.set('Beth Funk');p.theme_editor.load_base()
        self.assertEqual(a.ui_chrome['background'],BUILTIN_THEMES['Beth Funk']['background'])
        p.close();self.pump()
        self.assertEqual(a.theme_name.get(),'Pungent Funk')
        self.assertEqual(a.ui_chrome['background'],BUILTIN_THEMES['Pungent Funk']['background'])
    def test_theme_apply_then_close_preserves_applied_palette(self):
        from builtin_themes import BUILTIN_THEMES
        a=self.a;p=a.open_preferences('appearance');p.theme_editor.base.set('Space Funk');p.theme_editor.load_base()
        self.assertTrue(p.apply());p.close();self.pump()
        self.assertEqual(a.theme_name.get(),'Space Funk')
        self.assertEqual(a.ui_chrome['background'],BUILTIN_THEMES['Space Funk']['background'])

    def test_welcome_auto_import_toggle_updates_profile(self):
        w=self.a.show_startup_window(True);self.pump()
        self.assertFalse(self.a.auto_import_media)
        w.auto_import_toggle.invoke();self.pump()
        self.assertTrue(self.a.auto_import_media)
        w.auto_import_toggle.invoke();self.pump()
        self.assertFalse(self.a.auto_import_media)
