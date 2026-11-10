"""Regression for PyInstaller stdlib archive vs developer ZIP protection.

These checks operate on a real, tiny dpkg-deb test package. They do not
build Neospector or require NumPy, Qt, Tk, external network or a display.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from verify_shipping import ShippingError,verify_deb


@unittest.skipUnless(shutil.which('dpkg-deb'), 'dpkg-deb unavailable')
class ShippingAuditTests(unittest.TestCase):
    def build(self,extras=(),symlink_runtime=False):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root=Path(t.name)/'pkg'
        control=root/'DEBIAN/control'
        control.parent.mkdir(parents=True)
        control.write_text('Package: neospector-test\nVersion: 1.0.0\nArchitecture: all\nMaintainer: Test <test@example.invalid>\nDescription: Regression fixture\n')
        mandatory=['opt/neospector/Neospector','opt/neospector/NeospectorUpdater',
                   'opt/neospector/updates/public.pem']
        for rel in [*mandatory,*extras]:
            f=root/rel
            f.parent.mkdir(parents=True,exist_ok=True)
            f.write_bytes(b'test fixture')
        if symlink_runtime:
            f=root/'opt/neospector/_internal/base_library.zip'
            f.parent.mkdir(parents=True,exist_ok=True)
            f.symlink_to('/tmp/neospector-malicious.zip')
        target=Path(t.name)/'fixture.deb'
        p=subprocess.run(['dpkg-deb','--root-owner-group','--build',str(root),str(target)],capture_output=True,text=True)
        if p.returncode:raise RuntimeError(p.stderr)
        return target

    def test_exact_pyinstaller_runtime_zip_allowed(self):
        deb=self.build(['opt/neospector/_internal/base_library.zip'])
        self.assertGreaterEqual(verify_deb(deb),4)

    def test_same_name_in_wrong_directory_is_rejected(self):
        deb=self.build(['opt/neospector/base_library.zip'])
        with self.assertRaisesRegex(ShippingError,'Developer file'):
            verify_deb(deb)

    def test_other_zip_in_frozen_runtime_is_rejected(self):
        deb=self.build(['opt/neospector/_internal/app_source.zip'])
        with self.assertRaisesRegex(ShippingError,'Developer file'):
            verify_deb(deb)

    def test_source_and_backups_rejected(self):
        for rel in ['opt/neospector/source.zip',
                    'opt/neospector/tests/test_app.py',
                    'opt/neospector/.git/config',
                    'opt/neospector/README.md',
                    'opt/neospector/__pycache__/cached.pyc']:
            with self.subTest(rel=rel):
                with self.assertRaises(ShippingError):verify_deb(self.build([rel]))

    def test_symlink_cannot_impersonate_stdlib_zip(self):
        with self.assertRaisesRegex(ShippingError,'Developer file'):
            verify_deb(self.build(symlink_runtime=True))

    def test_missing_required_executable_is_rejected(self):
        # Deliberately omit the updater from the DEB for this fixture.
        # The method below builds a minimal package with just the app and key.
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        root=Path(t.name)/'pkg';(root/'DEBIAN').mkdir(parents=True)
        (root/'DEBIAN/control').write_text('Package: neospector-test\nVersion: 1.0.0\nArchitecture: all\nMaintainer: Test <test@example.invalid>\nDescription: Regression fixture\n')
        for rel in ['opt/neospector/Neospector','opt/neospector/updates/public.pem']:
            f=root/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b'x')
        target=Path(t.name)/'missing.deb'
        subprocess.run(['dpkg-deb','--root-owner-group','--build',str(root),str(target)],check=True,capture_output=True)
        with self.assertRaisesRegex(ShippingError,'Native updater missing'):verify_deb(target)


if __name__=='__main__':unittest.main()
