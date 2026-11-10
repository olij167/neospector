#!/usr/bin/env python3
"""Native-installer-only, owner-gated GitHub -> Cloudflare release publisher.

Check is read-only; 'prepare' edits tracked source draft metadata only;
'publish' is explicit and rejects uncommitted/unpushed code or reused assets.
No private signing material is copied into the repository or public payload.
"""
from __future__ import annotations
import argparse, ast, datetime, hashlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app_source'))
sys.path.insert(0,str(ROOT/'scripts'))
from installer_updates import platform_id,sign_release,verify_release,validate_release
from signed_updates import version_tuple, UpdateError
REPO='olij167/neospector'
ALIAS_FLAGS={'linux-x64':'linux','windows-x64':'windows','macos-arm64':'macos_arm64','macos-x64':'macos_x64'}
CATALOGUE=ROOT/'web/releases.json'
NATIVE=ROOT/'web/native_release.mjs'
PUBLIC=ROOT/'updates/public.pem'
PRIVATE=Path.home()/'.config/omne-private/neospector-owner-signing.pem'
class ReleaseBlocked(RuntimeError):pass

def cmd(*args, cwd=ROOT, timeout=50):
    try:p=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as exc:raise ReleaseBlocked('Missing or unavailable release dependency: '+str(args[0])) from exc
    if p.returncode:raise ReleaseBlocked('Command failed: '+' '.join(map(str,args[:4]))+' — '+(p.stderr or p.stdout).strip()[-300:])
    return p.stdout.strip()

def source_version():
    path=ROOT/'app_source/release_identity.py'
    tree=ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets):
            if isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):return node.value.value
    raise ReleaseBlocked('Unable to determine source version')

def prepare_version(version,title,notes):
    version_tuple(version)
    if not 1<=len(title.strip())<=140 or not 1<=len(notes.strip())<=8000:raise ReleaseBlocked('Title/notes required')
    identity=ROOT/'app_source/release_identity.py'
    text=identity.read_text()
    updated=re.sub(r'^VERSION\s*=.*$', 'VERSION = '+repr(version),text, count=1, flags=re.M)
    updated=re.sub(r'^RELEASE\s*=.*$', 'RELEASE = '+repr(title.strip()),updated,count=1,flags=re.M)
    updated=re.sub(r'^STATUS\s*=.*$', 'STATUS = '+repr('OWNER_NATIVE_RELEASE_CANDIDATE'),updated,count=1,flags=re.M)
    if updated==text and source_version()!=version:raise ReleaseBlocked('Unable to prepare release identity')
    identity.write_text(updated)
    (ROOT/'web/release_draft.json').write_text(json.dumps({'version':version,'title':title.strip(),'notes':notes.strip()},indent=2)+'\n')
    return {'version':version,'prepared':True,'next':'Review, commit and push changes, then build/test/sign native installers.'}

def check_git_and_live(version):
    remote=cmd('git','remote','get-url','origin')
    if not re.search(r'(?:github\.com[:/])olij167/neospector(?:\.git)?$',remote):
        raise ReleaseBlocked('Git origin is not the expected Neospector GitHub repository')
    # GitHub release assets are built from the pushed SHA. Unrelated local
    # generated files and release-tool backups must not block publication.
    release_inputs=('app_source','native','scripts','web','tests','vendor',
                    '.github/workflows','requirements.txt','requirements-drop.txt',
                    'requirements-loopback-windows.txt')
    dirty=cmd('git','diff','HEAD','--name-only','--',*release_inputs).splitlines()
    if dirty:
        raise ReleaseBlocked('Uncommitted release inputs: '+', '.join(dirty[:6])+
                             '. Use Prepare & Push before publishing.')
    head=cmd('git','rev-parse','HEAD')
    if not re.fullmatch('[0-9a-f]{40}',head):raise ReleaseBlocked('Invalid Git commit identity')
    cmd('gh','auth','status')
    branch=cmd('git','branch','--show-current')
    if branch!='main':raise ReleaseBlocked('Only main branch can publish stable releases')
    remote_head=cmd('git','ls-remote','origin','refs/heads/main').split()[0]
    if head!=remote_head:raise ReleaseBlocked('Current main commit has not been pushed to GitHub')
    live=json.loads(CATALOGUE.read_text())
    # Prevent publishing against stale local website metadata.
    from urllib.request import urlopen
    try:
        with urlopen('https://omne.space/downloads/neospector/releases.json',timeout=12) as response:
            public=json.loads(response.read(65537))
    except (OSError,ValueError) as exc:raise ReleaseBlocked('Live website catalogue could not be checked') from exc
    if public.get('version')!=live.get('version'):
        raise ReleaseBlocked('Local release catalogue is not synchronized with live omne.space')
    if live.get('schema')!=1 or live.get('product')!='Neospector':raise ReleaseBlocked('Invalid live release catalogue')
    if version_tuple(version)<=version_tuple(live['version']):raise ReleaseBlocked('New version must exceed currently listed version')
    old_tag='v'+live['version']
    try:cmd('git','rev-parse','--verify','refs/tags/'+old_tag)
    except ReleaseBlocked as exc:raise ReleaseBlocked('Published tag missing locally; use git fetch --tags origin before publishing') from exc
    count=int(cmd('git','rev-list','--count',old_tag+'..HEAD'))
    if count<=0:raise ReleaseBlocked('No new commits since the last published version')
    changed=cmd('git','diff','--name-only',old_tag+'..HEAD').splitlines()
    allowed=[p for p in changed if p.startswith(('app_source/','native/','scripts/','vendor/')) or p in ('requirements.txt','requirements-drop.txt')]
    if not allowed:raise ReleaseBlocked('No changed application or native build sources since last release')
    return {'commit':head,'commits':count,'changed_sources':allowed,'live':live}

