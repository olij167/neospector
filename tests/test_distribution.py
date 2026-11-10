import unittest,subprocess,json,hashlib,ast,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class DistributionTests(unittest.TestCase):
    def test_original_archive_is_untouched_and_manifest_valid(self):
        output=subprocess.run(['python3',str(ROOT/'scripts/prepare_source.py'),'--verify-only'],capture_output=True,text=True)
        self.assertEqual(output.returncode,0,output.stderr)
        self.assertIn('413 manifest files',output.stdout)
    def test_signed_feed_matches_accepted_archive(self):
        import base64,tempfile
        p=json.loads((ROOT/'web/stable.json').read_text());payload=p['payload'];archive=ROOT/'source'/payload['archive'];self.assertEqual(payload['platform'],'linux-x86_64')
        with archive.open('rb') as handle: self.assertEqual(payload['sha256'],hashlib.file_digest(handle,'sha256').hexdigest())
        self.assertEqual(payload['bytes'],archive.stat().st_size)
        with tempfile.TemporaryDirectory() as t:
            from pathlib import Path
            msg=Path(t)/'payload';sig=Path(t)/'sig'
            msg.write_bytes(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii'))
            sig.write_bytes(base64.b64decode(p['signature']))
            r=subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(ROOT/'web/public.pem'),'-rawin','-in',str(msg),'-sigfile',str(sig)],capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr)
    def test_catalogue_keeps_native_artifacts_unpublished(self):
        c=json.loads((ROOT/'web/releases.json').read_text())
        self.assertTrue(c['downloads']['linux-zip']['ready'])
        linux=c['downloads']['linux']
        self.assertTrue(linux['ready'])
        self.assertEqual(linux['key'],'neospector/releases/Neospector_0.7.25-ux41_linux-x64.deb')
        self.assertEqual(linux['sha256'],'7e01af68c16afb6d466a26be78e2b24793064984731d0db934399e75416852d3')
        for k in ('windows-x64','macos-arm64','macos-x64','windows-x64-portable','macos-arm64-pkg','macos-x64-pkg'):self.assertFalse(c['downloads'][k]['ready'])
    def test_native_scripts_target_accepted_entry(self):
        for file in ('build_macos.sh','build_windows.ps1'):
            text=(ROOT/'native'/file).read_text()
            self.assertIn('neospector.py',text)
            self.assertNotIn('omne_sequencer.py',text)
            self.assertIn('Neospector',text)
        self.assertIn('AppId={{EA6A4CF5', (ROOT/'native/windows_installer.iss').read_text())
    def test_version_metadata(self):
        s=ROOT/'web/releases.json';c=json.loads(s.read_text());self.assertEqual(c['version'],'0.7.25-ux41')
    def test_no_private_key_in_distribution(self):
        self.assertFalse(any(x.suffix=='.key' or 'PRIVATE KEY' in x.read_text(errors='ignore') for x in [ROOT/'web/public.pem']))

if __name__=='__main__':unittest.main()
