#!/usr/bin/env python3
"""UX44 Owner Studio workflow. All network mutations require a UI-confirmed action.

One local GitHub checkout -> GitHub Actions native build -> private artifact sync ->
verified public publication via owner_release.py. No signing key is copied to CI.
"""
from __future__ import annotations
import argparse
import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from owner_site_http import site_json

REPO = 'olij167/neospector'
WORKFLOW = 'neospector-native-v1.yml'
WORKFLOW_NAME = 'Neospector v1 multi-OS installer builds'
PLATFORMS = {'linux-x64':('.deb','shipping-audit','Linux'),
             'windows-x64':('_Setup.exe','authenticode-valid','Windows'),
             'macos-arm64':('.pkg','notarized','macOS'),
             'macos-x64':('.pkg','notarized','macOS')}
BLOCKED_PARTS = {'.git','.venv','__pycache__','node_modules','build-work','artifacts','dist',
                 'logs','.run-logs','evidence','.neospector-ux43-backups','backups','secrets'}
SENSITIVE = re.compile(r'(^|/)(\.env(?:\..*)?|.*(?:private|secret|token|password|credential|\.key|\.p12|\.pfx).*)$',re.I)
CODE_ROOTS = {'app_source','native','scripts','web','tests','vendor'}
ALLOWED_SUFFIX = {'.png','.svg','.ico','.icns','.py','.json','.js','.mjs','.yml','.yaml','.sh','.ps1','.iss','.txt','.toml','.cfg','.spec','.plist','.pyi'}
MAX_STAGE_BYTES = 2*1024*1024

class OwnerBlocked(RuntimeError):
    pass


def cmd(*args, cwd=None, timeout=75):
    try:
        p = subprocess.run([str(x) for x in args],cwd=cwd,text=True,stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise OwnerBlocked(f'{args[0]} could not run: {exc}') from exc
    if p.returncode:
        raise OwnerBlocked(f'{args[0]} failed: {(p.stderr or p.stdout).strip()[-850:]}')
    return p.stdout.strip()


def parse_version(value):
    m=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-ux(\d+))?',str(value).strip())
    if not m:raise OwnerBlocked('Use a stable version such as 1.0.0 (displayed as v1.0)')
    a,b,c,ux=m.groups()
    return (int(a),int(b),int(c),2 if ux is None else 1,int(ux or 0))


def next_version(current):
    major,minor,patch,kind,ux=parse_version(current)
    if kind==2:return f'{major}.{minor}.{patch+1}'
    return f'{major}.{minor}.{patch+1}-ux{ux+1}'


def source_version(repo):
    tree=ast.parse((Path(repo)/'app_source/release_identity.py').read_text(encoding='utf-8'))
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in n.targets))


def repo_valid(repo):
    repo=Path(repo).expanduser().resolve()
    if not (repo/'scripts/owner_release.py').is_file() or not (repo/'web/releases.json').is_file():
        raise OwnerBlocked('Select the Neospector source checkout, not an installer or archive')
    url=cmd('git','remote','get-url','origin',cwd=repo)
    if not re.search(r'(?:github\.com[:/])olij167/neospector(?:\.git)?$',url):
        raise OwnerBlocked('Git origin is not olij167/neospector')
    if cmd('git','branch','--show-current',cwd=repo)!='main':
        raise OwnerBlocked('Stable releases must be prepared on main')
    return repo


def data_home():
    return Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'omne/neospector-owner-publisher'


def release_notes_path(repo):
    return Path(repo)/'web/release_draft.json'


