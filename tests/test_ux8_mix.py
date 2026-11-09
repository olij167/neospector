import os,tempfile,unittest
from unittest.mock import patch
from neospector_console import NeospectorApp
from instrument_model import voice

class MixTests(unittest.TestCase):
 def test_mix_is_one_gesture_and_preserves_edit_owner(self):
  with tempfile.TemporaryDirectory() as profile,patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':profile}):
   app=NeospectorApp(test_mode=True)
   try:
    app.open_channel_effects('Master');app.update();target=app.deck.selected_owner_key
    self.assertTrue(hasattr(app,'visual_mix'))
    count=len(app.history.undo_stack)
    app.visual_mix.begin();app.visual_mix.write(.2);app.visual_mix.write(.7);app.visual_mix.finish();app.update()
    self.assertAlmostEqual(.7,app.project.voice_mix.value)
    self.assertAlmostEqual(1.,voice(app.project,'A').opacity.value)
    self.assertAlmostEqual(1.,voice(app.project,'B').opacity.value)
    self.assertEqual(target,app.deck.selected_owner_key)
    self.assertEqual(count+1,len(app.history.undo_stack))
    app.undo();app.update();self.assertEqual(count,len(app.history.undo_stack))
   finally:app.close(force=True)
