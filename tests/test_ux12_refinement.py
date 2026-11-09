"""UX12: unlinked media folder and rack-owned module browser."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from neospector_console import NeospectorApp
from effects_engine import make_effect

class UX12Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start();self.app=NeospectorApp(test_mode=True);self.app.geometry('1500x950');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()
    def test_independent_media_and_module_drawers(self):
        a=self.app
        self.assertTrue(a.project_media_folder.winfo_viewable())
        a.show_module_library();a.update()
        self.assertTrue(a.module_library.winfo_viewable())
        self.assertTrue(a.project_media_folder.winfo_viewable())
        self.assertGreater(a.module_library.winfo_rootx(),a.deck.winfo_rootx())
        a.toggle_module_library();a.update()
        self.assertFalse(a.module_library.winfo_viewable())
        self.assertTrue(a.project_media_folder.winfo_viewable())
        a.toggle_right_lower();a.update()
        self.assertFalse(a.project_media_folder.winfo_viewable())
        a.show_module_library();a.update()
        self.assertTrue(a.module_library.winfo_viewable())
        self.assertFalse(a.project_media_folder.winfo_viewable())
    def test_compact_fader_without_dial_or_detached_reaction_panel(self):
        a=self.app
        a.open_channel_effects('Master')
        self.assertTrue(a.insert_module_from_library(make_effect('blur'),'Blur',entry_type='Custom'))
        a.update()
        cell=a.deck.selected_cell()
        self.assertTrue(cell.card_parts)
        shell,body,_=next(iter(cell.card_parts.values()))
        rows=[child for child in shell.principal_controls.winfo_children() if hasattr(child,'scale')]
        self.assertTrue(rows)
        self.assertFalse(any(hasattr(row,'dial') for row in rows))
        self.assertTrue(rows[0].scale.winfo_viewable())
        self.assertLess(shell.winfo_height(),240)
    def test_music_distinct_and_source_icons_present(self):
        a=self.app
        music=a.queue_deck.pages['Music'];visual=a.queue_deck.pages['A']
        self.assertTrue(hasattr(music,'sound_badge'))
        self.assertFalse(hasattr(visual,'sound_badge'))
        self.assertTrue(music.mic_button.winfo_viewable())
        self.assertTrue(visual.camera_button.winfo_viewable())
        self.assertTrue(hasattr(visual,'visual_source_bar'))
    def test_inline_reaction_compact_and_editable(self):
        a=self.app;a.open_channel_effects('Master')
        fx=make_effect('blur');a.insert_module_from_library(fx,'Blur',entry_type='Custom');a.update()
        cell=a.deck.selected_cell()
        cell.toggle_tune(fx.id);a.update()
        shell=cell.card_parts[fx.id][0]
        self.assertTrue(shell.quick_tune_host.winfo_viewable())
        strip=cell.quick_tunes[fx.id]
        self.assertTrue(strip.winfo_viewable())
        self.assertIsNone(cell.tray)
        strip.set_band('bass');a.update()
        self.assertEqual('bass',fx.params['amount'].react_band)
        strip.set_source('song');a.update()
        self.assertEqual('song',fx.params['amount'].source)
        self.assertTrue(a.project_media_folder.winfo_viewable())
        cell.toggle_tune(fx.id);a.update()
        self.assertFalse(shell.quick_tune_host.winfo_viewable())

    def test_module_columns_reflow_on_window_resize(self):
        a=self.app;a.open_channel_effects('Master')
        for kind in ('liquid','blur','brightness','echo'):
            a.insert_module_from_library(make_effect(kind),kind,entry_type='Custom')
        for _ in range(3):a.update()
        cell=a.deck.selected_cell()
        self.assertGreater(len({part[0].grid_info()['column'] for part in cell.card_parts.values()}),1)
        a.geometry('1024x768+0+0')
        for _ in range(7):a.update()
        self.assertEqual({0},{part[0].grid_info()['column'] for part in cell.card_parts.values()})

    def test_module_insertion_with_media_hidden(self):
        a=self.app;a.toggle_right_lower()
        a.open_channel_effects('A');a.show_module_library();a.update()
        self.assertTrue(a.insert_module_from_library(make_effect('blur'),'Blur',entry_type='Custom'))
        self.assertFalse(a.project_media_folder.winfo_viewable())
        self.assertTrue(a.module_library.winfo_viewable())
