"""Stable identities, inclusion and cancellable enumeration for both media views.

Discovery never decodes media and never follows directory symlinks. Metadata is
optional; every discovered supported file is browseable before inspection ends.
"""
from __future__ import annotations
import hashlib, os, threading
from dataclasses import dataclass, field
from pathlib import Path

VIDEO={'.mp4','.mov','.mkv','.webm','.avi','.m4v','.mpg','.mpeg','.mts','.m2ts','.ogv'}
AUDIO={'.wav','.mp3','.flac','.m4a','.ogg','.opus','.aac','.aif','.aiff','.wma'}
IMAGE={'.png','.jpg','.jpeg','.gif','.webp','.tif','.tiff','.bmp','.avif'}

def media_kind(path):
    suffix=Path(path).suffix.casefold()
    return 'video' if suffix in VIDEO else 'audio' if suffix in AUDIO else 'image' if suffix in IMAGE else ''

def fingerprint(path):
    s=Path(path).stat();return (s.st_size,s.st_mtime_ns)

@dataclass
class BrowserItem:
    id: str
    path: str
    kind: str=''
    name: str=''
    size: int=0
    modified: int=0
    info: dict=field(default_factory=dict)
    error: str=''
    state: str='pending'
    fingerprint: tuple=()
    image: object=None
    def __post_init__(self):
        if not self.name:self.name=Path(self.path).name
        if not self.kind:self.kind=media_kind(self.path)
    @classmethod
    def from_path(cls,path):
        p=Path(path).expanduser().resolve();key=hashlib.sha256(os.path.normcase(str(p)).encode()).hexdigest()[:24]
        try:s,m=fingerprint(p);return cls(key,str(p),size=s,modified=m,fingerprint=(s,m))
        except OSError as e:return cls(key,str(p),error=str(e),state='error')
    def metadata_valid(self):
        try:return bool(self.info) and tuple(self.fingerprint)==fingerprint(self.path)
        except OSError:return False

class BrowserModel:
    def __init__(self,*,allow_existing=False):self.allow_existing=allow_existing;self.items={};self.checked=set();self.selected=set();self.focus=None;self.anchor=None
    def add(self,item):
        if item.id not in self.items:self.items[item.id]=item;return True
        return False
    def visible(self,*,query='',kind='all',sound='all',readiness='all',sort='name',descending=False):
        q=query.casefold().strip();rows=[]
        for r in self.items.values():
            if q and q not in (r.name+' '+r.path+' '+r.kind).casefold():continue
            if kind not in ('','all') and r.kind!=kind:continue
            has_sound=r.kind=='audio' or bool(r.info.get('has_audio'))
            if sound=='with sound' and not has_sound:continue
            if sound=='silent' and (has_sound or r.state=='pending'):continue
            if readiness=='ready' and r.state!='ready':continue
            if readiness=='issues' and not r.error:continue
            if readiness=='included' and r.id not in self.checked:continue
            rows.append(r)
        def key(r):
            v={'name':r.name.casefold(),'type':r.kind,'size':r.size,'date':r.modified,'duration':float(r.info.get('duration',0))}.get(sort,r.name.casefold())
            return (v,r.name.casefold(),r.id)
        return sorted(rows,key=key,reverse=descending)
    def hidden_checked(self,rows):return len(self.checked-{r.id for r in rows})
    def select(self,iid,ids,*,add=False,extend=False):
        if iid not in self.items:return
        if extend and self.anchor in ids and iid in ids:
            a,b=sorted((ids.index(self.anchor),ids.index(iid)));chosen=set(ids[a:b+1]);self.selected=(self.selected|chosen) if add else chosen
        elif add:
            if iid in self.selected:self.selected.remove(iid)
            else:self.selected.add(iid)
            self.anchor=iid
        else:self.selected={iid};self.anchor=iid
        self.focus=iid
    def toggle_selected(self):
        ids={i for i in (self.selected or ({self.focus} if self.focus else set())) if i in self.items and (self.allow_existing or not self.items[i].info.get('existing_asset_id'))}
        if ids and ids<=self.checked:self.checked.difference_update(ids)
        else:self.checked.update(ids)
    def include_visible(self,rows,operation):
        ids={r.id for r in rows if not r.error and (self.allow_existing or not r.info.get('existing_asset_id'))}
        if operation=='include':self.checked.update(ids)
        elif operation=='exclude':self.checked.difference_update(ids)
        elif operation=='invert':self.checked.symmetric_difference_update(ids)
        elif operation=='clear':self.checked.clear()
    def snapshot(self,sort='name',descending=False):
        # Inclusion persists through filtering; queue/import order follows the
        # chosen global sort, never opaque path-hash identifiers.
        return [r for r in self.visible(sort=sort,descending=descending) if r.id in self.checked and not r.error and (self.allow_existing or not r.info.get('existing_asset_id'))]

def scan_folder(folder,*,recursive=True,stop=None,include_hidden=False):
    """Yield all supported entries and visible error records, in bounded work steps."""
    stop=stop or threading.Event();pending=[Path(folder).expanduser()];seen=set()
    while pending and not stop.is_set():
        path=pending.pop()
        try:
            stat=path.stat();identity=(stat.st_dev,stat.st_ino)
            if identity in seen:continue
            seen.add(identity)
            with os.scandir(path) as entries:
                for e in entries:
                    if stop.is_set():return
                    if not include_hidden and e.name.startswith('.'):continue
                    if e.is_symlink():continue
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if recursive:pending.append(Path(e.path))
                        elif e.is_file(follow_symlinks=False) and media_kind(e.name):yield BrowserItem.from_path(e.path)
                    except OSError as exc:yield BrowserItem(str(e.path),str(e.path),error=str(exc),state='error')
        except OSError as exc:yield BrowserItem(str(path),str(path),error=str(exc),state='error')

def collection_sections(project,albums,members,available,*,include_unsorted=True,removed_albums=()):
    """Shared Visuals/Audio/Audio Browse grammar; no disk moves or imports."""
    local={k:v for k,v in project.extra.get('library_albums',{}).items() if k not in removed_albums};present=set(project.assets)
    filed={i for data in local.values() for i in data['ids']}
    sections=[{'id':'project-files','name':'Project files','ids':[i for i in available if i in present-filed],'current':True}]
    for aid,data in reversed(list(local.items())):
        sections.append({'id':aid,'name':data['name'],'ids':[i for i in data['ids'] if i in available],'current':True})
    grouped={i for ids in members.values() for i in ids}
    recent=[i for i in available if i not in present and i not in grouped]
    if recent and include_unsorted:sections.append({'id':'recent-imports','name':'Recent','ids':recent,'current':False})
    for album in albums:
        if album['id'] in local:continue
        sections.append({'id':album['id'],'name':album['name'],'ids':[i for i in members.get(album['id'],[]) if i in available],'current':False})
    return sections