def native_assets(options,version,*,check_native=True):
    assets={}
    for alias,flag in ALIAS_FLAGS.items():
        raw=getattr(options,flag,None)
        if not raw:continue
        path=Path(raw).expanduser().resolve()
        if path.is_symlink() or not path.is_file():raise ReleaseBlocked('Missing installer: '+str(path))
        if version not in path.name:raise ReleaseBlocked('Installer filename must carry proposed version: '+path.name)
        size=path.stat().st_size
        if size<=0 or size>800*1024*1024:raise ReleaseBlocked('Invalid installer size')
        from installer_updates import PLATFORMS
        if not path.name.endswith(PLATFORMS[alias]) or not any('_'+alias+tail in path.name for tail in ('.', '_')):raise ReleaseBlocked('Wrong platform installer filename: '+path.name)
        with path.open('rb') as f:
            digest=hashlib.sha256()
            for b in iter(lambda:f.read(1024*1024),b''):digest.update(b)
        if check_native:
            from subprocess import run as proc_run
            native_os=platform_id()
            if native_os!=alias:raise ReleaseBlocked('Sign/trust validation of '+alias+' must run on a native '+alias+' machine; no owner assertion substitutes.')
            sys.path.insert(0,str(ROOT/'app_source'))
            from native_installer_helper import verify_platform_signature
            verify_platform_signature(path,alias)
            if alias=='linux-x64':
                from verify_shipping import verify_deb
                verify_deb(path)
            elif alias=='windows-x64':
                thumb=os.environ.get('NEOSPECTOR_WINDOWS_CERT_THUMBPRINT','').replace(' ','').upper()
                if not re.fullmatch('[A-F0-9]{40}',thumb):raise ReleaseBlocked('Expected Windows publisher certificate thumbprint is required')
                # Native signature inspection must match the configured identity.
                ps=('param([string]$File,[string]$Expected)\n'
                    '$s=Get-AuthenticodeSignature -LiteralPath $File\n'
                    'if($s.Status -ne "Valid" -or $s.SignerCertificate.Thumbprint -ne $Expected){exit 2}\n')
                with tempfile.TemporaryDirectory() as d:
                    script=Path(d)/'check.ps1';script.write_text(ps)
                    cmd('powershell.exe','-NoProfile','-NonInteractive','-File',script,path,thumb)
            else:
                team=os.environ.get('NEOSPECTOR_APPLE_TEAM_ID','').strip()
                if not re.fullmatch('[A-Z0-9]{10}',team):raise ReleaseBlocked('Expected Apple Developer Team ID is required')
                output=cmd('pkgutil','--check-signature',path)
                if team not in output:raise ReleaseBlocked('macOS package signed by unexpected team')
        assets[alias]={'file':path.name,'sha256':digest.hexdigest(),'bytes':size,'_path':str(path)}
    if not assets:raise ReleaseBlocked('At least one verified native installer is required')
    return assets

