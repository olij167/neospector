"""UX18 behaviour contract: real overlay workbench, reaction-local controls, lighter source players."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX18Workbench(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True)
        self.app.geometry('1450x900+0+0');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()
    def test_fx_is_a_contextual_overlay_not_a_lower_workspace_panel(self):
        a=self.app
        before=a.shell.frames['panel.programme'].winfo_height()
        a.open_effects_context('Master');a.update()
        rack=a.shell.frames['panel.rack'];preview=a.shell.frames['panel.programme']
        self.assertTrue(rack.winfo_viewable())
        self.assertGreater(rack.winfo_rooty(),preview.winfo_rooty())
        self.assertGreater(rack.winfo_rootx(),preview.winfo_rootx())
        self.assertLess(rack.winfo_width(),preview.winfo_width())
        self.assertEqual(before,preview.winfo_height())
        self.assertTrue(a.deck.close_button.winfo_viewable())
        a.deck.close_button.invoke();a.update()
        self.assertFalse(a.shell.rack_open)
    def test_reaction_is_always_in_parameter_not_an_alternate_module_page(self):
        from effects_engine import make_effect
        a=self.app;a.project.master_rack.append(make_effect('blur'))
        a.open_effects_context('Master');a.deck.refresh(True);a.update()
        cell=a.deck.selected_cell();fx=a.project.master_rack[0]
        shell=cell.card_parts[fx.id][0]
        fader=shell.fader_rows[0]
        self.assertTrue(fader.scale.winfo_viewable())
        for name in ('reaction_source','reaction_band','reaction_amount'):
            self.assertTrue(hasattr(fader,name),name)
            self.assertTrue(getattr(fader,name).winfo_viewable())
        cell.quick_reaction(fx.id, fader.param);a.update()
        self.assertEqual('react',fader.param.mode)
        self.assertTrue(fader.scale.winfo_viewable())
        self.assertFalse(shell.quick_tune_host.winfo_viewable())
        before=fader.param.react_band
        fader.reaction_band.invoke();a.update()
        self.assertNotEqual(before,fader.param.react_band)
    def test_audio_radio_player_is_not_six_visual_transport_buttons(self):
        a=self.app;a.sidebar.set_open('Music',True);a.update()
        m=a.queue_deck.pages['Music']
        self.assertTrue(m.radio_transport.winfo_viewable())
        self.assertFalse(m.compact_toolbar.winfo_viewable())
        self.assertTrue(m.radio_play.winfo_viewable())
        self.assertFalse(m.current_canvas.winfo_viewable())  # No duplicate empty-media card
        # The browser is optional and must not replace the compact player.
        m.toggle_music_files();a.update()
        self.assertTrue(m.source_browser.winfo_viewable())
        self.assertTrue(m.radio_transport.winfo_viewable())
    def test_overlay_fits_content_and_one_column_modules_are_not_double_height(self):
        from effects_engine import make_effect
        from neospector_catalog import build_group
        a=self.app
        a.project.master_rack.extend([build_group('Acid Print'),make_effect('blur')])
        a.open_effects_context('Master');a.deck.refresh(True);a.update()
        self.assertLess(a.shell.frames['panel.rack'].winfo_height(),a.shell.frames['panel.programme'].winfo_height()*.72)
        a.geometry('1024x768+0+0');a.update()
        cell=a.deck.selected_cell();group=a.project.master_rack[0]
        shell=cell.card_parts[group.id][0]
        self.assertLessEqual(shell.winfo_height(),205)
        self.assertTrue(cell.card_controls[group.id]['delete'].winfo_viewable())

    def test_module_actions_are_visible_when_context_rack_is_open(self):
        from effects_engine import make_effect
        a=self.app
        fx=make_effect('liquid')
        a.project.master_rack.append(fx)
        a.open_effects_context('Master');a.deck.refresh(True);a.update()
        cell=a.deck.selected_cell()
        for action in ('delete','duplicate','lock','earlier','later','power'):
            self.assertTrue(cell.card_controls[fx.id][action].winfo_viewable(),action)
        cell.card_controls[fx.id]['delete'].invoke();a.update()
        self.assertNotIn(fx.id,[f.id for f in a.project.master_rack])

    def test_visual_transport_only_visible_when_queue_has_content(self):
        a=self.app;a.sidebar.set_open('B',True);a.update()
        b=a.queue_deck.pages['B']
        self.assertFalse(b.compact_toolbar.winfo_viewable())
        from sequencer_model import add_asset,Clip
        from instrument_model import voice
        asset=add_asset(a.project,path='',kind='colour',name='Fixture',metadata={'colour':'#3399cc'})
        voice(a.project,'B').clips.append(Clip('ux18-item',asset.id,start=0,duration=8))
        b.refresh(True);a.update()
        self.assertTrue(b.compact_toolbar.winfo_viewable())
