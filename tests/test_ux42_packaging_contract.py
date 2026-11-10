"""New installers must have native trust paths and avoid runtime pip installs."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class PackagingTests(unittest.TestCase):
    def test_windows_signs_program_before_zip_and_inno_setup(self):
        content=(ROOT/'native/build_windows.ps1').read_text()
        self.assertIn('NEOSPECTOR_WINDOWS_CERT_THUMBPRINT',content)
        self.assertIn('Get-AuthenticodeSignature',content)
        self.assertIn('signtool',content.lower())
        self.assertIn('sign',content.lower())
        iss=(ROOT/'native/windows_installer.iss').read_text()
        self.assertIn('SignedUninstaller=yes',iss)
        self.assertIn('SignTool=neospector',iss)
    def test_macos_uses_notarytool_and_strict_gatekeeper_validation(self):
        s=(ROOT/'native/build_macos.sh').read_text()
        self.assertIn('NEOSPECTOR_APPLE_APPLICATION_ID',s)
        self.assertIn('NEOSPECTOR_APPLE_INSTALLER_ID',s)
        self.assertIn('NEOSPECTOR_APPLE_NOTARY_PROFILE',s)
        self.assertIn('spctl --assess',s)
        self.assertIn('pkgutil --check-signature',s)
    def test_linux_new_native_candidate_is_frozen_and_no_first_run_pip(self):
        s=(ROOT/'native/build_linux_frozen_deb.sh').read_text()
        self.assertIn('PyInstaller',s)
        self.assertIn('NeospectorUpdater',s)
        self.assertNotIn('cp "$ROOT/install_linux.py"',s)
        self.assertIn('verify_shipping.py',s)
        self.assertNotIn('exec python3 install_linux.py',s)
        self.assertNotIn('RUN_POC.sh',s)
        self.assertIn('dpkg-deb',s)
        self.assertIn('CANDIDATE',s)
    def test_release_workflow_not_automatically_publishing_unsigned(self):
        content=(ROOT/'.github/workflows/neospector-native-candidates.yml').read_text()
        self.assertNotIn('wrangler deploy',content)
        self.assertNotIn('scripts/publish_native_installer.py',content)
if __name__=='__main__':unittest.main()
