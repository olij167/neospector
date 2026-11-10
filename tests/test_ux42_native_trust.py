"""UX42 publication: user confirmation is never a substitute for platform trust."""
import importlib.util, pathlib, subprocess, sys, tempfile, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pub',ROOT/'scripts/publish_native_installer.py')
pub=importlib.util.module_from_spec(spec);spec.loader.exec_module(pub)
class NativeTrustGateTests(unittest.TestCase):
    def test_linux_owner_acceptance_has_no_windows_or_mac_bypass(self):
        with patch.object(pub,'inspect',return_value=(pathlib.Path('/tmp/test.exe'),None,'a'*64,{})):
            with patch.object(pub,'run') as runner:
                with self.assertRaises(pub.PublicationError):pub.publish('windows-x64','test.exe',tested=True)
                runner.assert_not_called()
    def test_macos_cannot_be_published_from_linux_by_signing_claim(self):
        with patch.object(pub,'inspect',return_value=(pathlib.Path('/tmp/test.dmg'),None,'b'*64,{})):
            with patch.object(pub,'run') as runner:
                with self.assertRaises(pub.PublicationError):pub.publish('macos-arm64','test.dmg',tested=True)
                runner.assert_not_called()
    def test_verifier_requires_native_operating_system(self):
        with patch.object(pub.sys,'platform','linux'):
            with self.assertRaises(pub.PublicationError):pub.verify_native_trust('windows-x64',pathlib.Path('/tmp/foo.exe'))
            with self.assertRaises(pub.PublicationError):pub.verify_native_trust('macos-arm64',pathlib.Path('/tmp/foo.dmg'))
    def test_windows_validator_rejects_missing_expected_publisher(self):
        with patch.object(pub.sys,'platform','win32'),patch.dict(pub.os.environ,{},clear=True):
            with self.assertRaises(pub.PublicationError):pub.verify_native_trust('windows-x64',pathlib.Path('foo.exe'))
    def test_macos_validator_rejects_missing_expected_team(self):
        with patch.object(pub.sys,'platform','darwin'),patch.dict(pub.os.environ,{},clear=True):
            with self.assertRaises(pub.PublicationError):pub.verify_native_trust('macos-arm64',pathlib.Path('foo.dmg'))
if __name__=='__main__':unittest.main()
