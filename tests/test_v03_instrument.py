import copy, importlib.util, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from sequencer_model import Project, Asset, Clip, Layer, project_to_dict, project_from_dict, ProgrammableParameter

class InstrumentContract(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('instrument_model'), 'v0.3 instrument model is missing')
        import instrument_model
        return instrument_model
    def test_default_two_voices_and_no_legacy_rewrite(self):
        m=self.api();p=m.new_instrument();self.assertEqual([l.extra.get('voice') for l in p.layers],['A','B'])
        self.assertTrue(p.instrument_mode);q=Project(layers=[Layer('legacy','L')]);self.assertFalse(q.instrument_mode)
    def test_assign_preserves_rack_and_prior_source_when_playing(self):
        m=self.api();p=m.new_instrument();a=Asset('a','','colour','A',metadata={'colour':'#ff0000'});b=Asset('b','','colour','B',metadata={'colour':'#0000ff'});p.assets={'a':a,'b':b}
        m.assign_source(p,'A','a',0);p.layers[0].effects['saturation'].value=.7
        m.assign_source(p,'A','b',4,performing=True)
        self.assertEqual(p.layers[0].effects['saturation'].value,.7)
        old,new=sorted(p.layers[0].clips,key=lambda c:c.start);self.assertEqual(old.end,4);self.assertEqual(new.start,4);self.assertEqual(old.asset_id,'a')
    def test_locked_voice_rejects_assignment(self):
        m=self.api();p=m.new_instrument();p.assets['a']=Asset('a','','colour','A');p.layers[0].locked=True;before=project_to_dict(p)
        with self.assertRaises(ValueError):m.assign_source(p,'A','a',2)
        self.assertEqual(before,project_to_dict(p))
    def test_roundtrip_new_mixer(self):
        m=self.api();p=m.new_instrument();p.voice_mix.value=.7;p.voice_mixer_mode='crossfade';p.voice_mix.add_keyframe(2,.2)
        q=project_from_dict(project_to_dict(p));self.assertEqual(q.voice_mix.keyframes,p.voice_mix.keyframes);self.assertTrue(q.instrument_mode)
    def test_capture_independent_and_retains_absolute_parameter_time(self):
        m=self.api();p=m.new_instrument();p.assets['a']=Asset('a','','colour','A');m.assign_source(p,'A','a',0);p.layers[0].opacity.add_keyframe(6,.3)
        q=m.capture_interval(p,4,9);self.assertEqual(q.extra['capture_range'],[4.,9.]);q.layers[0].opacity.value=.1
        self.assertEqual(p.layers[0].opacity.value,1);self.assertEqual(q.layers[0].opacity.keyframes[0].time,6)
    def test_capture_rejects_unretained_camera(self):
        m=self.api();p=m.new_instrument();p.assets['a']=Asset('a','live:camera','camera','Camera');m.assign_source(p,'A','a',0)
        with self.assertRaisesRegex(ValueError,'retained|record'):m.capture_interval(p,0,5)
    def test_live_parameters_converted_only_with_retained_envelopes(self):
        m=self.api();p=m.new_instrument();param=p.layers[0].opacity;param.mode='react';param.source='microphone';param.react_amount=-.4
        with self.assertRaisesRegex(ValueError,'reaction|record'):m.capture_interval(p,0,5)
        p.recorded_analysis={'version':2,'offset':0,'duration':6,'hop_seconds':1,'bands':{'full':[.2]*6}}
        q=m.capture_interval(p,0,5);self.assertEqual(q.layers[0].opacity.source,'recorded')
    def test_mixer_pixel_endpoints(self):
        m=self.api();from programme_renderer import ProgrammeRenderer
        p=m.new_instrument();p.assets={'a':Asset('a','','colour','A',metadata={'colour':'#ff0000'}),'b':Asset('b','','colour','B',metadata={'colour':'#0000ff'})};m.assign_source(p,'A','a',0);m.assign_source(p,'B','b',0);p.voice_mixer_mode='crossfade'
        r=ProgrammeRenderer()
        try:
            p.voice_mix.value=0;self.assertEqual(r.render(p,1,(32,32)).getpixel((16,16))[:3],(255,0,0))
            p.voice_mix.value=1;self.assertEqual(r.render(p,1,(32,32)).getpixel((16,16))[:3],(0,0,255))
        finally:r.close()
    def test_empty_b_bypasses_global_mixer(self):
        m=self.api();from programme_renderer import ProgrammeRenderer
        p=m.new_instrument();p.assets['a']=Asset('a','','colour','A',metadata={'colour':'#ff0000'});m.assign_source(p,'A','a',0);p.voice_mix.value=1;p.voice_mixer_mode='crossfade';r=ProgrammeRenderer()
        try:self.assertEqual(r.render(p,1,(32,32)).getpixel((16,16))[:3],(255,0,0))
        finally:r.close()
    def test_style_archive_preserves_past_and_review_edit(self):
        m=self.api();p=m.new_instrument();before=copy.deepcopy(p);p.layers[0].opacity.value=.2;m.archive_styles(before,p,5)
        past=m.style_at(p.layers[0],2);self.assertEqual(past.opacity.value,1);self.assertEqual(m.style_at(p.layers[0],7).opacity.value,.2)
        past.opacity.value=.6;m.store_style(p.layers[0],2,past);self.assertEqual(m.style_at(p.layers[0],2).opacity.value,.6)
    def test_mutation_preserves_voices_and_racks(self):
        m=self.api();p=m.new_instrument();p.assets={str(i):Asset(str(i),'', 'colour',str(i),metadata={'colour':'#112233'}) for i in range(3)}
        p.layers[0].effects['saturation'].value=.8;m.mutate_instrument(p,42)
        self.assertEqual(len(p.layers),2);self.assertEqual(p.layers[0].effects['saturation'].value,.8);self.assertTrue(p.layers[0].clips)
    def test_mutation_in_live_range_keeps_past(self):
        m=self.api();p=m.new_instrument();p.assets={str(i):Asset(str(i),'', 'colour',str(i)) for i in range(3)};m.mutate_instrument(p,42)
        old=[copy.deepcopy(c) for c in p.layers[0].clips if c.start<6];m.mutate_instrument(p,52,time_range=(6,20))
        for c in old:self.assertEqual(p.clip(c.id)[1],c)

