#!/usr/bin/env python3
"""Emit a native build receipt only after a runner's build/verification job passes.

GitHub Actions stores receipts alongside the private installer artifacts. The
owner syncs and checks these against the successful workflow run/commit.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,sys
from pathlib import Path

REQUIRED={'linux-x64':'shipping-audit','windows-x64':'authenticode-valid',
          'macos-arm64':'notarized','macos-x64':'notarized'}
RUNNER={'linux-x64':'Linux','windows-x64':'Windows','macos-arm64':'macOS','macos-x64':'macOS'}
SUFFIX={'linux-x64':'.deb','windows-x64':'_Setup.exe','macos-arm64':'.pkg','macos-x64':'.pkg'}

def receipt(platform,version,commit,path,checks,runner,tier='stable'):
    if platform not in REQUIRED or not re.fullmatch(r'\d+\.\d+\.\d+(?:-ux\d+)?',version):raise ValueError('Invalid version/platform')
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Invalid commit')
    p=Path(path)
    if not p.is_file() or p.is_symlink() or not p.name.startswith('Neospector_'+version+'_'+platform) or not p.name.endswith(SUFFIX[platform]):
        raise ValueError('Native installer filename must match prepared version and platform')
    if tier not in ('stable','preview'):raise ValueError('Invalid release tier')
    required=(REQUIRED[platform],) if tier=='stable' else ('installer-created','build-smoke')
    if RUNNER[platform]!=runner or not set(required).issubset(checks):
        raise ValueError('Required native runner checks not recorded')
    h=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):h.update(chunk)
    digest=h.hexdigest()
    return {'schema':1,'version':version,'platform':platform,'commit':commit,'runner':runner,
            'verified':True,'tier':tier,'file':p.name,'sha256':digest,'bytes':p.stat().st_size,
            'checks':sorted(set(checks))}

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--platform',required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--file',required=True,type=Path)
    parser.add_argument('--check',action='append',required=True)
    parser.add_argument('--tier',choices=('stable','preview'),default='stable')
    parser.add_argument('--runner',required=True)
    a=parser.parse_args(argv)
    try:
        data=receipt(a.platform,a.version,a.commit,a.file,a.check,a.runner,a.tier)
        out=a.file.with_name('ci-receipt-'+a.platform+'.json')
        out.write_text(json.dumps(data,indent=2)+'\n')
        Path(str(a.file)+'.sha256').write_text(data['sha256']+'  '+a.file.name+'\n')
        print(out);return 0
    except (ValueError,OSError) as exc:
        print('NATIVE BUILD BLOCKED: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
