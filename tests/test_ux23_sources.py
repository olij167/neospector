"""UX23 requirements: one source shelf, real live cues, predictable popup lifecycle."""
import os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class SourceModel(unittest.TestCase):
    def test_live_destination_matrix(self):
        from ux23_live_placement import eligible_source_roles
        self.assertEqual(('A','B'), eligible_source_roles('camera'))
        self.assertEqual(('A','B'), eligible_source_roles('window'))
        self.assertEqual(('Music',),eligible_source_roles('microphone'))
        self.assertEqual(('Music',),eligible_source_roles('application'))
    def test_audio_cues_have_real_positions_and_are_inert_until_due(self):
        from ux23_live_placement import AudioCueQueue
        p=SimpleNamespace(id='project',extra={'sound_events':[{'start':0.,'duration':10.}]})
        a=SimpleNamespace(project=p,playing=True,reviewing=False,playhead=4.,programme_time=lambda:4.,started=[])
        a.start_sound_source=lambda device,label,react_only=True:a.started.append((device,label,react_only))
        a.transaction=lambda label,fn:fn()
        q=AudioCueQueue(a)
        cue=q.enqueue('default','Microphone','next')
        self.assertEqual(10.,cue['start']);self.assertFalse(a.started)
        q.step();self.assertFalse(a.started)
        a.programme_time=lambda:10.1
        q.step();self.assertEqual([('default','Microphone',True)],a.started)
        q.step();self.assertEqual(1,len(a.started))
    def test_visual_live_source_is_not_inserted_until_capture_ready(self):
        from ux23_live_placement import LiveVisualPlacement
        p=SimpleNamespace(id='project',assets={},layers=[SimpleNamespace(extra={'voice':'A'},locked=False)])
        pending=[];calls=[]
        a=SimpleNamespace(project=p,closing=False,reviewing=False,camera_task=lambda label,fn:pending.append(fn),
                          update_status=lambda msg:calls.append(('status',msg)), events=SimpleNamespace(put=lambda item:calls.append(item)),
                          live=SimpleNamespace(acquire_camera=lambda device:SimpleNamespace(state='live',error='')))
        task=LiveVisualPlacement(a)
        task.place('A','default','camera','next')
        self.assertFalse(p.assets)
        self.assertEqual(1,len(pending))

