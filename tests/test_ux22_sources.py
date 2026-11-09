"""UX22 contract: one media catalogue, compact contextual source panes and stable mixer control."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class SourceEligibility(unittest.TestCase):
    def test_media_types_route_only_to_compatible_queues(self):
        from ux22_project_browser import eligible_destinations
        from types import SimpleNamespace
        def asset(kind,**meta):return SimpleNamespace(kind=kind,metadata=meta)
        self.assertEqual(('A','B'),eligible_destinations(asset('image')))
        self.assertEqual(('A','B'),eligible_destinations(asset('video',has_audio=False)))
        self.assertEqual(('A','B','Music'),eligible_destinations(asset('video',has_audio=True)))
        self.assertEqual(('Music',),eligible_destinations(asset('audio')))
        self.assertEqual((),eligible_destinations(asset('camera')))

class UX22Sources(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True);self.app.geometry('1500x900+0+0');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()
    def test_source_labels_camera_buttons_secondary(self):
        a=self.app
        self.assertFalse(a.sources_heading.winfo_viewable())
        self.assertIn('Channel A',a.source_tab_buttons['A'].cget('text'))
        self.assertIn('Channel B',a.source_tab_buttons['B'].cget('text'))
        self.assertIn('Audio Channel',a.source_tab_buttons['Music'].cget('text'))
        self.assertLess(a.preview_camera.winfo_width(),a.source_tab_buttons['A'].winfo_width())
    def test_one_shared_browser_and_inline_source_configuration(self):
        a=self.app
        self.assertTrue(hasattr(a.sidebar,'shared_browser'))
        a.sidebar.set_open('A',True);a.update()
        p=a.queue_deck.pages['A']
        self.assertTrue(hasattr(p,'inline_source'))
        p.show_inline_source('screen');a.update()
        self.assertTrue(p.inline_source.winfo_viewable())
        self.assertFalse(p.source_browser.winfo_viewable())
        p.show_inline_source('camera');a.update()
        self.assertIn('Camera',p.inline_source.mode.get())
        p.show_inline_source('queue');a.update()
        self.assertFalse(p.inline_source.winfo_viewable())
    def test_visual_panels_compact_and_expand_with_content(self):
        a=self.app;a.sidebar.set_open('A',True);a.update()
        self.assertLess(a.sidebar.sections['A']['frame'].winfo_height(),400)
        a.sidebar.set_open('B',True);a.update()
        self.assertLess(a.sidebar.sections['B']['frame'].winfo_height(),400)
    def test_optional_queues_do_not_reserve_full_height_sidebar(self):
        a=self.app;a.sidebar.set_open('A',True);a.update()
        frame=a.frames['panel.library'] if hasattr(a,'frames') else a.shell.frames['panel.library']
        self.assertLess(frame.winfo_height(),400)
        self.assertGreater(a.viewport_frame.winfo_width(),1000)
        a.sidebar.set_open('B',True);a.sidebar.set_open('Music',True);a.update()
        self.assertGreater(frame.winfo_height(),600)
    def test_mixer_dropdowns_and_depth_does_not_refresh_while_dragging(self):
        a=self.app;m=a.visual_mix
        self.assertTrue(hasattr(m,'previous_band'))
        self.assertTrue(hasattr(m,'next_band'))
        self.assertTrue(hasattr(m,'open_transition_menu'))
        self.assertTrue(hasattr(m,'open_band_menu'))
        m.set_reactive(True);m.react_depth.set(.34);m._depth_dragging=True
        m.refresh()
        self.assertAlmostEqual(.34,m.react_depth.get(),places=3)
        m._depth_dragging=False
    def test_shared_browser_media_selection_is_inert_and_placement_uses_engine(self):
        from sequencer_model import add_asset
        a=self.app
        x=add_asset(a.project,path='/tmp/silent.png',kind='image',name='Still')
        y=add_asset(a.project,path='/tmp/with-audio.mp4',kind='video',name='Video + Sound',metadata={'has_audio':True})
        z=add_asset(a.project,path='/tmp/song.wav',kind='audio',name='Song')
        browser=a.sidebar.shared_browser
        a.sidebar.open_browser('B');browser.refresh(force=True)
        browser.items.selection_set(x.id);browser._selection_changed()
        self.assertEqual(('A','B'),browser.allowed())
        self.assertEqual([],a.project.layers[0].clips)
        self.assertEqual('B',browser.destination)
        browser.place('queue')
        from instrument_model import voice
        self.assertTrue(any(c.asset_id==x.id for c in voice(a.project,'B').clips))
        browser.items.selection_set(y.id);browser._selection_changed()
        self.assertEqual(('A','B','Music'),browser.allowed())
        browser.items.selection_set(z.id);browser._selection_changed()
        self.assertEqual(('Music',),browser.allowed())
        browser.items.selection_set(x.id,z.id);browser._selection_changed()
        self.assertEqual((),browser.allowed())
    def test_rack_side_swap_not_visible(self):
        a=self.app;a.open_effects_context('Master');a.update()
        self.assertFalse(a.rack_flip_control.winfo_viewable())
