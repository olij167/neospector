"""Neospector signed, bounded, same-origin Linux update transport.

This module has no GUI, does not import user code, and never executes downloaded
files. Ed25519 verification is delegated to OpenSSL, not handwritten crypto.
"""
from __future__ import annotations
import base64,hashlib,json,os,re,stat,subprocess,tempfile,urllib.parse,urllib.request,urllib.error,zipfile
from pathlib import Path

DEFAULT_FEED='https://omne.space/neospector/updates/stable.json'
MAX_MANIFEST=32768
MAX_ARCHIVE=400*1024*1024
MAX_UNPACKED=1200*1024*1024
MAX_FILES=3500
PRODUCT='Neospector'
PLATFORM='linux-x86_64'
VERSION_RE=re.compile(r'^\d+\.\d+\.\d+(?:-[a-zA-Z0-9][a-zA-Z0-9.-]*)?$')
FILE_RE=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*\.zip$')

class UpdateError(Exception):pass

def canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')

def version_tuple(version):
    """Comparable Neospector versions, including our numeric -uxNN release series.

    A UX iteration at the same X.Y.Z outranks an earlier UX iteration.  A
    final X.Y.Z without a suffix outranks UX prereleases of X.Y.Z.
    Unknown prerelease labels are rejected rather than silently misordered.
    """
    if not isinstance(version,str) or not VERSION_RE.fullmatch(version):
        raise UpdateError('Invalid release version')
    core, _, prerelease = version.partition('-')
    parts = tuple(int(part) for part in core.split('.'))
    if not prerelease:
        return (*parts, 2, 0)
    m = re.fullmatch(r'ux([0-9]+)', prerelease, re.IGNORECASE)
    if m:
        return (*parts, 1, int(m.group(1)))
    raise UpdateError('Unsupported release version suffix')

def verify_envelope(document,public_pem):
    """Verify a signed manifest against the pinned publisher key (Ed25519)."""
    if not isinstance(document,dict) or set(document)!={'payload','signature'}:raise UpdateError('Invalid manifest envelope')
    payload=document['payload']
    if not isinstance(payload,dict):raise UpdateError('Invalid release record')
    try:sig=base64.b64decode(document['signature'],validate=True)
    except (TypeError,ValueError) as e:raise UpdateError('Invalid release signature encoding') from e
    if len(sig)!=64:raise UpdateError('Invalid release signature size')
    public=Path(public_pem)
    if not public.is_file():raise UpdateError('Publisher verification key missing')
    with tempfile.TemporaryDirectory(prefix='neospector-signature-') as tmp:
        message=Path(tmp)/'release.json';signature=Path(tmp)/'release.sig'
        message.write_bytes(canonical(payload));signature.write_bytes(sig)
        try:
            proc=subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(public),'-rawin',
                '-in',str(message),'-sigfile',str(signature)],capture_output=True,timeout=7)
        except (FileNotFoundError,subprocess.TimeoutExpired) as e:raise UpdateError('OpenSSL Ed25519 verifier is unavailable') from e
        if proc.returncode!=0:raise UpdateError('Publisher signature verification failed')
    return validate_payload(payload)