def verified_ci_assets(bundle_file,version,git_info,*,allow_preview=False):
    """Allow a cross-platform artifact only with a successful GitHub Actions
    run, same published commit, and native-runner validation receipts. A checkbox
    or a local JSON file alone is never sufficient evidence.
    """
    from owner_workflow import (REPO as CI_REPO,WORKFLOW_NAME,check_run,
                                verified_assets,OwnerBlocked)
    bundle=json.loads(Path(bundle_file).expanduser().read_text(encoding='utf-8'))
    if (bundle.get('schema')!=1 or bundle.get('repository')!=CI_REPO
        or bundle.get('workflow')!=WORKFLOW_NAME or bundle.get('version')!=version
        or bundle.get('commit')!=git_info['commit']):
        raise ReleaseBlocked('Synced native build is not for this published-source commit')
    expected=bundle.get('assets')
    if not isinstance(expected,dict) or not expected:
        raise ReleaseBlocked('No synced native installer artifacts')
    try:
        check_run(ROOT,bundle['run_id'],git_info['commit'])
        first=next(iter(expected.values()))
        if not isinstance(first,dict) or not first.get('receipt'):
            raise ReleaseBlocked('Missing runner evidence')
        root=Path(first['receipt']).resolve().parents[1]
        verified=verified_assets(root,version,git_info['commit'])
    except (OwnerBlocked,OSError,ValueError,KeyError,IndexError) as exc:
        raise ReleaseBlocked('Native CI proof failed: '+str(exc)) from exc
    if set(verified)!=set(expected):raise ReleaseBlocked('Synced native platform list changed')
    required_tier='preview' if allow_preview else 'stable'
    if any(x.get('tier')!=required_tier for x in verified.values()):
        raise ReleaseBlocked('Native CI trust level does not permit this publication channel')
    assets={}
    for alias,entry in verified.items():
        prior=expected[alias]
        if any(prior.get(key)!=entry.get(key) for key in ('file','sha256','bytes','_path')):
            raise ReleaseBlocked('Native build changed after GitHub verification: '+alias)
        assets[alias]={key:entry[key] for key in ('file','sha256','bytes','_path')}
    return assets


def release_payload(version,title,notes,git_info,assets):
    return validate_release({'schema':2,'product':'Neospector','channel':'stable','version':version,
      'title':title.strip(),'notes':notes.strip(),'date':datetime.date.today().isoformat(),
      'commit':git_info['commit'],'installers':{k:{j:v for j,v in entry.items() if j!='_path'} for k,entry in assets.items()}})

def preview(args):
    version=args.version;version_tuple(version)
    if not 1<=len(args.title.strip())<=140 or not 1<=len(args.notes.strip())<=8000:raise ReleaseBlocked('Update name and release notes are required')
    if source_version()!=version:raise ReleaseBlocked('Source release_identity.VERSION does not match proposed version; use prepare first')
    draft=ROOT/'web/release_draft.json'
    if not draft.is_file() or json.loads(draft.read_text())!={'version':version,'title':args.title.strip(),'notes':args.notes.strip()}:
        raise ReleaseBlocked('Committed release draft must match version/title/notes exactly; use prepare first')
    git_info=check_git_and_live(version)
    if not args.accepted_on_device:
        raise ReleaseBlocked('Native installer install/launch acceptance is required before publication')
    assets=verified_ci_assets(args.ci_bundle,version,git_info) if args.ci_bundle else native_assets(args,version)
    payload=release_payload(version,args.title,args.notes,git_info,assets)
    key=Path(args.key).expanduser()
    if not key.is_file() or not PUBLIC.is_file():raise ReleaseBlocked('Owner signing key or public verifier key missing')
    envelope=sign_release(payload,key)
    verify_release(envelope,PUBLIC)
    return {'payload':payload,'envelope':envelope,'assets':assets,'live':git_info['live']}

def new_catalogue(doc,prior):
    c=json.loads(json.dumps(prior))
    c.update({'version':doc['version'],'date':doc['date'],'title':doc['title'],'notes':doc['notes'],'commit':doc['commit']})
    old_hist=c.get('history',[])
    c['history']=[{'version':doc['version'],'title':doc['title'],'date':doc['date'],'notes':doc['notes'],'commit':doc['commit']}]+[x for x in old_hist if x.get('version')!=doc['version']][:99]
    for entry in c['downloads'].values():entry.update({'ready':False,'key':None,'sha256':None,'bytes':None})
    aliases={'linux-x64':'linux','windows-x64':'windows-x64','macos-arm64':'macos-arm64-pkg','macos-x64':'macos-x64-pkg'}
    for alias,record in doc['installers'].items():
        c['downloads'][aliases[alias]]={'ready':True,'key':'neospector/releases/'+record['file'],'sha256':record['sha256'],'bytes':record['bytes']}
    c['publication_note']='Native installers: '+', '.join(doc['installers'])
    return c