def can_stage(path,repo):
    """Auto-commit only bounded, release-relevant source files, never credentials/builds."""
    p=Path(path)
    if p.is_absolute() or '..' in p.parts or not p.parts or any(x in BLOCKED_PARTS or (x.startswith('.neospector-') and 'backup' in x) for x in p.parts):return False
    if SENSITIVE.search(p.as_posix()):return False
    if len(p.parts)==1:
        return p.name in {'.gitignore','requirements.txt','requirements-drop.txt','requirements-loopback-windows.txt'}
    if p.parts[0]=='.github':return len(p.parts)>=3 and p.parts[1]=='workflows' and p.suffix in {'.yml','.yaml'}
    if p.parts[0] not in CODE_ROOTS or p.suffix not in ALLOWED_SUFFIX:return False
    if p.name.endswith(('.log','.sha256')):return False
    f=repo/p
    if f.is_symlink():return False
    if f.exists():
        if not f.is_file() or f.stat().st_size>MAX_STAGE_BYTES:return False
        if p.suffix in {'.py','.sh','.js','.mjs','.json','.yml','.yaml','.txt'}:
            try:
                head=f.read_bytes()[:128*1024]
                if b'-----BEGIN PRIVATE KEY-----' in head or b'-----BEGIN OPENSSH PRIVATE KEY-----' in head:return False
            except OSError:return False
    return True


def changed_paths(repo):
    output=cmd('git','status','--porcelain=v1','--untracked-files=all','-z',cwd=repo)
    bits=output.split('\x00');selected=[];skipped=[];i=0
    while i<len(bits):
        row=bits[i];i+=1
        if not row:continue
        path=row[3:]
        if row[:2].strip().startswith(('R','C')):i+=1
        if can_stage(path,repo):selected.append(path)
        else:skipped.append(path)
    return sorted(set(selected)),sorted(set(skipped))


def pending_release_paths(repo):
    """Unpublished release inputs, not unrelated local state.

    GitHub Actions builds the pushed SHA, so generated backups and local
    development files must not block a remote build. Unsaved application,
    publishing, workflow or test changes still block to prevent stale builds.
    """
    repo=Path(repo)
    tracked=cmd('git','diff','HEAD','--name-only','-z',cwd=repo).split('\x00')
    eligible,_=changed_paths(repo)
    prefixes=('app_source/','native/','scripts/','web/','tests/',
              'vendor/','.github/workflows/')
    exact={'requirements.txt','requirements-drop.txt',
           'requirements-loopback-windows.txt'}
    paths=set(tracked)|set(eligible)
    return sorted(p for p in paths if p and not any(
        part in BLOCKED_PARTS or (part.startswith('.neospector-') and 'backup' in part)
        for part in Path(p).parts)
        and (p.startswith(prefixes) or p in exact))

def status(repo):
    repo=repo_valid(repo)
    live=json.loads((repo/'web/releases.json').read_text())
    source=source_version(repo)
    selected,skipped=changed_paths(repo)
    try:
        cmd('gh','auth','status',cwd=repo)
        github=True
    except OwnerBlocked:github=False
    return {'repository':REPO,'source_version':source,'published_version':live.get('version'),
            'github_authenticated':github,'ready_to_publish':False,
            'pending_files':selected,'excluded_files':skipped,
            'signing_key_ready':(Path.home()/'.config/omne-private/neospector-owner-signing.pem').is_file(),
            'cloudflare_cli_ready':bool(shutil.which('wrangler'))}


