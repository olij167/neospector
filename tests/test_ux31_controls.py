"""UX31 regression contracts for sparse mixer and separate-but-shared creative controls."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace
from PIL import Image,ImageChops
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class SparseMixer(unittest.TestCase):
    def test_only_engaged_sources_are_listed(self):
        from sound_panel import active_source_order
        from sound_routes import source_id
        mic=source_id('default')
        sources=[{'id':mic,'device':'default','kind':'microphone','label':'Mic'},
                 {'id':'live:spotify','device':{'kind':'application'},'label':'Spotify','kind':'application'}]
        routes={'soundtrack':{'enabled':True},'voice:A':{'enabled':False},mic:{'enabled':False},'live:spotify':{'enabled':True}}
        states={'live:spotify':{'state':'live'},mic:{'state':'stopped'}}
        ids,_=active_source_order(SimpleNamespace(project=SimpleNamespace(layers=[]),last_microphone_device='default'),routes,sources,states,has_audio_queue=False)
        self.assertEqual(ids,['live:spotify'])
    def test_soundtrack_returns_when_queued_and_microphone_when_live(self):
        from sound_panel import active_source_order
        from sound_routes import source_id
        mic=source_id('default')
        ids,_=active_source_order(SimpleNamespace(project=SimpleNamespace(layers=[]),last_microphone_device='default'),{},[],{mic:{'state':'live'}},has_audio_queue=True)
        self.assertEqual(ids,['soundtrack',mic])
    def test_enabled_but_empty_visual_sound_channel_is_not_a_fader(self):
        from sound_panel import active_source_order
        app=SimpleNamespace(project=SimpleNamespace(layers=[]),last_microphone_device='default')
        ids,_=active_source_order(app,{'voice:A':{'enabled':True}},[],{},False)
        self.assertEqual(ids,[])
    def test_unassigned_but_actively_running_application_can_be_shown(self):
        from sound_panel import active_source_order
        app=SimpleNamespace(project=SimpleNamespace(layers=[]),last_microphone_device='default')
        rows=[{'id':'live:spotify','kind':'application','label':'Spotify','device':{'kind':'application'}}]
        ids,_=active_source_order(app,{},rows,{'live:spotify':{'state':'live'}},False)
        self.assertEqual(ids,['live:spotify'])

class TransitionCustomisation(unittest.TestCase):
    def test_style_change_retains_authored_controls(self):
        from ux16_transitions import configure_transition
        p=SimpleNamespace(extra={},voice_mixer_mode='auto')
        configure_transition(p,'wipe_left',softness=.21,easing='smooth',effect='grain',effect_strength=.6)
        configure_transition(p,'wipe_right')
        self.assertEqual(p.extra['ux16_transition']['softness'],.21)
        self.assertEqual(p.extra['ux16_transition']['effect'],'grain')
        self.assertEqual(p.extra['ux16_transition']['kind'],'wipe_right')
    def test_effect_only_applies_during_transition(self):
        from ux16_transitions import configure_transition,composited_mix
        p=SimpleNamespace(extra={},voice_mixer_mode='auto',id='stable')
        a=Image.new('RGBA',(32,24),(160,42,85,255));b=Image.new('RGBA',(32,24),(17,218,50,255))
        configure_transition(p,'dissolve',effect='invert',effect_strength=.85)
        self.assertEqual(ImageChops.difference(composited_mix(p,a,b,0),a).getbbox(),None)
        self.assertEqual(ImageChops.difference(composited_mix(p,a,b,1),b).getbbox(),None)
        before=Image.blend(a,b,.5)
        self.assertIsNotNone(ImageChops.difference(composited_mix(p,a,b,.5),before).convert("RGB").getbbox())
    def test_transition_settings_validation(self):
        from ux16_transitions import configure_transition
        p=SimpleNamespace(extra={},voice_mixer_mode='auto')
        for change in ({'softness':5},{'effect':'echo'},{'effect_strength':-1},{'easing':'banana'}):
            with self.subTest(change=change),self.assertRaises(ValueError):configure_transition(p,'dissolve',**change)

class SharedEditor(unittest.TestCase):
    def test_editor_supports_distinct_transition_and_rack_sections(self):
        from creative_controls import CreativeControls
        self.assertTrue(callable(getattr(CreativeControls,'save_transition',None)))
        self.assertTrue(callable(getattr(CreativeControls,'save_rack_options',None)))

if __name__=='__main__':unittest.main()
