"""UX26 live Tk acceptance: direct source grammar and content-aware dock geometry."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX26Integration(unittest.TestCase):
    def setUp(self):
        self.sandbox=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.sandbox.name,
                                         'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.a=NeospectorApp(test_mode=True)
        self.a.geometry('1400x880+0+0');self.idle()
    def tearDown(self):
        try:self.a.close(force=True)
        finally:self.env.stop();self.sandbox.cleanup()
    def idle(self):
        for i in range(4):self.a.update()
    def add_visual(self,role,count):
        from instrument_model import voice
        from sequencer_model import add_asset
        from queue_model import append_assets
        a=self.a
        def apply():
            assets=[add_asset(a.project,path=f'/tmp/ux26-{role}-{i}.png',kind='image',name=f'{role} asset {i}',metadata={'sequence_preferences':{'clip_min':6.}}) for i in range(count)]
            append_assets(a.project,voice(a.project,role).id,[x.id for x in assets])
        a.transaction('Fixture',apply)
        self.idle()
    def test_mix_strip_keeps_height_and_mic_is_next_to_react(self):
        # UX27: the Audio queue moved to its own bottom-left preview dock;
        # the reaction toolbar continues to own MIC, without growing.
        a=self.a;mix=a.visual_mix;before=mix.winfo_height()
        self.assertTrue(mix.mic_button.winfo_viewable())
        self.assertFalse(mix.audio_queue_button.winfo_ismapped())
        self.assertTrue(a.sidebar.music_button.winfo_viewable())
        self.assertEqual(a.source_capture_buttons['Music'],mix.mic_button)
        a.set_audio_tray_open(True);self.idle()
        self.assertEqual(before,mix.winfo_height())
        self.assertTrue(a.audio_tray_host.winfo_viewable())
        self.assertLess(a.audio_tray_host.winfo_rootx(),a.sidebar.dock_bar.winfo_rootx())
        a.set_audio_tray_open(False);self.idle()
        self.assertFalse(a.audio_tray_host.winfo_ismapped())
        self.assertEqual(before,mix.winfo_height())
    def test_browser_single_list_and_destination_exclusive_with_effects(self):
        a=self.a;s=a.sidebar
        self.assertEqual({},s.source_shelf.tabs)
        self.assertEqual({'A','B','Music'},set(s.source_shelf.dest_buttons))
        s.open_browser('A','files');self.idle()
        self.assertTrue(s.browser_frame.winfo_viewable())
        s.source_shelf.prefer('Music');self.idle()
        self.assertEqual('Music',s.source_shelf.destination_choice.get())
        self.assertEqual('Music',s.source_shelf.media.destination)
        a.open_effects_context('Master');self.idle()
        self.assertFalse(s._browser_open)
        self.assertTrue(a.shell.rack_open)
        s.open_browser('B','files');self.idle()
        self.assertFalse(a.shell.rack_open)
        self.assertTrue(s._browser_open)
    def test_queue_heights_symmetric_and_never_cover_preview_top(self):
        a=self.a;s=a.sidebar
        self.add_visual('A',8);self.add_visual('B',4)
        s.set_open('A',True);s.set_open('B',True)
        a.queue_deck.pages['A'].set_future(True)
        a.queue_deck.pages['B'].set_future(True)
        a.set_audio_tray_open(True);self.idle()
        aheight=s.sections['A']['frame'].winfo_height()
        bheight=s.sections['B']['frame'].winfo_height()
        self.assertGreater(aheight,bheight)
        self.assertGreaterEqual(s.sections['A']['frame'].winfo_rooty(),a.viewport.canvas.winfo_rooty()-2)
        self.assertGreater(a.queue_deck.pages['B'].canvas.winfo_height(),35)
        self.assertTrue(a.queue_deck.pages['A'].queue_count.get().endswith('upcoming'))
        self.assertEqual({'A','B'},set(s.dock_buttons))
        self.assertFalse(a.shell.grips['right'].winfo_ismapped())
    def test_visual_row_end_reorder_is_immediate(self):
        from types import SimpleNamespace
        from instrument_model import voice
        a=self.a;p=a.queue_deck.pages['A']
        self.add_visual('A',5)
        a.sidebar.set_open('A',True);p.set_future(True);self.idle()
        before=[c.id for c in voice(a.project,'A').clips]
        target=before[1]
        hit=next(h for h in p.hits if len(h)>=6 and h[0]==target and h[3]=='move_down')
        result=p.press(SimpleNamespace(x=int((hit[4]+hit[5])/2),y=int(hit[1]+6)))
        self.idle()
        after=[c.id for c in voice(a.project,'A').clips]
        self.assertEqual('break',result)
        self.assertEqual(target,after[2])
        self.assertEqual(before[0],after[0])

    def test_empty_expanded_has_one_row_and_inline_take_action(self):
        a=self.a;p=a.queue_deck.pages['A']
        a.sidebar.set_open('A',True);p.set_future(True);self.idle()
        # UX28's compact counter uses a count instead of repeating the empty message.
        self.assertEqual('0 next',p.queue_count.get())
        self.assertGreaterEqual(p.canvas.winfo_height(),35)
        self.add_visual('A',4)
        p.refresh(True);self.idle()
        self.assertTrue(any(h[3]=='take' for h in p.hits if len(h)>=6))
        self.assertTrue(any(h[3]=='remove' for h in p.hits if len(h)>=6))
        # Click current occurrence's x: the next occurrence survives.
        from instrument_model import voice
        old=voice(a.project,'A').clips[0].id
        p.remove_current();self.idle()
        self.assertNotIn(old,[c.id for c in voice(a.project,'A').clips])

if __name__=='__main__':unittest.main()