def prepare_push(repo,version,title,notes):
    repo=repo_valid(repo)
    parse_version(version)
    if not title.strip() or not notes.strip():raise OwnerBlocked('Enter an update name and release notes')
    live=json.loads((repo/'web/releases.json').read_text())
    if parse_version(version)<=parse_version(live['version']):raise OwnerBlocked('New version must be greater than published version')
    cmd('gh','auth','status',cwd=repo)
    cmd('git','fetch','origin','main','--tags',cwd=repo,timeout=90)
    remote=cmd('git','rev-parse','origin/main',cwd=repo)
    head=cmd('git','rev-parse','HEAD',cwd=repo)
    if remote!=head:
        # Local ahead-only commits are legitimate release work; the companion
        # can push them. Refuse remote-ahead/diverged branches without merging.
        try:cmd('git','merge-base','--is-ancestor',remote,head,cwd=repo)
        except OwnerBlocked as exc:
            raise OwnerBlocked('GitHub main is ahead of or divergent from local main; resolve this before release') from exc
    # Validate the set before modifying the checkout. User consent comes from the GUI.
    to_stage,skipped=changed_paths(repo)
    source_changed=[x for x in to_stage if x.startswith(('app_source/','native/','scripts/','vendor/'))
                    and x!='app_source/release_identity.py']
    if not source_changed:
        try:
            tag='v'+live['version']
            committed=cmd('git','diff','--name-only',tag+'..HEAD',cwd=repo).splitlines()
        except OwnerBlocked:committed=[]
        substantive=[x for x in committed if x.startswith(('app_source/','native/','scripts/','vendor/'))
                     and x!='app_source/release_identity.py']
        if not substantive:raise OwnerBlocked('No releasable source changes. Publishing metadata alone is not allowed.')
    # Explicitly exclude generated files and credentials from git add.
    sys.path.insert(0,str(repo/'scripts'))
    from owner_release import prepare_version
    prepare_version(version,title,notes)
    to_stage,_=changed_paths(repo)
    mandatory={'app_source/release_identity.py','web/release_draft.json'}
    if not mandatory.issubset(set(to_stage)|set(cmd('git','ls-files',cwd=repo).splitlines())):
        raise OwnerBlocked('Release identity or draft could not be staged')
    to_stage=sorted(set(to_stage)|mandatory)
    if not to_stage:raise OwnerBlocked('No publishable changes')
    cmd('git','add','-A','--',*to_stage,cwd=repo)
    staged=cmd('git','diff','--cached','--name-only',cwd=repo).splitlines()
    unexpected=[x for x in staged if not can_stage(x,repo)]
    if unexpected:raise OwnerBlocked('Unapproved staged files: '+', '.join(unexpected))
    if not staged:
        # Recover a previous attempt where commit succeeded but network push
        # failed. Do not create an empty release commit or require terminal git.
        if remote!=head:
            cmd('git','push','origin','main',cwd=repo,timeout=150)
            return {'status':'EXISTING RELEASE COMMIT PUSHED','version':version,'commit':head,
                    'source_changes':0,'excluded_files':len(skipped),
                    'next':'Build native installers using GitHub Actions'}
        if source_version(repo)==version and remote==head:
            draft=json.loads(release_notes_path(repo).read_text(encoding='utf-8'))
            if draft=={'version':version,'title':title.strip(),'notes':notes.strip()}:
                return {'status':'ALREADY PREPARED AND PUSHED','version':version,
                        'commit':head,'source_changes':0,'excluded_files':len(skipped),
                        'next':'Build native installers using GitHub Actions'}
        raise OwnerBlocked('No new source changes to publish')
    # User should be able to understand exactly what was published in history.
    cmd('git','commit','-m',f'Neospector {version}: {title.strip()[:120]}',cwd=repo,timeout=90)
    commit=cmd('git','rev-parse','HEAD',cwd=repo)
    cmd('git','push','origin','main',cwd=repo,timeout=150)
    return {'status':'PREPARED AND PUSHED','version':version,'commit':commit,
            'source_changes':len(staged),'excluded_files':len(skipped),
            'next':'Build native installers using GitHub Actions'}


def build(repo,version,platforms):
    repo=repo_valid(repo)
    choices=set(platforms)
    if not choices or not choices.issubset({'linux','windows','macos'}):raise OwnerBlocked('Choose a valid nonempty OS set')
    if source_version(repo)!=version:raise OwnerBlocked('Prepare & Push this version first')
    if cmd('git','rev-parse','HEAD',cwd=repo)!=cmd('git','ls-remote','origin','refs/heads/main',cwd=repo).split()[0]:
        raise OwnerBlocked('Commit is not on GitHub main')
    pending=pending_release_paths(repo)
    if pending:
        raise OwnerBlocked('Uncommitted release inputs: '+', '.join(pending[:6])+
                           (' (+%d more)'%(len(pending)-6) if len(pending)>6 else '')+
                           '. Use Prepare & Push to include them, or discard only the edits you do not want.')
    cmd('gh','workflow','run',WORKFLOW,'-R',REPO,'--ref','main',
        '-f','version='+version,'-f','platforms='+','.join(sorted(choices)),cwd=repo,timeout=100)
    return {'status':'NATIVE BUILD REQUESTED','version':version,'platforms':sorted(choices),
            'url':'https://github.com/'+REPO+'/actions/workflows/'+WORKFLOW,
            'next':'Use Sync Native Builds after the GitHub workflow succeeds'}


