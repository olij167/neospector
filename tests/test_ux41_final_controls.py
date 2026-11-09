"""UX41 red/green contracts: stable reaction controls and deterministic A/B ping-pong."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class ReactionModelTests(unittest.TestCase):
    def setUp(self):
        from effects_engine import make_effect
        self.fx=make_effect('blur');p=next(iter(self.fx.params.values()))
        from sequencer_model import ProgrammableParameter
        self.fx.params['extra']=ProgrammableParameter(.4,0,1)
    def test_module_routing_is_bulk_but_preserves_each_depth(self):
        from module_reaction import apply_all_routing,reaction_summary
        from rack_editing import update_parameter
        p=list(self.fx.params.values());update_parameter(p[0],{'mode':'react','react_amount':-.35})
        apply_all_routing(self.fx,source='microphone',band='bass')
        self.assertTrue(all(q.source=='microphone' and q.react_band=='bass' for q in p))
        self.assertAlmostEqual(p[0].react_amount,-.35)
        self.assertEqual(reaction_summary(self.fx)['source'],'microphone')
        self.assertEqual(reaction_summary(self.fx)['band'],'bass')
    def test_master_routing_stays_selected_when_enabling(self):
        from module_reaction import apply_all_routing,apply_all_reactions
        apply_all_routing(self.fx,source='song',band='high')
        apply_all_reactions(self.fx,True)
        self.assertTrue(all(p.mode=='react' and p.source=='song' and p.react_band=='high' for p in self.fx.params.values()))
    def test_signed_reaction_explains_direction_and_zero(self):
        from ux18_reaction_surface import depth_label
        self.assertEqual(depth_label(-.65),'−65%')
        self.assertEqual(depth_label(.65),'+65%')
        self.assertEqual(depth_label(0),'0%')

class PingPongTests(unittest.TestCase):
    def setUp(self):
        from instrument_model import new_instrument
        self.project=new_instrument()
    def test_dwell_crossfade_and_reverse(self):
        from timed_mix import configure_pingpong,pingpong_at
        configure_pingpong(self.project,True,start=0,hold=3,fade=2,first='A')
        expected=[(0,0),(2.5,0),(3,0),(4,.5),(5,1),(7,1),(9,.5),(10,0)]
        for t,value in expected:self.assertAlmostEqual(pingpong_at(self.project,t),value,places=5,msg=str(t))
    def test_start_channel_and_large_time_are_deterministic(self):
        from timed_mix import configure_pingpong,pingpong_at
        configure_pingpong(self.project,True,start=12,hold=1,fade=1,first='B')
        self.assertEqual(pingpong_at(self.project,12),1.)
        self.assertAlmostEqual(pingpong_at(self.project,13.5),.5)
        self.assertEqual(pingpong_at(self.project,16),1.)
    def test_signal_evaluator_resolves_auto_in_preview_and_export(self):
        from timed_mix import configure_pingpong
        from signal_engine import SignalEvaluator
        configure_pingpong(self.project,True,start=0,hold=1,fade=1,first='A')
        self.project.voice_mix.value=.3
        evaluation=SignalEvaluator(self.project)
        self.assertAlmostEqual(evaluation.value(self.project.voice_mix,1.5),.5)
        self.assertEqual(evaluation.value(self.project.voice_mix,2),1.)
        self.assertEqual(self.project.voice_mix.value,.3)
    def test_project_save_load_preserves_authored_cycle(self):
        from timed_mix import configure_pingpong,pingpong_at
        from sequencer_model import project_to_dict,project_from_dict
        configure_pingpong(self.project,True,start=1.25,hold=2.5,fade=1.5,first='B')
        restored=project_from_dict(project_to_dict(self.project))
        self.assertEqual(restored.extra['ux41_pingpong']['hold'],2.5)
        self.assertEqual(restored.extra['ux41_pingpong']['fade'],1.5)
        self.assertAlmostEqual(pingpong_at(self.project,5),pingpong_at(restored,5))

    def test_pingpong_config_rejects_bad_numbers(self):
        from timed_mix import configure_pingpong
        for kwargs in ({'hold':-1},{'fade':0},{'fade':float('nan')}):
            with self.assertRaises(ValueError):configure_pingpong(self.project,True,**kwargs)

class GUIControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ux41-gui-')
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'});self.env.start()
        from neospector_console import NeospectorApp
        from effects_engine import make_effect
        self.app=NeospectorApp(test_mode=True);self.app.geometry('1350x850+0+0')
        self.fx=make_effect('blur');self.app.project.master_rack.append(self.fx)
        self.app.open_effects_context('Master');self.app.deck.refresh(True);self.app.update()
        self.cell=self.app.deck.selected_cell();self.row=self.cell.card_parts[self.fx.id][0].fader_rows[0]
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()
    def test_depth_refresh_never_rewinds_active_slider(self):
        from ux18_reaction_surface import begin_depth,change_depth
        begin_depth(self.cell,self.row,self.fx.id)
        self.row.reaction_amount.set(.7)
        self.row._refresh_reaction()
        self.assertAlmostEqual(float(self.row.reaction_amount.get()),.7,delta=.06)
        change_depth(self.cell,self.row,self.fx.id)
        self.app.update()
        self.assertAlmostEqual(self.row.param.react_amount,.7,delta=.06)
        self.assertEqual(self.row.reaction_depth_label.cget('text'),'+70%')
    def test_module_footer_has_source_band_and_master(self):
        ctrl=self.cell.card_controls[self.fx.id]
        self.assertTrue(all(key in ctrl for key in ('react_all','source_all','band_all')))
        self.assertTrue(ctrl['source_all'].winfo_viewable())
        ctrl['source_all'].invoke();self.app.update()
        self.assertTrue(all(p.source=='microphone' for p in self.fx.params.values()))
    def test_pingpong_button_and_rate_fields_are_in_mixer(self):
        mix=self.app.visual_mix
        mix.pingpong_button.invoke();self.app.update()
        self.assertTrue(self.app.project.extra['ux41_pingpong']['enabled'])
        self.assertTrue(mix.hold_entry.winfo_viewable())
        self.assertTrue(mix.fade_entry.winfo_viewable())

if __name__=='__main__':unittest.main()
