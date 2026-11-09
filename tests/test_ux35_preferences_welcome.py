"""UX35: user-configurable start, shared preferences, and fully visible rack controls."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX35Tk(unittest.TestCase):
    def setUp(self):
        self.home=tempfile.TemporaryDirectory(prefix='ux35-fixture-')
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.home.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.a=NeospectorApp(test_mode=True)
        self.a.geometry('1450x900+0+0');self.pump()
    def pump(self):
        for _ in range(4):self.a.update()
    def tearDown(self):
        try:self.a.close(force=True)
        finally:self.env.stop();self.home.cleanup()
    def test_welcome_has_brand_recents_and_immediate_controls(self):
        from pathlib import Path
        path=Path(self.home.name)/'Recent.omne-sequence.json';path.write_text('{}')
        self.a.recent_projects=[str(path)]
        w=self.a.show_startup_window(True);self.pump()
        self.assertTrue(hasattr(w,'preferences_actions'))
        self.assertTrue(hasattr(w,'recent_project_actions'))
        self.assertIn(str(path),w.recent_project_actions)
        self.assertEqual(set(('devices','recording','output','appearance')).difference(w.preferences_actions),set())
        self.assertIn('OmN-e',w.brand_heading.cget('text'))
        self.assertEqual(w.product_title.cget('text'),'Neospector')
        self.assertTrue(w.support_button.winfo_ismapped())
    def test_file_menu_exposes_every_welcome_destination(self):
        labels=[self.a.application_menu.entrycget(i,'label') for i in range(self.a.application_menu.index('end')+1) if self.a.application_menu.type(i)=='command']
        for required in ('Preferences…','Theme Studio…','Welcome…','Check for Updates…','Support Neospector…','Media & Sources…','Visual Queues…','Effects…','New Project','Open Project…'):
            self.assertIn(required,labels)
    def test_preferences_use_one_window_with_target_pages(self):
        a=self.a;p=a.open_preferences('recording');self.pump()
        self.assertEqual(p.active_page(),'recording')
        self.assertIs(a.open_preferences('devices'),p)
        self.assertEqual(p.active_page(),'devices')
        self.assertIn('appearance',p.pages)
        self.assertIn('output',p.pages)
        self.assertIn('general',p.pages)
    def test_saved_defaults_update_no_live_sources(self):
        a=self.a;p=a.open_preferences('devices')
        p.vars['camera'].set('/dev/video5');p.vars['microphone'].set('test-device');p.vars['folder'].set(str(Path(self.home.name)))
        p.vars['auto_import'].set(True)
        self.assertTrue(p.apply())
        self.assertEqual(a.last_camera_device,'/dev/video5')
        self.assertEqual(a.last_microphone_device,'test-device')
        self.assertTrue(a.auto_import_media)
        self.assertFalse(a.live.source_states())
    def test_bounded_auto_import_filters_unsupported_and_symlinks(self):
        a=self.a;folder=Path(self.home.name)
        (folder/'demo.png').write_bytes(b'png')
        (folder/'notes.txt').write_text('ignore')
        (folder/'link.mp4').symlink_to(folder/'demo.png')
        a.last_import_folder=str(folder);a.auto_import_media=True
        with patch.object(a,'import_files') as imported:
            self.assertTrue(a.auto_import_folder_if_enabled())
            self.assertEqual(imported.call_args.args[0],[str(folder/'demo.png')])
        a.auto_import_media=False
        with patch.object(a,'import_files') as imported:
            self.assertFalse(a.auto_import_folder_if_enabled())
            imported.assert_not_called()

    def test_live_recording_dialog_uses_same_preferences_browser(self):
        p=self.a.open_record_settings();self.pump()
        self.assertIs(p,self.a.open_preferences('recording'))
        self.assertEqual(p.active_page(),'recording')

    def test_card_height_covers_all_five_parameter_rows_and_footer(self):
        from effects_engine import make_effect
        a=self.a;a.open_effects_context('Transition')
        a.insert_module_from_library(make_effect('transition_iris'),'Iris')
        self.pump();cell=a.deck.selected_cell()
        self.assertTrue(cell.card_parts)
        shell,body,_=next(iter(cell.card_parts.values()))
        # Inspect measured requirements rather than a hard-coded height across DPI values.
        rows=1+max(int(r.grid_info()['row']) for r in shell.fader_rows if r.winfo_manager()=='grid')
        row_height=max(r.winfo_reqheight() for r in shell.fader_rows)
        chrome=sum(w.winfo_reqheight() for w in shell.pack_slaves() if w is not body)
        self.assertGreaterEqual(shell.winfo_height(),rows*row_height+chrome+12)
        self.assertGreaterEqual(shell.footer.winfo_rooty(),max(r.winfo_rooty()+r.winfo_height() for r in shell.fader_rows)+6)
