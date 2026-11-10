"""UX43 real GUI: protected toolbar regions at a range of desktop widths."""
from __future__ import annotations
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
@unittest.skipUnless(os.environ.get('DISPLAY') or sys.platform in ('darwin','win32'),'X display required')
class ProtectedToolbar(unittest.TestCase):
    def test_effects_and_media_not_obscured_by_mixer(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':d,'NEOSPECTOR_NO_NATIVE_DROP':'1'}):
            from neospector_console import NeospectorApp
            app=NeospectorApp(test_mode=True)
            try:
                for width in (860,1024,1280,1380,1460,1600,1920):
                    with self.subTest(width=width):
                        app.geometry(f'{width}x900+0+0')
                        for _ in range(5):app.update()
                        left=[app.application_button,app.master_fx_button,app.media_sources_button]
                        middle=[app.record_button,app.output_viewer_button,app.visual_mix.focus_button]
                        right=[app.preview_camera,app.preview_camera_b,app.preview_microphone]
                        for widget in [*left,*middle,*right]:
                            self.assertTrue(widget.winfo_viewable(),str(widget))
                            self.assertGreaterEqual(widget.winfo_rootx(),app.winfo_rootx())
                            self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),app.winfo_rootx()+app.winfo_width()+3)
                        # All groups have distinct bounds even at 860px.
                        for a in left:
                            for b in middle:
                                vertical=abs(a.winfo_rooty()-b.winfo_rooty())
                                if vertical<max(a.winfo_height(),b.winfo_height()):
                                    self.assertLessEqual(a.winfo_rootx()+a.winfo_width(),b.winfo_rootx()+2)
                        if 1280<=width<=1460:self.assertFalse(app.visual_mix.transition_label.winfo_manager())
                        self.assertLessEqual(app.media_sources_button.winfo_rootx()+app.media_sources_button.winfo_width(),app.top_source_host.winfo_rootx())
            finally:app.close(force=True)

    def test_protected_regions_with_larger_font_metric_button_requests(self):
        """Placed controls still occupy a real width when Tk's font grows.

        A PriorityToolbar's *container* may request 1px because it places
        children. Test with larger child widths to emulate CI/OS differences.
        """
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':d,'NEOSPECTOR_NO_NATIVE_DROP':'1'}):
            from neospector_console import NeospectorApp
            app=NeospectorApp(test_mode=True)
            try:
                app.media_sources_button.configure(width=24)
                app.master_fx_button.configure(width=12)
                for width in (860,1024,1280,1380,1460,1600,1920):
                    with self.subTest(width=width):
                        app.geometry(f'{width}x900+0+0')
                        for _ in range(7):app.update()
                        left=(app.media_sources_button.winfo_rootx()+app.media_sources_button.winfo_width())
                        # Pinned controls must fit their *own* grid column;
                        # the old 330px constant fails this on larger fonts.
                        self.assertLessEqual(left,app.global_toolbar.winfo_rootx()+app.global_toolbar.winfo_width()+1)
                        source_left=app.top_source_host.winfo_rootx()
                        if abs(app.media_sources_button.winfo_rooty()-app.top_source_host.winfo_rooty())<app.media_sources_button.winfo_height():
                            self.assertLessEqual(left,source_left+1)
                        self.assertLessEqual(left,app.winfo_rootx()+app.winfo_width()+2)
                        self.assertLessEqual(app.top_source_host.winfo_rootx()+app.top_source_host.winfo_width(),app.winfo_rootx()+app.winfo_width()+3)
                        if 1280<=width<=1460:
                            self.assertFalse(app.visual_mix.transition_label.winfo_manager())
            finally:app.close(force=True)