def check_run(repo,run_id,expected_commit):
    info=json.loads(cmd('gh','run','view',str(int(run_id)),'-R',REPO,
                        '--json','databaseId,headSha,headBranch,status,conclusion,workflowName,event',cwd=repo))
    if (info.get('databaseId')!=int(run_id) or info.get('headSha')!=expected_commit
        or info.get('headBranch')!='main' or info.get('status')!='completed'
        or info.get('conclusion')!='success' or info.get('workflowName')!=WORKFLOW_NAME
        or info.get('event')!='workflow_dispatch'):
        raise OwnerBlocked('GitHub native build does not match this published-source commit or is not successful')
    return info


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def verified_assets(directory,version,commit):
    """Read only native files + receipts; refuse archives and unverifiable builds."""
    root=Path(directory).resolve(strict=True)
    assets={}
    receipts=list(root.rglob('ci-receipt-*.json'))
    if not receipts:raise OwnerBlocked('No native verification receipts found in the GitHub build')
    for receipt_path in receipts:
        if (receipt_path.is_symlink() or not receipt_path.resolve().is_relative_to(root)
            or receipt_path.stat().st_size>65536):
            raise OwnerBlocked('Unsafe native verification receipt')
        data=json.loads(receipt_path.read_text(encoding='utf-8'))
        alias=data.get('platform')
        if alias not in PLATFORMS or alias in assets:raise OwnerBlocked('Unknown/duplicate native platform evidence')
        suffix,check,runner=PLATFORMS[alias]
        name=data.get('file')
        checks=data.get('checks')
        if not isinstance(checks,list) or any(not isinstance(c,str) for c in checks):
            raise OwnerBlocked('Malformed native verification checks')
        tier=data.get('tier','stable')
        required_checks=(check,) if tier=='stable' else ('installer-created','build-smoke') if tier=='preview' else ()
        if (data.get('schema')!=1 or data.get('version')!=version or data.get('commit')!=commit
            or data.get('verified') is not True or not required_checks or not set(required_checks).issubset(data.get('checks',[])) or runner!=data.get('runner')
            or not isinstance(name,str) or not re.fullmatch(r'Neospector_[A-Za-z0-9_.-]+',name) or '..' in name
            or not name.startswith('Neospector_'+version+'_'+alias)
            or not name.endswith(suffix)):
            raise OwnerBlocked('Native build receipt does not match signed installer: '+receipt_path.name)
        path=receipt_path.parent/name
        if not path.is_file() or path.is_symlink() or path.stat().st_size<1024:
            raise OwnerBlocked('Native installer missing: '+name)
        digest=file_sha(path)
        if digest!=data.get('sha256') or path.stat().st_size!=data.get('bytes'):
            raise OwnerBlocked('Native installer checksum failed: '+name)
        sha_file=Path(str(path)+'.sha256')
        if not sha_file.is_file() or sha_file.read_text().split()[0].lower()!=digest:
            raise OwnerBlocked('Missing/mismatched checksum companion: '+name)
        assets[alias]={'file':name,'sha256':digest,'bytes':path.stat().st_size,
                       '_path':str(path),'checks':list(data['checks']),'tier':tier,
                       'trusted':tier=='stable', 'receipt':str(receipt_path)}
    if len({x['tier'] for x in assets.values()})!=1:
        raise OwnerBlocked('Cannot mix stable and testing installers in one release')
    return assets


