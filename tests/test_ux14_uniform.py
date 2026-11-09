"""UX14: bounded pedal faces and deterministic responsive rack placement."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from neospector_console import NeospectorApp
from effects_engine import make_effect
from module_engine import group_effects

class FaceLayoutTests(unittest.TestCase):
    def test_wide_group_uses_two_columns_without_changing_height(self):
        from pedal_face_layout import place_faces
        layout=place_faces(810,[("a",1),("b",5),("c",2)])
        self.assertEqual(3,layout.columns)
        self.assertEqual((0,1,2),layout.positions['b'])
        self.assertEqual((1,0,1),layout.positions['c'])
        self.assertEqual(layout.height,layout.height)
    def test_narrow_group_has_banked_controls_instead_of_growth(self):
        from pedal_face_layout import face_pages,place_faces
        layout=place_faces(315,[("g",8)])
        self.assertEqual(1,layout.columns)
        self.assertEqual((0,0,1),layout.positions['g'])
        self.assertEqual(3,face_pages(8,False))
        self.assertEqual(2,face_pages(8,True))

class UniformPedalUITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start();self.app=NeospectorApp(test_mode=True);self.app.geometry('1500x950');self.app.update()
        self.app.open_channel_effects('Master')
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()
    def add(self,kind):
        from effects_engine import make_effect
        fx=make_effect(kind)
        self.assertTrue(self.app.insert_module_from_library(fx,kind,entry_type='Custom'))
        self.app.update();return self.app.deck.selected_cell(),fx
    def test_simple_and_three_parameter_pedals_have_identical_height(self):
        cell,blur=self.add('blur');_,echo=self.add('echo');self.app.update()
        b=cell.card_parts[blur.id][0];e=cell.card_parts[echo.id][0]
        self.assertEqual(b.winfo_height(),e.winfo_height())
        self.assertLessEqual(b.winfo_height(),225)
        self.assertTrue(all(row.scale.winfo_viewable() for row in cell.rows if row.param in echo.params.values()))
    def test_one_parameter_fader_uses_available_middle_of_face(self):
        cell,fx=self.add('blur')
        shell=cell.card_parts[fx.id][0]
        fader=shell.fader_rows[0]
        middle=shell.middle
        self.assertGreater(middle.winfo_height(),90)
        midpoint=fader.scale.winfo_rooty()+fader.scale.winfo_height()/2
        self.assertGreater(midpoint,middle.winfo_rooty()+middle.winfo_height()*.30)
        self.assertLess(midpoint,middle.winfo_rooty()+middle.winfo_height()*.75)

    def test_reaction_replaces_controls_and_keeps_the_pedal_height(self):
        cell,fx=self.add('echo');shell=cell.card_parts[fx.id][0]
        before=shell.winfo_height()
        row=next(row for row in cell.rows if row.param is fx.params['delay'])
        row.mode_button.invoke();self.app.update()
        self.assertTrue(shell.quick_tune_host.winfo_viewable())
        self.assertFalse(shell.middle.winfo_viewable())
        self.assertEqual(before,shell.winfo_height())
        self.assertTrue(cell.card_controls[fx.id]['delete'].winfo_viewable(), 'remove remains visible while reacting')
        self.assertTrue(cell.quick_tunes[fx.id].back.winfo_viewable())
        self.assertLessEqual(cell.quick_tunes[fx.id].winfo_height(),135)
        cell.quick_tunes[fx.id].back.invoke();self.app.update()
        self.assertTrue(shell.middle.winfo_viewable())
        self.assertEqual(before,shell.winfo_height())
    def test_complex_group_occupies_two_columns_same_height_as_effects(self):
        cell,_=self.add('blur');_,_=self.add('echo');_,_=self.add('liquid')
        rack,_=cell.target()
        group=group_effects(rack,[fx.id for fx in rack],'Complex group')
        self.app.deck.refresh(True);self.app.update()
        cell=self.app.deck.selected_cell()
        shell=cell.card_parts[group.id][0]
        self.assertEqual(2,int(shell.grid_info()['columnspan']))
        self.assertLessEqual(shell.winfo_height(),225)
        self.assertTrue(cell.card_controls[group.id]['delete'].winfo_viewable())

    def test_module_controls_remain_accessible_and_no_inner_scroller(self):
        cell,fx=self.add('liquid');shell=cell.card_parts[fx.id][0]
        for key in ('delete','duplicate','lock','earlier','later','power'):
            self.assertTrue(cell.card_controls[fx.id][key].winfo_viewable(),key)
        self.assertFalse(any('Scrollbar' in str(child.winfo_class()) for child in shell.winfo_children()))
        cell.card_controls[fx.id]['delete'].invoke();self.app.update()
        self.assertFalse(any(f.id==fx.id for f in cell.target()[0]))