def validate_payload(p):
    required={'schema','product','channel','platform','version','archive','sha256','bytes','notes'}
    if not isinstance(p,dict) or set(p)!=required:raise UpdateError('Unsupported manifest schema')
    if p['schema']!=1 or p['product']!=PRODUCT or p['channel']!='stable' or p['platform']!=PLATFORM:
        raise UpdateError('Release does not match this application and platform')
    version_tuple(p['version'])
    if not isinstance(p['archive'],str) or not FILE_RE.fullmatch(p['archive']) or '..' in p['archive']:
        raise UpdateError('Unsafe archive name')
    if not isinstance(p['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',p['sha256']):raise UpdateError('Invalid archive digest')
    if type(p['bytes']) is not int or not 0<p['bytes']<=MAX_ARCHIVE:raise UpdateError('Unsupported archive size')
    if not isinstance(p['notes'],str) or len(p['notes'])>2500:raise UpdateError('Invalid release notes')
    return p

def validated_feed_url(url,allow_local=False):
    if not isinstance(url,str) or len(url)>2048:raise UpdateError('Invalid update address')
    u=urllib.parse.urlsplit(url)
    if u.scheme=='file' and allow_local and u.netloc in ('','localhost') and u.path.endswith('.json'):return url
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.fragment or u.query:
        raise UpdateError('Updates require an HTTPS manifest URL')
    if not u.path.endswith('.json'):raise UpdateError('Invalid release feed path')
    return url

def archive_url(manifest_url,record,allow_local=False):
    validated_feed_url(manifest_url,allow_local)
    base=urllib.parse.urlsplit(manifest_url)
    result=urllib.parse.urljoin(manifest_url,record['archive'])
    u=urllib.parse.urlsplit(result)
    if (u.scheme,u.netloc)!=(base.scheme,base.netloc):raise UpdateError('Download host mismatch')
    if not result.rsplit('/',1)[0]==manifest_url.rsplit('/',1)[0]:raise UpdateError('Download directory mismatch')
    return result

class SameOriginRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        old=urllib.parse.urlsplit(request.full_url);new=urllib.parse.urlsplit(newurl)
        if (old.scheme,old.netloc)!=(new.scheme,new.netloc):raise UpdateError('Redirect outside update host blocked')
        return super().redirect_request(request,fp,code,msg,headers,newurl)

_OPENER=urllib.request.build_opener(SameOriginRedirects)

def fetch_release(feed,public_pem,current_version,allow_local=False):
    validated_feed_url(feed,allow_local)
    request=urllib.request.Request(feed,headers={'User-Agent':'Neospector-Updater/1','Accept':'application/json'})
    try:
        with _OPENER.open(request,timeout=6) as response:data=response.read(MAX_MANIFEST+1)
    except (OSError,ValueError,urllib.error.URLError) as e:raise UpdateError('Release feed unavailable: '+str(e)) from e
    if len(data)>MAX_MANIFEST:raise UpdateError('Release feed too large')
    try:doc=json.loads(data)
    except (ValueError,UnicodeDecodeError) as e:raise UpdateError('Invalid release feed JSON') from e
    record=verify_envelope(doc,public_pem)
    archive_url(feed,record,allow_local)
    if version_tuple(record['version'])<=version_tuple(current_version):return None
    return record,doc

def verify_archive(path,record):
    source=Path(path)
    if not source.is_file() or source.is_symlink() or source.stat().st_size!=record['bytes']:
        raise UpdateError('Update archive size mismatch')
    digest=hashlib.sha256()
    with source.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    if digest.hexdigest()!=record['sha256']:raise UpdateError('Update archive hash mismatch')
    if not zipfile.is_zipfile(source):raise UpdateError('Downloaded update is not a ZIP')
    return True

def download_release(feed,record,destination,progress=None,allow_local=False):
    url=archive_url(feed,record,allow_local)
    dest=Path(destination);dest.parent.mkdir(parents=True,exist_ok=True)
    part=dest.with_suffix('.part');h=hashlib.sha256();size=0
    try:
        with _OPENER.open(urllib.request.Request(url,headers={'User-Agent':'Neospector-Updater/1'}),timeout=12) as response,part.open('wb') as out:
            while True:
                buf=response.read(256*1024)
                if not buf:break
                size+=len(buf)
                if size>record['bytes']:raise UpdateError('Archive exceeds signed size')
                out.write(buf);h.update(buf)
                if progress:progress(size,record['bytes'])
        if size!=record['bytes'] or h.hexdigest()!=record['sha256']:raise UpdateError('Downloaded archive failed verification')
        os.replace(part,dest)
        verify_archive(dest,record)
        return dest
    except Exception:
        part.unlink(missing_ok=True)
        raise

def safe_extract(archive,destination):
    """Reject traversal, symlinks, duplicates, zip bombs, and extra root trees."""
    dest=Path(destination).resolve();dest.mkdir(parents=True,exist_ok=False)
    seen=set();total=0;roots=set()
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist()
        if len(entries)>MAX_FILES:raise UpdateError('Excessive number of files in update')
        for item in entries:
            name=item.filename
            if '\\' in name or name.startswith('/') or '\x00' in name:raise UpdateError('Unsafe archive entry')
            parts=Path(name).parts
            if not parts or '..' in parts or '.' in parts or name in seen:raise UpdateError('Invalid archive path')
            seen.add(name);roots.add(parts[0]);total+=item.file_size
            if total>MAX_UNPACKED:raise UpdateError('Update exceeds extraction size limit')
            mode=(item.external_attr>>16)&0o170000
            if mode not in (0,stat.S_IFREG,stat.S_IFDIR):raise UpdateError('Unsupported archive entry type')
            target=(dest/name).resolve()
            if not target.is_relative_to(dest):raise UpdateError('Archive path escapes destination')
        if len(roots)!=1:raise UpdateError('Expected a single top-level release directory')
        for item in entries:
            target=dest/item.filename
            if item.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(item) as stream,target.open('xb') as output:
                written=0
                while True:
                    block=stream.read(256*1024)
                    if not block:break
                    written+=len(block)
                    if written>item.file_size or written>MAX_UNPACKED:raise UpdateError('Unsafe decompressed entry size')
                    output.write(block)
    root=dest/next(iter(roots))
    for filename in ('RUN_POC.sh','bootstrap.py','install_linux.py','MANIFEST.sha256','app_source/release_identity.py'):
        if not (root/filename).is_file():raise UpdateError('Release is missing '+filename)
    return root
