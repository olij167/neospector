"""UX16 acceptance: the right action is local to its source/parameter."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class LayoutPolicyTests(unittest.TestCase):
    def test_dense_pack_uses_vertical_space_for_wide_units(self):
        from ux16_layout import dense_pack
        result=dense_pack(3,[('a',2),('b',1),('c',2),('d',1)])
        assert result['a'][:2]==(0,0)
        assert result['b'][:2]==(2,0)
        # c may use horizontal or vertical orientation, but must never leave an interior hole.
        cells=set()
        for x,y,w,h in result.values():
            for yy in range(y,y+h):
                for xx in range(x,x+w):
                    self.assertNotIn((yy,xx),cells)
                    cells.add((yy,xx))
        last=max(y for y,x in cells)
        for y in range(last):
            for x in range(3):self.assertIn((y,x),cells)
    def test_semantic_parameter_kinds(self):
        from ux16_layout import parameter_kind
        self.assertEqual('bipolar',parameter_kind('hue',-180,180))
        self.assertEqual('steps',parameter_kind('columns',1,12))
        self.assertEqual('switch',parameter_kind('enabled',0,1))
        self.assertEqual('continuous',parameter_kind('blur',0,20))

class UX16WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from neospector_console import NeospectorApp
        cls.App=NeospectorApp
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'});self.env.start()
        self.app=self.App(test_mode=True);self.app.geometry('1500x950');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()
    def test_default_context_rack_is_closed_until_fx_requested(self):
        app=self.app
        self.assertFalse(app.shell.rack_open)
        for role in ('A','B'):
            page=app.queue_deck.pages[role]
            self.assertFalse(page.upcoming_visible)
            self.assertTrue(page.fx_button.winfo_exists())
        app.open_effects_context('A');app.update()
        self.assertTrue(app.shell.rack_open)
        self.assertIn('Visual A',app.deck.owner_title())
        app.toggle_effects_context('A');app.update()
        self.assertFalse(app.shell.rack_open)
    def test_current_rack_library_inserts_without_switching_sources(self):
        from effects_engine import make_effect
        from instrument_model import voice
        app=self.app;app.open_effects_context('B');app.toggle_module_library(True);app.update()
        self.assertTrue(app.insert_module_from_library(make_effect('blur'),'Blur',entry_type='Custom'))
        self.assertEqual(['blur'],[f.kind for f in voice(app.project,'B').rack])
        self.assertEqual([],voice(app.project,'A').rack)
        self.assertIn('1',app.queue_deck.pages['B'].fx_badge())
    def test_left_channel_label_excludes_music_and_audio_is_right(self):
        app=self.app
        labels=[w.cget('text') for w in app.queue_deck.panel_bar.winfo_children() if hasattr(w,'cget') and 'text' in w.keys()]
        self.assertIn('CHANNEL A',labels)
        self.assertNotIn('CHANNEL A / MUSIC',labels)
        self.assertIs(app.queue_deck.sound_host.master,app.media_tab)

    def test_project_browser_is_embedded_in_source_not_permanent_media_tray(self):
        app=self.app
        self.assertFalse(app.project_media_folder.winfo_viewable())
        self.assertTrue(app.queue_deck.pages['Music'].winfo_viewable())
        for role in ('A','B','Music'):
            page=app.queue_deck.pages[role]
            self.assertTrue(hasattr(page,'source_browser'))
            self.assertFalse(page.source_browser.winfo_viewable())
            page.toggle_browser();app.update()
            self.assertTrue(page.source_browser.winfo_viewable())
    def test_mixer_has_real_transition_controls(self):
        from ux16_transitions import configure_transition
        app=self.app
        self.assertTrue(hasattr(app.visual_mix,'transition_style'))
        configure_transition(app.project,'wipe_left')
        self.assertEqual('wipe_left',app.project.extra['ux16_transition']['kind'])
        self.assertEqual('crossfade',app.project.voice_mixer_mode)
    def test_audio_reactive_master_edits_real_mix_parameter(self):
        app=self.app
        app.visual_mix.set_reactive(True)
        self.assertEqual('react',app.project.voice_mix.mode)
        app.visual_mix.set_reaction_band('onset')
        self.assertEqual('onset',app.project.voice_mix.react_band)

class UX16SurfaceTests(unittest.TestCase):
    def setUp(self):
        import tempfile,os
        from unittest.mock import patch
        from neospector_console import NeospectorApp
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.tmp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'});self.env.start()
        self.app=NeospectorApp(test_mode=True);self.app.geometry('1540x950');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.tmp.cleanup()
    def test_rack_header_exposes_new_mutate_library_undo_redo(self):
        app=self.app;app.open_effects_context('Master');app.update()
        self.assertTrue(app.deck.randomise_button.winfo_viewable())
        self.assertTrue(app.deck.mutate_button.winfo_viewable())
        self.assertTrue(app.deck.library_button.winfo_viewable())
        self.assertTrue(app.deck.undo_button.winfo_viewable())
        self.assertTrue(app.deck.redo_button.winfo_viewable())
        self.assertFalse(app.deck.save_rack_button.winfo_viewable())
        self.assertFalse(app.deck.owner_buttons['A'].winfo_viewable())
    def test_repeated_clips_keep_independent_fx_racks(self):
        # Model ownership: one media source can be used in separate occurrences.
        from sequencer_model import Clip
        a=Clip('occurrence-a','asset-1');b=Clip('occurrence-b','asset-1')
        from effects_engine import make_effect
        a.rack.append(make_effect('blur'))
        self.assertEqual(['blur'],[fx.kind for fx in a.rack]);self.assertEqual([],b.rack)
    def test_master_transition_pixel_midpoint_and_glitch_are_real(self):
        from PIL import Image
        from ux16_transitions import configure_transition,composited_mix
        p=self.app.project
        a=Image.new('RGBA',(64,48),(255,0,0,255));b=Image.new('RGBA',(64,48),(0,0,255,255))
        configure_transition(p,'wipe_left');out=composited_mix(p,a,b,.5)
        self.assertNotEqual(out.getpixel((4,20)),out.getpixel((60,20)))
        configure_transition(p,'glitch_wipe');glitch=composited_mix(p,a,b,.5)
        self.assertNotEqual(glitch.tobytes(),a.tobytes());self.assertNotEqual(glitch.tobytes(),b.tobytes())

class UX16MediaBehaviourTests(unittest.TestCase):
    def setUp(self):
        from neospector_console import NeospectorApp
        self.profile=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.profile.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start();self.app=NeospectorApp(test_mode=True);self.app.geometry('1340x900+0+0');self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.profile.cleanup()
    def test_source_browser_imports_without_taking_and_filters_types(self):
        from sequencer_model import add_asset
        from instrument_model import voice
        app=self.app
        a=add_asset(app.project,path='',kind='colour',name='Test still',duration=4,metadata={'colour':'#d24564'})
        music=add_asset(app.project,path='',kind='audio',name='Test song',duration=4)
        visual=app.queue_deck.pages['B'].source_browser
        sound=app.queue_deck.pages['Music'].source_browser
        visual.refresh(True);sound.refresh(True)
        self.assertIn(a.id,[x.id for x in visual.filtered()]);self.assertNotIn(music.id,[x.id for x in visual.filtered()])
        self.assertIn(music.id,[x.id for x in sound.filtered()]);self.assertNotIn(a.id,[x.id for x in sound.filtered()])
        visual.items.selection_set(a.id);visual.append();app.update()
        self.assertEqual(1,len(voice(app.project,'B').clips))
        self.assertEqual(0,len(voice(app.project,'A').clips))
        self.assertFalse(app.shell.rack_open)
    def test_queue_reorder_is_possible_after_expanding_collapsed_list(self):
        from sequencer_model import add_asset,Clip
        from instrument_model import voice
        app=self.app;layer=voice(app.project,'A')
        a=add_asset(app.project,path='',kind='colour',name='Red',metadata={'colour':'#ff0000'})
        layer.clips=[Clip('one',a.id,start=0,duration=4),Clip('two',a.id,start=4,duration=4)]
        page=app.queue_deck.pages['A'];page.set_future(True);app.update();page.refresh(True);app.update()
        self.assertTrue(page.canvas.winfo_viewable())
        before=app.playhead
        page.selected='one';page.move_selected(1);app.update()
        self.assertEqual('one',voice(app.project,'A').clips[-1].id)
        self.assertEqual(before,app.playhead)
