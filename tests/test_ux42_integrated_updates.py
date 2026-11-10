"""UX42 integrated updater: real version ordering, one decision, safe publication."""
from __future__ import annotations
import importlib.util, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app_source'),str(ROOT/'tools'),str(ROOT/'scripts')]
from signed_updates import UpdateError, version_tuple
import update_ui

spec=importlib.util.spec_from_file_location('approve_release',ROOT/'scripts/approve_release.py')
pub=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)

class VersionTests(unittest.TestCase):
    def test_ux_series_is_numeric(self):
        self.assertLess(version_tuple('0.7.25-ux9'),version_tuple('0.7.25-ux10'))
        self.assertLess(version_tuple('0.7.25-ux41'),version_tuple('0.7.25-ux42'))
        self.assertLess(version_tuple('0.7.25-ux999'),version_tuple('0.7.26-ux1'))
        self.assertLess(version_tuple('0.7.25-ux42'),version_tuple('0.7.25'))
        self.assertEqual(version_tuple('0.7.25-ux42'),version_tuple('0.7.25-UX42'))
    def test_unsupported_suffix_is_rejected_not_ignored(self):
        with self.assertRaises(UpdateError):version_tuple('0.7.25-dirty')

class PublisherTests(unittest.TestCase):
    def test_clears_old_native_platform_ready_flags(self):
        existing={'schema':1,'product':'Neospector','downloads':{'linux-zip':{'ready':True},'linux':{'ready':True},'windows-x64':{'ready':True}}}
        record={'version':'0.7.26-ux43','archive':'Neospector_UX43.zip','sha256':'a'*64,'bytes':131}
        new=pub.prepare_catalogue(record,existing)
        self.assertEqual(new['version'],record['version'])
        self.assertTrue(new['downloads']['linux-zip']['ready'])
        self.assertFalse(new['downloads']['linux']['ready'])
        self.assertFalse(new['downloads']['windows-x64']['ready'])
    def test_preflight_rejects_same_version_without_remote_calls(self):
        existing={'schema':1,'product':'Neospector','version':'0.7.25-ux41','downloads':{}}
        signed={'version':'0.7.25-ux41','platform':'linux-x86_64'}
        with patch.object(pub,'verify_staged',return_value=signed), \
             patch.object(pub,'verify_envelope',return_value=signed), \
             patch('pathlib.Path.read_text',return_value='{}'):
            with self.assertRaises(pub.PublicationError):pub.release_plan('/dummy','/pub')
    def test_new_source_must_match_release(self):
        signed={'version':'0.7.26-ux43','platform':'linux-x86_64'}
        old={'version':'0.7.25-ux41'}
        with patch.object(pub,'verify_staged',return_value=signed),\
             patch.object(pub,'verify_envelope',return_value=old),\
             patch('pathlib.Path.read_text',return_value='{}'),\
             patch.object(pub,'read_source_version',return_value='0.7.25-ux41'):
            with self.assertRaises(pub.PublicationError):pub.release_plan('/dummy','/pub')

class OneClickControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        try:
            cls.root=tk.Tk();cls.root.withdraw()
        except tk.TclError as e:raise unittest.SkipTest('X server required') from e
    @classmethod
    def tearDownClass(cls):cls.root.destroy()
    def setUp(self):
        import tkinter as tk
        self.app=tk.Toplevel(self.root);self.app.withdraw()
        self.app.dirty=False;self.app.closing=False;self.app.rendering=False
        self.app.output_busy=False;self.app.capture_busy=False
        def close():self.app.closing=True
        self.app.close=close
        self.controller=update_ui.UpdateController(self.app)
        self.record={'version':'0.7.26-ux43','notes':'new','installers':{'linux-x64':{'file':'Neospector_0.7.26-ux43_linux-x64.deb','bytes':5,'sha256':'0'*64}}}
        self.controller.available=(self.record, {'payload':self.record,'signature':'abc'})
    def tearDown(self):
        if self.app.winfo_exists():self.app.destroy()
    def test_decline_never_starts_download_or_closes_instrument(self):
        self.controller.show()
        with patch.object(update_ui,'download_installer') as dl:
            self.assertTrue(self.controller.decline())
            dl.assert_not_called()
        self.assertFalse(self.app.closing)
    def test_dirty_state_has_no_side_effects(self):
        self.app.dirty=True
        with patch.object(update_ui,'updater_command',return_value=(['python3','helper.py'],'key')) as cmd:
            self.assertFalse(self.controller.accept())
            cmd.assert_not_called()
        self.assertIn('Save or discard',self.controller.status)
    def test_update_click_downloads_once_without_second_confirmation(self):
        # Dispatch on this fake root runs directly (no event loop for worker).
        self.controller._dispatch=lambda fn,*args:fn(*args)
        self.controller.show()
        with tempfile.TemporaryDirectory() as directory,\
             patch.dict(os.environ,{'XDG_CACHE_HOME':directory}),\
             patch.object(update_ui,'updater_command',return_value=(['python3','helper.py'],'key')),\
             patch.object(update_ui,'download_installer',return_value=Path(directory)/'file.deb') as dl,\
             patch.object(update_ui,'verify_installer',return_value=True),\
             patch.object(update_ui.subprocess,'Popen') as spawn,\
             patch.object(update_ui.threading,'Thread') as Thread:
            # Run the background worker to completion synchronously.
            Thread.side_effect=lambda target,**kw:MagicMock(start=target)
            self.assertTrue(self.controller.accept())
            self.assertTrue(self.app.closing)
            dl.assert_called_once()
            spawn.assert_called_once()
            self.assertIn('--wait-pid',spawn.call_args.args[0])
            self.assertEqual(self.controller.status,'Downloading and verifying 0.7.26-ux43…')
    def test_background_check_is_not_blocking_offline(self):
        self.controller._on_check_error('offline')
        self.assertFalse(self.controller.running)
        self.assertIsNone(self.controller.window)

if __name__=='__main__':unittest.main()
