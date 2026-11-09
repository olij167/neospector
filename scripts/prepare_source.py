#!/usr/bin/env python3
"""Verify the accepted UX41 source ZIP and safely extract it for native builders."""
from __future__ import annotations
import argparse,hashlib,os,stat,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'source/Neospector_UX41_Final_Reactions_PingPong_20261109.zip'

def verify(root=ROOT):
    archive=root/'source/Neospector_UX41_Final_Reactions_PingPong_20261109.zip'
    checksum=archive.with_suffix('.zip.sha256')
    line=checksum.read_text().strip().split()
    if len(line)!=2 or line[1].lstrip('*')!=archive.name:raise ValueError('Bad source checksum file')
    with archive.open('rb') as fh: h=hashlib.file_digest(fh,'sha256').hexdigest()
    if h!=line[0]:raise ValueError('Source archive SHA-256 mismatch')
    with zipfile.ZipFile(archive) as z:
        items=z.infolist();names=set();roots=set();total=0
        for item in items:
            name=item.filename
            parts=Path(name).parts
            if not parts or '..' in parts or '.' in parts or name.startswith('/') or '\\' in name or name in names:
                raise ValueError('Unsafe or duplicated source entry')
            if (item.external_attr>>16)&0o170000 not in (0,stat.S_IFREG,stat.S_IFDIR):
                raise ValueError('Unsupported source entry')
            names.add(name);roots.add(parts[0]);total+=item.file_size
            if total>1600*1024*1024 or len(items)>5000:raise ValueError('Source archive exceeds safety limits')
        if len(roots)!=1:raise ValueError('Expected single source root')
        member=next(iter(roots))
        needed={member+'/MANIFEST.sha256',member+'/app_source/neospector.py',member+'/app_source/release_identity.py'}
        if not needed.issubset(names):raise ValueError('Missing UX41 source files')
        manifest=z.read(member+'/MANIFEST.sha256').decode().splitlines()
        expected={}
        for row in manifest:
            digest,sep,path=row.partition('  ')
            if sep!='  ' or len(digest)!=64 or path in expected:raise ValueError('Bad release manifest')
            expected[path]=digest
        actual={n[len(member)+1:] for n in names if n.startswith(member+'/') and not n.endswith('/') and n!=member+'/MANIFEST.sha256'}
        if actual!=set(expected):raise ValueError('Release manifest membership mismatch')
        for path,digest in expected.items():
            if hashlib.sha256(z.read(member+'/'+path)).hexdigest()!=digest:raise ValueError('Release manifest checksum mismatch: '+path)
    return archive,member,len(expected)

def extract(out,root=ROOT):
    archive,member,n=verify(root)
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('Target must be empty')
    with zipfile.ZipFile(archive) as z:z.extractall(out)
    return out/member,n

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',default=str(ROOT/'build-work/source'));ap.add_argument('--verify-only',action='store_true');args=ap.parse_args()
    if args.verify_only:
        a,r,n=verify();print(f'Verified accepted {a.name}, {n} manifest files')
    else:
        location=Path(args.output)
        if location.exists():
            if any(location.iterdir()):
                print('Using existing extraction; verifying source archive and local identity')
                _,name,n=verify();root=location/name
                if not (root/'app_source/neospector.py').is_file():raise SystemExit('Incomplete source extraction')
            else:root,n=extract(location)
        else:root,n=extract(location)
        print(root)
