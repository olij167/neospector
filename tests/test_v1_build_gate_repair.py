"""Local-only release gate regression; never calls GitHub."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import types
import sys
import json
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts'/'owner_workflow.py'
sp=importlib.util.spec_from_file_location('owner_workflow_v1_repair', SCRIPT)
workflow=importlib.util.module_from_spec(sp)
sp.loader.exec_module(workflow)


def git(repo,*args):
    p=subprocess.run(['git',*args],cwd=repo,text=True,capture_output=True,check=True)
    return p.stdout.strip()


class BuildGateTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.repo=Path(self.t.name)
        git(self.repo,'init','-q','-b','main')
        git(self.repo,'config','user.email','local@example.invalid')
        git(self.repo,'config','user.name','Local Test')
        for p,contents in [('app_source/main.py','VERSION="1.0.0"\n'),
                           ('scripts/owner_release.py','old\n'),
                           ('web/releases.json','{}\n'),
                           ('README.md','read me\n')]:
            f=self.repo/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(contents)
        git(self.repo,'add','.')
        git(self.repo,'commit','-q','-m','v1 source')
        self.sha=git(self.repo,'rev-parse','HEAD')

    def test_generated_untracked_backups_never_block(self):
        (self.repo/'.neospector-ux42-integrated-backups'/'20261109').mkdir(parents=True)
        (self.repo/'.neospector-ux42-integrated-backups'/'20261109'/'abc.py').write_text('x')
        (self.repo/'.neospector-ux43-backups').mkdir()
        (self.repo/'.neospector-ux43-backups'/'junk.py').write_text('x')
        (self.repo/'README.md').write_text('edited readme\n')
        self.assertEqual(workflow.pending_release_paths(self.repo),[])
        allowed,excluded=workflow.changed_paths(self.repo)
        self.assertNotIn('.neospector-ux42-integrated-backups/20261109/abc.py',allowed)

    def test_modified_release_source_blocks(self):
        (self.repo/'app_source/main.py').write_text('changed\n')
        self.assertEqual(workflow.pending_release_paths(self.repo),['app_source/main.py'])

    def test_untracked_release_source_blocks(self):
        (self.repo/'native').mkdir()
        (self.repo/'native/build.sh').write_text('echo build\n')
        self.assertEqual(workflow.pending_release_paths(self.repo),['native/build.sh'])

    def test_gitignore_is_safe_to_stage(self):
        (self.repo/'.gitignore').write_text('.neospector-*-backups/\n')
        self.assertTrue(workflow.can_stage('.gitignore',self.repo))

    def test_build_dispatches_committed_sha_despite_local_junk(self):
        (self.repo/'.neospector-ux42-integrated-backups').mkdir()
        (self.repo/'.neospector-ux42-integrated-backups'/'junk.txt').write_text('x')
        (self.repo/'README.md').write_text('local notes\n')
        realcmd=workflow.cmd
        calls=[]
        def intercepted(*args,**kwargs):
            if args[:2]==('git','ls-remote'):
                return self.sha+'\trefs/heads/main'
            if args[:3]==('gh','workflow','run'):
                calls.append(args)
                return ''
            return realcmd(*args,**kwargs)
        with mock.patch.object(workflow,'repo_valid',lambda p:self.repo), \
             mock.patch.object(workflow,'source_version',lambda p:'1.0.0'), \
             mock.patch.object(workflow,'cmd',side_effect=intercepted):
            answer=workflow.build(self.repo,'1.0.0',['linux','windows','macos'])
        self.assertEqual(answer['status'],'NATIVE BUILD REQUESTED')
        self.assertEqual(len(calls),1)

    def test_build_blocked_on_unsaved_app_change(self):
        (self.repo/'app_source/main.py').write_text('x\n')
        realcmd=workflow.cmd
        def intercepted(*args,**kwargs):
            if args[:2]==('git','ls-remote'):
                return self.sha+'\trefs/heads/main'
            return realcmd(*args,**kwargs)
        with mock.patch.object(workflow,'repo_valid',lambda p:self.repo), \
             mock.patch.object(workflow,'source_version',lambda p:'1.0.0'), \
             mock.patch.object(workflow,'cmd',side_effect=intercepted):
            with self.assertRaisesRegex(workflow.OwnerBlocked,'app_source/main.py'):
                workflow.build(self.repo,'1.0.0',['linux','windows','macos'])

    def test_prepare_is_idempotent_when_release_commit_already_pushed(self):
        git(self.repo,'tag','v0.7.25-ux41')
        (self.repo/'web/releases.json').write_text(json.dumps({'version':'0.7.25-ux41'}))
        (self.repo/'app_source/main.py').write_text('released change\n')
        (self.repo/'app_source/release_identity.py').write_text('VERSION = "1.0.0"\n')
        release={'version':'1.0.0','title':'First Release','notes':'Test notes'}
        (self.repo/'web/release_draft.json').write_text(json.dumps(release))
        git(self.repo,'add','.')
        git(self.repo,'commit','-q','-m','v1.0.0 release committed')
        committed=git(self.repo,'rev-parse','HEAD')
        realcmd=workflow.cmd
        def intercepted(*args,**kwargs):
            if args[:3]==('git','fetch','origin'):return ''
            if args[:3]==('git','rev-parse','origin/main'):return committed
            if args[:2]==('gh','auth'):return ''
            if args[:3]==('git','push','origin'):
                self.fail('Already pushed source should not be pushed a second time')
            return realcmd(*args,**kwargs)
        with mock.patch.object(workflow,'repo_valid',lambda p:self.repo), \
             mock.patch.object(workflow,'source_version',lambda p:'1.0.0'), \
             mock.patch.object(workflow,'cmd',side_effect=intercepted), \
             mock.patch.dict(sys.modules,{'owner_release':types.SimpleNamespace(prepare_version=lambda *a:None)}):
            result=workflow.prepare_push(self.repo,'1.0.0','First Release','Test notes')
        self.assertEqual(result['status'],'ALREADY PREPARED AND PUSHED')
        self.assertEqual(git(self.repo,'rev-parse','HEAD'),committed)

if __name__=='__main__':unittest.main()
