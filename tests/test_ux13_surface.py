"""UX13: module controls and queue/source controls are direct, not menus."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from neospector_console import NeospectorApp
from effects_engine import make_effect

class UX13SurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start();self.app=NeospectorApp(test_mode=True);self.app.geometry('1500x950');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()
    def insert(self,kind='blur'):
        a=self.app;a.open_channel_effects('Master');f=make_effect(kind)
        self.assertTrue(a.insert_module_from_library(f,kind,entry_type='Custom'))
        a.update();return a.deck.selected_cell(),f
    def test_remove_and_duplicate_are_always_visible_on_each_pedal(self):
        cell,fx=self.insert()
        controls=cell.card_controls[fx.id]
        self.assertTrue(controls['delete'].winfo_viewable())
        self.assertTrue(controls['duplicate'].winfo_viewable())
        self.assertFalse(any(w.winfo_viewable() and w.cget('text')=='⋯' for w in cell.card_parts[fx.id][0].winfo_children() if 'text' in w.keys()))
        controls['duplicate'].invoke();self.app.update()
        self.assertEqual(2,len(cell.target()[0]))
        controls['delete'].invoke();self.app.update()
        self.assertEqual(1,len(cell.target()[0]))
    def test_module_has_no_hidden_more_or_precise_dropdown(self):
        cell,fx=self.insert()
        shell=cell.card_parts[fx.id][0]
        self.assertFalse(hasattr(shell,'module_menu_button'))
        self.assertFalse(any(w.winfo_viewable() and w.cget('text') in ('More','⋯','CONTROLS','Fine ↗') for w in self.descendants(shell) if 'text' in w.keys()))
        self.assertTrue(all(row.scale.winfo_viewable() for row in cell.rows if row.winfo_exists() and row.owner is cell.target()[1]))
    def test_reaction_shows_in_module_on_activation_and_can_disable(self):
        cell,fx=self.insert();shell=cell.card_parts[fx.id][0]
        row=next(w for w in cell.rows if w.winfo_exists() and w.param is fx.params['amount'])
        row.mode_button.invoke();self.app.update()
        self.assertEqual('react',row.param.mode)
        self.assertTrue(shell.quick_tune_host.winfo_viewable())
        self.assertFalse(any(w.winfo_viewable() and w.cget('text')=='Fine ↗' for w in self.descendants(shell) if 'text' in w.keys()))
        row.mode_button.invoke();self.app.update()
        self.assertEqual('static',row.param.mode)
    def test_reaction_strip_tracks_the_parameter_edited_on_multi_fader_module(self):
        cell,fx=self.insert('echo')
        self.assertIn('delay',fx.params)
        row=next(w for w in cell.rows if w.winfo_exists() and w.param is fx.params['delay'])
        row.mode_button.invoke();self.app.update()
        self.assertEqual('react',fx.params['delay'].mode)
        self.assertEqual('delay',cell.quick_tunes[fx.id].key)

    def test_player_source_drop_arrows_are_not_mounted(self):
        for role in ('A','B','Music'):
            player=self.app.queue_deck.pages[role]
            if role=='Music':self.assertFalse(player.mic_choices.winfo_viewable())
            else:self.assertFalse(player.source_disclosure.winfo_viewable())
    def test_rack_actions_are_visible_without_overflow(self):
        deck=self.app.deck
        self.assertFalse(deck.more_button.winfo_viewable())
        self.assertTrue(deck.group_button.winfo_viewable())
        self.assertTrue(deck.save_rack_button.winfo_viewable())
    def test_module_library_has_no_filter_or_sort_dropdowns(self):
        self.app.show_module_library();self.app.update()
        library=self.app.module_library
        from tkinter import ttk
        self.assertFalse(isinstance(library.sort_button,ttk.Menubutton))
        self.assertFalse(library.filter_button.winfo_viewable())
        self.assertTrue(library.sort_button.winfo_viewable(), 'Sort action must not disappear with the old menu')
        old=library.sort.get();library.sort_button.invoke();self.app.update()
        self.assertNotEqual(old,library.sort.get())
    def test_application_menu_only_offers_file_functions(self):
        menu=self.app.application_menu
        self.assertEqual('File',menu.entrycget(0,'label'))
        self.assertEqual(1,menu.index('end')+1)
    def test_narrow_module_browser_does_not_crush_active_pedal(self):
        a=self.app;a.geometry('1024x768+0+0')
        for _ in range(6):a.update()
        a.show_module_library();a.update()
        self.assertTrue(a.library_open)
        self.assertTrue(a.module_library_host.winfo_viewable())
        self.assertFalse(a.rack_primary.winfo_viewable())
        a.toggle_module_library(False);a.update()
        self.assertTrue(a.rack_primary.winfo_viewable())

    def test_panel_right_click_does_not_open_menu(self):
        with patch('tkinter.Menu', side_effect=AssertionError('No panel dropdown menus')):
            self.assertEqual('break', self.app.shell.panel_menu('panel.rack'))

    def test_obsolete_rack_and_audio_menu_handlers_cannot_open_dropdown(self):
        with patch('tkinter.Menu', side_effect=AssertionError('No contextual dropdown')):
            self.app.deck.integrated_menu()
            self.app.queue_deck.pages['Music'].music_source_menu()

    def descendants(self,node):
        for c in node.winfo_children():
            yield c
            yield from self.descendants(c)
