"""UX10 acceptance contracts: two permanent queues, non-destructive media, right builder."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from neospector_console import NeospectorApp
from instrument_model import voice
from sequencer_model import add_asset
from visual_channels import channels

class UX10WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start();self.app=NeospectorApp(test_mode=True)
        self.app.geometry('1580x950');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()

    def test_one_permanent_two_channel_media_desk(self):
        a=self.app
        self.assertEqual(['A','B','Music'],list(a.queue_deck.pages))
        self.assertEqual(['A','B'],[l.extra['voice'] for l in channels(a.project)])
        self.assertTrue(all(a.queue_deck.pages[n].winfo_viewable() for n in ('A','B','Music')))
        self.assertEqual(a.queue_deck.pages['A'].winfo_y(),a.queue_deck.pages['B'].winfo_y())
        self.assertGreater(a.project_media_folder.winfo_height(),180)
        self.assertTrue(a.project_media_folder.remove_button.winfo_viewable())
        self.assertFalse(a.input_bar.winfo_viewable())
        self.assertFalse(a.play_button.winfo_viewable())
        self.assertTrue(a.save_project_button.winfo_viewable())

    def test_mix_is_complementary_and_one_undo(self):
        a=self.app
        self.assertAlmostEqual(.5,a.project.voice_mix.value)
        self.assertAlmostEqual(1.,voice(a.project,'A').opacity.value)
        self.assertAlmostEqual(1.,voice(a.project,'B').opacity.value)
        count=len(a.history.undo_stack)
        a.visual_mix.begin();a.visual_mix.write(.8);a.visual_mix.finish();a.update()
        self.assertAlmostEqual(.8,a.project.voice_mix.value)
        self.assertAlmostEqual(1.,voice(a.project,'A').opacity.value)
        self.assertEqual(count+1,len(a.history.undo_stack))
        a.undo();a.update();self.assertAlmostEqual(.5,a.project.voice_mix.value)

    def test_library_is_on_right_and_context_does_not_take_live(self):
        a=self.app;before=len(a.history.undo_stack)
        self.assertFalse(a.shell.frames['panel.library'].winfo_viewable())
        a.show_module_library();a.update()
        self.assertTrue(a.module_library.winfo_viewable())
        self.assertGreater(a.shell.frames['panel.library'].winfo_x(),a.shell.frames['panel.rack'].winfo_x())
        self.assertEqual(before,len(a.history.undo_stack))
        a.shell.collapse('Library');a.update()
        self.assertFalse(a.module_library.winfo_viewable())
        self.assertTrue(a.deck.winfo_viewable())

    def test_right_group_builder_returns_to_library(self):
        a=self.app;a.show_module_library()
        for kind in ('blur','brightness'):
            entry=next(r for r in a.module_library._rows.values() if r['type']=='Base' and r['key']==kind)
            self.assertTrue(a.module_library.add_row(entry))
        cell=a.deck.selected_cell();cell.selected_fx={f.id for f in a.project.master_rack}
        self.assertTrue(a.deck.group_selected());a.update()
        self.assertEqual(1,len(a.project.master_rack))
        self.assertIsNotNone(a.module_builder)
        self.assertTrue(a.module_builder.winfo_viewable())
        self.assertFalse(a.module_library.winfo_viewable())
        a.close_module_builder();a.update()
        self.assertTrue(a.module_library.winfo_viewable())

    def test_project_media_folder_is_safe_and_queue_explicit(self):
        a=self.app
        source=Path(self.tmp.name)/'an-original.png';source.write_bytes(b'untouched')
        image=add_asset(a.project,path=str(source),kind='image',name='an-original.png',duration=10)
        a.refresh_library();a.update()
        browser=a.project_media_folder.browser
        self.assertIn(image.id,browser.model.items)
        browser.selection_set(image.id)
        a.project_media_folder.assign('A');a.update()
        self.assertEqual(1,len(voice(a.project,'A').clips))
        self.assertEqual(0,len(voice(a.project,'B').clips))
        with patch('ux10_project_media.messagebox.showwarning') as blocked:
            a.project_media_folder.remove();blocked.assert_called_once()
        self.assertTrue(source.is_file())

    def test_new_visual_crossfader_is_true_linear_rgb_mix(self):
        from PIL import Image
        from programme_renderer import ProgrammeRenderer
        from queue_model import append_assets
        from sequencer_model import add_asset
        a=self.app
        for role,colour in (('A','red'),('B','blue')):
            path=Path(self.tmp.name)/('test-'+role+'.png')
            Image.new('RGB',(40,40),colour).save(path)
            media=add_asset(a.project,path=str(path),kind='image',name=role,duration=5,width=40,height=40)
            append_assets(a.project,voice(a.project,role).id,[media.id])
        renderer=ProgrammeRenderer()
        try:
            for mix,expected in ((0,(255,0,0)),(.5,(128,0,128)),(1,(0,0,255))):
                a.project.voice_mix.value=mix
                image=renderer.render(a.project,.5,(100,100))
                self.assertEqual(expected,image.getpixel((50,50))[:3])
        finally:renderer.close()

    def test_visual_pause_freezes_its_own_clock(self):
        from queue_model import mode_at,queue_position
        from sequencer_model import add_asset
        from queue_model import append_assets,materialize
        a=self.app;layer=voice(a.project,'A')
        item=add_asset(a.project,path='',name='Still',kind='colour',duration=12,metadata={'colour':'#cc2266'})
        append_assets(a.project,layer.id,[item.id]);a.set_playhead(2)
        a.queue_deck.pages['A'].toggle_channel_play();a.update()
        self.assertEqual('pause',mode_at(voice(a.project,'A'),2)['mode'])
        self.assertAlmostEqual(2.,queue_position(voice(a.project,'A'),8))
        self.assertNotEqual('pause',mode_at(voice(a.project,'B'),2)['mode'])
        frozen=materialize(a.project,3,5)
        self.assertEqual(0.,voice(frozen,'A').clips[0].playback_rate)
        a.undo();a.update()
        self.assertEqual('queue',mode_at(voice(a.project,'A'),2)['mode'])

    def test_short_window_keeps_queue_and_rack_operable(self):
        a=self.app;a.geometry('1024x768');a.update()
        for r in ('A','B'):
            self.assertGreater(a.queue_deck.pages[r].winfo_height(),175)
            self.assertTrue(a.queue_deck.pages[r].winfo_viewable())
        self.assertGreater(a.deck.winfo_height(),250)
        a.show_module_library();a.update()
        self.assertTrue(a.module_library.winfo_viewable())

    def test_import_button_does_not_invoke_legacy_library(self):
        with patch('immediate_actions.filedialog.askopenfilenames',return_value=()) as chooser:
            self.app.add_media();chooser.assert_called_once()
        self.assertFalse(self.app.shell.frames['panel.library'].winfo_viewable())

if __name__=='__main__':unittest.main()
