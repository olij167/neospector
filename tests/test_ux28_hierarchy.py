"""UX28: grouped live/queue controls and aligned preview actions."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX28Tk(unittest.TestCase):
    def setUp(self):
        self.sandbox=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.sandbox.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.a=NeospectorApp(test_mode=True)
        self.a.geometry('1600x920+0+0');self.pump()
    def tearDown(self):
        try:self.a.close(force=True)
        finally:self.env.stop();self.sandbox.cleanup()
    def pump(self):
        for _ in range(8):self.a.update()
    def test_top_row_has_three_paired_capture_and_queue_controls(self):
        a=self.a
        self.assertEqual(set(a.source_capture_buttons),{'A','B','Music'})
        for role in ('A','B','Music'):
            live=a.source_capture_buttons[role]
            queue=a.sidebar.sections[role]['button']
            self.assertTrue(live.winfo_viewable());self.assertTrue(queue.winfo_viewable())
            self.assertEqual(live.master,queue.master)
            self.assertLess(live.winfo_rooty(),queue.winfo_rooty())
            self.assertLess(abs(live.winfo_rootx()-queue.winfo_rootx()),3)
        self.assertEqual(a.source_capture_buttons['Music'].cget('text').strip().split()[0], 'MIC')
    def test_audio_shares_bottom_right_queue_stack(self):
        a=self.a
        a.sidebar.set_open('A',True);a.sidebar.set_open('B',True);a.set_audio_tray_open(True);self.pump()
        frames=[a.sidebar.sections[r]['frame'] for r in ('A','B','Music')]
        self.assertEqual(len({f.master for f in frames}),1)
        self.assertTrue(all(f.winfo_viewable() for f in frames))
        self.assertEqual(len({f.winfo_rootx() for f in frames}),1)
        self.assertEqual(sorted(f.winfo_rooty() for f in frames),[f.winfo_rooty() for f in frames])
        self.assertFalse(a.sidebar.dock_bar.winfo_ismapped())
        self.assertFalse(a.sidebar.music_dock_bar.winfo_ismapped())
        self.assertLessEqual(frames[-1].winfo_rooty()+frames[-1].winfo_height(), a.winfo_rooty()+a.winfo_height())
    def test_queue_camera_and_mic_controls_are_compact_and_linked(self):
        a=self.a
        for role in ('A','B','Music'):a.sidebar.set_open(role,True)
        self.pump()
        for role in ('A','B'):
            p=a.queue_deck.pages[role]
            self.assertTrue(p.quick_live_button.winfo_viewable())
            self.assertTrue(p.quick_live_button.winfo_width()<100)
            with patch.object(p,'toggle_camera') as toggle:
                p.quick_live_button.invoke();a.source_capture_buttons[role].invoke()
                self.assertEqual(toggle.call_count,2)
        with patch.object(a,'quick_microphone') as toggle:
            a.queue_deck.pages['Music'].quick_live_button.invoke()
            a.source_capture_buttons['Music'].invoke()
            self.assertEqual(toggle.call_count,2)
    def test_preview_actions_left_transition_and_react_right(self):
        a=self.a;m=a.visual_mix
        self.assertLess(m.preview_actions.winfo_rootx(),m.transition_group.winfo_rootx())
        self.assertLess(m.transition_group.winfo_rootx(),m.audio_group.winfo_rootx())
        self.assertLess(abs(m.preview_actions.winfo_rooty()-m.transition_group.winfo_rooty()),7)
        buttons=[a.record_button,a.output_viewer_button,m.focus_button,m.transition_display,m.react_button]
        self.assertLessEqual(max(b.winfo_height() for b in buttons)-min(b.winfo_height() for b in buttons),5)
        self.assertLessEqual(m.winfo_height(),100)
    def test_narrow_browser_keeps_preview_toolbar_controls_inside_view(self):
        a=self.a
        a.geometry('1024x768+0+0')
        a.sidebar.open_browser('Music','files')
        self.pump()
        m=a.visual_mix
        right=m.tools.winfo_rootx()+m.tools.winfo_width()
        self.assertLessEqual(m.audio_group.winfo_rootx()+m.audio_group.winfo_width(),right+3)
        self.assertLessEqual(m.preview_actions.winfo_rootx()+m.preview_actions.winfo_width(),right+3)
        self.assertLess(m.transition_group.winfo_rootx(),m.audio_group.winfo_rootx())
        self.assertGreaterEqual(m.transition_group.winfo_rooty(),m.preview_actions.winfo_rooty())

    def test_all_three_expanded_share_height_and_preserve_preview(self):
        a=self.a
        for role in ('A','B','Music'):
            a.sidebar.set_open(role,True)
            a.queue_deck.pages[role].set_future(True)
        a.sidebar.open_browser('A','files')
        self.pump()
        f=[a.sidebar.sections[r]['frame'] for r in ('A','B','Music')]
        self.assertTrue(all(x.winfo_viewable() for x in f))
        self.assertTrue(all(f[i].winfo_rooty()+f[i].winfo_height()<=f[i+1].winfo_rooty() for i in range(2)))
        self.assertGreaterEqual(f[0].winfo_rooty(),a.viewport.canvas.winfo_rooty())
        self.assertLessEqual(f[-1].winfo_rooty()+f[-1].winfo_height(), a.shell.stage.winfo_rooty()+a.shell.stage.winfo_height()+1)

    def test_capture_and_queue_styles_are_distinct(self):
        a=self.a
        live=a.source_capture_buttons['A'].cget('style')
        queue=a.sidebar.sections['A']['button'].cget('style')
        self.assertNotEqual(live,queue)
        from tkinter import ttk
        style=ttk.Style(a)
        self.assertNotEqual(style.lookup(live,'background'),style.lookup(queue,'background'))
    def test_queue_toggle_controls_correct_tray_without_moving_stage(self):
        a=self.a
        before=a.visual_mix.winfo_height()
        for role in ('A','B','Music'):
            b=a.sidebar.sections[role]['button']
            self.assertFalse(a.sidebar.sections[role]['open']);b.invoke();self.pump()
            self.assertTrue(a.sidebar.sections[role]['open'])
        self.assertEqual(before,a.visual_mix.winfo_height())
        a.sidebar.sections['Music']['button'].invoke();self.pump()
        self.assertFalse(a.sidebar.sections['Music']['open'])
if __name__=='__main__':unittest.main()
