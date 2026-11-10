"""v1.0 release preview: all four installers, honest trust labels, no signed feed changes."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'app_source')]
from owner_workflow import parse_version,next_version,OwnerBlocked,verified_assets,build,WORKFLOW
from owner_ci_receipt import receipt
from owner_preview import public_test_catalogue,preview_publication
from owner_release import ReleaseBlocked

class V1ReleaseContract(unittest.TestCase):
    def test_stable_version_is_1_0_0_and_older_ux_is_lower(self):
        self.assertGreater(parse_version('1.0.0'),parse_version('0.7.25-ux41'))
        self.assertGreater(parse_version('1.0.0'),parse_version('1.0.0-ux44'))
        self.assertEqual(next_version('1.0.0'),'1.0.1')
        self.assertEqual(next_version('0.7.25-ux41'),'0.7.26-ux42')
        with self.assertRaises(OwnerBlocked):parse_version('1.0')

    def test_ci_testing_receipt_is_not_a_trusted_signature(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Neospector_1.0.0_windows-x64_Setup.exe'
            p.write_bytes(b'mock-installer'*100)
            rec=receipt('windows-x64','1.0.0','a'*40,p,['installer-created','build-smoke'],'Windows',tier='preview')
            self.assertEqual(rec['tier'],'preview')
            self.assertNotIn('authenticode-valid',rec['checks'])
            with self.assertRaises(ValueError):
                receipt('windows-x64','1.0.0','a'*40,p,['installer-created'],'Windows',tier='preview')
            with self.assertRaises(ValueError):
                receipt('windows-x64','1.0.0','a'*40,p,['installer-created','build-smoke'],'Windows',tier='stable')

    def test_all_four_build_receipts_required_even_for_public_testing(self):
        suffixes={'linux-x64':'.deb','windows-x64':'_Setup.exe', 'macos-arm64':'.pkg','macos-x64':'.pkg'}
        runners={'linux-x64':'Linux','windows-x64':'Windows','macos-arm64':'macOS','macos-x64':'macOS'}
        with tempfile.TemporaryDirectory() as d:
            for alias,suffix in suffixes.items():
                sub=Path(d)/('neospector-native-'+alias);sub.mkdir()
                pkg=sub/('Neospector_1.0.0_'+alias+suffix);pkg.write_bytes((alias+'-build').encode()*200)
                rec=receipt(alias,'1.0.0','a'*40,pkg,['installer-created','build-smoke'],runners[alias],tier='preview')
                (sub/('ci-receipt-'+alias+'.json')).write_text(json.dumps(rec))
                (sub/(pkg.name+'.sha256')).write_text(rec['sha256']+'  '+pkg.name+'\n')
            files=verified_assets(d,'1.0.0','a'*40)
            self.assertEqual(set(files),set(suffixes))
            self.assertFalse(any(x['trusted'] for x in files.values()))
            (Path(d)/'neospector-native-macos-arm64/ci-receipt-macos-arm64.json').unlink()
            self.assertNotEqual(set(verified_assets(d,'1.0.0','a'*40)),set(suffixes))

    def test_public_testing_catalogue_disables_old_zip_and_production_autoupdate(self):
        prior={'schema':1,'product':'Neospector','version':'0.7.25-ux41',
               'downloads':{'linux-zip':{'ready':True,'key':'old.zip','sha256':'a'*64,'bytes':200},
                            'linux':{'ready':True},'windows-x64':{'ready':False}},
               'history':[]}
        alias=['linux-x64','windows-x64','macos-arm64','macos-x64']
        assets={a:{'file':'Neospector_1.0.0_'+a+('.deb' if a=='linux-x64' else '_Setup.exe' if a=='windows-x64' else '.pkg'),
                   'sha256':'b'*64,'bytes':1000,'_path':'/private/'+a,'trusted':False} for a in alias}
        data=public_test_catalogue('1.0.0','First Release','Test feedback wanted',{'live':prior,'commit':'c'*40},assets)
        self.assertEqual(data['release_stage'],'public-test')
        self.assertFalse(data['signed_auto_updates'])
        self.assertFalse(data['downloads']['linux-zip']['ready'])
        self.assertEqual(data['version'],'1.0.0')
        self.assertTrue(all(data['downloads'][x]['ready'] for x in ('linux','windows-x64','macos-arm64-pkg','macos-x64-pkg')))
        self.assertEqual(data['preview_tag'],'v1.0.0')
        with self.assertRaises(ReleaseBlocked):
            public_test_catalogue('1.0.0','First Release','notes',{'live':prior,'commit':'c'*40},dict(list(assets.items())[:3]))

    def test_public_test_approval_requires_all_os(self):
        with patch('owner_workflow.repo_valid',return_value=ROOT), patch('owner_workflow.source_version',return_value='1.0.0'),\
             patch('owner_workflow.cmd',return_value='a'*40):
            with self.assertRaises(OwnerBlocked):build(ROOT,'1.0.0',['linux'])

    def test_preview_stable_source_tag_is_not_created_during_check(self):
        with self.assertRaises(ReleaseBlocked):
            preview_publication(ROOT,'1.0.0-ux45','First','Notes','/not-there.json',publish=False)

if __name__=='__main__':unittest.main()
