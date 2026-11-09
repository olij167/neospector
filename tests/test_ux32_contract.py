"""UX32: transition module rack, inline variation, source navigation and contextual menus."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class TransitionRackContract(unittest.TestCase):
    def test_serialized_transition_module_rack_roundtrip(self):
        from sequencer_model import Project,project_from_dict,project_to_dict
        from effects_engine import make_effect
        p=Project();p.transition_rack.append(make_effect('grain'))
        q=project_from_dict(project_to_dict(p))
        self.assertEqual(q.transition_rack[0].kind,'grain')
        self.assertIsNot(q.transition_rack[0],p.transition_rack[0])
    def test_transition_rack_only_processes_mix_interior(self):
        from sequencer_model import Project
        from effects_engine import make_effect
        from ux16_transitions import composited_mix
        from PIL import Image,ImageChops
        p=Project();p.transition_rack=[make_effect('invert')]
        p.transition_rack[0].params['amount'].value=1
        a=Image.new('RGBA',(24,24),'#281800');b=Image.new('RGBA',(24,24),'#00aaee')
        self.assertIs(composited_mix(p,a,b,0),a)
        self.assertIs(composited_mix(p,a,b,1),b)
        base=Image.blend(a,b,.5)
        self.assertIsNotNone(ImageChops.difference(base.convert('RGB'),composited_mix(p,a,b,.5).convert('RGB')).getbbox())
    def test_temporal_modules_are_refused_but_groups_are_available(self):
        from effects_engine import make_effect
        from ux16_transitions import validate_transition_rack
        from module_engine import group_selected
        rack=[make_effect('grain'),make_effect('invert')]
        group_selected(rack,{f.id for f in rack})
        self.assertEqual(len(validate_transition_rack(rack)),2)
        with self.assertRaisesRegex(ValueError,'history'):
            validate_transition_rack([make_effect('echo')])

    def test_custom_reveal_field_is_a_transition_only_module(self):
        from sequencer_model import Project
        from effects_engine import make_effect
        from ux16_transitions import composited_mix,validate_transition_rack
        from PIL import Image,ImageChops
        p=Project();reveal=make_effect('transition_reveal');reveal.params['angle'].value=45
        reveal.params['softness'].value=.015;p.transition_rack=[reveal]
        self.assertEqual(len(validate_transition_rack(p.transition_rack)),1)
        a=Image.new('RGBA',(60,40),(10,10,10,255));b=Image.new('RGBA',(60,40),(240,250,250,255))
        middle=composited_mix(p,a,b,.5)
        self.assertNotEqual(middle.getpixel((0,0)),middle.getpixel((59,39)))
        self.assertIs(composited_mix(p,a,b,0),a)
        self.assertIs(composited_mix(p,a,b,1),b)

class ContextMenus(unittest.TestCase):
    def test_pointer_popups_flip_above_and_clamp_horizontally(self):
        from contextual_surface import popup_coordinates
        from types import SimpleNamespace
        anchor=SimpleNamespace(winfo_vrootx=lambda:0,winfo_vrooty=lambda:0,
            winfo_vrootwidth=lambda:1024,winfo_vrootheight=lambda:768,
            winfo_rootx=lambda:980,winfo_rooty=lambda:738,winfo_height=lambda:20,
            winfo_screenwidth=lambda:1024,winfo_screenheight=lambda:768)
        event=SimpleNamespace(x_root=1005,y_root=750)
        x,y=popup_coordinates(anchor,300,230,event)
        self.assertLessEqual(x+300,1024)
        self.assertLess(y,750)
        self.assertGreaterEqual(x,0)

class UX32Tk(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patcher=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.temp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'});self.patcher.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True);self.app.geometry('1500x950+0+0');self.pump()
    def pump(self):
        for _ in range(6):self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.patcher.stop();self.temp.cleanup()
    def test_transition_uses_effects_rack_not_creative_window(self):
        a=self.app
        a.visual_mix.open_transition_menu();self.pump()
        self.assertEqual(a.deck.scope.get(),'Transition')
        self.assertTrue(a.shell.rack_open)
        self.assertIsNone(getattr(a,'_creative_controls',None))
        self.assertIn('Transition',a.deck.owner_title())
    def test_inline_variation_toolbar_is_visible_and_persists(self):
        a=self.app;a.open_effects_context('Master');self.pump()
        deck=a.deck
        deck.toggle_variation_options();self.pump()
        self.assertTrue(deck.variation_options.winfo_viewable())
        deck.random_count.set('3');deck.random_variation.set('45');deck.save_variation_options();self.pump()
        self.assertEqual(a.project.extra['randomise_settings']['module_count'],3)
        self.assertAlmostEqual(a.project.extra['randomise_settings']['variation'],.45)
    def test_transition_and_output_have_independent_bypass_and_racks(self):
        from effects_engine import make_effect
        a=self.app;a.open_effects_context('Transition');self.pump()
        a.insert_module_from_library(make_effect('grain'),'Grain');self.pump()
        self.assertEqual(len(a.project.transition_rack),1)
        self.assertEqual(len(a.project.master_rack),0)
        a.deck.direct_toggle_fx();self.pump()
        self.assertTrue(a.project.extra.get('transition_rack_bypassed'))
        self.assertFalse(a.project.extra.get('rack_bypassed',False))
        a.open_effects_context('Master');self.pump()
        self.assertFalse(a.project.extra.get('rack_bypassed',False))
        a.open_effects_context('Transition');self.pump()
        a.deck.direct_toggle_fx();self.pump()
        self.assertFalse(a.project.extra.get('transition_rack_bypassed',False))
    def test_transition_library_offers_reveal_and_filters_history(self):
        a=self.app;a.open_effects_context('Transition');a.toggle_module_library(True);self.pump()
        lib=a.module_library;lib.refresh(force=True)
        self.assertIn('base:transition_reveal',lib._rows)
        self.assertNotIn('base:echo',lib._rows)
        a.open_effects_context('Master');lib.refresh(force=True);self.pump()
        self.assertNotIn('base:transition_reveal',lib._rows)
        self.assertIn('base:echo',lib._rows)
    def test_transition_shape_is_authored_in_rack_not_popup(self):
        a=self.app;a.open_effects_context('Transition');self.pump()
        self.assertTrue(a.transition_shape_row.winfo_viewable())
        before=a.project.extra.get('ux16_transition',{}).get('kind','dissolve')
        a.cycle_transition_property('kind');self.pump()
        self.assertNotEqual(a.project.extra['ux16_transition']['kind'],before)
        a.transition_softness.set(.29);a.commit_transition_softness();self.pump()
        self.assertAlmostEqual(a.project.extra['ux16_transition']['softness'],.29)
        a.open_effects_context('A');self.pump()
        self.assertFalse(a.transition_shape_row.winfo_viewable())
    def test_transition_reveal_group_roundtrip_and_insertion(self):
        from effects_engine import make_effect
        from sequencer_model import project_to_dict,project_from_dict
        a=self.app;a.open_effects_context('Transition');self.pump()
        a.insert_module_from_library(make_effect('transition_reveal'),'Reveal Field')
        a.insert_module_from_library(make_effect('grain'),'Grain');self.pump()
        cell=a.deck.selected_cell();cell.selected_fx={fx.id for fx in a.project.transition_rack}
        self.assertTrue(a.deck.group_selected());self.pump()
        self.assertEqual(a.project.transition_rack[0].kind,'module')
        restored=project_from_dict(project_to_dict(a.project))
        self.assertEqual(restored.transition_rack[0].kind,'module')
    def test_advanced_variation_randomises_only_selected_rack(self):
        a=self.app;a.open_effects_context('Transition');self.pump()
        a.deck.random_count.set('2');a.deck.random_variation.set('25')
        a.deck.variation_seed.set('301');a.deck.random_now(False);self.pump()
        self.assertEqual(len(a.project.transition_rack),2)
        self.assertFalse(a.project.master_rack)
        from ux16_transitions import validate_transition_rack
        self.assertTrue(validate_transition_rack(a.project.transition_rack))

    def test_transition_target_and_advanced_controls_fit_sidebar(self):
        a=self.app;a.geometry('1350x850+0+0')
        a.open_effects_context('Transition');a.deck.toggle_variation_options(True);self.pump()
        button=a.rack_target_buttons['Transition']
        self.assertGreaterEqual(button.winfo_width(),93,'Transition target must not show TRA…')
        self.assertFalse(a.deck.variation_status_label.winfo_viewable(), 'empty feedback must not create a blank toolbar row')
        row=a.deck.variation_options
        self.assertGreater(row.winfo_height(),0)
        self.assertGreater(len(row.winfo_children()),4)
        for child in row.winfo_children():
            self.assertTrue(child.winfo_viewable(),f'advanced option hidden: {child}')
            self.assertLessEqual(child.winfo_x()+child.winfo_width(),row.winfo_width()+2,
                f'advanced option clipped by sidebar: {child}')

    def test_audio_add_opens_sources_not_menu(self):
        a=self.app
        music=a.queue_deck.pages['Music'];music.show_audio_view('mixer');self.pump()
        music.audio_mixer.add_sources();self.pump()
        self.assertTrue(a.sidebar._browser_open)
        self.assertEqual(a.sidebar.source_shelf.mode,'sources')
        self.assertFalse(bool(getattr(a,'_posted_native_menu',None)))

if __name__=='__main__':unittest.main()
