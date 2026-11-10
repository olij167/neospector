#!/usr/bin/env python3
"""Explicit, fail-closed owner publishing of accepted Neospector native installers.

The accepted signed Linux source ZIP is never changed or re-signed. Public
release assets are uploaded before the public catalogue is updated.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys, tempfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CATALOGUE=ROOT/'web/releases.json'
REPO='olij167/neospector'
EXT={'linux':'.deb','windows-x64':'.exe','windows-x64-portable':'.zip',
     'macos-arm64':'.dmg','macos-x64':'.dmg',
     'macos-arm64-pkg':'.pkg','macos-x64-pkg':'.pkg'}

class PublicationError(Exception):pass

def inspect(alias,filepath):
    if alias not in EXT:raise PublicationError('Unsupported platform alias')
    path=Path(filepath).expanduser().resolve()
    if not path.is_file():raise PublicationError('Missing installer: '+str(path))
    doc=json.loads(CATALOGUE.read_text())
    version=doc.get('version','')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-ux[0-9]+',version):
        raise PublicationError('No valid approved catalogue version')
    if not re.fullmatch(r'Neospector_'+re.escape(version)+r'_[A-Za-z0-9_.-]+',path.name) or path.suffix.lower()!=EXT[alias]:
        raise PublicationError('Unexpected filename or extension for '+alias+': '+path.name)
    sidecar=path.with_name(path.name+'.sha256')
    if not sidecar.is_file():raise PublicationError('Missing SHA-256 sidecar: '+str(sidecar))
    expected=sidecar.read_text().strip().split()[0].lower()
    if not re.fullmatch('[0-9a-f]{64}',expected):raise PublicationError('Malformed checksum')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=expected:raise PublicationError('Installer SHA-256 mismatch')
    cat=doc
    if cat.get('schema')!=1:raise PublicationError('Incompatible catalogue')
    if alias not in cat['downloads']:raise PublicationError('Unrecognised catalogue alias')
    if alias=='linux':
        p=subprocess.run(['dpkg-deb','-f',str(path),'Package','Version','Architecture'],capture_output=True,text=True)
        values=dict(line.split(': ',1) for line in p.stdout.strip().splitlines() if ': ' in line)
        if p.returncode or [values.get(k) for k in ('Package','Version','Architecture')]!=['neospector',version.replace('-','~'),'amd64']:
            raise PublicationError('DEB identity mismatch: '+p.stdout.strip())
    return path,sidecar,digest,cat

def run(*argv):
    proc=subprocess.run(argv,capture_output=True,text=True)
    if proc.returncode:raise PublicationError('Command failed: '+str(argv)+'\n'+(proc.stderr or proc.stdout)[-2000:])
    return proc.stdout

def verify_native_trust(alias, path):
    """Verify publisher identity on the native OS before a non-Linux upload.

    A signed checkbox, hash sidecar or plain JSON attestation is not proof.
    Cross-platform remote attestations are deliberately not inferred here.
    """
    if alias=='linux':return
    if alias.startswith('windows-'):
        if sys.platform!='win32':raise PublicationError('Windows signing must be validated on Windows')
        thumb=os.environ.get('NEOSPECTOR_WINDOWS_CERT_THUMBPRINT','').replace(' ','').upper()
        if not re.fullmatch(r'[A-F0-9]{40}',thumb):
            raise PublicationError('Expected Windows certificate thumbprint not configured')
        def check(executable):
            # The PowerShell command is constant. File path is passed through
            # an environment variable, never embedded in an executable string.
            env=dict(os.environ,NEOSPECTOR_VERIFY_PATH=str(executable))
            ps=("$ErrorActionPreference='Stop'; "
                "$s=Get-AuthenticodeSignature -LiteralPath $env:NEOSPECTOR_VERIFY_PATH; "
                "if($s.Status -ne 'Valid' -or $null -eq $s.SignerCertificate){exit 4}; "
                "$s.SignerCertificate.Thumbprint")
            proc=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',ps],
                                capture_output=True,text=True,env=env)
            if proc.returncode or proc.stdout.strip().upper()!=thumb:
                raise PublicationError('Windows Authenticode or publisher verification failed')
        if alias=='windows-x64-portable':
            with tempfile.TemporaryDirectory(prefix='neospector-verify-') as t:
                try:
                    with zipfile.ZipFile(path) as z:
                        matches=[n for n in z.namelist() if n.split('/')[-1]=='Neospector.exe' and not n.endswith('/')]
                        if len(matches)!=1:raise PublicationError('Portable ZIP must contain one Neospector.exe')
                        item=z.getinfo(matches[0])
                        if item.file_size>600*1024*1024:raise PublicationError('Executable too large')
                        exe=Path(t)/'Neospector.exe';exe.write_bytes(z.read(item));check(exe)
                except zipfile.BadZipFile as e:raise PublicationError('Invalid portable ZIP') from e
        else:check(path)
        return
    if alias.startswith('macos-'):
        if sys.platform!='darwin':raise PublicationError('macOS signing must be validated on macOS')
        team=os.environ.get('NEOSPECTOR_APPLE_TEAM_ID','').strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{10}',team):
            raise PublicationError('Expected Apple Developer team ID not configured')
        def execute(*args):
            proc=subprocess.run(args,capture_output=True,text=True)
            if proc.returncode:raise PublicationError('Apple verification failed: '+str(args[:3])+': '+(proc.stderr or proc.stdout)[-400:])
            return proc.stdout+proc.stderr
        execute('xcrun','stapler','validate',str(path))
        if path.suffix=='.pkg':
            info=execute('pkgutil','--check-signature',str(path))
            if 'Developer ID Installer' not in info or '('+team+')' not in info:
                raise PublicationError('Package not signed by expected Developer ID Installer')
            execute('spctl','--assess','--type','install','--verbose=4',str(path))
        elif path.suffix=='.dmg':
            execute('spctl','--assess','--type','open','--verbose=4',str(path))
            with tempfile.TemporaryDirectory(prefix='neospector-mount-') as t:
                execute('hdiutil','attach','-readonly','-nobrowse','-mountpoint',t,str(path))
                try:
                    app=Path(t)/'Neospector.app'
                    if not app.is_dir():raise PublicationError('Neospector.app missing from disk image')
                    execute('codesign','--verify','--deep','--strict',str(app))
                    output=execute('codesign','-dv','--verbose=4',str(app))
                    if 'TeamIdentifier='+team not in output:
                        raise PublicationError('Application signed by wrong developer team')
                    execute('spctl','--assess','--type','execute','--verbose=4',str(app))
                finally:execute('hdiutil','detach',t)
        else:raise PublicationError('Unsupported macOS distribution format')
        return
    raise PublicationError('Unknown platform')


def publish(alias,filepath,*,tested):
    path,sha,digest,doc=inspect(alias,filepath)
    if not tested:raise PublicationError('Native installation and launch acceptance must be explicitly confirmed')
    verify_native_trust(alias,path)
    name=path.name
    tag='v'+doc['version']
    run('gh','release','upload',tag,str(path),str(sha),'-R',REPO)
    assets=json.loads(run('gh','release','view',tag,'-R',REPO,'--json','assets'))['assets']
    names={a['name'] for a in assets}
    if name not in names or sha.name not in names:raise PublicationError('Release asset not visible after upload')
    doc['downloads'][alias]={'ready':True,'key':'neospector/releases/'+name,
                             'sha256':digest,'bytes':path.stat().st_size}
    ready=[k for k,x in doc['downloads'].items() if x['ready']]
    doc['publication_note']='Approved downloads: '+', '.join(ready)
    tmp=CATALOGUE.with_suffix('.json.tmp');tmp.write_text(json.dumps(doc,indent=2)+'\n');tmp.replace(CATALOGUE)
    run(sys.executable,str(ROOT/'scripts/sync_release_data.py'))
    # This JSON is a separate GitHub release asset; signed stable.json stays unchanged.
    run('gh','release','upload',tag,str(CATALOGUE),'--clobber','-R',REPO)
    print('PUBLISHED ASSET + CATALOGUE:',name)
    print('NEXT: cd web && wrangler deploy')
    print('NEXT: git add web/releases.json web/release_data.mjs && git commit && git push')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('alias',choices=tuple(EXT))
    parser.add_argument('artifact',type=Path)
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--accepted',action='store_true',help='Owner confirms actual native installation and launch')
    a=parser.parse_args()
    try:
        if a.publish:publish(a.alias,a.artifact,tested=a.accepted)
        else:
            path,sha,digest,doc=inspect(a.alias,a.artifact)
            print('CHECK PASS:',a.alias,path.name,path.stat().st_size,'bytes',digest)
            print('No upload or catalogue change. Publish only after native acceptance.')
    except PublicationError as e:raise SystemExit('NOT PUBLISHED: '+str(e))
