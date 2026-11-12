"""Proof-of-origin validator for assembling four native installers from distinct CI runs.

All assets must be from successful, same-commit, same-version GitHub Actions runs.
A CI receipt is not a substitute for installer code-signing or device acceptance.
"""
from __future__ import annotations
import json
from pathlib import Path

ALIASES = {'linux-x64':'linux-x64', 'windows-x64':'windows-x64',
           'macos-arm64':'macos (macos-15, arm64)',
           'macos-x64':'macos (macos-15-intel, x64)'}


def verify_multi_bundle(bundle_file, version, git_info, *, allow_preview=False):
    from owner_release import ROOT, ReleaseBlocked, REPO
    from owner_workflow import WORKFLOW_NAME, check_run, verified_assets, OwnerBlocked
    bundle=json.loads(Path(bundle_file).expanduser().read_text(encoding='utf-8'))
    required=set(ALIASES)
    if (bundle.get('schema')!=2 or bundle.get('repository')!=REPO
        or bundle.get('workflow')!=WORKFLOW_NAME or bundle.get('version')!=version
        or bundle.get('commit')!=git_info['commit']
        or set(bundle.get('assets',{}))!=required
        or set(bundle.get('run_ids',{}))!=required):
        raise ReleaseBlocked('Multi-run CI bundle identity or platform set does not match this release')
    result={}
    try:
        for alias in sorted(required):
            prior=bundle['assets'][alias]
            run_id=bundle['run_ids'][alias]
            if not isinstance(run_id,int) or run_id<=0:
                raise ReleaseBlocked('Invalid GitHub run ID for '+alias)
            run=check_run(ROOT,run_id,git_info['commit'])
            # Validate the required exact platform job, not just a successful workflow.
            import subprocess
            p=subprocess.run(['gh','run','view',str(run_id),'-R',REPO,'--json','jobs'],
                             cwd=ROOT,text=True,capture_output=True,timeout=120)
            if p.returncode:raise ReleaseBlocked('Could not check GitHub platform job for '+alias)
            jobs=json.loads(p.stdout).get('jobs') or []
            if not any(j.get('name')==ALIASES[alias] and j.get('status')=='completed'
                       and j.get('conclusion')=='success' for j in jobs):
                raise ReleaseBlocked('Platform job did not succeed in build '+str(run_id)+': '+alias)
            receipt=Path(prior['receipt']).resolve(strict=True)
            if receipt.name!='ci-receipt-'+alias+'.json' or receipt.is_symlink():
                raise ReleaseBlocked('Unexpected native receipt path: '+alias)
            # gh run download uses per-artifact named subdirectories.
            root=receipt.parent.parent
            verified=verified_assets(root,version,git_info['commit'])
            if alias not in verified:raise ReleaseBlocked('Missing verified native installer for '+alias)
            item=verified[alias]
            if item.get('tier')!=('preview' if allow_preview else 'stable'):
                raise ReleaseBlocked('Installer is not approved for this release channel: '+alias)
            if any(prior.get(k)!=item.get(k) for k in ('file','sha256','bytes','_path','receipt')):
                raise ReleaseBlocked('Native installer or receipt changed after verification: '+alias)
            result[alias]={k:item[k] for k in ('file','sha256','bytes','_path')}
    except (OSError,KeyError,ValueError,OwnerBlocked) as exc:
        raise ReleaseBlocked('Multi-run native installer proof invalid: '+str(exc)) from exc
    return result