def publish(args):
    plan=preview(args)
    if not args.publish:return {'status':'READY / NO UPLOAD','version':args.version,'platforms':list(plan['assets']),'commit':plan['payload']['commit']}
    # Candidate is a private draft until every native asset is present.
    tag='v'+args.version
    try:cmd('gh','release','view',tag,'-R',REPO,'--json','id')
    except ReleaseBlocked:pass
    else:raise ReleaseBlocked('Release already exists; refusing to overwrite published artifacts')
    with tempfile.TemporaryDirectory(prefix='neospector-owner-release-') as d:
        notes_file=Path(d)/'notes.md';notes_file.write_text(args.notes,encoding='utf-8')
        cmd('gh','release','create',tag,'-R',REPO,'--target',plan['payload']['commit'],
            '--title',args.title,'--notes-file',notes_file,'--draft','--latest=false',timeout=180)
        paths=[v['_path'] for v in plan['assets'].values()]
        cmd('gh','release','upload',tag,*paths,'-R',REPO,timeout=400)
        remote=json.loads(cmd('gh','release','view',tag,'-R',REPO,'--json','assets,isDraft',timeout=90))
        if not remote.get('isDraft'):raise ReleaseBlocked('New release unexpectedly not a draft')
        found={a['name']:a.get('size') for a in remote['assets']}
        for record in plan['assets'].values():
            if found.get(record['file'])!=record['bytes']:raise ReleaseBlocked('GitHub asset identity/size mismatch; draft retained')
        # GH assets must be publicly reachable before Cloudflare fetch can proxy.
        # Publishing draft is irreversible, so do not call this a completed
        # public update until the Cloudflare deployment is independently verified.
        cmd('gh','release','edit',tag,'-R',REPO,'--draft=false',timeout=90)
        before={p:p.read_bytes() for p in (CATALOGUE,NATIVE,ROOT/'web/release_data.mjs')}
        try:
            CATALOGUE.write_text(json.dumps(new_catalogue(plan['payload'],plan['live']),indent=2)+'\n')
            NATIVE.write_text('export const SIGNED_INSTALLERS = '+json.dumps(plan['envelope'],sort_keys=True)+';\n')
            cmd(sys.executable,ROOT/'scripts/sync_release_data.py')
            cmd('wrangler','deploy',cwd=ROOT/'web',timeout=200)
            # Live verification is mandatory. Asset routes are immutable by tag.
            from urllib.request import urlopen
            def get(path):
                with urlopen('https://omne.space'+path,timeout=15) as resp:return resp.read(100000)
            live=json.loads(get('/neospector/updates/installers.json'))
            if verify_release(live,PUBLIC)!=plan['payload']:raise ReleaseBlocked('Live signed feed differs')
            website=json.loads(get('/downloads/neospector/releases.json'))
            if website['version']!=args.version or not any(x['version']==args.version for x in website.get('history',[])):
                raise ReleaseBlocked('Live website version/changelog did not advance')
        except Exception:
            # Keep local changes and logs for recovery; never imply the remote
            # release was rolled back after becoming visible on GitHub.
            raise
    return {'status':'PUBLISHED AND LIVE VERIFIED','version':args.version,'platforms':list(plan['assets']),'tag':tag,
            'next':'Review generated web metadata, commit and push publication changes.'}

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--version',required=True);ap.add_argument('--title',required=True)
    ap.add_argument('--notes-file',type=Path,required=True)
    for flag in ALIAS_FLAGS.values():ap.add_argument('--'+flag.replace('_','-'),dest=flag)
    ap.add_argument('--key',default=str(PRIVATE));ap.add_argument('--prepare',action='store_true')
    ap.add_argument('--publish',action='store_true')
    ap.add_argument('--ci-bundle',type=Path,help='Verified private GitHub Actions native artifact bundle')
    ap.add_argument('--accepted-on-device',action='store_true',help='Owner confirms native installer has been installed and tested')
    a=ap.parse_args(argv)
    try:
        a.notes=a.notes_file.read_text(encoding='utf-8').strip()
        result=prepare_version(a.version,a.title,a.notes) if a.prepare else publish(a)
        print(json.dumps(result,indent=2))
        return 0
    except (ReleaseBlocked,ValueError,OSError,UpdateError) as exc:
        print('RELEASE BLOCKED:',exc,file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
