"""UX29 product contracts: one shelf, contextual destinations, routed mixer."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX29Tk(unittest.TestCase):
    def setUp(self):
        self.sandbox=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.sandbox.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.a=NeospectorApp(test_mode=True)
        self.a.geometry('1450x890+0+0');self.pump()
    def pump(self):
        for _ in range(5):self.a.update()
    def tearDown(self):
        try:self.a.close(force=True)
        finally:self.env.stop();self.sandbox.cleanup()

    def test_browser_navigation_is_local_files_sources_only(self):
        shelf=self.a.sidebar.source_shelf
        self.assertEqual(set(shelf.tab_buttons),{'files','sources'})
        self.assertFalse(shelf.dest_row.winfo_manager())
        self.assertFalse(shelf.placement.winfo_manager())
        self.a.sidebar.open_browser('A','sources');self.pump()
        self.assertEqual(shelf.mode,'sources')
        self.assertTrue(shelf.source_list.winfo_ismapped() or shelf.source_list.winfo_viewable())
        shelf.show('files');self.pump()
        self.assertTrue(shelf.media.winfo_ismapped())

    def test_browser_files_display_all_media_independent_of_queue(self):
        shelf=self.a.sidebar.source_shelf
        from sequencer_model import add_asset
        def add():
            add_asset(self.a.project,path='/tmp/image.png',kind='image',name='Static Image')
            add_asset(self.a.project,path='/tmp/sound.wav',kind='audio',name='Sound Clip')
            add_asset(self.a.project,path='/tmp/movie.mp4',kind='video',name='Movie',metadata={'has_audio':True})
        self.a.transaction('Fixture media',add)
        shelf.media.refresh(force=True)
        kinds={a.kind for a in shelf.media.assets()}
        self.assertTrue({'image','audio','video'}<=kinds)
        self.assertFalse(shelf.media.dest_row.winfo_ismapped())
        self.assertFalse(shelf.media.actions_frame.winfo_ismapped())
        with patch.object(shelf.media,'offer_destinations') as popup:
            ids=list(shelf.media.items.get_children())
            for aid in ids:
                shelf.media.items.selection_set(aid)
                shelf.media.place('next')
            self.assertEqual(popup.call_count,3)

    def test_context_destinations_match_asset_capabilities(self):
        from ux29_browser_model import file_destinations,source_destinations
        class Asset:
            def __init__(self,kind,has_audio=False):self.kind=kind;self.metadata={'has_audio':has_audio}
        self.assertEqual(file_destinations([Asset('image')]),('A','B'))
        self.assertEqual(file_destinations([Asset('audio')]),('Music',))
        self.assertEqual(file_destinations([Asset('video',True)]),('A','B','Music'))
        self.assertEqual(source_destinations({'kind':'window'}),('A','B'))
        self.assertEqual(source_destinations({'kind':'application'}),('Music',))

    def test_discovered_sources_are_individual_action_rows(self):
        shelf=self.a.sidebar.source_shelf
        shelf.show('sources')
        shelf.populate_sources([
            {'kind':'camera','label':'Camera USB','device':'/dev/video2'},
            {'kind':'window','label':'App window','device':{'kind':'window','name':'App window','id':'500'}},
            {'kind':'application','label':'App · Browser','device':{'kind':'application','backend':'pulse','device':'monitor','stream':24}},
        ],[])
        self.pump()
        self.assertEqual(len(shelf.source_list.get_children()),3)
        for iid in shelf.source_list.get_children():
            self.assertEqual(shelf.source_list.item(iid,'values'),('▶','⏭','＋'))
        with patch.object(shelf,'offer_source_destinations') as popup:
            shelf.place_source('next',shelf.source_list.get_children()[2]);popup.assert_called_once()

    def test_file_destination_menu_actions_are_contextual_and_commit(self):
        from sequencer_model import add_asset
        from contextual_surface import post_native_menu
        shelf=self.a.sidebar.source_shelf
        add=lambda:add_asset(self.a.project,path='/tmp/vis.png',kind='image',name='Fixture image')
        asset=self.a.transaction('Add fixture',add)
        shelf.media.refresh(True)
        shelf.media.items.selection_set(asset.id)
        menus=[]
        with patch('contextual_surface.post_native_menu',side_effect=lambda root,menu,anchor,event=None:menus.append(menu)):
            shelf.media.place('now')
        self.assertEqual([m.entrycget(i,'label') for m in menus for i in range(m.index('end')+1)],['Channel A','Channel B'])
        with patch.object(self.a,'place_media') as place:
            menus[0].invoke(1)
            place.assert_called_once_with([asset.id],'B',action='now')

    def test_app_audio_cue_is_not_created_until_dest_confirmed(self):
        shelf=self.a.sidebar.source_shelf
        record={'kind':'application','label':'App · test','device':{'kind':'application','backend':'pulse','device':'x.monitor','stream':11}}
        before=len(shelf.audio_cues.items())
        with patch('contextual_surface.post_native_menu',side_effect=lambda *args,**kwargs:None):
            shelf.offer_source_destinations(record,'next')
        self.assertEqual(len(shelf.audio_cues.items()),before)
        with patch.object(shelf.audio_cues,'enqueue',return_value={'start':12}) as enqueue:
            shelf.place_selected_source(record,'Music','next')
            enqueue.assert_called_once_with(record['device'],record['label'],'next')

    def test_audio_mixer_and_queue_switch_expand_tray(self):
        app=self.a
        audio=app.queue_deck.pages['Music']
        self.assertTrue(hasattr(audio,'audio_mode_buttons'))
        app.sidebar.set_open('Music',False)
        audio.show_audio_view('mixer');self.pump()
        self.assertTrue(app.sidebar.sections['Music']['open'])
        self.assertTrue(audio.audio_mixer.winfo_viewable())
        self.assertFalse(audio.future_body.winfo_ismapped())
        self.assertIn('soundtrack',audio.audio_mixer.rows)
        audio.show_audio_view('queue');self.pump()
        self.assertTrue(app.sidebar.sections['Music']['open'])
        self.assertFalse(audio.audio_mixer.winfo_ismapped())
        self.assertTrue(audio.radio_transport.winfo_ismapped())

    def test_mixer_height_can_expand_and_stays_within_preview(self):
        app=self.a
        audio=app.queue_deck.pages['Music']
        app.sidebar.set_open('A',True)
        audio.show_audio_view('mixer');self.pump()
        frame=app.sidebar.sections['Music']['frame']
        self.assertGreaterEqual(frame.winfo_height(),180)
        self.assertLessEqual(frame.winfo_rooty()+frame.winfo_height(),app.winfo_rooty()+app.winfo_height()+8)

if __name__=='__main__':unittest.main()

# Context menus deliberately distinguish sequenced *tracks* from timed live
# reaction cues; both share the music destination authority, not semantics.
class UX29DestinationWording(unittest.TestCase):
    def test_file_music_and_live_audio_have_distinct_destination_meaning(self):
        from ux29_browser_model import ROLE_NAMES,LIVE_ROLE_NAMES
        self.assertEqual(ROLE_NAMES['Music'],'Audio queue')
        self.assertEqual(LIVE_ROLE_NAMES['Music'],'Audio · timed reaction cue')