class UX23Tk(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.temp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'});self.env.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True);self.app.geometry('1440x900+0+0');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.temp.cleanup()
    def test_shared_shelf_has_source_modes_and_is_not_in_each_channel(self):
        a=self.app
        self.assertTrue(hasattr(a.sidebar,'source_shelf'))
        a.sidebar.open_browser('A','camera');a.update()
        self.assertEqual('camera',a.sidebar.source_shelf.mode)
        self.assertFalse(a.queue_deck.pages['A'].inline_source.winfo_viewable())
        self.assertTrue(a.sidebar.source_shelf.winfo_viewable())
        self.assertTrue(a.sidebar._browser_open)
        self.assertNotIn('until Use',a.sidebar.source_shelf.inline.status.get())
    def test_empty_visual_player_has_one_source_entry_and_not_legacy_source_tabs(self):
        a=self.app;a.sidebar.set_open('B',True);a.update()
        p=a.queue_deck.pages['B']
        self.assertFalse(p.visual_source_bar.winfo_viewable())
        self.assertIn('Add',p.browse_button.cget('text'))
    def test_native_mix_menu_is_managed_with_outside_click(self):
        a=self.app;m=a.visual_mix
        menu=m.open_transition_menu();a.update()
        self.assertIsNotNone(getattr(a,'_posted_native_menu',None))
        a.popup_menu if hasattr(a,'popup_menu') else None
        a._posted_native_menu['dismiss']();a.update()
        self.assertIsNone(getattr(a,'_posted_native_menu',None))
    def test_shared_source_actions_and_tabs_fit_at_small_width(self):
        a=self.app;a.geometry('1024x768+0+0');a.update()
        a.sidebar.open_browser('A','files');a.update()
        for mode in ('camera','screen','audio'):
            a.sidebar.source_shelf.show(mode);a.update()
            shelf=a.sidebar.source_shelf
            for b in shelf.tabs.values():
                self.assertTrue(b.winfo_viewable(),(mode,b.cget('text')))
                self.assertLessEqual(b.winfo_rootx()+b.winfo_width(),shelf.winfo_rootx()+shelf.winfo_width()+2)
            self.assertTrue(shelf.action_bar.winfo_viewable(),mode)
            footer=shelf.placement.winfo_children()[-1]
            self.assertLessEqual(footer.winfo_rooty()+footer.winfo_height(),
                                 shelf.winfo_rooty()+shelf.winfo_height()+2,(mode,'footer clipped'))
            self.assertLessEqual(shelf.action_bar.winfo_rooty()+shelf.action_bar.winfo_height(),
                                 shelf.winfo_rooty()+shelf.winfo_height()+2,mode)
    def test_outside_click_dismisses_transition_menu(self):
        a=self.app;a.visual_mix.open_transition_menu();a.update()
        self.assertIsNotNone(getattr(a,'_posted_native_menu',None))
        a.viewport.canvas.event_generate('<ButtonPress-1>',x=5,y=5);a.update()
        self.assertIsNone(getattr(a,'_posted_native_menu',None))
    def test_expanded_crop_controls_and_actions_fit_at_small_size(self):
        a=self.app;a.geometry('1024x768+0+0');a.update()
        a.sidebar.open_browser('B','screen');a.update()
        shelf=a.sidebar.source_shelf;shelf.inline.toggle_crop();a.update()
        self.assertTrue(shelf.inline.crop_canvas.winfo_viewable())
        self.assertTrue(shelf.action_bar.winfo_viewable())
        self.assertLessEqual(shelf.action_bar.winfo_rooty()+shelf.action_bar.winfo_height(),
                             shelf.winfo_rooty()+shelf.winfo_height()+2)
    def test_queued_live_visual_item_does_not_show_seek_transport(self):
        from sequencer_model import add_asset
        from queue_model import append_assets
        from instrument_model import voice
        a=self.app
        asset=add_asset(a.project,path='live:camera',kind='camera',name='Live camera',metadata={'device':'default'})
        append_assets(a.project,voice(a.project,'A').id,[asset.id])
        a.sidebar.set_open('A',True);a.queue_deck.refresh(True);a.update()
        page=a.queue_deck.pages['A']
        self.assertFalse(page.compact_toolbar.winfo_viewable())
    def test_reaction_depth_release_commits_without_snapback(self):
        m=self.app.visual_mix;m.set_reactive(True);self.app.update()
        m._depth_dragging=True;m.react_depth.set(.42)
        m.refresh();m.finish_depth_drag();self.app.update()
        self.assertAlmostEqual(.42,abs(self.app.project.voice_mix.react_amount),places=2)
    def test_release_live_camera_when_last_queued_item_is_removed(self):
        from sequencer_model import add_asset
        from queue_model import append_assets
        from instrument_model import voice
        a=self.app
        asset=add_asset(a.project,path='live:camera',kind='camera',name='Camera cue',metadata={'device':'default'})
        clip=append_assets(a.project,voice(a.project,'A').id,[asset.id])[0]
        count=[];a.release_unassigned_cameras=lambda:count.append(True)
        a.queue_remove('A',clip.id)
        self.assertEqual([True],count)
    def test_reaction_depth_control_remains_mapped_during_refresh(self):
        m=self.app.visual_mix;m.set_reactive(True);self.app.update()
        self.assertTrue(m.depth_slider.winfo_ismapped())
        m._depth_dragging=True;m.react_depth.set(.31)
        for _ in range(5):m.refresh()
        self.assertAlmostEqual(.31,m.react_depth.get(),places=2)
        self.assertTrue(m.depth_slider.winfo_ismapped())
        m._depth_dragging=False

if __name__=='__main__':unittest.main()
