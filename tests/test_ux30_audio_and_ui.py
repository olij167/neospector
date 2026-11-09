"""UX30 focused seams: missing Linux audio utilities, fader source identity, UI contracts."""
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from system_audio import pulse_choices

class AudioDiscoveryUX30(unittest.TestCase):
    def test_spotify_name_is_discoverable_from_pulse_stream(self):
        items=pulse_choices([], [{'index':1,'name':'out','monitor_source_name':'out.monitor'}],
            [{'index':16,'sink':1,'properties':{'application.name':'Spotify','application.process.id':'123','media.name':'music'}}],parec_available=True)
        apps=[s for s in items if s['kind']=='application']
        self.assertEqual(len(apps),1);self.assertIn('Spotify',apps[0]['label'])
    def test_pipewire_fallback_names_playing_apps_without_claiming_capture(self):
        from system_audio import pipewire_app_choices
        nodes=[{'id':123,'type':'PipeWire:Interface:Node','info':{'props':{'media.class':'Stream/Output/Audio','application.name':'Spotify','media.name':'Spotify Music'}}},
               {'id':124,'type':'PipeWire:Interface:Node','info':{'props':{'media.class':'Audio/Sink','node.name':'alsa.output'}}}]
        result=pipewire_app_choices(nodes)
        self.assertEqual(len(result),1);self.assertEqual(result[0]['kind'],'application')
        self.assertFalse(result[0]['capture_available']);self.assertIn('Spotify',result[0]['label'])
    def test_unsupported_discovered_app_cannot_be_queued(self):
        from ux29_browser_model import source_destinations
        self.assertEqual(source_destinations({'kind':'application','capture_available':False}),())
        self.assertEqual(source_destinations({'kind':'application','capture_available':True}),('Music',))

class MixerUX30(unittest.TestCase):
    def test_mic_route_always_visible_even_without_discovery(self):
        from sound_panel import source_order
        from sound_routes import source_id
        class App:
            last_microphone_device='default'
        ids,sources=source_order(App(),{'soundtrack':{},'voice:A':{}},[],False)
        self.assertIn(source_id('default'),ids)
        self.assertIn(source_id('default'),sources)
    def test_compact_vertical_mixer_is_real_control(self):
        from sound_panel import DeskFaderMixer, SourceMixer
        self.assertTrue(issubclass(DeskFaderMixer,SourceMixer))

class LibraryUX30(unittest.TestCase):
    def test_library_exposes_close_group_and_variation_controls(self):
        from module_library import ModuleLibraryPanel
        self.assertTrue(callable(getattr(ModuleLibraryPanel,'open_group_tools',None)))
        self.assertTrue(callable(getattr(ModuleLibraryPanel,'open_variation_tools',None)))

if __name__=='__main__':unittest.main()
