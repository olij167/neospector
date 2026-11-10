import importlib.util, pathlib, tempfile, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('nativepub',ROOT/'scripts/publish_native_installer.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class NativePublicationTests(unittest.TestCase):
    def test_unsupported_alias_fails_closed(self):
        with self.assertRaises(mod.PublicationError):mod.inspect('macos-other','missing')
    def test_missing_installer_fails_closed(self):
        with self.assertRaises(mod.PublicationError):mod.inspect('linux','/nonexistent/Neospector_0.7.25-ux41_linux-x64.deb')
    def test_wrong_filename_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'installer.exe';path.write_bytes(b'test')
            with self.assertRaises(mod.PublicationError):mod.inspect('windows-x64',path)
    def test_unsigned_mac_fails_closed_before_any_upload(self):
        with patch.object(mod,'inspect',return_value=(pathlib.Path('/tmp/test.pkg'),None,'abc',{})),patch.object(mod,'run') as call:
            with self.assertRaisesRegex(mod.PublicationError,'macOS signing'):
                mod.publish('macos-arm64-pkg','test.pkg',tested=True)
            call.assert_not_called()
    def test_unaccepted_linux_fails_closed_before_any_upload(self):
        with patch.object(mod,'inspect',return_value=(pathlib.Path('/tmp/test.deb'),None,'abc',{})),patch.object(mod,'run') as call:
            with self.assertRaisesRegex(mod.PublicationError,'acceptance'):
                mod.publish('linux','test.deb',tested=False)
            call.assert_not_called()
if __name__=='__main__':unittest.main()
