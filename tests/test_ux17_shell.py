"""UX17 acceptance: preview-first shell, right source stack, direct FX ownership."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class UX17Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True)
        self.app.geometry('1340x900+0+0');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()
    def test_preview_is_main_field_with_one_right_sidebar(self):
        a=self.app
        self.assertFalse(a.shell.left_open)
        self.assertFalse(a.shell.frames['panel.queues'].winfo_viewable())
        self.assertFalse(a.sidebar.sections['Music']['open'])
        self.assertFalse(a.sidebar.sections['A']['open'])
        self.assertFalse(a.sidebar.sections['B']['open'])
        self.assertTrue(a.shell.frames['panel.library'].winfo_viewable())
        self.assertLessEqual(a.sidebar.winfo_width(),60)
    def test_right_sections_toggle_independently_and_share_resizable_pane(self):
        s=self.app.sidebar
        s.toggle('A');s.toggle('B');s.toggle('Music');self.app.update()
        self.assertEqual(('A','B','Music'),s.open_roles())
        self.assertEqual(3,len(s.pane.panes()))
        s.toggle('A');self.app.update()
        self.assertEqual(('B','Music'),s.open_roles())
        self.assertTrue(s.sections['Music']['open'])
    def test_preview_header_has_live_camera_and_microphone(self):
        a=self.app
        self.assertTrue(a.preview_camera.winfo_viewable())
        self.assertTrue(a.preview_microphone.winfo_viewable())
        self.assertFalse(a.queue_deck.pages['A'].camera_button.winfo_viewable())
        self.assertFalse(a.queue_deck.pages['Music'].mic_button.winfo_viewable())
    def test_master_fx_navigator_opens_context_and_toggles_processing(self):
        from effects_engine import make_effect
        a=self.app
        self.assertTrue(a.master_fx_button.winfo_viewable())
        a.project.master_rack.append(make_effect('blur'))
        a.show_master_fx();a.update()
        self.assertTrue(a.master_fx_tray.winfo_viewable())
        self.assertEqual(1,a.effects_count('Master'))
        a.fx_nav_target('Master');a.update()
        self.assertTrue(a.shell.rack_open)
        self.assertEqual('Master',a.deck.scope.get())
    def test_effect_map_lists_active_clip_rack_and_bypass_is_reversible(self):
        from effects_engine import make_effect
        from instrument_model import voice
        from sequencer_model import Clip
        a=self.app
        clip=Clip('clip-ux17','media-ux17')
        clip.rack.append(make_effect('blur'))
        voice(a.project,'B').clips.append(clip)
        a.queue_deck.pages['B'].current_id=clip.id
        a.refresh_fx_map()
        self.assertIn('B · CLIP',a.fx_nav_clip_rows)
        a.fx_nav_toggle('B')
        self.assertTrue(voice(a.project,'B').extra['rack_bypassed'])
        a.undo();self.assertFalse(voice(a.project,'B').extra.get('rack_bypassed',False))

    def test_queue_reorder_after_opening_right_channel(self):
        from sequencer_model import add_asset,Clip
        from instrument_model import voice
        a=self.app;a.sidebar.set_open('B',True)
        layer=voice(a.project,'B')
        asset=add_asset(a.project,path='',kind='colour',name='Test',metadata={'colour':'#aa5599'})
        layer.clips=[Clip('first',asset.id,start=0,duration=4),Clip('second',asset.id,start=4,duration=4)]
        page=a.queue_deck.pages['B'];page.set_future(True)
        a.update();page.refresh(True);a.update()
        self.assertTrue(page.canvas.winfo_viewable())
        before=a.playhead;page.selected='first';page.move_selected(1);a.update()
        self.assertEqual('first',voice(a.project,'B').clips[-1].id)
        self.assertEqual(before,a.playhead)

    def test_radio_is_optional_but_remains_a_usable_audio_browser(self):
        a=self.app;a.sidebar.set_open('Music',True);a.update()
        music=a.queue_deck.pages['Music']
        self.assertTrue(music.current_canvas.winfo_viewable())
        self.assertTrue(music.compact_toolbar.winfo_viewable())
        music.toggle_music_files();a.update()
        self.assertTrue(music.source_browser.winfo_viewable())
        self.assertFalse(a.shell.frames['panel.queues'].winfo_viewable())

    def test_fx_owner_is_visible_from_tab_without_opening_queue(self):
        from instrument_model import voice
        from effects_engine import make_effect
        a=self.app
        voice(a.project,'A').rack.append(make_effect('blur'))
        a.refresh_effects_badges();a.update()
        self.assertIn('•',a.sidebar.sections['A']['button'].cget('text'))
        a.open_effects_context('A');a.update()
        self.assertEqual('A',a.sidebar.selected)
        self.assertFalse(a.sidebar.sections['A']['open'])

    def test_three_parameter_pedal_keeps_all_actions_visible(self):
        from neospector_catalog import build_group
        from pedal_face_layout import FACE_HEIGHT
        a=self.app;a.open_effects_context('Master')
        from effects_engine import make_effect
        a.sidebar.set_open('A',True);a.sidebar.set_open('B',True)
        a.geometry('1500x900+0+0');a.update()
        fx=build_group('CCD Afterglow')
        a.project.master_rack.extend([build_group('Acid Print'),make_effect('blur'),fx])
        a.deck.refresh(True);a.update()
        cell=a.deck.selected_cell();shell=cell.card_parts[fx.id][0]
        self.assertLessEqual(FACE_HEIGHT,186)
        self.assertGreaterEqual(shell.footer.winfo_rooty(),shell.winfo_rooty())
        self.assertLessEqual(shell.footer.winfo_rooty()+shell.footer.winfo_height(),
                             shell.winfo_rooty()+shell.winfo_height()-2)
        for control in (cell.card_controls[fx.id]['delete'],cell.card_controls[fx.id]['duplicate']):
            self.assertTrue(control.winfo_viewable())
            self.assertLessEqual(control.winfo_rooty()+control.winfo_height(),
                                 shell.winfo_rooty()+shell.winfo_height()-3)

    def test_source_buttons_fit_in_expanded_sidebar(self):
        a=self.app
        a.sidebar.set_open('A',True)
        a.sidebar.set_open('B',True)
        for width,height in ((1500,900),(1024,768)):
            a.geometry(f'{width}x{height}+0+0');a.update()
            for role in ('A','B'):
                page=a.queue_deck.pages[role]
                button=page.source_actions['files']
                self.assertTrue(button.winfo_viewable())
                self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),
                                     a.sidebar.sections[role]['frame'].winfo_rootx()+a.sidebar.sections[role]['frame'].winfo_width()-1)

    def test_module_faces_are_compact_and_tooltip_callback_accepts_events(self):
        from pedal_face_layout import FACE_HEIGHT
        from ui_chrome import ToolTip
        self.assertLessEqual(FACE_HEIGHT,186)
        a=self.app
        tip=ToolTip(a.preview_camera,'Camera',a.ui_chrome)
        tip._cancel(None)
        tip._force_hide(None)
