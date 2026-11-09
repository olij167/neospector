#!/usr/bin/env python3
"""Verify this isolated source release, back up profile metadata, then launch."""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,shutil,sqlite3,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def verify_manifest(root):
    root=Path(root).resolve();seen=set()
    for line in (root/'MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split('  ',1)
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or name in seen:
            raise ValueError('Unsafe or repeated manifest path: '+name)
        path=root/relative
        if not path.resolve().is_relative_to(root) or path.is_symlink():raise ValueError('Unsafe manifest target: '+name)
        if not path.is_file():raise ValueError('Missing file: '+name)
        with path.open('rb') as f:
            actual=hashlib.file_digest(f,'sha256').hexdigest() if hasattr(hashlib,'file_digest') else hashlib.sha256(f.read()).hexdigest()
        if actual!=digest:raise ValueError('Checksum mismatch: '+name)
        seen.add(name)
    if not seen:raise ValueError('Empty manifest')
    return len(seen)

def profile_path():
    if os.environ.get('OMNE_SEQUENCER_SANDBOX'):return Path(os.environ['OMNE_SEQUENCER_SANDBOX'])/'config'
    return Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'omne-sequencer'

def backup_profile(profile,destination):
    profile=Path(profile)
    if not profile.is_dir():return None
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup=Path(destination)/('Neospector-'+stamp);backup.mkdir(parents=True,exist_ok=False)
    copied=[]
    # Keep preferences, themes, recovery/Draft documents and a transactionally
    # consistent catalogue. Recorded/source media stays at its original path.
    for source in sorted(profile.rglob('*')):
        if source.is_symlink() or not source.is_file() or source.suffix.lower() not in ('.json','.sqlite3','.db'):continue
        if not source.resolve().is_relative_to(profile.resolve()):continue
        target=backup/source.relative_to(profile);target.parent.mkdir(parents=True,exist_ok=True)
        if source.suffix.lower() in ('.sqlite3','.db'):
            with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as original:
                with sqlite3.connect(target) as copy:original.backup(copy)
        else:shutil.copy2(source,target)
        copied.append(str(source.relative_to(profile)))
    (backup/'BACKUP.json').write_text(json.dumps({'profile':str(profile),'files':copied,
        'note':'Metadata backup. Source and recorded media remain at their original paths.'},indent=2))
    return backup

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Verify packaged files only; no profile writes or launch')
    options=parser.parse_args()
    try:
        count=verify_manifest(ROOT);print(f'Verified {count} release files.',flush=True)
        if options.check:return 0
        if not sys.platform.startswith('linux'):raise ValueError('This helper is for Linux; native ports remain separately gated.')
        # Run once per isolated installation. This never overwrites an earlier backup.
        marker=ROOT/'.profile-backup.json'
        if not marker.exists():
            profile=profile_path();backup=backup_profile(profile,profile.parent/'omne-sequencer-backups')
            marker.write_text(json.dumps({'backup':str(backup) if backup else None},indent=2))
            if backup:print('Profile metadata backup: '+str(backup),flush=True)
        return subprocess.call([sys.executable,str(ROOT/'bootstrap.py')],cwd=ROOT)
    except (OSError,ValueError,sqlite3.Error) as exc:
        print('SAFE STOP: '+str(exc)+'. Existing application files and media were not replaced.',file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
