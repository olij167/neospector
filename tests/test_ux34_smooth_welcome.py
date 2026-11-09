"""UX34: unchanged surfaces do not churn; onboarding actions remain discoverable."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX34Tk(unittest.TestCase):
    def setUp(self):
        self.home=tempfile.TemporaryDirectory(prefix='ux34-test-')
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.home.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.a=NeospectorApp(test_mode=True)
        self.a.geometry('1380x860+0+0')
        self.pump()
    def pump(self):
        for _ in range(3):self.a.update()
    def tearDown(self):
        try:self.a.close(force=True)
        finally:self.env.stop();self.home.cleanup()
    def test_toggling_peer_does_not_unmount_existing_queue(self):
        s=self.a.sidebar
        s.set_open('A',True);self.pump()
        original=s.sections['A']['frame']
        self.assertEqual(original.winfo_manager(),'pack')
        with patch.object(original,'pack_forget',wraps=original.pack_forget) as forget:
            s.set_open('B',True)
            self.assertEqual(forget.call_count,0,'A should remain mounted while B opens')
        self.pump()
        self.assertTrue(original.winfo_ismapped())
    def test_queue_sync_does_not_reconfigure_unchanged_peers(self):
        s=self.a.sidebar;s.set_open('A',True);s.set_open('B',True);self.pump()
        f=s.sections['A']['frame']
        with patch.object(f,'pack_configure',wraps=f.pack_configure) as configure:
            s._sync()
            self.assertEqual(configure.call_count,0,'unchanged layout must not reconfigure the existing card')
    def test_repeated_source_tab_selection_is_stable(self):
        shelf=self.a.sidebar.source_shelf
        shelf.show('files');self.pump()
        with patch.object(shelf.media,'pack_forget',wraps=shelf.media.pack_forget) as forget, patch.object(shelf.media,'refresh',wraps=shelf.media.refresh) as refresh:
            shelf.show('files')
            self.assertEqual(forget.call_count,0,'already selected tab must not disappear')
            self.assertFalse(any(c.kwargs.get('force',False) for c in refresh.call_args_list),'unchanged browser must not force a list rebuild')
    def test_unchanged_media_list_does_not_delete_rows(self):
        browser=self.a.sidebar.source_shelf.media
        # Populate a row without needing physical media, then repeat a forced refresh.
        from sequencer_model import Asset
        asset=Asset('test-media','/tmp/ux34-example.png','image','Test image',1,32,32,{})
        self.a.project.assets[asset.id]=asset
        browser.refresh(force=True)
        with patch.object(browser.items,'delete',wraps=browser.items.delete) as deleted, patch.object(browser.items,'insert',wraps=browser.items.insert) as inserted:
            browser.refresh(force=True)
            self.assertEqual(deleted.call_count,0)
            self.assertEqual(inserted.call_count,0)
    def test_idle_rack_refresh_keeps_widget_geometry(self):
        a=self.a
        a.open_effects_context('Transition');self.pump()
        cell=a.deck.selected_cell()
        with patch.object(cell,'relayout',wraps=cell.relayout) as layout:
            a.deck.refresh(False)
            a.deck.refresh(False)
            self.assertEqual(layout.call_count,0,'nonstructural refresh should update values, not reflow the entire rack')
    def test_welcome_canceled_example_preserves_current_project(self):
        self.a.show_startup_window(True);self.pump()
        win=self.a.startup_window;project=self.a.project
        with patch.object(self.a,'confirm_discard',return_value=False):
            self.a.welcome_example.invoke()
        self.pump()
        self.assertIs(self.a.project,project)
        self.assertTrue(win.winfo_exists())

    def test_welcome_is_responsive_at_narrow_width_without_live_inputs(self):
        self.a.show_startup_window(True);self.pump()
        win=self.a.startup_window
        win.geometry('515x430+0+0');self.pump()
        self.assertEqual(win._welcome_columns,1)
        self.assertFalse(self.a.live.camera_is_active('A') if hasattr(self.a.live,'camera_is_active') else False)
        self.assertTrue(win.winfo_exists())
    def test_welcome_actions_and_guided_path_are_available(self):
        win=self.a.show_startup_window(True)
        self.pump()
        win=self.a.startup_window
        self.assertTrue(win.winfo_exists())
        self.assertTrue(hasattr(win,'onboarding_actions'))
        self.assertEqual(set(win.onboarding_actions),{'media','queues','effects'})
        self.assertTrue(all(callable(v) for v in win.onboarding_actions.values()))
        win.onboarding_actions['effects']()
        self.pump()
        self.assertTrue(self.a.shell.rack_open)
        self.assertFalse(win.winfo_exists())
