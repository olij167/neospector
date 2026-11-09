"""UX40 controls: final-value commit, animation fidelity, per-module React, themed chrome."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX40Controls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ux40-')
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.temp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'});self.env.start()
        from neospector_console import NeospectorApp
        from effects_engine import make_effect
        self.a=NeospectorApp(test_mode=True);self.a.geometry('1350x850+0+0')
        self.fx=make_effect('blur');self.a.project.master_rack.append(self.fx)
        self.a.open_effects_context('Master');self.a.deck.refresh(True);self.a.update()
        self.cell=self.a.deck.selected_cell();self.f=self.cell.card_parts[self.fx.id][0].fader_rows[0]
    def tearDown(self):
        try:self.a.close(force=True)
        finally:self.env.stop();self.temp.cleanup()
    def test_final_scale_position_persists_even_when_callback_is_queued(self):
        f=self.f;param=f.param;f.begin();f.scale.set(.73);f.finish();self.a.update()
        self.assertAlmostEqual(param.value,param.minimum+.73*(param.maximum-param.minimum),delta=.08)
        self.assertAlmostEqual(float(f.text.get()),param.value,delta=.08)
    def test_number_commits_when_field_loses_focus(self):
        f=self.f;f.entry.focus_set();self.a.update();f.text.set('7.25');f.scale.focus_set();self.a.update()
        self.assertAlmostEqual(f.param.value,7.25,places=2)
        self.assertAlmostEqual(float(f.text.get()),7.25,places=2)
    def test_number_and_slider_follow_animated_keyframe_not_old_base(self):
        from sequencer_model import Keyframe
        f=self.f;p=f.param;p.value=2;p.mode='animate';p.keyframes=[Keyframe(0.,2.)];self.a.playhead=1.0
        f.refresh();f.text.set('9.25');f.enter();self.a.update();f.refresh()
        self.assertAlmostEqual(p.animated_value(1.),9.25,places=2)
        self.assertAlmostEqual(float(f.text.get()),9.25,places=2)
        f.begin();f.scale.set(.4);f.finish();self.a.update();f.refresh()
        self.assertAlmostEqual(p.animated_value(1.),p.minimum+.4*(p.maximum-p.minimum),delta=.08)
        self.assertAlmostEqual(float(f.text.get()),p.animated_value(1.),delta=.08)
    def test_stepped_numeric_field_commits_integral_value(self):
        from effects_engine import make_effect
        fx=make_effect('scanlines');self.a.project.master_rack.append(fx)
        self.a.deck.refresh(True);self.a.update()
        cell=self.a.deck.selected_cell()
        f=next(r for r in cell.card_parts[fx.id][0].fader_rows if r.semantic_kind=='steps')
        f.text.set('7.5');f.enter();self.a.update()
        self.assertEqual(f.param.value,8)
        self.assertEqual(f.text.get(),'8')
    def test_group_master_reaction_changes_all_promoted_params(self):
        from effects_engine import make_effect
        from module_engine import group_selected
        rack=self.a.project.master_rack
        a,b=make_effect('scanlines'),make_effect('blur')
        rack.extend([a,b]);group=group_selected(rack,[a.id,b.id]);self.a.deck.refresh(True);self.a.update()
        cell=self.a.deck.selected_cell();controls=cell.card_controls[group.id]
        controls['react_all'].invoke();self.a.update()
        self.assertEqual(sum(p.mode=='react' for p in group.params.values()),len(group.params))
        controls['react_all'].invoke();self.a.update()
        self.assertTrue(all(p.mode!='react' for p in group.params.values()))
    def test_drag_after_editing_number_does_not_end_drag_gesture(self):
        f=self.f;f.entry.focus_set();self.a.update();f.text.set('8')
        f.begin();self.a.update();f.scale.set(.62);f.finish();self.a.update()
        self.assertAlmostEqual(f.param.value,f.from_normal(.62),delta=.08)
        self.assertAlmostEqual(float(f.text.get()),f.param.value,delta=.08)
    def test_existing_native_combobox_popup_is_rethemed(self):
        from builtin_themes import BUILTIN_THEMES
        w=self.a.show_startup_window(True);self.a.update()
        combo=w.camera_selector
        popup=self.a.tk.call('ttk::combobox::PopdownWindow',combo)
        listbox=popup+'.f.l'
        self.a.apply_theme('Space Funk',save=False)
        self.assertEqual(self.a.tk.call(listbox,'cget','-background'),BUILTIN_THEMES['Space Funk']['field_bg'])
        self.a.apply_theme('Pungent Funk',save=False)
        self.assertEqual(self.a.tk.call(listbox,'cget','-background'),BUILTIN_THEMES['Pungent Funk']['field_bg'])
    def test_master_reaction_is_one_reversible_transaction(self):
        from module_reaction import apply_all_reactions,reaction_summary,apply_all_depth
        from sequencer_model import Keyframe
        from effects_engine import make_effect
        fx=make_effect('liquid')
        if len(fx.params)<2:
            fx=make_effect('blur');fx.params['second']=fx.params['amount'].__class__(.4,0,1)
        keys=list(fx.params);fx.params[keys[0]].mode='animate';fx.params[keys[0]].keyframes=[Keyframe(0.,.2)]
        self.assertEqual(reaction_summary(fx)['state'],'off')
        apply_all_reactions(fx,True)
        self.assertTrue(all(p.mode=='react' for p in fx.params.values()))
        self.assertTrue(fx.params[keys[0]].combine_animation)
        apply_all_depth(fx,-.35)
        self.assertTrue(all(abs(p.react_amount+.35)<.00001 for p in fx.params.values()))
        apply_all_reactions(fx,False)
        self.assertEqual(fx.params[keys[0]].mode,'animate')
        self.assertEqual(len(fx.params[keys[0]].keyframes),1)
        self.assertEqual(fx.params[keys[1]].mode,'static')
    def test_master_react_control_and_remove_button_are_on_card(self):
        cell=self.cell;parts=cell.card_parts[self.fx.id];ctrl=cell.card_controls[self.fx.id]
        self.assertIs(ctrl['delete'].master,parts[0].winfo_children()[0])
        self.assertTrue(ctrl['delete'].winfo_viewable())
        self.assertIn('react_all',ctrl)
        self.assertTrue(ctrl['react_all'].winfo_viewable())
        ctrl['react_all'].invoke();self.a.update()
        self.assertTrue(all(p.mode=='react' for p in self.fx.params.values()))
        ctrl['react_all'].invoke();self.a.update()
        self.assertTrue(all(p.mode!='react' for p in self.fx.params.values()))
    def test_live_queue_and_popup_chrome_follow_all_published_themes(self):
        from builtin_themes import PUBLISHED_THEME_ORDER,BUILTIN_THEMES
        from tkinter import ttk
        style=ttk.Style(self.a)
        for theme in PUBLISHED_THEME_ORDER:
            self.a.apply_theme(theme,save=False)
            c=BUILTIN_THEMES[theme]
            self.assertEqual(style.lookup('UX28.QueueIdle.TButton','background'),c['button_bg'],theme)
            self.assertEqual(style.lookup('UX28.Group.TFrame','background'),c['panel_bg'],theme)
            self.assertEqual(style.lookup('TCombobox','fieldbackground',('readonly',)),c['field_bg'],theme)
            self.assertEqual(self.a.tk.call('option','get',self.a._w,'menuBackground','MenuBackground') or c['field_bg'],c['field_bg'])

if __name__=='__main__':unittest.main()
