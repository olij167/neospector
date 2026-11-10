"""Static integration gates for the slim code-review snapshot.

The full 413-file release runtime is on the owner's checkout; these tests
cover the actual UX41 instrument source without fabricating unavailable files.
"""
from pathlib import Path
import ast, unittest
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'app_source'
class UX42IntegrationContractTests(unittest.TestCase):
    def test_startup_clamps_geometry_before_tk_window_is_shown(self):
        code=(APP/'omne_sequencer.py').read_text()
        ast.parse(code)
        self.assertIn('startup_geometry(',code)
        self.assertIn('minimum_window_size(',code)
        self.assertNotIn("self.geometry(pref.get('geometry','1440x940'))",code)
        self.assertNotIn('self.minsize(1080,740)',code)
    def test_workspace_does_not_reassert_obsolete_minimum(self):
        code=(APP/'omne_workspace.py').read_text()
        ast.parse(code)
        self.assertNotIn('self.minsize(1024,768)',code)
    def test_stage_uses_responsive_policy(self):
        code=(APP/'instrument_shell.py').read_text()
        ast.parse(code)
        self.assertIn('project_stage(',code)
        self.assertNotIn('aw=min(380,max(304,int(w*.305)))',code)
    def test_retains_queue_and_playback_engines(self):
        code=(APP/'instrument_shell.py').read_text()
        self.assertIn('stack.fit_heights(',code)
        self.assertIn("stack.request_fit()",code)
        self.assertIn("self.frames['panel.library'].lift()",code)
        self.assertIn("self.sync()",code)
if __name__=='__main__':unittest.main()
