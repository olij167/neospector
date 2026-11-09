"""File identity and explicit relinking. Never identify a file by its name alone.

Hash work belongs on import workers. Existing IDs and source defaults survive
relinking; duplicate imports reuse those IDs and may add album membership.
"""
from __future__ import annotations
import hashlib, os
from pathlib import Path

def canonical(path):
    return os.path.normcase(str(Path(path).expanduser().resolve()))

def content_hash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

class IdentityIndex:
    def __init__(self,assets):
        self.assets=list(assets);self.paths={};self.sizes={};self.hashes={}
        for a in self.assets:
            if a.kind not in ('image','video','audio'):continue
            self.paths[canonical(a.path)]=a.id
            try:
                st=Path(a.path).stat();self.sizes.setdefault(st.st_size,[]).append(a)
            except OSError:continue
    def find(self,path):
        key=canonical(path)
        if key in self.paths:return self.paths[key]
        try:stat=Path(path).stat()
        except OSError:return None
        candidates=self.sizes.get(stat.st_size,[])
        if not candidates:return None
        digest=content_hash(path)
        for a in candidates:
            try:
                st=Path(a.path).stat();cachekey=(a.path,st.st_size,st.st_mtime_ns)
                if cachekey not in self.hashes:self.hashes[cachekey]=content_hash(a.path)
                if self.hashes[cachekey]==digest:return a.id
            except OSError:continue
        return None
    def add(self,asset):
        self.paths[canonical(asset.path)]=asset.id
        try:self.sizes.setdefault(Path(asset.path).stat().st_size,[]).append(asset)
        except OSError:pass

def unavailable(project):
    return [a for a in project.assets.values() if a.kind in ('audio','video','image') and not Path(a.path).is_file()]

def apply_relink(asset,path,info,kind):
    if asset.kind=='audio':
        if not info.get('has_audio'):raise ValueError('Choose a source with an audio stream.')
    elif kind!=asset.kind:raise ValueError('Choose the same media type. Use Replace to change the kind of source.')
    asset.path=str(Path(path).expanduser().resolve())
    asset.duration=float(info.get('duration',asset.duration));asset.width=int(info.get('width',asset.width));asset.height=int(info.get('height',asset.height))
    asset.metadata.update(info);asset.metadata.pop('content_sha256',None)
    # Occurrences, defaults, names, attribution and identities are intentionally unchanged.

def reconcile_asset_records(project):
    """Consolidate proven path identity, never names or intentional queue repeats.

    Alternate names/defaults remain in an archive; only reference keys are
    remapped. The original media files and all occurrence IDs stay untouched.
    No file hashing/I/O is done here, so load and undo remain bounded.
    """
    import copy
    from sequencer_model import _encode
    by_path={};aliases={}
    for aid,asset in sorted(project.assets.items()):
        if asset.kind not in ('audio','image','video') or not asset.path:continue
        key=(asset.kind,canonical(asset.path))
        prior=by_path.get(key)
        if prior is None:by_path[key]=asset;continue
        # All defaults affect future output or selection, including unknown
        # fields introduced by newer projects. Archiving a differing record
        # cannot replace preserving its active occurrence/source references.
        if prior.metadata.get('sequence_preferences',{})!=asset.metadata.get('sequence_preferences',{}):continue
        one=prior.metadata.get('content_sha256');two=asset.metadata.get('content_sha256')
        if one and two and one!=two:continue  # known different revisions of a replaced file
        aliases[aid]=prior.id
    if not aliases:return {}
    archive=project.extra.setdefault('asset_alias_records',{})
    for aid in aliases:archive.setdefault(aid,copy.deepcopy(_encode(project.assets[aid])))
    reference_keys={'asset_id','audio_asset_id','camera_id','source_asset_id','visual_asset_id'}
    list_keys={'pool_ids','asset_ids'}
    def visit(data):
        if isinstance(data,dict):
            for k,v in list(data.items()):
                if k in ('asset_alias_records','asset_aliases'):continue
                if k in reference_keys and isinstance(v,str):data[k]=aliases.get(v,v)
                elif k in list_keys and isinstance(v,list):data[k]=list(dict.fromkeys(aliases.get(x,x) for x in v))
                else:visit(v)
        elif isinstance(data,list):
            for value in data:visit(value)
    for layer in project.layers:
        for clip in layer.clips:
            clip.asset_id=aliases.get(clip.asset_id,clip.asset_id);visit(clip.extra)
        visit(layer.extra)
    project.audio_asset_id=aliases.get(project.audio_asset_id,project.audio_asset_id)
    visit(project.extra);visit(project.conductor.extra)
    recorded=project.extra.setdefault('asset_aliases',{})
    for old,target in list(recorded.items()):recorded[old]=aliases.get(target,target)
    recorded.update(aliases)
    for aid in aliases:del project.assets[aid]
    return aliases
