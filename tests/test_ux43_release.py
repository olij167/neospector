"""UX43: signed native installers, owner gating and no source ZIP publication."""
from __future__ import annotations
import json, hashlib, subprocess, tempfile, sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app_source'),str(ROOT/'scripts')]
from installer_updates import platform_id,validate_release,sign_release,verify_release,verify_installer,installer_url
from signed_updates import UpdateError
import owner_release

PAYLOAD={'schema':2,'product':'Neospector','channel':'stable','version':'0.7.26-ux43',
  'title':'Native Installer Updates','notes':'New release notes.','date':'2026-11-10',
  'commit':'a'*40,'installers':{'linux-x64':{'file':'Neospector_0.7.26-ux43_linux-x64.deb','sha256':'b'*64,'bytes':123}}}

class NativeReleaseContract(unittest.TestCase):
    def test_platform_mapping(self):
        self.assertEqual(platform_id('Linux','x86_64'),'linux-x64')
        self.assertEqual(platform_id('Windows','AMD64'),'windows-x64')
        self.assertEqual(platform_id('Darwin','arm64'),'macos-arm64')
        self.assertEqual(platform_id('Darwin','x86_64'),'macos-x64')
        self.assertIsNone(platform_id('Linux','armv7'))
    def test_rejects_zip_exe_on_linux_and_malformed_release(self):
        for changed in [{'file':'Neospector_0.7.26-ux43_linux-x64.zip'},
                        {'file':'../Neospector_0.7.26-ux43_linux-x64.deb'},
                        {'file':'Neospector_0.7.26-ux43_windows-x64_Setup.exe'}]:
            doc=json.loads(json.dumps(PAYLOAD));doc['installers']['linux-x64'].update(changed)
            with self.assertRaises(UpdateError):validate_release(doc)
        self.assertTrue(validate_release(PAYLOAD))
    def test_signs_and_detects_any_manifest_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            secret=Path(d)/'key.pem';public=Path(d)/'public.pem'
            subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(secret)],check=True)
            with public.open('wb') as out:subprocess.run(['openssl','pkey','-in',str(secret),'-pubout'],stdout=out,check=True)
            envelope=sign_release(PAYLOAD,secret)
            self.assertEqual(verify_release(envelope,public),PAYLOAD)
            copy=json.loads(json.dumps(envelope));copy['payload']['installers']['linux-x64']['sha256']='c'*64
            with self.assertRaises(UpdateError):verify_release(copy,public)
    def test_native_download_path_pinned_same_origin(self):
        result=installer_url('https://omne.space/neospector/updates/installers.json','Neospector_0.7.26-ux43_linux-x64.deb')
        self.assertEqual(result,'https://omne.space/neospector/updates/native/Neospector_0.7.26-ux43_linux-x64.deb')
        with self.assertRaises(UpdateError):installer_url('http://evil.test/installers.json','Neospector_x.deb')
    def test_downloaded_bytes_required(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/PAYLOAD['installers']['linux-x64']['file'];f.write_bytes(b'unit')
            record={'file':f.name,'sha256':hashlib.sha256(b'unit').hexdigest(),'bytes':4}
            self.assertTrue(verify_installer(f,record))
            f.write_bytes(b'unit-')
            with self.assertRaises(UpdateError):verify_installer(f,record)

class OwnerPublicationContract(unittest.TestCase):
    def test_prevents_release_without_new_source_commit(self):
        with patch.object(owner_release,'cmd',side_effect=['https://github.com/olij167/neospector.git','', 'f'*40,'', 'main','f'*40]) as c:
            with patch('pathlib.Path.read_text',return_value=json.dumps({'schema':1,'product':'Neospector','version':'0.7.25-ux41'})),\
                 patch('urllib.request.urlopen') as u:
                u.return_value.__enter__.return_value.read.return_value=json.dumps({'version':'0.7.25-ux41'}).encode()
                with self.assertRaises(owner_release.ReleaseBlocked):owner_release.check_git_and_live('0.7.25-ux41')
    def test_catalogue_does_not_retain_old_zip_or_platform_flags(self):
        prior={'schema':1,'product':'Neospector','version':'0.7.25-ux41','downloads':{
           'linux-zip':{'ready':True},'linux':{'ready':True},'windows-x64':{'ready':True}}}
        updated=owner_release.new_catalogue(PAYLOAD,prior)
        self.assertFalse(updated['downloads']['linux-zip']['ready'])
        self.assertFalse(updated['downloads']['windows-x64']['ready'])
        self.assertTrue(updated['downloads']['linux']['ready'])
        self.assertEqual(updated['history'][0]['title'],'Native Installer Updates')

if __name__=='__main__':unittest.main()
