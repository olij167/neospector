#!/usr/bin/env python3
"""Separate post-shutdown Linux update installer: versioned, verified, rollbackable.
No privilege escalation, no overwrites of a running source copy or user media.
"""
from __future__ import annotations
import argparse,json,os,platform,shutil,stat,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app_source'))
from signed_updates import verify_envelope,verify_archive,safe_extract,UpdateError,version_tuple


def managed_root():
    return Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'omne/neospector'

def profile_path():
    if os.environ.get('OMNE_SEQUENCER_SANDBOX'):return Path(os.environ['OMNE_SEQUENCER_SANDBOX'])/'config'
    return Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'omne-sequencer'

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,prefix='.pointer-',delete=False) as tmp:
        json.dump(value,tmp,indent=2);tmp.write('\n');temp=Path(tmp.name)
        tmp.flush();os.fsync(tmp.fileno())
    os.replace(temp,path)

def verify_manifest(root):
    root=Path(root).resolve();manifest=root/'MANIFEST.sha256';seen=set()
    import hashlib
    for line in manifest.read_text().splitlines():
        pieces=line.split('  ',1)
        if len(pieces)!=2:raise UpdateError('Invalid internal manifest line')
        digest,name=pieces;relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or name in seen:raise UpdateError('Unsafe internal manifest')
        source=root/relative
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root):raise UpdateError('Internal manifest path invalid')
        with source.open('rb') as f:
            h=hashlib.file_digest(f,'sha256').hexdigest()
        if h!=digest:raise UpdateError('Internal manifest hash mismatch: '+name)
        seen.add(name)
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if actual!=seen|{'MANIFEST.sha256'}:raise UpdateError('Unlisted or missing release files')
    return len(seen)

def wait_for_exit(pid,timeout=35):
    if pid is None:return
    for _ in range(timeout*5):
        try:os.kill(pid,0)
        except ProcessLookupError:return
        time.sleep(.2)
    raise UpdateError('Original instrument did not close; no update installed')

def write_launchers(root):
    launcher=root/'launch.sh'
    launcher.write_text('#!/usr/bin/env bash\nset -e\nROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\nexec "${ROOT}/versions/$(python3 -c \'import json,sys;print(json.load(open(sys.argv[1]))["version"])\' "${ROOT}/current.json")/RUN_POC.sh" "$@"\n')
    launcher.chmod(0o755)
    desktop=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'applications/neospector.desktop'
    desktop.parent.mkdir(parents=True,exist_ok=True)
    # Exec= path cannot contain whitespace without quoting. Desktop Entry spec supports double quotes.
    desktop.write_text('[Desktop Entry]\nType=Application\nName=Neospector\nComment=OmN-e audiovisual instrument\nExec="'+str(launcher).replace('"','\\"')+'"\nTerminal=false\nCategories=AudioVideo;AudioVideoEditing;\n')

def apply_update(archive,envelope,public_key,wait_pid=None,launch=True,data_root=None):
    if not sys.platform.startswith('linux') or platform.machine()!='x86_64':
        raise UpdateError('This installer supports Linux x86-64 only')
    record=verify_envelope(json.loads(Path(envelope).read_text()),public_key)
    verify_archive(archive,record)
    wait_for_exit(wait_pid)
    root=Path(data_root or managed_root()).expanduser().resolve()
    versions=root/'versions';versions.mkdir(parents=True,exist_ok=True)
    destination=versions/record['version'];pointer=root/'current.json'
    if destination.exists():raise UpdateError('Version is already installed; refusing to overwrite it')
    staging=Path(tempfile.mkdtemp(prefix='.stage-',dir=versions));installed=False;prior=None;pointer_written=False
    try:
        extracted=safe_extract(archive,staging/'unpacked')
        count=verify_manifest(extracted)
        # Do not execute downloaded source to infer its version; inspect as data.
        import ast
        identity=ast.parse((extracted/'app_source/release_identity.py').read_text())
        versions_in_source=[node.value.value for node in identity.body if isinstance(node,ast.Assign)
            and any(isinstance(target,ast.Name) and target.id=='VERSION' for target in node.targets)
            and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str)]
        if versions_in_source!=[record['version']]:raise UpdateError('Release identity does not match signed version')
        if (extracted/'RELEASE.json').is_file():
            if json.loads((extracted/'RELEASE.json').read_text()).get('version')!=record['version']:
                raise UpdateError('Release metadata does not match version')
        if pointer.is_file():
            prior=json.loads(pointer.read_text());old=prior.get('version')
            if old and version_tuple(record['version'])<=version_tuple(old):raise UpdateError('Downgrade or repeated version blocked')
        # Backup metadata (not source media) before switching to a newly installed release.
        import importlib.util
        spec=importlib.util.spec_from_file_location('neospector_backup_helper',str(ROOT/'install_linux.py'))
        helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        profile=profile_path()
        backup=helper.backup_profile(profile,profile.parent/'omne-sequencer-backups')
        shutil.move(str(extracted),str(destination));installed=True
        for script in ('RUN_POC.sh','INSTALL_LINUX.sh'): (destination/script).chmod(0o755)
        atomic_json(pointer,{'version':record['version'],'previous':prior['version'] if prior else None,
                             'profile_backup':str(backup) if backup else None,'manifest_sha256':record['sha256']})
        pointer_written=True
        write_launchers(root)
        if launch:
            child=subprocess.Popen(['bash',str(destination/'RUN_POC.sh')],cwd=destination,
                                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            time.sleep(1.5)
            result=child.poll()
            if result is not None and result!=0:
                if prior:atomic_json(pointer,prior)
                else:pointer.unlink(missing_ok=True)
                raise UpdateError('New release exited immediately; current pointer rolled back')
        print(f'Installed Neospector {record["version"]} · {count} files verified')
        print('Managed launcher:',root/'launch.sh')
        print('Previous copies and original media were preserved.')
        return destination
    except Exception:
        if pointer_written:
            if prior:atomic_json(pointer,prior)
            else:pointer.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(staging,ignore_errors=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',required=True);p.add_argument('--manifest',required=True)
    p.add_argument('--wait-pid',type=int);p.add_argument('--no-launch',action='store_true')
    args=p.parse_args()
    try:apply_update(args.archive,args.manifest,ROOT/'updates/public.pem',args.wait_pid,not args.no_launch)
    except (OSError,ValueError,UpdateError) as e:
        print('SAFE STOP:',e,file=sys.stderr);return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