class LibraryContract(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('creative_library'),'creative library missing')
        from creative_library import CreativeLibrary
        return CreativeLibrary
    def test_album_membership_non_destructive(self):
        cls=self.api()
        with tempfile.TemporaryDirectory() as td:
            lib=cls(Path(td)/'library.sqlite');a=Asset('a','/not/deleted','video','River');lib.put_asset(a);x=lib.create_album('River');y=lib.create_album('Textures');lib.add_members(x,['a']);lib.add_members(y,['a']);lib.remove_members(x,['a'])
            self.assertEqual(lib.member_ids(y),{'a'});self.assertEqual(lib.member_ids(x),set());lib.close()
    def test_ingredient_revisions_not_mutated(self):
        cls=self.api()
        with tempfile.TemporaryDirectory() as td:
            lib=cls(Path(td)/'library.sqlite');a=lib.save_ingredient('Pulse','rack',{'value':1});b=lib.save_ingredient('Pulse','rack',{'value':2},ingredient_id=a['id'])
            self.assertEqual(lib.ingredient(a['id'],1)['payload']['value'],1);self.assertEqual(b['revision'],2);lib.close()
    def test_restart_retains_album_and_payload(self):
        cls=self.api()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'library.sqlite';lib=cls(path);lib.create_album('One');it=lib.save_ingredient('Pulse','recipe',{'seed':7});lib.close();lib=cls(path)
            self.assertEqual(lib.ingredient(it['id'])['payload']['seed'],7);self.assertEqual(len(lib.albums()),1);lib.close()
    def test_ingredient_export_import_roundtrip(self):
        cls=self.api()
        with tempfile.TemporaryDirectory() as td:
            lib=cls(Path(td)/'library.sqlite');a=lib.save_ingredient('Pulse','rack',{'value':1});f=Path(td)/'pulse.omne-ingredient.json';lib.export_ingredient(a['id'],f);b=lib.import_ingredient(f)
            self.assertEqual(a['payload'],b['payload']);lib.close()

if __name__=='__main__':unittest.main()