def sync(repo,version,platforms=None):
    """Combine matching installer receipts from one or more successful CI runs.

    A selective run can contribute only its successfully built platform. The
    verified CI bundle records the original GitHub run for *each* installer.
    No cross-version or cross-commit merging is permitted.
    """
    repo=repo_valid(repo)
    if source_version(repo)!=version:raise OwnerBlocked('Source version differs from selected release')
    commit=cmd('git','rev-parse','HEAD',cwd=repo)
    remote=cmd('git','ls-remote','origin','refs/heads/main',cwd=repo).split()[0]
    if commit!=remote:raise OwnerBlocked('Push source changes to GitHub first')
    runs=json.loads(cmd('gh','run','list','-R',REPO,'--workflow',WORKFLOW,
                        '--limit','100','--json','databaseId,headSha,status,conclusion,createdAt,event',cwd=repo))
    good=[r for r in runs if r.get('headSha')==commit and
          r.get('conclusion')=='success' and r.get('status')=='completed' and
          r.get('event')=='workflow_dispatch']
    if not good:raise OwnerBlocked('No successful native builds for the exact current commit')
    assets={};original_runs={}
    for run in sorted(good,key=lambda r:r.get('createdAt',''),reverse=True):
        run_id=int(run['databaseId'])
        check_run(repo,run_id,commit)
        dest=data_home()/'builds'/version/commit/str(run_id)
        if not dest.is_dir() or not list(dest.rglob('ci-receipt-*.json')):
            dest.mkdir(parents=True,exist_ok=True)
            cmd('gh','run','download',str(run_id),'-R',REPO,'--pattern','neospector-native-*',
                '--dir',dest,cwd=repo,timeout=480)
        verified=verified_assets(dest,version,commit)
        for alias,item in verified.items():
            if alias not in assets:
                assets[alias]=item
                original_runs[alias]=run_id
        if set(assets)==set(PLATFORMS):break
    missing=set(PLATFORMS)-set(assets)
    if missing:raise OwnerBlocked('Full publication needs four verified native installers; missing: '+', '.join(sorted(missing)))
    if len(set(original_runs.values()))==1:
        # Backward-compatible bundle for the original single workflow.
        bundle={'schema':1,'repository':REPO,'workflow':WORKFLOW_NAME,
                'run_id':next(iter(original_runs.values())),'version':version,
                'commit':commit,'assets':assets}
    else:
        bundle={'schema':2,'repository':REPO,'workflow':WORKFLOW_NAME,
                'run_ids':original_runs,'version':version,'commit':commit,'assets':assets}
    bundle_path=data_home()/'builds'/version/'verified_bundle.json'
    bundle_path.parent.mkdir(parents=True,exist_ok=True)
    tmp=bundle_path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(bundle,indent=2)+'\n')
    tmp.replace(bundle_path)
    return {'status':'NATIVE BUILD ARTIFACTS CHECKED (NOT A DEVICE TEST)',
            'version':version,'platforms':sorted(assets),
            'run_id':next(iter(original_runs.values())) if len(set(original_runs.values()))==1 else None,
            'run_ids':original_runs,'bundle':str(bundle_path),
            'next':'Publish the four-platform, clearly labelled public testing release'}

def bundle_for(repo,version):
    repo=repo_valid(repo)
    path=data_home()/'builds'/version/'verified_bundle.json'
    if not path.is_file():raise OwnerBlocked('Sync Native Builds first')
    data=json.loads(path.read_text())
    if data.get('commit')!=cmd('git','rev-parse','HEAD',cwd=repo):
        raise OwnerBlocked('Native builds belong to a different source commit; rebuild first')
    return path


def finalize_publication_commit(repo,version):
    """Keep GitHub source catalogue in sync *after* a verified public release.

    On failure, public release remains live: caller reports recovery needed.
    """
    files=('web/releases.json','web/native_release.mjs','web/release_data.mjs')
    cmd('git','add','--',*files,cwd=repo)
    staged=cmd('git','diff','--cached','--name-only',cwd=repo).splitlines()
    if staged:
        if set(staged)-set(files):
            raise OwnerBlocked('Unexpected staged changes after website publication')
        cmd('git','commit','-m','Publish Neospector '+version+' website catalogue',cwd=repo)
        cmd('git','push','origin','main',cwd=repo,timeout=150)
    return len(staged)


