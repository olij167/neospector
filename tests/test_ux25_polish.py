"""UX25 focused geometry, source state, and direct-placement regressions."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX25Tk(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.temp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True)
        self.app.geometry('1200x840+0+0')
        for _ in range(3):self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.temp.cleanup()
    def idle(self):
        for _ in range(4):self.app.update()

    def test_single_and_triple_queues_are_bottom_docked_and_unresizable(self):
        a=self.app;s=a.sidebar
        self.assertEqual('TFrame',s.pane.winfo_class())
        for role in ('A','B','Music'):
            self.assertTrue(s.dock_buttons[role].winfo_viewable())
            self.assertGreater(s.dock_buttons[role].winfo_rooty(),a.viewport.winfo_rooty()+a.viewport.winfo_height()*.7)
        s.set_open('A',True);self.idle()
        self.assertTrue(s.sections['A']['frame'].winfo_viewable())
        self.assertLess(s.winfo_height(),a.viewport.winfo_height()*.6)
        for role in ('B','Music'):s.set_open(role,True)
        self.idle()
        for role in ('A','B','Music'):
            self.assertTrue(s.sections[role]['frame'].winfo_viewable())
        self.assertLess(s.winfo_height(),a.viewport.winfo_height()*.85)
        bottom=a.shell.frames['panel.library'].winfo_rooty()+a.shell.frames['panel.library'].winfo_height()
        self.assertLessEqual(bottom,s.dock_bar.winfo_rooty()+2)
        self.assertFalse(a.shell.grips['right'].winfo_ismapped())
        s.set_open('Music',False);self.idle()
        self.assertGreater(s.winfo_rooty(),a.viewport.winfo_rooty()+a.viewport.winfo_height()*.4)

    def test_top_is_labeled_live_controls_bottom_is_queue_visibility(self):
        a=self.app
        for role in ('A','B'):
            camera=a.source_capture_buttons[role]
            self.assertTrue(camera.winfo_viewable())
            self.assertIn(role,camera.cget('text'))
            self.assertLess(camera.winfo_rooty(),a.viewport.winfo_rooty())
            self.assertGreater(a.source_tab_buttons[role].winfo_rooty(),a.viewport.winfo_rooty()+300)
        self.assertIn('MIC',a.source_capture_buttons['Music'].cget('text'))

    def test_queued_camera_is_seen_by_top_toggle_and_skips_on_toggle_off(self):
        a=self.app
        from sequencer_model import add_asset
        from instrument_model import voice
        from queue_model import append_assets,current
        from ux25_source_state import queued_camera_active
        layer=voice(a.project,'A')
        def assign():
            cam=add_asset(a.project,path='live:camera',kind='camera',name='Test camera',metadata={
                'device':'test','sequence_preferences':{'clip_min':10.}})
            image=add_asset(a.project,path='/tmp/ux25-image.png',kind='image',name='Following still',metadata={
                'sequence_preferences':{'clip_min':6.}})
            append_assets(a.project,layer.id,[cam.id,image.id])
        a.transaction('Test camera queue',assign)
        self.idle();a.refresh_primary_toolbar()
        self.assertTrue(queued_camera_active(a.project,layer,a.playhead))
        self.assertIn('●',a.preview_camera.cget('text'))
        self.assertEqual('camera',a.queue_deck.pages['A'].live_device_kind())
        # No hardware is needed to test release of an already queued source.
        a.queue_deck.pages['A'].toggle_camera();self.idle()
        self.assertFalse(queued_camera_active(a.project,layer,a.playhead))
        self.assertEqual('Following still',a.project.asset(current(layer,a.playhead).asset_id).name)
        self.assertNotIn('●',a.preview_camera.cget('text'))
        self.assertTrue(any(c.name=='Following still' for c in a.project.assets.values()))

    def test_shared_shelf_updates_without_tab_navigation(self):
        a=self.app
        a.sidebar.open_browser('A','files');self.idle()
        browser=a.sidebar.source_shelf.media
        from sequencer_model import add_asset
        a.transaction('New project media',lambda:add_asset(a.project,path='/tmp/fresh-asset.png',kind='image',name='Instantly visible'))
        a.refresh_library();self.idle()
        self.assertTrue(any('Instantly visible' in browser.items.item(i,'text') for i in browser.items.get_children()))
        self.assertEqual(('▶','⏭','＋'),tuple(browser.items.item(browser.items.get_children()[-1],'values')))
        self.assertFalse(browser.actions_frame.winfo_ismapped())
        browser.items.selection_set(browser.items.get_children()[-1]);browser.choose_destination('B')
        self.assertEqual('B',a.sidebar._flash_role)
        self.assertEqual('UX25.Signal.TButton',a.source_tab_buttons['B'].cget('style'))
        self.assertEqual('#b6cb79',a.sidebar.sections['B']['frame'].cget('highlightbackground'))

if __name__=='__main__':unittest.main()
