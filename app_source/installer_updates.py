"""Signed installer-only release metadata for Neospector native distributions.

This deliberately does not accept the legacy source-ZIP feed. A version is
shown only if a native installer exists for the running OS and architecture.
"""
from __future__ import annotations
import base64, hashlib, json, os, platform, re, tempfile, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from signed_updates import canonical, version_tuple, UpdateError, SameOriginRedirects

FEED = 'https://omne.space/neospector/updates/installers.json'
MAX_FEED = 64 * 1024
MAX_INSTALLER = 800 * 1024 * 1024
PLATFORMS = {'linux-x64': '.deb', 'windows-x64': '_Setup.exe', 'macos-arm64': '.pkg', 'macos-x64': '.pkg'}
FILE = re.compile(r'^Neospector_[A-Za-z0-9_.-]+\.(?:deb|exe|pkg)$')
HEX = re.compile(r'^[0-9a-f]{64}$')
OPENER = urllib.request.build_opener(SameOriginRedirects)


def platform_id(system=None, machine=None):
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    if system == 'linux' and machine in ('x86_64', 'amd64'):return 'linux-x64'
    if system == 'windows' and machine in ('amd64', 'x86_64'):return 'windows-x64'
    if system == 'darwin' and machine in ('aarch64', 'arm64'):return 'macos-arm64'
    if system == 'darwin' and machine == 'x86_64':return 'macos-x64'
    return None


def validate_release(p):
    required = {'schema','product','channel','version','title','notes','date','commit','installers'}
    if not isinstance(p,dict) or set(p) != required or p['schema'] != 2 or p['product'] != 'Neospector' or p['channel'] != 'stable':
        raise UpdateError('Unsupported signed native release')
    version_tuple(p['version'])
    if not isinstance(p['title'],str) or not (1 <= len(p['title']) <= 140):raise UpdateError('Invalid update title')
    if not isinstance(p['notes'],str) or not (1 <= len(p['notes']) <= 8000):raise UpdateError('Invalid update notes')
    if not isinstance(p['date'],str) or not re.fullmatch(r'\d{4}-\d\d-\d\d',p['date']):raise UpdateError('Invalid date')
    if not isinstance(p['commit'],str) or not re.fullmatch('[0-9a-f]{40}',p['commit']):raise UpdateError('Invalid source commit')
    installers=p['installers']
    if not isinstance(installers,dict) or not installers or set(installers)-set(PLATFORMS):raise UpdateError('Invalid installer platforms')
    for alias,record in installers.items():
        if not isinstance(record,dict) or set(record)!={'file','sha256','bytes'}:raise UpdateError('Invalid installer entry')
        name=record['file'];expected=PLATFORMS[alias]
        if (not isinstance(name,str) or not FILE.fullmatch(name) or '..' in name or not name.endswith(expected)
            or not any('_'+alias+tail in name for tail in ('.', '_'))):
            raise UpdateError('Unsafe native installer filename')
        if not isinstance(record['sha256'],str) or not HEX.fullmatch(record['sha256']):raise UpdateError('Bad installer digest')
        if type(record['bytes']) is not int or not 0<record['bytes']<=MAX_INSTALLER:raise UpdateError('Bad installer size')
    return p


def sign_release(payload, private_key):
    """Owner-only. Signing key remains on owner's machine."""
    import subprocess
    validate_release(payload)
    with tempfile.TemporaryDirectory(prefix='neospector-sign-') as d:
        message=Path(d)/'message';signature=Path(d)/'signature'
        message.write_bytes(canonical(payload))
        proc=subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(private_key),'-rawin','-in',str(message),'-out',str(signature)],capture_output=True,timeout=20)
        if proc.returncode:raise UpdateError('Cannot sign installer metadata')
        return {'payload':payload,'signature':base64.b64encode(signature.read_bytes()).decode('ascii')}