def publish(repo,version,title,notes,accepted=False,only_check=False):
    """Public test releases need successful platform-native CI builds, not a false
    assertion that the owner tested operating systems they do not own.

    Stable signed-updater releases are handled separately by owner_release.py.
    """
    repo=repo_valid(repo)
    bundle=bundle_for(repo,version)
    sys.path.insert(0,str(repo/'scripts'))
    from owner_preview import preview_publication
    publication=preview_publication(repo,version,title,notes,bundle,publish=not only_check)
    if not only_check and publication.get('status')=='PUBLIC TEST RELEASE LIVE':
        try:
            publication['website_source_files_synced']=finalize_publication_commit(repo,version)
        except (OwnerBlocked,OSError) as exc:
            publication['status']='PUBLIC TEST RELEASE LIVE — SOURCE SYNC NEEDS ATTENTION'
            publication['source_sync_error']=str(exc)
    return publication


def verify_live(version,repo=None):
    def get(path):
        return site_json(path,timeout=12,max_bytes=100000)
    catalogue=get('/downloads/neospector/releases.json')
    if catalogue.get('version')!=version or not any(x.get('version')==version for x in catalogue.get('history',[])):
        raise OwnerBlocked('Live website version or release notes do not match')
    if catalogue.get('release_stage')=='public-test':
        if catalogue.get('preview_tag')!='v'+version:
            raise OwnerBlocked('Public test release tag does not match')
        if not all(catalogue.get('downloads',{}).get(alias,{}).get('ready') for alias in ('linux','windows-x64','macos-arm64-pkg','macos-x64-pkg')):
            raise OwnerBlocked('A test installer is missing from the live download catalogue')
        # This stage is deliberately NOT an authenticated production update feed.
        return {'status':'PUBLIC TEST DOWNLOADS VERIFIED','version':version,'signed_auto_updates':False,
                'downloads':'https://omne.space/downloads/neospector',
                'changelog':'https://omne.space/downloads/neospector/changelog'}
    feed=get('/neospector/updates/installers.json')
    if feed.get('payload',{}).get('version')!=version:
        raise OwnerBlocked('Live installer update feed differs from published version')
    if repo is not None:
        repo=Path(repo)
        sys.path.insert(0,str(repo/'app_source'))
        from installer_updates import verify_release
        try:verify_release(feed,repo/'updates/public.pem')
        except Exception as exc:raise OwnerBlocked('Live installer feed signature invalid') from exc
    return {'status':'LIVE WEBSITE VERIFIED','version':version,
            'downloads':'https://omne.space/downloads/neospector',
            'changelog':'https://omne.space/downloads/neospector/changelog'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('status','prepare','build','sync','check','publish','verify'))
    p.add_argument('--repo',type=Path,default=Path.home()/'Projects/neospector')
    p.add_argument('--version',default='')
    p.add_argument('--title',default='')
    p.add_argument('--notes-file',type=Path)
    p.add_argument('--platforms',default='linux,windows,macos')
    p.add_argument('--accepted-on-device',action='store_true',help='Reserved for future stable signed releases')
    a=p.parse_args(argv)
    try:
        notes=a.notes_file.read_text(encoding='utf-8').strip() if a.notes_file else ''
        if a.action=='status':result=status(a.repo)
        elif a.action=='prepare':result=prepare_push(a.repo,a.version,a.title,notes)
        elif a.action=='build':result=build(a.repo,a.version,a.platforms.split(','))
        elif a.action=='sync':result=sync(a.repo,a.version,a.platforms.split(','))
        elif a.action=='check':result=publish(a.repo,a.version,a.title,notes,a.accepted_on_device,True)
        elif a.action=='publish':result=publish(a.repo,a.version,a.title,notes,a.accepted_on_device)
        else:result=verify_live(a.version,a.repo)
        print(json.dumps(result,indent=2));return 0
    except (OwnerBlocked,ValueError,OSError,subprocess.SubprocessError) as exc:
        print('RELEASE BLOCKED: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
