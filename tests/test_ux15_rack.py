"""UX15 observable rack contract: inline group controls, direct library destination."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from effects_engine import make_effect
from neospector_catalog import build_group
from module_engine import children,group_effects
from neospector_console import NeospectorApp
from instrument_model import voice

class UX15GroupModelTests(unittest.TestCase):
    def test_factory_group_front_exposes_each_immediate_child_parameter(self):
        group=build_group('CCD Afterglow')
        expected=sum(len(fx.params) for fx in children(group))
        self.assertEqual(expected,len(group.params))
        self.assertEqual(expected,len(group.extra['mappings']))

class UX15RackTests(unittest.TestCase):
    def setUp(self):
        self.profile=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.profile.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start();self.app=NeospectorApp(test_mode=True)
        self.app.geometry('1520x970');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.profile.cleanup()

    def test_no_plus_fx_button_and_library_follows_live_rack_choice(self):
        app=self.app
        app.show_module_library();app.open_channel_effects('A');app.update()
        self.assertFalse(app.deck.add_button.winfo_viewable())
        self.assertTrue(app.insert_module_from_library(make_effect('blur'),'Blur',entry_type='Custom'))
        app.open_channel_effects('B');app.update()
        self.assertTrue(app.insert_module_from_library(make_effect('grain'),'Grain',entry_type='Custom'))
        self.assertEqual(['blur'],[e.kind for e in voice(app.project,'A').rack])
        self.assertEqual(['grain'],[e.kind for e in voice(app.project,'B').rack])
        self.assertEqual([],app.project.master_rack)
        self.assertIn('Visual B',app.module_library.destination_caption.get())

    def test_groups_display_all_controls_in_wide_pedal_without_group_page(self):
        app=self.app;app.open_channel_effects('Master')
        fx=build_group('CCD Afterglow')
        self.assertTrue(app.insert_module_from_library(fx,'CCD Afterglow',entry_type='Group'))
        app.update();cell=app.deck.selected_cell();shell=cell.card_parts[fx.id][0]
        self.assertEqual(2,int(shell.grid_info()['columnspan']))
        self.assertEqual(len(fx.params),len(shell.fader_rows))
        self.assertEqual(1,shell.face_pages)
        self.assertTrue(all(row.scale.winfo_viewable() for row in shell.fader_rows))
        footer=shell.footer
        self.assertGreaterEqual(footer.winfo_height(),24,
                                'module footer buttons must not be clipped by the fixed-height chassis')
        self.assertFalse(cell.card_controls[fx.id]['react'].winfo_viewable())
        self.assertFalse(app.deck.group_host.winfo_viewable())
        self.assertFalse(app.deck.back_button.winfo_viewable())

    def test_new_group_keeps_parameters_on_face(self):
        app=self.app;app.open_channel_effects('Master')
        for kind in ('blur','echo','liquid'):
            self.assertTrue(app.insert_module_from_library(make_effect(kind),kind,entry_type='Custom'))
        cell=app.deck.selected_cell();cell.selected_fx={f.id for f in app.project.master_rack}
        app.deck.group_selected();app.update()
        self.assertEqual(1,len(app.project.master_rack))
        group=app.project.master_rack[0]
        self.assertEqual('module',group.kind)
        self.assertEqual(sum(len(c.params) for c in children(group)),len(group.params))
        self.assertFalse(app.deck.group_host.winfo_viewable())

class UX15GroupResetTests(unittest.TestCase):
    def test_reset_preserves_the_control_face_and_neutralises_values(self):
        from module_engine import reset_effect,compile_rack
        group=build_group('CCD Afterglow')
        original=list(group.params);before=len(group.extra['mappings'])
        reset_effect(group)
        self.assertEqual(original,list(group.params))
        self.assertEqual(before,len(group.extra['mappings']))
        self.assertEqual(3,len(compile_rack([group])))
