"""Local metadata catalogue. Albums never move or delete source files.

Every saved ingredient is an immutable revision. A portable project embeds its
own processing and media references; losing this catalogue does not lose a take.
"""
from __future__ import annotations
import json, sqlite3, threading, time, uuid
from pathlib import Path
from sequencer_model import Asset, _encode

KINDS={'rack','patch','recipe','transition','behaviour','gesture'}
MAX_INGREDIENT=8*1024*1024

class CreativeLibrary:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.generation=0;self._asset_write_order={}
        self.db=sqlite3.connect(self.path,check_same_thread=False,timeout=5)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS asset_aliases(alias TEXT PRIMARY KEY,canonical TEXT NOT NULL,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS albums(id TEXT PRIMARY KEY,name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS members(album TEXT,asset TEXT,PRIMARY KEY(album,asset),FOREIGN KEY(album) REFERENCES albums(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS ingredients(id TEXT,revision INTEGER,name TEXT,kind TEXT,payload TEXT,created REAL,PRIMARY KEY(id,revision));
        CREATE TABLE IF NOT EXISTS asset_variants(asset TEXT,project TEXT,payload TEXT NOT NULL,updated REAL,PRIMARY KEY(asset,project));
        CREATE TABLE IF NOT EXISTS album_revisions(album TEXT,revision TEXT,project TEXT,payload TEXT NOT NULL,updated REAL,PRIMARY KEY(album,revision));
        CREATE TABLE IF NOT EXISTS album_aliases(alias TEXT PRIMARY KEY,canonical TEXT NOT NULL,provenance TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS album_drafts(album TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS album_activity(album TEXT PRIMARY KEY,used REAL);
        CREATE TABLE IF NOT EXISTS album_browser(album TEXT PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 0,removed INTEGER NOT NULL DEFAULT 0);''');self.db.commit()
        self._migrate_album_names()
    def close(self):
        with self.lock:self.db.commit();self.db.close()
    def put_asset(self,a:Asset):
        text=json.dumps(_encode(a),ensure_ascii=False,allow_nan=False)
        with self.lock:
            if self.db.execute('SELECT 1 FROM asset_aliases WHERE alias=?',(a.id,)).fetchone():return
            cursor=self.db.execute('INSERT OR IGNORE INTO assets VALUES(?,?)',(a.id,text));self.db.commit()
            if cursor.rowcount:self.generation+=1
    def merge_asset_records(self,canonical_asset,aliases):
        """Atomic album/reference repair; delayed old writes cannot resurrect an alias."""
        payload=json.dumps(_encode(canonical_asset),ensure_ascii=False,allow_nan=False)
        with self.lock,self.db:
            self.db.execute('INSERT OR IGNORE INTO assets VALUES(?,?)',(canonical_asset.id,payload))
            for aid,asset in aliases.items():
                raw=_encode(asset) if isinstance(asset,Asset) else asset
                self.db.execute('INSERT OR REPLACE INTO asset_aliases VALUES(?,?,?)',(aid,canonical_asset.id,json.dumps(raw,ensure_ascii=False)))
                self.db.execute('INSERT OR IGNORE INTO members SELECT album,? FROM members WHERE asset=?',(canonical_asset.id,aid))
                self.db.execute('DELETE FROM members WHERE asset=?',(aid,))
                self.db.execute('DELETE FROM assets WHERE id=?',(aid,))
    def alias_map(self):
        with self.lock:return dict(self.db.execute('SELECT alias,canonical FROM asset_aliases'))
    def assets(self):
        with self.lock:return [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM assets')]
    def _migrate_album_names(self):
        """Remove legacy name uniqueness without changing IDs or memberships."""
        sql=self.db.execute("SELECT sql FROM sqlite_master WHERE name='albums'").fetchone()[0]
        if 'UNIQUE' not in sql.upper():return
        backup=self.path.with_suffix(self.path.suffix+'.pre-r5c4')
        if not backup.exists():
            target=sqlite3.connect(backup)
            try:self.db.backup(target)
            finally:target.close()
        self.db.execute('PRAGMA foreign_keys=OFF')
        with self.db:
            self.db.execute('CREATE TABLE albums_r5c4(id TEXT PRIMARY KEY,name TEXT NOT NULL)')
            self.db.execute('INSERT INTO albums_r5c4 SELECT id,name FROM albums')
            self.db.execute('DROP TABLE albums')
            self.db.execute('ALTER TABLE albums_r5c4 RENAME TO albums')
        self.db.execute('PRAGMA foreign_keys=ON')
    def create_album(self,name,album_id=None):
        name=str(name).strip()
        if not name or len(name)>120:raise ValueError('Use an album name of 1–120 characters')
        aid=album_id or 'album_'+uuid.uuid4().hex[:12]
        with self.lock,self.db:
            created=self.db.execute('INSERT OR IGNORE INTO albums VALUES(?,?)',(aid,name))
            if created.rowcount:self.db.execute('INSERT OR IGNORE INTO album_drafts VALUES(?)',(aid,))
            self.db.execute('INSERT OR REPLACE INTO album_activity VALUES(?,?)',(aid,time.time()))
            self.generation+=1
        return aid
    def albums(self,include_removed=False):
        with self.lock:return [{'id':r[0],'name':r[1]} for r in self.db.execute(
            'SELECT a.id,a.name FROM albums a LEFT JOIN album_activity u ON u.album=a.id '
            'LEFT JOIN album_browser b ON b.album=a.id '+('' if include_removed else 'WHERE COALESCE(b.removed,0)=0 ')+
            'ORDER BY COALESCE(u.used,0) DESC,a.name COLLATE NOCASE,a.id')]
    def browser_album_ids(self):
        """Only explicitly enabled archives belong in the working Library."""
        with self.lock:return {r[0] for r in self.db.execute('SELECT album FROM album_browser WHERE enabled=1 AND removed=0')}
    def removed_album_ids(self):
        with self.lock:return {r[0] for r in self.db.execute('SELECT album FROM album_browser WHERE removed=1')}
    def set_album_visible(self,album,enabled):
        with self.lock,self.db:
            self.db.execute('INSERT INTO album_browser(album,enabled) VALUES(?,?) ON CONFLICT(album) DO UPDATE SET enabled=excluded.enabled',(album,int(bool(enabled))))
            self.generation+=1
    def archive_albums(self,albums,removed=True):
        """Tombstone browser entries; retain files, membership, revisions and visibility.

        Old project saves can still update their revision but cannot undo this
        deliberate choice. Restore is the inverse and does not reimport media.
        """
        with self.lock,self.db:
            self.db.executemany('INSERT INTO album_browser(album,removed) VALUES(?,?) ON CONFLICT(album) DO UPDATE SET removed=excluded.removed',[(a,int(bool(removed))) for a in dict.fromkeys(albums)])
            self.generation+=1
    def rename_album(self,album,name):
        name=str(name).strip()
        if not name or len(name)>120:raise ValueError('Use an album name of 1–120 characters')
        with self.lock,self.db:
            self.db.execute('UPDATE albums SET name=? WHERE id=?',(name,album));self.generation+=1
    def duplicate_albums(self):
        groups={}
        for album in self.albums():
            members=tuple(sorted(self.member_ids(album['id'])))
            if members:groups.setdefault(members,[]).append(album['id'])
        return [ids for ids in groups.values() if len(ids)>1]
    def touch_album(self,album):
        with self.lock,self.db:self.db.execute('INSERT OR REPLACE INTO album_activity VALUES(?,?)',(album,time.time()))
    def persist_project_assets(self,project_id,assets,order=None):
        """One working edited use per project; original rows never track edits."""
        order=time.monotonic_ns() if order is None else order
        with self.lock,self.db:
            for asset in assets:
                if asset.kind=='camera':continue
                if self.db.execute('SELECT 1 FROM asset_aliases WHERE alias=?',(asset.id,)).fetchone():continue
                key=(project_id,asset.id)
                if order<self._asset_write_order.get(key,-1):continue
                self._asset_write_order[key]=order
                payload=json.dumps(_encode(asset),ensure_ascii=False,sort_keys=True,allow_nan=False)
                self.db.execute('INSERT OR IGNORE INTO assets VALUES(?,?)',(asset.id,payload))
                original=json.loads(self.db.execute('SELECT payload FROM assets WHERE id=?',(asset.id,)).fetchone()[0])
                prior=self.db.execute('SELECT payload FROM asset_variants WHERE asset=? AND project=?',(asset.id,project_id)).fetchone()
                if original==json.loads(payload):
                    self.db.execute('DELETE FROM asset_variants WHERE asset=? AND project=?',(asset.id,project_id))
                    if prior:self.generation+=1
                elif not prior or json.loads(prior[0])!=json.loads(payload):
                    self.db.execute('INSERT OR REPLACE INTO asset_variants VALUES(?,?,?,?)',(asset.id,project_id,payload,time.time()));self.generation+=1
    def asset_versions(self,asset_id):
        with self.lock:
            row=self.db.execute('SELECT payload FROM assets WHERE id=?',(asset_id,)).fetchone()
            original=[{'id':asset_id,'revision':'original','project':None,'payload':json.loads(row[0])}] if row else []
            return original+[{'id':asset_id,'revision':'project:'+p,'project':p,'payload':json.loads(raw)} for p,raw in self.db.execute(
                'SELECT project,payload FROM asset_variants WHERE asset=? ORDER BY updated DESC',(asset_id,))]
    def album_revision(self,album,revision=None):
        if not revision or revision=='original':
            with self.lock:
                if not self.db.execute('SELECT 1 FROM albums WHERE id=?',(album,)).fetchone():raise KeyError('Album is unavailable')
                ids=[r[0] for r in self.db.execute('SELECT asset FROM members WHERE album=? ORDER BY rowid',(album,))]
            return {'id':album,'revision':'original','ids':ids}
        with self.lock:row=self.db.execute('SELECT payload FROM album_revisions WHERE album=? AND revision=?',(album,revision)).fetchone()
        if row is None:raise KeyError('Album revision is unavailable')
        return json.loads(row[0])
    def album_versions(self,album):
        with self.lock:
            return [self.album_revision(album)]+[json.loads(r[0]) for r in self.db.execute(
                'SELECT payload FROM album_revisions WHERE album=? ORDER BY updated DESC',(album,))]
    def sync_project_albums(self,project_id,albums,assets):
        """Archive project membership under the same album; preserve original set."""
        with self.lock,self.db:
            for aid,data in albums.items():
                known=self.db.execute('SELECT 1 FROM albums WHERE id=?',(aid,)).fetchone()
                if not known:
                    self.db.execute('INSERT INTO albums VALUES(?,?)',(aid,data['name']))
                    self.db.executemany('INSERT OR IGNORE INTO members VALUES(?,?)',[(aid,i) for i in data['ids']])
                ids=list(dict.fromkeys(data['ids']));revision='project:'+project_id
                # Only a proven newly-created draft may establish its original
                # membership on first filing. Empty legacy/established albums
                # retain their original and receive a project revision instead.
                draft=self.db.execute('SELECT 1 FROM album_drafts WHERE album=?',(aid,)).fetchone()
                if ids and draft and not self.member_ids(aid):
                    self.db.executemany('INSERT OR IGNORE INTO members VALUES(?,?)',[(aid,i) for i in ids])
                    self.db.execute('DELETE FROM album_drafts WHERE album=?',(aid,));self.generation+=1
                original={a['id']:a for a in self.assets()}
                edited=any(i in assets and i in original and _encode(assets[i])!=original[i] for i in ids)
                if ids==self.album_revision(aid)['ids'] and not edited:
                    self.db.execute('DELETE FROM album_revisions WHERE album=? AND revision=?',(aid,revision))
                else:
                    payload={'id':aid,'revision':revision,'project':project_id,'name':data['name'],'ids':ids,
                             'assets':{i:_encode(assets[i]) for i in ids if i in assets}}
                    self.db.execute('INSERT OR REPLACE INTO album_revisions VALUES(?,?,?,?,?)',
                        (aid,revision,project_id,json.dumps(payload,ensure_ascii=False,allow_nan=False),time.time()))
    def ingredient_versions(self,iid):
        with self.lock:revisions=[r[0] for r in self.db.execute('SELECT revision FROM ingredients WHERE id=? ORDER BY revision',(iid,))]
        return [self.ingredient(iid,r) for r in revisions]
    def add_members(self,album,assets):
        assets=tuple(assets)
        with self.lock,self.db:
            self.db.executemany('INSERT OR IGNORE INTO members VALUES(?,?)',[(album,a) for a in assets])
            if assets:self.db.execute('DELETE FROM album_drafts WHERE album=?',(album,))
            self.generation+=1
    def remove_members(self,album,assets):
        with self.lock:self.db.executemany('DELETE FROM members WHERE album=? AND asset=?',[(album,a) for a in assets]);self.db.commit();self.generation+=1
    def member_ids(self,album):
        with self.lock:return {r[0] for r in self.db.execute('SELECT asset FROM members WHERE album=?',(album,))}
    def save_ingredient(self,name,kind,payload,ingredient_id=None):
        name=str(name).strip()
        if not name or len(name)>120 or kind not in KINDS:raise ValueError('Choose an ingredient name and supported type')
        text=json.dumps(payload,ensure_ascii=False,allow_nan=False)
        if len(text.encode())>MAX_INGREDIENT:raise ValueError('Ingredient exceeds 8 MB. Keep source media outside the recipe.')
        from module_engine import compile_rack
        from sequencer_model import _effect_from
        def check_rack(raw):compile_rack([_effect_from(e) for e in raw])
        if kind=='rack':check_rack(payload.get('rack',[]))
        if kind=='patch':
            check_rack(payload.get('master',[]))
            for data in payload.get('voices',{}).values():check_rack(data.get('rack',[]))
        iid=ingredient_id or 'ing_'+uuid.uuid4().hex[:16]
        with self.lock:
            rev=self.db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM ingredients WHERE id=?',(iid,)).fetchone()[0]
            self.db.execute('INSERT INTO ingredients VALUES(?,?,?,?,?,?)',(iid,rev,name,kind,text,time.time()));self.db.commit();self.generation+=1
        return self.ingredient(iid,rev)
    def ingredient(self,iid,revision=None):
        with self.lock:
            row=self.db.execute('SELECT id,revision,name,kind,payload,created FROM ingredients WHERE id=?'+(' AND revision=?' if revision else '')+' ORDER BY revision DESC LIMIT 1',(iid,revision) if revision else (iid,)).fetchone()
        if not row:raise KeyError('Ingredient revision not found')
        return dict(id=row[0],revision=row[1],name=row[2],kind=row[3],payload=json.loads(row[4]),created=row[5])
    def ingredients(self):
        with self.lock:ids=[r[0] for r in self.db.execute('SELECT id FROM ingredients GROUP BY id ORDER BY MAX(created) DESC')]
        return [self.ingredient(iid) for iid in ids]
    def export_ingredient(self,iid,path,revision=None):
        d={'kind':'omne/ingredient','format_version':'1.0.0','ingredient':self.ingredient(iid,revision)}
        target=Path(path);tmp=target.with_name(target.name+'.tmp');tmp.write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');tmp.replace(target)
    def import_ingredient(self,path):
        path=Path(path)
        if path.stat().st_size>MAX_INGREDIENT:raise ValueError('Ingredient exceeds 8 MB')
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('kind')!='omne/ingredient' or data.get('format_version')!='1.0.0':raise ValueError('Unsupported ingredient format')
        a=data['ingredient'];return self.save_ingredient(a['name'],a['kind'],a['payload'])
