#!/usr/bin/env python3
"""Fail-closed DEB payload audit: no developer tools, docs, .git or source ZIPs."""
from __future__ import annotations
import argparse, subprocess
from pathlib import Path
DENY_PARTS={'tests','tools','web','.git','.github','.runtime-neospector-omne-r5',
    'evidence','examples','docs','scripts','build-work','artifacts','__pycache__'}
DENY_EXTS={'.zip','.md','.pyc','.pyo','.pem.key','.pfx','.p12'}
class ShippingError(RuntimeError):pass

def verify_deb(path):
    source=Path(path)
    if not source.is_file() or source.suffix!='.deb':raise ShippingError('Not a Debian installer')
    result=subprocess.run(['dpkg-deb','--contents',str(source)],capture_output=True,text=True,timeout=60)
    if result.returncode:raise ShippingError('Cannot inspect DEB contents')
    entries=[]
    for line in result.stdout.splitlines():
        if not line.strip():continue
        name=line.split()[-1]
        if name.endswith('/'):continue
        entries.append(name)
        parts=set(Path(name).parts)
        # The frozen runtime may contain a `tools/` folder holding required
        # ffmpeg binaries: inspect the actual location rather than blanket ban.
        if parts & (DENY_PARTS-{'tools'}):raise ShippingError('Developer directory in installer: '+name)
        if name.endswith(tuple(DENY_EXTS)):raise ShippingError('Developer file in installer: '+name)
        if name.startswith('./opt/neospector/tools/') and not name.endswith(('ffmpeg','ffprobe','ffplay')):
            raise ShippingError('Unexpected updater/build tool in runtime: '+name)
    if not any(x.endswith('/opt/neospector/Neospector') for x in entries):raise ShippingError('Native app missing')
    if not any(x.endswith('/opt/neospector/NeospectorUpdater') for x in entries):raise ShippingError('Native updater missing')
    if not any(x.endswith('/opt/neospector/updates/public.pem') for x in entries):raise ShippingError('Pinned publisher key missing')
    return len(entries)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('deb');a=p.parse_args()
    try:print('SHIPPING PAYLOAD VERIFIED:',verify_deb(a.deb),'files')
    except ShippingError as e:raise SystemExit('SHIPPING BLOCKED: '+str(e))
