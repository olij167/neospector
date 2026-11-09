"""UX33 acceptance: authored A/B transition primitives and library taxonomy."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from PIL import Image,ImageChops

class AuthoredTransition(unittest.TestCase):
    def setUp(self):
        from sequencer_model import Project
        self.p=Project()
        self.a=Image.new('RGBA',(96,60),(210,30,65,255))
        self.b=Image.new('RGBA',(96,60),(30,185,220,255))
    def render(self,mix):
        from ux16_transitions import composited_mix
        return composited_mix(self.p,self.a,self.b,mix)
    def test_new_primitives_are_real_module_types(self):
        from effects_engine import EFFECTS
        for name in ('transition_timing','transition_reveal','transition_iris','transition_pixels','transition_glitch','transition_slide'):
            self.assertIn(name,EFFECTS)
            self.assertEqual(EFFECTS[name].group,'Transition')
    def test_rack_determines_animation_independent_of_legacy_presets(self):
        from effects_engine import make_effect
        self.p.extra['ux16_transition']={'kind':'glitch_wipe'}
        self.p.transition_rack=[make_effect('transition_reveal',{'softness':.01,'angle':0})]
        first=self.render(.5)
        self.p.extra['ux16_transition']={'kind':'pixel_dissolve'}
        self.assertIsNone(ImageChops.difference(first,self.render(.5)).getbbox())
        self.assertIs(self.render(0),self.a)
        self.assertIs(self.render(1),self.b)
    def test_authored_geometry_fields_are_distinct(self):
        from effects_engine import make_effect
        samples={}
        for kind in ('transition_reveal','transition_iris','transition_pixels','transition_glitch','transition_slide'):
            self.p.transition_rack=[make_effect(kind)]
            samples[kind]=self.render(.35).tobytes()
        self.assertGreaterEqual(len(set(samples.values())),4)
    def test_timing_module_alters_progress_not_endpoints(self):
        from effects_engine import make_effect
        self.p.transition_rack=[make_effect('transition_reveal',{'angle':35}),make_effect('transition_timing',{'start':.25,'end':.9,'curve':.5})]
        # Timing affects earlier modules regardless of its face order.
        delayed=self.render(.3)
        self.p.transition_rack=[self.p.transition_rack[0]]
        original=self.render(.3)
        self.assertNotEqual(delayed.tobytes(),original.tobytes())
        self.assertIs(self.render(0),self.a)
        self.assertIs(self.render(1),self.b)
    def test_grouped_factory_transitions_are_editable_and_roundtrip(self):
        from neospector_catalog import build_group
        from ux16_transitions import validate_transition_rack
        from sequencer_model import project_from_dict,project_to_dict
        from module_engine import children
        for name in ('Directional Wipe','Iris Bloom','Pixel Scatter','Glitch Tear','Moving Slide'):
            group=build_group(name)
            self.assertEqual(group.kind,'module')
            self.assertTrue(validate_transition_rack([group]))
            self.assertGreater(len(children(group)),1)
        self.p.transition_rack=[build_group('Pixel Scatter')]
        restored=project_from_dict(project_to_dict(self.p))
        self.assertEqual(restored.transition_rack[0].extra['name'],'Pixel Scatter')
        self.assertTrue(self.render(.5))
    def test_random_transition_builds_a_real_animation_stage(self):
        from ux16_transitions import random_transition_rack,ANIMATION_MODULES
        from module_engine import compile_rack
        for seed in range(10):
            rack=random_transition_rack([],seed,3,.6)
            self.assertTrue(any(fx.kind in ANIMATION_MODULES for fx in compile_rack(rack)))

    def test_unsupported_transition_modules_stay_outside_visual_racks(self):
        from effects_engine import make_effect
        from ux16_transitions import validate_transition_rack
        with self.assertRaisesRegex(ValueError,'history'):
            validate_transition_rack([make_effect('echo')])
    def test_legacy_transition_files_remain_visible_when_no_rack_exists(self):
        from ux16_transitions import composited_mix
        self.p.extra['ux16_transition']={'kind':'wipe_left'}
        legacy=composited_mix(self.p,self.a,self.b,.5)
        self.assertNotEqual(legacy.tobytes(),Image.blend(self.a,self.b,.5).tobytes())

class DeclarativeRecipe(unittest.TestCase):
    def test_imports_safe_registered_module_graph(self):
        from module_recipe_io import read_recipe
        from module_engine import children
        recipe={'format':'neospector/module-recipe','version':1,'name':'My Pixel Gate','family':'Transition',
                'tags':['mask','stutter'],'operations':[{'kind':'transition_timing','params':{'start':.1,'end':.9}},
                    {'kind':'transition_pixels','params':{'cell':18,'softness':.1}}]}
        import json
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pixel.json';path.write_text(json.dumps(recipe))
            fx=read_recipe(path)
            self.assertEqual(len(children(fx)),2)
            self.assertEqual(fx.extra['tags'],['mask','stutter'])
    def test_rejects_arbitrary_execution_and_invalid_values(self):
        from module_recipe_io import parse_recipe
        good={'format':'neospector/module-recipe','version':1,'name':'Bad','family':'Transition','operations':[{'kind':'transition_glitch','params':{'bands':9999}}]}
        with self.assertRaises(ValueError):parse_recipe(good)
        good['operations'][0]['kind']='python';good['operations'][0]['params']={}
        with self.assertRaises(ValueError):parse_recipe(good)
        good['operations'][0]['kind']='transition_reveal';good['operations'][0]['params']={'amount':.8,'code':'__import__("os")'}
        with self.assertRaises(ValueError):parse_recipe(good)

class LibraryTk(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.patch=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.temp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'});self.patch.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True);self.app.geometry('1400x900+0+0');self.pump()
    def pump(self):
        for i in range(4):self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.patch.stop();self.temp.cleanup()
    def test_catalogue_transition_primitives_and_groups_are_filterable(self):
        a=self.app;a.open_effects_context('Transition');a.toggle_module_library(True);self.pump()
        lib=a.module_library;lib.refresh(force=True)
        self.assertIn('group:Glitch Tear',lib._rows)
        self.assertIn('base:transition_iris',lib._rows)
        self.assertTrue(hasattr(lib,'family_filter_row'))
        self.assertIn('Transition',lib.family_buttons)
        lib.family.set('Transition');lib.refresh();self.pump()
        self.assertTrue(lib._visible)
        self.assertTrue(all(lib._rows[k]['family']=='Transition' for k in lib._visible))
        a.open_effects_context('Master');lib.refresh(force=True)
        self.assertNotIn('base:transition_glitch',lib._rows)
    def test_imported_recipe_is_saved_as_editable_group(self):
        import json
        a=self.app;a.open_effects_context('Transition');a.toggle_module_library(True);self.pump()
        recipe={'format':'neospector/module-recipe','version':1,
                'name':'Custom Field','family':'Transition','tags':['personal','reveal'],
                'operations':[{'kind':'transition_timing','params':{'curve':.6}},
                              {'kind':'transition_reveal','params':{'angle':185,'softness':.03}}]}
        path=Path(self.temp.name)/'custom.json';path.write_text(json.dumps(recipe))
        self.assertTrue(a.module_library.import_recipe(path));self.pump()
        a.module_library.refresh(force=True)
        rows=[r for r in a.module_library._rows.values() if r['name']=='Custom Field']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['family'],'Transition')
        self.assertEqual(rows[0]['tags'],['personal','reveal'])
        self.assertTrue(a.module_library.add_row(rows[0]));self.pump()
        self.assertEqual(a.project.transition_rack[-1].kind,'module')

    def test_preview_uses_rack_authoring_not_preset_arrows(self):
        a=self.app;self.assertFalse(a.visual_mix.previous_transition.winfo_ismapped());self.assertFalse(a.visual_mix.next_transition.winfo_ismapped())
        a.visual_mix.open_transition_menu();self.pump()
        self.assertEqual(a.deck.scope.get(),'Transition')
        self.assertTrue(a.transition_shape_row.winfo_viewable())
        self.assertFalse(hasattr(a,'_creative_controls') and a._creative_controls)
