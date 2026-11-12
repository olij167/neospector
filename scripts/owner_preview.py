#!/usr/bin/env python3
"""Owner-approved first public test release: four native installer files, one version.

This is deliberately NOT the stable signed auto-update channel. It publishes
checksummed native installers labelled 'TEST BUILD' for participants to install
on Windows/macOS hardware the owner doesn't have. GitHub runner receipts prove
build provenance, not real user-device acceptance or publisher code signing.
"""
from __future__ import annotations
import datetime
import json
import re
import sys
import tempfile
from pathlib import Path
from owner_site_http import site_json

from owner_release import ROOT, CATALOGUE, REPO, cmd, source_version, check_git_and_live, verified_ci_assets, ReleaseBlocked

ALIASES = {'linux-x64': 'linux', 'windows-x64': 'windows-x64',
           'macos-arm64': 'macos-arm64-pkg', 'macos-x64': 'macos-x64-pkg'}
REQUIRED = set(ALIASES)


def public_test_catalogue(version, title, notes, git_info, assets):
    """Do not mutate the existing signed installer feed or its pinned key."""
    old = git_info['live']
    data = json.loads(json.dumps(old))
    if set(assets) != REQUIRED:
        raise ReleaseBlocked('All four native installers are mandatory for the v1.0 test release')
    date = datetime.date.today().isoformat()
    data.update(version=version, title=title.strip(), notes=notes.strip(), date=date,
                commit=git_info['commit'], release_stage='public-test',
                preview_tag='v' + version,
                publication_note=f'{version} public test release · installers need platform user testing',
                signed_auto_updates=False)
    history = data.get('history') or []
    data['history'] = [dict(version=version, title=title.strip(), notes=notes.strip(),
                            commit=git_info['commit'], date=date, stage='public-test')]
    data['history'] += [x for x in history if x.get('version') != version][:99]
    # Clear old aliases, especially the previously shipped ZIP.
    for entry in data.get('downloads', {}).values():
        entry.update(ready=False, key=None, sha256=None, bytes=None)
    for alias, output in assets.items():
        public_key = ALIASES[alias]
        data['downloads'][public_key] = dict(ready=True,
            key='neospector/releases/' + output['file'],
            sha256=output['sha256'], bytes=output['bytes'],
            release_tag='v' + version, stage='public-test',
            trust='signed' if output.get('trusted') else 'unsigned-or-unnotarized',
            notice=('Publisher-signed' if output.get('trusted') else
                    'Unverified test build: OS security warnings or blocking may occur'))
    return data


def preview_publication(repo, version, title, notes, bundle_file, *, publish=False):
    repo = Path(repo).resolve()
    if repo != ROOT:
        # source scripts run from user's checkout, not a copied working directory
        raise ReleaseBlocked('Publisher scripts must run from the active project checkout')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ReleaseBlocked('Use a stable version like 1.0.0')
    if not 1 <= len(title.strip()) <= 140 or not 1 <= len(notes.strip()) <= 8000:
        raise ReleaseBlocked('Version name and update notes are required')
    if source_version() != version:
        raise ReleaseBlocked('Prepare & Push the selected source version first')
    draft = json.loads((repo/'web/release_draft.json').read_text())
    if draft.get('version') != version:
        raise ReleaseBlocked('Release draft version differs from the built application version')
    git_info = check_git_and_live(version)
    assets = verified_ci_assets(bundle_file, version, git_info, allow_preview=True)
    if set(assets) != REQUIRED:
        raise ReleaseBlocked('All four installer builds must be synced together before publishing')
    # Explicit trust is checked against native-runner receipts. An unknown or
    # unnotarized artifact is NEVER allowed into signed automatic updates.
    catalogue = public_test_catalogue(version, title, notes, git_info, assets)
    result = {'status':'PUBLIC TEST BUILD READY / NOT YET PUBLISHED', 'version':version,
              'commit':git_info['commit'], 'installer_files':sorted(x['file'] for x in assets.values()),
              'platforms':sorted(assets), 'signed_auto_updates':False,
              'note':'Public test downloads are not verified production installers.'}
    if not publish:
        return result
    tag = 'v' + version
    try:
        cmd('gh', 'release', 'view', tag, '-R', REPO, '--json', 'id')
    except ReleaseBlocked:
        pass
    else:
        raise ReleaseBlocked('The release tag already exists; refusing to overwrite test installers')
    with tempfile.TemporaryDirectory(prefix='neospector-public-testing-') as d:
        notes_file = Path(d)/'release-notes.md'
        notes_file.write_text('# Public testing release\n\n'
            'Linux, Windows and macOS native installers. Windows/macOS users should expect '
            'that test builds may be unsigned or not notarized, and operating systems may block installation. '
            'This build has not been verified on the owner\'s Windows/macOS devices. '
            'Do not disable operating-system protections.\n\n' + notes, encoding='utf-8')
        cmd('gh','release','create',tag,'-R',REPO,'--target',git_info['commit'],
            '--title',f'Neospector {version} · Public testing', '--notes-file',notes_file,
            '--draft','--prerelease','--latest=false',timeout=180)
        upload=[p for x in assets.values() for p in (x['_path'], x['_path']+'.sha256')]
        cmd('gh','release','upload',tag,*upload,'-R',REPO,timeout=400)
        remote=json.loads(cmd('gh','release','view',tag,'-R',REPO,'--json','assets,isDraft',timeout=90))
        if remote.get('isDraft') is not True:
            raise ReleaseBlocked('GitHub public testing release unexpectedly not a draft')
        got={a['name']:a.get('size') for a in remote['assets']}
        for item in assets.values():
            if got.get(item['file'])!=item['bytes']:
                raise ReleaseBlocked('GitHub installer size mismatch; draft retained')
        # An owner-confirmed public-test release. This step exposes unsigned
        # test builds with a clear GitHub pre-release label.
        cmd('gh','release','edit',tag,'-R',REPO,'--draft=false','--prerelease',timeout=90)
        before=CATALOGUE.read_bytes()
        try:
            CATALOGUE.write_text(json.dumps(catalogue,indent=2)+'\n')
            cmd(sys.executable,repo/'scripts/sync_release_data.py')
            cmd('wrangler','deploy',cwd=repo/'web',timeout=220)
            live=site_json('/downloads/neospector/releases.json',timeout=18,max_bytes=65536)
            if (live.get('version')!=version or live.get('release_stage')!='public-test'
                    or live.get('preview_tag')!=tag or
                    not all(live['downloads'].get(alias,{}).get('ready') for alias in ALIASES.values())):
                raise ReleaseBlocked('Cloudflare did not serve the full native test catalogue')
        except Exception:
            CATALOGUE.write_bytes(before)
            cmd(sys.executable,repo/'scripts/sync_release_data.py')
            raise
    result.update(status='PUBLIC TEST RELEASE LIVE',
                  downloads='https://omne.space/downloads/neospector',
                  changelog='https://omne.space/downloads/neospector/changelog',
                  source_version=version)
    return result
