#!/usr/bin/env python3
"""Owner-approved Neospector GitHub -> Cloudflare publication (never implicit).

This publishes a *signed source ZIP* for the existing Linux updater.
Windows/macOS readiness remains false until native signing and acceptance.
Owner key is used only by the separate staging utility; this script does not
need, load, copy, or upload any private key.
"""
from __future__ import annotations
import argparse, ast, datetime, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app_source'))
sys.path.insert(0, str(ROOT / 'tools'))
from signed_updates import version_tuple, verify_envelope, verify_archive, UpdateError
from publication_companion import verify_staged, verify_live

CATALOGUE = ROOT / 'web/releases.json'
STABLE = ROOT / 'web/stable.json'
REPO = 'olij167/neospector'
FEED = 'https://omne.space/neospector/updates/stable.json'

class PublicationError(RuntimeError):
    pass


def command(args, *, cwd=ROOT):
    proc = subprocess.run(list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=300, check=False)
    if proc.returncode:
        raise PublicationError('Command failed: ' + ' '.join(args[:3]) + '\n' + (proc.stderr or proc.stdout)[-600:])
    return proc.stdout


def read_source_version():
    tree = ast.parse((ROOT/'app_source/release_identity.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets):
            if isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
                return node.value.value
    raise PublicationError('No literal VERSION in release_identity.py')


def release_plan(stage, public_key):
    record = verify_staged(stage, public_key)
    if record['platform'] != 'linux-x86_64':
        raise PublicationError('Only the Linux source ZIP feed is implemented')
    old = json.loads(STABLE.read_text())
    installed = verify_envelope(old, public_key)
    if version_tuple(record['version']) <= version_tuple(installed['version']):
        raise PublicationError('New release must be newer than the live signed feed')
    if record['version'] != read_source_version():
        raise PublicationError('Staged version does not match current repository release_identity.py')
    cat=json.loads(CATALOGUE.read_text())
    if cat.get('schema') != 1 or cat.get('product') != 'Neospector':
        raise PublicationError('Invalid repository release catalogue')
    tag='v'+record['version']
    return record, tag, cat


def check_remote(tag):
    info=json.loads(command(['gh','release','view',tag,'-R',REPO,'--json','isDraft,isPrerelease,assets']))
    if info.get('isDraft') or info.get('isPrerelease'):
        raise PublicationError('GitHub release must be stable and published before Worker promotion')
    return info


def prepare_catalogue(record, existing):
    doc=json.loads(json.dumps(existing))
    doc['version']=record['version']
    doc['date']=datetime.date.today().isoformat()
    doc['publication_note']='Approved downloads: linux-zip'
    for alias, entry in doc['downloads'].items():
        entry.update({'ready': False, 'key': None, 'sha256': None, 'bytes': None})
    doc['downloads']['linux-zip'] = {'ready': True, 'key':'neospector/updates/'+record['archive'],
                                      'sha256':record['sha256'], 'bytes':record['bytes']}
    return doc


def publish(stage, public_key, feed_url=FEED, *, dry_run=True):
    stage=Path(stage).expanduser().resolve()
    public_key=Path(public_key).expanduser().resolve()
    record, tag, catalogue=release_plan(stage,public_key)
    if dry_run:
        return {'tag':tag,'version':record['version'],'archive':record['archive'], 'mode':'preflight-only'}
    # Never upload if any preflight check fails.
    if not shutil.which('gh') or not shutil.which('wrangler'):
        raise PublicationError('GitHub CLI (gh) and wrangler are required on the owner workstation')
    info=check_remote(tag)
    names={a['name'] for a in info.get('assets', [])}
    if record['archive'] in names:
        raise PublicationError('GitHub release ZIP already exists: refusing clobber')
    source=stage/record['archive']
    verify_archive(source,record)
    command(['gh','release','upload',tag,str(source),'-R',REPO])
    with tempfile.TemporaryDirectory(prefix='neospector-publish-verify-') as temp:
        command(['gh','release','download',tag,'-R',REPO,'--pattern',record['archive'],'--dir',temp])
        verify_archive(Path(temp)/record['archive'],record)
    info=check_remote(tag)
    if record['archive'] not in {a['name'] for a in info.get('assets', [])}:
        raise PublicationError('Uploaded ZIP not visible in GitHub Release')
    # Only now prepare a new Worker feed. Local files are restored on deploy failure;
    # deployed content is always verified live before declaring success.
    prior={file:file.read_bytes() for file in (STABLE,CATALOGUE,ROOT/'web/release_data.mjs')}
    try:
        STABLE.write_text(json.dumps(json.loads((stage/'stable.json').read_text()),indent=2)+'\n')
        CATALOGUE.write_text(json.dumps(prepare_catalogue(record,catalogue),indent=2)+'\n')
        command([sys.executable,str(ROOT/'scripts/sync_release_data.py')])
        command(['wrangler','deploy'],cwd=ROOT/'web')
        verified=verify_live(feed_url,stage,public_key)
        if verified!=record:
            raise PublicationError('Live signed release differs from staged record')
    except BaseException:
        for file,data in prior.items():file.write_bytes(data)
        raise
    return {'tag':tag,'version':record['version'],'archive':record['archive'], 'mode':'published-and-verified'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',required=True)
    parser.add_argument('--public-key',default=str(ROOT/'updates/public.pem'))
    parser.add_argument('--feed-url',default=FEED)
    parser.add_argument('--publish',action='store_true',help='EXPLICIT remote upload and Cloudflare deploy')
    args=parser.parse_args(argv)
    try:
        result=publish(args.stage,args.public_key,args.feed_url,dry_run=not args.publish)
        print(json.dumps(result,indent=2))
    except (PublicationError,UpdateError,ValueError,OSError,subprocess.TimeoutExpired) as error:
        print('NOT PUBLISHED: '+str(error),file=sys.stderr)
        return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
