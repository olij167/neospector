"""UX11 mirrored workspace acceptance tests, written before shell changes."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from neospector_console import NeospectorApp

class UX11WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start();self.app=NeospectorApp(test_mode=True)
        self.app.geometry('1580x950');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()

    def test_channel_positions_and_mix_above_preview(self):
        a=self.app
        left=a.queue_deck.pages['A'];right=a.queue_deck.pages['B'];music=a.queue_deck.pages['Music']
        self.assertTrue(left.winfo_viewable() and right.winfo_viewable() and music.winfo_viewable())
        self.assertLess(left.winfo_rootx(),a.viewport.winfo_rootx())
        self.assertGreater(right.winfo_rootx(),a.viewport.winfo_rootx())
        self.assertGreater(music.winfo_rooty(),left.winfo_rooty())
        self.assertEqual(a.visual_mix.master,a.shell.bodies['panel.programme'])
        self.assertLess(a.visual_mix.winfo_rooty(),a.viewport.winfo_rooty())

    def test_collapse_upcoming_only(self):
        a=self.app
        page=a.queue_deck.pages['A'];start=a.project.voice_mix.value
        self.assertTrue(page.canvas.winfo_viewable())
        page.toggle_future();a.update()
        self.assertFalse(page.canvas.winfo_viewable())
        self.assertTrue(page.current_canvas.winfo_viewable())
        self.assertTrue(page.transport_play.winfo_viewable())
        self.assertEqual(start,a.project.voice_mix.value)
        page.toggle_future();a.update();self.assertTrue(page.canvas.winfo_viewable())

    def test_right_side_tabs_and_safe_collapse(self):
        a=self.app
        a.show_module_library();a.update()
        self.assertTrue(a.module_library.winfo_viewable())
        a.select_right_tray('Media');a.update()
        self.assertTrue(a.project_media_folder.winfo_viewable())
        self.assertFalse(a.module_library.winfo_viewable())
        a.shell.collapse('Library');a.update()
        self.assertFalse(a.queue_deck.pages['B'].winfo_viewable())
        self.assertTrue(a.shell.right_restore.winfo_viewable())
        a.shell.show('Library');a.update()
        self.assertTrue(a.queue_deck.pages['B'].winfo_viewable())

    def test_output_does_not_mark_a_or_b_as_editing(self):
        a=self.app
        a.open_channel_effects('Master');a.update()
        self.assertEqual('Master',a.queue_deck.active_role)
        self.assertEqual('Edit FX',a.queue_deck.pages['A'].edit_button.cget('text'))
        self.assertEqual('Edit FX',a.queue_deck.pages['B'].edit_button.cget('text'))
        a.queue_deck.show_role('B');a.update()
        self.assertEqual('EDITING',a.queue_deck.pages['B'].edit_button.cget('text'))
        a.queue_deck.show_role('Music');a.update()
        self.assertEqual('B',a.queue_deck.active_role)

    def test_channels_and_output_are_distinct_edit_targets(self):
        a=self.app
        a.queue_deck.show_role('B');a.update()
        self.assertEqual('Layer',a.deck.scope.get())
        self.assertEqual('B',a.deck.selected_cell().adapter.owner.extra.get('voice'))
        a.open_channel_effects('Master');a.update()
        self.assertEqual('Master',a.deck.scope.get())
        self.assertTrue(a.deck.owner_buttons['Master'].winfo_viewable())
        a.queue_deck.show_role('A');a.update()
        self.assertEqual('A',a.deck.selected_cell().adapter.owner.extra.get('voice'))

    def test_transport_is_single_row_and_output_actions_are_progressively_disclosed(self):
        a=self.app
        for role in ('A','B','Music'):
            player=a.queue_deck.pages[role]
            buttons=[w for w in player.compact_toolbar.winfo_children() if w.winfo_class()=='TButton']
            self.assertEqual(6,len(buttons))
            self.assertEqual({0},{int(w.grid_info()['row']) for w in buttons})
        self.assertTrue(a.deck.owner_buttons['Master'].winfo_viewable())
        self.assertFalse(a.deck.group_button.winfo_viewable())
        self.assertFalse(a.deck.save_rack_button.winfo_viewable())

    def test_small_rack_primary_actions_fit_without_overflow(self):
        a=self.app;a.geometry('1024x768');a.update()
        self.assertTrue(a.deck.add_button.winfo_viewable())
        self.assertTrue(a.deck.randomise_button.winfo_viewable())
        self.assertLessEqual(a.deck.add_button.winfo_rootx()+a.deck.add_button.winfo_width(),
                             a.shell.frames['panel.rack'].winfo_rootx()+a.shell.frames['panel.rack'].winfo_width())

    def test_left_collapsing_future_gives_music_more_room(self):
        a=self.app;a.geometry('1024x768');a.update()
        music=a.queue_deck.pages['Music'];before=music.winfo_height()
        a.queue_deck.pages['A'].toggle_future();a.update()
        self.assertGreater(music.winfo_height(),before)

    def test_insertions_follow_selected_channel_and_output(self):
        from effects_engine import make_effect
        from instrument_model import voice
        a=self.app
        for role in ('A','B','Master'):
            a.open_channel_effects(role)
            self.assertTrue(a.insert_module_from_library(make_effect('blur'),'Blur',entry_type='Custom'))
        self.assertEqual(1,len(voice(a.project,'A').rack))
        self.assertEqual(1,len(voice(a.project,'B').rack))
        self.assertEqual(1,len(a.project.master_rack))

    def test_module_builder_does_not_replace_b(self):
        from effects_engine import make_effect
        a=self.app
        a.open_channel_effects('Master')
        for kind in ('blur','brightness'):
            self.assertTrue(a.insert_module_from_library(make_effect(kind),kind,entry_type='Custom'))
        a.select_right_tray('Media')
        cell=a.deck.selected_cell();cell.selected_fx={f.id for f in a.project.master_rack}
        self.assertTrue(a.deck.group_selected());a.update()
        self.assertTrue(a.queue_deck.pages['B'].winfo_viewable())
        self.assertTrue(a.module_builder.winfo_viewable())
        self.assertFalse(a.project_media_folder.winfo_viewable())
        a.close_module_builder();a.update()
        self.assertTrue(a.module_library.winfo_viewable())

    def test_left_sidebar_can_restore(self):
        a=self.app
        a.shell.collapse('Queues');a.update()
        self.assertFalse(a.queue_deck.pages['A'].winfo_viewable())
        self.assertTrue(a.shell.left_restore.winfo_viewable())
        a.shell.show('Queues');a.update()
        self.assertTrue(a.queue_deck.pages['A'].winfo_viewable())

if __name__=='__main__':unittest.main()
