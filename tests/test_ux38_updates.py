"""UX38 signing, delivery and transactional versioned install contracts."""
from __future__ import annotations
import base64,hashlib,json,os,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app_source'),str(ROOT/'tools')]
from signed_updates import (UpdateError,canonical,verify_envelope,fetch_release,download_release,
                            safe_extract,verify_archive,validated_feed_url)
from update_installer import apply_update
from owner_publisher import prepare

class SignedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ux38-update-')
        self.base=Path(self.temp.name)
        self.key=self.base/'private.pem';self.pub=self.base/'public.pem'
        subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(self.key)],check=True,capture_output=True)
        self.key.chmod(0o600)
        subprocess.run(['openssl','pkey','-in',str(self.key),'-pubout','-out',str(self.pub)],check=True,capture_output=True)
        self.archive=self._release('0.7.99-ux99')
        self.output=self.base/'staged'
        self.payload,self.manifest=prepare(self.archive,self.key,self.output,'Test signed update')
        self.doc=json.loads(self.manifest.read_text())
    def tearDown(self):self.temp.cleanup()
    def _release(self,version):
        folder=self.base/('Neospector_Test_'+version.replace('.','_'))
        (folder/'app_source').mkdir(parents=True)
        (folder/'app_source/release_identity.py').write_text('VERSION = '+repr(version)+'\n')
        for f in ('RUN_POC.sh','INSTALL_LINUX.sh','bootstrap.py','install_linux.py'): (folder/f).write_text('#!/usr/bin/env bash\necho safe\n')
        (folder/'RELEASE.json').write_text(json.dumps({'version':version}))
        files=[p for p in folder.rglob('*') if p.is_file()]
        (folder/'MANIFEST.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(folder))+'\n' for p in files))
        arc=self.base/(folder.name+'.zip')
        with zipfile.ZipFile(arc,'w',zipfile.ZIP_DEFLATED) as z:
            for p in folder.rglob('*'):
                if p.is_file():z.write(p,folder.name+'/'+str(p.relative_to(folder)))
        return arc
    def test_signed_feed_verified_and_downloads(self):
        result=fetch_release(self.manifest.as_uri(),self.pub,'0.7.22-ux38',allow_local=True)
        self.assertEqual(result[0]['version'],'0.7.99-ux99')
        dest=self.base/'received.zip'
        download_release(self.manifest.as_uri(),result[0],dest,allow_local=True)
        self.assertTrue(verify_archive(dest,result[0]))
    def test_stale_version_is_ignored(self):
        self.assertIsNone(fetch_release(self.manifest.as_uri(),self.pub,'0.7.99-ux99',allow_local=True))
    def test_tampering_with_version_or_notes_is_rejected(self):
        for key,value in [('version','99.9.9'),('notes','Injected release notes')]:
            with self.subTest(key=key):
                doc=json.loads(self.manifest.read_text());doc['payload'][key]=value
                with self.assertRaisesRegex(UpdateError,'signature'):verify_envelope(doc,self.pub)
    def test_wrong_public_key_does_not_verify(self):
        other=self.base/'other.pem';subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(other)],check=True,capture_output=True)
        pub=self.base/'other.pub';subprocess.run(['openssl','pkey','-in',str(other),'-pubout','-out',str(pub)],check=True,capture_output=True)
        with self.assertRaises(UpdateError):verify_envelope(self.doc,pub)
    def test_download_hash_rejects_modified_bytes(self):
        damaged=self.base/'damaged.zip';damaged.write_bytes(self.archive.read_bytes()[:-1]+b'!')
        with self.assertRaisesRegex(UpdateError,'hash'):verify_archive(damaged,self.payload)
    def test_live_feed_rejects_http_and_userinfo(self):
        for url in ('http://omne.space/updates/stable.json','https://me:pw@omne.space/stable.json',
                    'file:///tmp/stable.json','https://omne.space/updates/data.txt'):
            with self.subTest(url=url),self.assertRaises(UpdateError):validated_feed_url(url)
    def test_archive_path_traversal_and_symlink_rejected(self):
        evil=self.base/'evil.zip'
        with zipfile.ZipFile(evil,'w') as z:z.writestr('Neospector_Test/../../escaped','not allowed')
        with self.assertRaises(UpdateError):safe_extract(evil,self.base/'unpacked')
    def test_apply_versioned_install_backups_and_pointer(self):
        data=self.base/'private-data';config=self.base/'config';config.mkdir()
        (config/'preferences-neospector-omne-r5.json').write_text('{"my_settings":true}')
        with patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':str(self.base),
                                'XDG_DATA_HOME':str(data),'XDG_CONFIG_HOME':str(self.base)}):
            release=apply_update(self.archive,self.manifest,self.pub,launch=False,data_root=data/'omne/neospector')
        self.assertTrue((release/'MANIFEST.sha256').exists())
        current=json.loads((data/'omne/neospector/current.json').read_text())
        self.assertEqual(current['version'],'0.7.99-ux99')
        self.assertTrue((data/'omne/neospector/launch.sh').exists())
        self.assertTrue((data/'applications/neospector.desktop').exists())
        launched=subprocess.run(['bash',str(data/'omne/neospector/launch.sh')],capture_output=True,text=True)
        self.assertEqual(launched.returncode,0,launched.stderr)
        self.assertIn('safe',launched.stdout)
        with self.assertRaises(UpdateError):apply_update(self.archive,self.manifest,self.pub,launch=False,data_root=data/'omne/neospector')

class UpdateUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        try:cls.root=tk.Tk();cls.root.withdraw()
        except tk.TclError as e:raise unittest.SkipTest('requires X display') from e
    @classmethod
    def tearDownClass(cls):cls.root.destroy()
    def test_preferences_and_welcome_use_one_update_controller(self):
        from neospector_console import NeospectorApp
        with tempfile.TemporaryDirectory(prefix='ux38-ui-') as home,patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':home,'NEOSPECTOR_NO_NATIVE_DROP':'1'}):
            app=NeospectorApp(test_mode=True)
            try:
                self.assertIsNotNone(app.update_controller)
                pref=app.open_preferences('general');app.update()
                self.assertTrue(pref.vars['auto_check_updates'].get())
                descendants=[pref.pages['general']]
                for node in descendants[:]:descendants.extend(node.winfo_children())
                labels=[w.cget('text') for w in descendants if 'text' in w.keys()]
                self.assertIn('Check for updates now',labels)
                self.assertNotIn('Check for updates on website',labels)
                self.assertIn('https://',pref.vars['update_feed_url'].get())
                self.assertTrue(callable(app.check_for_updates))
                with patch.object(app.update_controller,'check',return_value=True) as spy:
                    self.assertTrue(app.check_for_updates());spy.assert_called_once_with(silent=False)
                pref.vars['auto_check_updates'].set(False)
                self.assertTrue(pref.apply());self.assertFalse(app.auto_check_updates)
                win=app.show_startup_window(True);app.update()
                labels=[child.cget('text') for child in win.winfo_children() if 'text' in child.keys()]
                self.assertTrue(win.winfo_exists())
            finally:app.close(force=True)

if __name__=='__main__':unittest.main()
