#!/usr/bin/env python3
"""Neospector Owner Publisher — offline signing and optional SSH publication.

No account credentials, SSH keys or signing keys are bundled with this companion.
Only the owner supplies a private signing key. Public Neospector copies embed its
corresponding pinned public key.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,os,re,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path

VERSION_RE=re.compile(r'^\d+\.\d+\.\d+(?:-[a-zA-Z0-9][a-zA-Z0-9.-]*)?$')
FILE_RE=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*\.zip$')

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')

def package_version(archive):
    import ast
    with zipfile.ZipFile(archive) as z:
        names=[name for name in z.namelist() if name.endswith('/app_source/release_identity.py')]
        if len(names)!=1:raise ValueError('Expected exactly one version identity in ZIP')
        source=z.read(names[0]);node=ast.parse(source)
        versions=[item.value.value for item in node.body if isinstance(item,ast.Assign)
                  and any(isinstance(x,ast.Name) and x.id=='VERSION' for x in item.targets)
                  and isinstance(item.value,ast.Constant) and isinstance(item.value.value,str)]
        if len(versions)!=1 or not VERSION_RE.fullmatch(versions[0]):raise ValueError('Invalid Neospector version')
        return versions[0]

def sign(payload,key):
    key=Path(key).expanduser().resolve()
    if not key.is_file():raise ValueError('Owner signing key file was not found')
    # Require owner-controlled private-file permissions on Linux, preventing casual disclosure.
    if os.name=='posix' and key.stat().st_mode & 0o077:raise ValueError('Private signing key must be chmod 600')
    with tempfile.TemporaryDirectory(prefix='neospector-owner-sign-') as tmp:
        message=Path(tmp)/'message';signature=Path(tmp)/'signature'
        message.write_bytes(canonical(payload))
        proc=subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(key),'-rawin','-in',str(message),'-out',str(signature)],
                            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=12)
        if proc.returncode:raise ValueError('Could not sign with owner key: '+proc.stderr.decode(errors='replace')[:200])
        raw=signature.read_bytes()
        if len(raw)!=64:raise ValueError('Invalid Ed25519 signature')
        return base64.b64encode(raw).decode('ascii')

def prepare(archive,key,output,notes):
    archive=Path(archive).expanduser().resolve()
    if not archive.is_file() or not FILE_RE.fullmatch(archive.name):raise ValueError('Choose a Neospector ZIP file')
    if not zipfile.is_zipfile(archive) or archive.stat().st_size>400*1024*1024:raise ValueError('Invalid/oversized ZIP')
    if len(notes)>2500:raise ValueError('Release notes must be 2500 characters or fewer')
    version=package_version(archive)
    h=hashlib.sha256()
    with archive.open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    payload={'schema':1,'product':'Neospector','channel':'stable','platform':'linux-x86_64',
             'version':version,'archive':archive.name,'sha256':h.hexdigest(),
             'bytes':archive.stat().st_size,'notes':notes.strip()}
    envelope={'payload':payload,'signature':sign(payload,key)}
    output=Path(output).expanduser().resolve();output.mkdir(parents=True,exist_ok=True)
    target=output/archive.name
    if target!=archive:shutil.copy2(archive,target)
    temp=output/'stable.json.tmp';temp.write_text(json.dumps(envelope,indent=2)+'\n')
    os.replace(temp,output/'stable.json')
    return payload,output/'stable.json'

def deploy(folder,destination):
    """Optional owner's explicit SSH destination, using their normal SSH identity."""
    if not re.fullmatch(r'[A-Za-z0-9_.@-]+:/[A-Za-z0-9_./-]+',destination) or '..' in destination:
        raise ValueError('SSH destination must be user@host:/absolute/path without traversal')
    folder=Path(folder)
    doc=json.loads((folder/'stable.json').read_text())
    archive=folder/doc['payload']['archive']
    if not archive.is_file():raise ValueError('Release archive is missing from staging')
    if not shutil.which('rsync'):raise ValueError('rsync is not installed')
    # Upload archive first, and manifest last; existing feed stays valid until ready.
    for file in (archive,folder/'stable.json'):
        proc=subprocess.run(['rsync','-av','--',str(file),destination.rstrip('/')+'/'],timeout=180)
        if proc.returncode:raise ValueError('Upload failed; release feed may not have changed')
    return True

def deploy_rclone(folder,target):
    """Optional authenticated rclone target (Cloudflare R2, WebDAV, S3, etc.)."""
    if not isinstance(target,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+:[A-Za-z0-9_./-]+',target) or '..' in target:
        raise ValueError('Rclone target must be remote:bucket/path with no traversal')
    if not shutil.which('rclone'):raise ValueError('rclone is not installed or configured')
    folder=Path(folder);doc=json.loads((folder/'stable.json').read_text());archive=folder/doc['payload']['archive']
    if not archive.is_file():raise ValueError('Release archive missing from staging')
    for item in (archive,folder/'stable.json'):
        remote=target.rstrip('/')+'/'+item.name
        proc=subprocess.run(['rclone','copyto',str(item),remote],timeout=240)
        if proc.returncode:raise ValueError('Rclone upload failed; check remote and credentials')
    return True

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('prepare',help='Sign and stage one release ZIP')
    for flag in ('archive','key','output'):p.add_argument('--'+flag,required=True)
    p.add_argument('--notes',default='Neospector signed release.')
    q=sub.add_parser('deploy',help='Upload a prepared feed over your configured SSH access')
    q.add_argument('--folder',required=True)
    destinations=q.add_mutually_exclusive_group(required=True)
    destinations.add_argument('--ssh-target');destinations.add_argument('--rclone-target')
    args=parser.parse_args(argv)
    try:
        if args.cmd=='prepare':
            payload,manifest=prepare(args.archive,args.key,args.output,args.notes)
            print('Signed:',payload['version']);print('Staged:',manifest.parent)
            print('Deploy ZIP first, stable.json last to the HTTPS update directory.')
        elif args.ssh_target:deploy(args.folder,args.ssh_target);print('Uploaded release archive and signed feed to SSH target')
        else:deploy_rclone(args.folder,args.rclone_target);print('Uploaded release archive and signed feed with rclone')
        return 0
    except (OSError,ValueError,subprocess.TimeoutExpired) as e:print('SAFE STOP:',str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
