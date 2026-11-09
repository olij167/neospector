import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from instrument_model import new_instrument,voice
from sequencer_model import add_asset
from queue_model import append_assets,queue_position,current
from ux26_queue_actions import stop_queue,remove_playing

class UX26Actions(unittest.TestCase):
    def demo(self):
        p=new_instrument();a=add_asset(p,path='/tmp/a.png',kind='image',name='A',metadata={'sequence_preferences':{'clip_min':10.}});b=add_asset(p,path='/tmp/b.png',kind='image',name='B',metadata={'sequence_preferences':{'clip_min':10.}})
        append_assets(p,voice(p,'A').id,[a.id,b.id]);return p
    def test_stop_visual_immediately_disables_repeat_without_mutating_b(self):
        p=self.demo();la=voice(p,'A');lb=voice(p,'B');lb.extra['queue_policy']='repeat';la.extra['queue_policy']='repeat'
        stop_queue(p,'A',3.)
        self.assertEqual('finish',la.extra['queue_policy'])
        self.assertIsNone(current(la,3.01));self.assertEqual('repeat',lb.extra['queue_policy'])
        self.assertTrue(la.extra.get('queue_history'))
    def music_demo(self):
        from audio_bus import add_sound
        p=new_instrument()
        a=add_asset(p,path='/tmp/a.wav',kind='audio',name='Track A',duration=10.)
        b=add_asset(p,path='/tmp/b.wav',kind='audio',name='Track B',duration=10.)
        first=add_sound(p,a.id,start=0.,duration=10.)
        second=add_sound(p,b.id,start=10.,duration=10.)
        return p,first,second
    def test_stop_music_disables_repeat_and_preserves_performed_output(self):
        from queue_policies import music_position
        p,first,second=self.music_demo();p.extra['music_queue_policy']='repeat'
        stop_queue(p,'Music',3.)
        self.assertEqual('finish',p.extra['music_queue_policy'])
        self.assertTrue(p.extra.get('music_queue_history'))
        self.assertGreaterEqual(music_position(p,3.001),19.9)
    def test_remove_playing_music_advances_to_next_track(self):
        from music_queue import items
        from queue_policies import music_position
        p,first,second=self.music_demo()
        remove_playing(p,'Music',first['id'],3.)
        self.assertEqual([second['id']],[e['id'] for e in items(p)])
        self.assertTrue(p.extra.get('music_queue_history'))
        self.assertLess(music_position(p,3.001),.1)

    def test_remove_current_visual_advances_and_retains_history(self):
        p=self.demo();layer=voice(p,'A');ids=[c.id for c in layer.clips]
        remove_playing(p,'A',ids[0],2.)
        self.assertEqual(ids[1],current(layer,2.1).id)
        self.assertNotIn(ids[0],[c.id for c in layer.clips]);self.assertTrue(layer.extra['queue_history'])

if __name__=='__main__':unittest.main()
