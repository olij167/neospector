"""UX27 queue-dock geometry and compact-content assertions."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from ux26_queue_layout import requested_height,allocate,GAP

class UX27Heights(unittest.TestCase):
    def test_collapsed_visuals_reserve_only_the_chrome(self):
        self.assertLessEqual(requested_height('A',False,90),120)
        self.assertEqual(requested_height('A',False,0),requested_height('B',False,90))
    def test_expanded_content_does_not_stretch_to_fill_free_space(self):
        wants={'A':requested_height('A',True,0),'B':requested_height('B',False,7)}
        self.assertEqual(wants,allocate(('A','B'),wants,700,{'A':True,'B':False}))
    def test_music_uses_same_compact_upcoming_row_rule(self):
        self.assertLessEqual(requested_height('Music',False,9),145)
        self.assertEqual(42,requested_height('Music',True,3)-requested_height('Music',True,2))

class UX27Tk(unittest.TestCase):
    def setUp(self):
        self.sandbox=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.sandbox.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.a=NeospectorApp(test_mode=True)
        self.a.geometry('1400x880+0+0');self.pump()
    def tearDown(self):
        try:self.a.close(force=True)
        finally:self.env.stop();self.sandbox.cleanup()
    def pump(self):
        for _ in range(7):self.a.update()
    def test_audio_docked_in_left_corner_and_toolbar_does_not_expand(self):
        a=self.a
        before=a.visual_mix.winfo_height()
        a.set_audio_tray_open(True);a.sidebar.set_open('A',True);self.pump()
        audio=a.sidebar.sections['Music']['frame']
        visual=a.shell.frames['panel.library']
        self.assertTrue(audio.winfo_viewable())
        self.assertTrue(a.sidebar.music_dock_bar.winfo_viewable())
        self.assertFalse(a.visual_mix.audio_queue_button.winfo_ismapped())
        self.assertEqual(before,a.visual_mix.winfo_height())
        self.assertLess(audio.winfo_rootx(),visual.winfo_rootx())
        self.assertGreater(audio.winfo_rooty(),a.viewport.canvas.winfo_rooty())
        self.assertLessEqual(audio.winfo_rooty()+audio.winfo_height(),a.sidebar.music_dock_bar.winfo_rooty())
    def test_collapsed_visual_cards_do_not_have_empty_filler(self):
        a=self.a
        a.sidebar.set_open('A',True);a.sidebar.set_open('B',True);self.pump()
        for role in ('A','B'):
            section=a.sidebar.sections[role]['frame']
            page=a.queue_deck.pages[role]
            self.assertLessEqual(section.winfo_height(),page.winfo_reqheight()+15)
        a.sidebar.set_open('A',False);self.pump()
        self.assertLessEqual(a.sidebar.sections['B']['frame'].winfo_height(),120)
    def test_audio_header_owns_disclosure_and_collapsed_card_is_compact(self):
        a=self.a
        a.set_audio_tray_open(True);self.pump()
        page=a.queue_deck.pages['Music']
        self.assertTrue(page.queue_toggle.winfo_viewable())
        self.assertFalse(page.queue_fold.winfo_ismapped())
        self.assertLessEqual(a.audio_tray_host.winfo_height(),120)
        page.queue_toggle.invoke();self.pump()
        self.assertTrue(page.upcoming_visible)
        self.assertGreater(a.audio_tray_host.winfo_height(),120)

    def test_music_dock_respects_open_left_workbench(self):
        a=self.a
        a.set_audio_tray_open(True)
        a.sidebar.open_browser('Music','files');self.pump()
        audio=a.sidebar.sections['Music']['frame']
        browser=a.sidebar.browser_frame
        self.assertGreaterEqual(audio.winfo_rootx(),browser.winfo_rootx()+browser.winfo_width())
        self.assertTrue(audio.winfo_viewable())
        self.assertTrue(a.sidebar.music_dock_bar.winfo_viewable())
        a.sidebar.close_browser();self.pump()
        self.assertLess(audio.winfo_rootx(),browser.winfo_rootx()+browser.winfo_width())

    def test_audio_expanded_does_not_displace_visual_docks(self):
        a=self.a
        a.sidebar.set_open('A',True);a.sidebar.set_open('B',True);a.set_audio_tray_open(True);self.pump()
        before=a.sidebar.dock_bar.winfo_rooty()
        audio=a.queue_deck.pages['Music'];audio.set_future(True);self.pump()
        self.assertEqual(before,a.sidebar.dock_bar.winfo_rooty())
        self.assertEqual(a.sidebar.music_dock_bar.winfo_rooty(),a.sidebar.dock_bar.winfo_rooty())
        a.set_audio_tray_open(False);self.pump()
        self.assertFalse(a.sidebar.sections['Music']['frame'].winfo_ismapped())
        self.assertTrue(a.sidebar.music_dock_bar.winfo_viewable())

if __name__=='__main__':unittest.main()