def verify_release(envelope, public_key):
    if not isinstance(envelope,dict) or set(envelope)!={'payload','signature'}:raise UpdateError('Bad signed installer envelope')
    payload=validate_release(envelope['payload'])
    try: signature=base64.b64decode(envelope['signature'],validate=True)
    except (TypeError,ValueError) as exc:raise UpdateError('Bad native update signature') from exc
    if len(signature)!=64:raise UpdateError('Bad native signature size')
    # Frozen clients bundle cryptography. On the owner's Linux workstation,
    # use the already-required OpenSSL CLI when cryptography is not installed.
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        import subprocess
        with tempfile.TemporaryDirectory(prefix='neospector-verify-') as d:
            msg=Path(d)/'message';sig=Path(d)/'signature'
            msg.write_bytes(canonical(payload));sig.write_bytes(signature)
            try:p=subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(public_key),'-rawin',
                '-in',str(msg),'-sigfile',str(sig)],capture_output=True,timeout=20)
            except (OSError,subprocess.TimeoutExpired) as exc:raise UpdateError('No trusted signature verifier') from exc
            if p.returncode:raise UpdateError('Installer feed signature is invalid')
    else:
        try:
            key=serialization.load_pem_public_key(Path(public_key).read_bytes())
            if not isinstance(key,Ed25519PublicKey):raise ValueError('Not an Ed25519 key')
            key.verify(signature,canonical(payload))
        except Exception as exc:raise UpdateError('Installer feed signature is invalid') from exc
    return payload


def installer_url(feed, name):
    p=urllib.parse.urlsplit(feed)
    if p.scheme!='https' or p.username or p.password or p.fragment or p.query or not p.hostname or not p.path.endswith('/installers.json'):
        raise UpdateError('Invalid update feed URL')
    if not FILE.fullmatch(name) or '..' in name:raise UpdateError('Invalid installer file')
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path.rsplit('/',1)[0]+'/native/'+name,'',''))


def fetch_release(feed,public_key,current_version,os_id=None):
    installer_url(feed,'Neospector_probe.deb')
    alias=os_id if os_id is not None else platform_id()
    if alias is None:return None
    request=urllib.request.Request(feed,headers={'Accept':'application/json','User-Agent':'Neospector-NativeUpdater/2'})
    try:
        with OPENER.open(request,timeout=6) as response:raw=response.read(MAX_FEED+1)
    except (OSError,urllib.error.URLError) as exc:raise UpdateError('Update service unavailable') from exc
    if len(raw)>MAX_FEED:raise UpdateError('Update feed oversized')
    try:envelope=json.loads(raw)
    except ValueError as exc:raise UpdateError('Update feed is invalid JSON') from exc
    payload=verify_release(envelope,public_key)
    if version_tuple(payload['version'])<=version_tuple(current_version):return None
    if alias not in payload['installers']:return None
    return payload,envelope


def verify_installer(path,record):
    source=Path(path)
    if source.is_symlink() or not source.is_file() or source.stat().st_size!=record['bytes']:raise UpdateError('Installer size mismatch')
    digest=hashlib.sha256()
    with source.open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):digest.update(data)
    if digest.hexdigest()!=record['sha256']:raise UpdateError('Installer checksum mismatch')
    return True


def download_installer(feed,record,destination,progress=None):
    url=installer_url(feed,record['file'])
    dest=Path(destination);dest.parent.mkdir(parents=True,exist_ok=True)
    part=dest.with_name(dest.name+'.part');digest=hashlib.sha256();size=0
    try:
        with OPENER.open(urllib.request.Request(url,headers={'User-Agent':'Neospector-NativeUpdater/2'}),timeout=20) as response,part.open('wb') as out:
            while True:
                data=response.read(256*1024)
                if not data:break
                size+=len(data)
                if size>record['bytes']:raise UpdateError('Installer too large')
                digest.update(data);out.write(data)
                if progress:progress(size,record['bytes'])
        if size!=record['bytes'] or digest.hexdigest()!=record['sha256']:raise UpdateError('Installer integrity mismatch')
        os.replace(part,dest)
        verify_installer(dest,record)
        return dest
    except Exception:
        part.unlink(missing_ok=True)
        raise
