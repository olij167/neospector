import sys, unittest,tempfile,copy
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from sequencer_model import *
from effects_engine import *
from programme_renderer import ProgrammeRenderer
from signal_engine import SignalEvaluator

class BehaviourRegressions(unittest.TestCase):
    def test_transition_easing_changes_pixels(self):
        a=Image.new('RGBA',(32,24),'red');b=Image.new('RGBA',(32,24),'blue')
        tr=Transition('t','a','b',duration=1,easing='linear')
        linear=transition_image(a,b,tr,.25).tobytes();tr.easing='ease_in'
        self.assertNotEqual(linear,transition_image(a,b,tr,.25).tobytes())
    def test_wipe_left_moves_boundary_to_left(self):
        a=Image.new('RGBA',(32,24),'red');b=Image.new('RGBA',(32,24),'blue')
        im=transition_image(a,b,Transition('t','a','b',kind='wipe_left',duration=1),.5)
        self.assertEqual(im.getpixel((30,12))[:3],(0,0,255));self.assertEqual(im.getpixel((1,12))[:3],(255,0,0))
    def test_echo_does_not_apply_opacity_twice(self):
        a=Asset('a','','colour','White',metadata={'colour':'#ffffff'});c=Clip('c','a',duration=2);c.opacity.value=.5;c.rack=[make_effect('echo',{'amount':.5,'delay':.1,'taps':1})]
        p=Project(width=32,height=24,duration=2,assets={'a':a},layers=[Layer('l','Layer',clips=[c])]);r=ProgrammeRenderer()
        try:pixel=r.render(p,1).getpixel((10,10));self.assertGreaterEqual(pixel[0],125);self.assertLessEqual(pixel[0],129)
        finally:r.close()
    def test_zero_scale_is_transparent_not_division_error(self):
        a=Asset('a','','colour','White',metadata={'colour':'#ffffff'});c=Clip('c','a',duration=2);c.scale.minimum=0;c.scale.value=0
        p=Project(width=32,height=24,duration=2,assets={'a':a},layers=[Layer('l','Layer',clips=[c])]);r=ProgrammeRenderer()
        try:self.assertEqual(r.render(p,1).getpixel((10,10))[:3],(0,0,0))
        finally:r.close()
    def test_asset_effect_exclusion_is_honoured(self):
        from conductor import generate
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'a.png';Image.new('RGB',(32,24),'red').save(path)
            p=Project(duration=15);add_asset(p,path=str(path),kind='image',metadata={'sequence_preferences':{'effect_preferences':{k:'exclude' for k in p.conductor.effect_preferences},'reaction_preferences':{k:'exclude' for k in p.conductor.reaction_preferences}}})
            generate(p,5);self.assertTrue(all(not c.rack for l in p.layers for c in l.clips))
    def test_live_take_converts_mic_sources_without_replacing_locked_clip(self):
        from live_panel import add_take_to_project
        p=Project(duration=2,layers=[Layer('l','Layer')]);p.layers[0].opacity.mode='react';p.layers[0].opacity.source='mix'
        data={'start':0,'duration':2,'analysis':{'duration':2,'offset':0,'hop_seconds':1,'bands':{'full':[.1,.2,.3]}},'video':'','audio':''}
        add_take_to_project(p,data,replace_live=True)
        self.assertEqual(p.layers[0].opacity.source,'song_recorded')
        self.assertEqual(p.recorded_analysis['bands']['full'],[.1,.2,.3])

if __name__=='__main__':unittest.main()

class FinalSignalAndMutationRegressions(unittest.TestCase):
    def test_sustained_microphone_tone_does_not_retrigger_onset_every_block(self):
        from live_sources import LiveInputs
        live=LiveInputs();samples=(.1*np.sin(np.arange(1024)*2*np.pi*110/24000)).astype(np.float32)
        live._audio(samples,1.);live._audio(samples,1.05)
        self.assertLess(live.signal()[0]['onset'],.001)
    def test_motion_mutation_preserves_existing_grain_identity(self):
        from conductor import _style_clip,stream
        p=Project();a=Asset('a','','image','Image');c=Clip('c','a',duration=5)
        c.rack=[make_effect('grain')];c.rack[0].extra['seed']='authored-grain'
        _style_clip(p,c,a,stream(123,'style'),'motion')
        self.assertEqual(c.rack[0].extra['seed'],'authored-grain')
    def test_scoped_effect_mutation_does_not_reroll_locked_transition(self):
        from conductor import generate
        p=Project(duration=4,assets={'a':Asset('a','','image','Image')})
        a=Clip('a1','a',duration=2.5);b=Clip('b1','a',channel='B',start=2,duration=2)
        tr=Transition('tr',a.id,b.id,kind='pixel_dissolve',start=2,duration=.5,locked=True,extra={'seed':'KEEP'})
        p.layers=[Layer('l','Layer',clips=[a,b],transitions=[tr])]
        generate(p,678,scope='effects')
        self.assertEqual(tr.extra['seed'],'KEEP')
