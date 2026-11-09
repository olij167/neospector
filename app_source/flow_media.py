"""Library/import ownership, safe file identity, drop routing and relinking."""
from __future__ import annotations
import copy, threading, json
from pathlib import Path
from urllib.parse import unquote,urlparse
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from media_identity import IdentityIndex,unavailable,apply_relink,canonical,reconcile_asset_records
from sequencer_model import Asset,add_asset,project_from_dict
from media_engine import probe_media,kind_for_path

class MediaWorkflow:
    def repair_asset_records(self,project=None):
        p=project or self.project
        aliases=reconcile_asset_records(p)
        mapping=p.extra.get('asset_aliases',{})
        if hasattr(self,'catalog') and mapping:
            groups={}
            for old,target in mapping.items():
                if target in p.assets and old in p.extra.get('asset_alias_records',{}):
                    groups.setdefault(target,{})[old]=p.extra['asset_alias_records'][old]
            # Catalogue tables are small; run under its transaction/lock. Original
            # alias definitions are retained, and pending puts cannot recreate them.
            for target,records in groups.items():self.catalog.merge_asset_records(p.assets[target],records)
        if p is self.project:
            self.selected_asset_id=mapping.get(self.selected_asset_id,self.selected_asset_id)
        if aliases:self.log('Merged duplicate asset records: '+repr(aliases)+'; queue occurrences retained')
        return aliases
    def load_catalogue_assets(self):
        super().load_catalogue_assets();self.repair_asset_records()
    def restore_project(self,project,path=None,*,new_history=True):
        if self.live.recording or self.output_recording or self.capture_busy:
            return super().restore_project(project,path,new_history=new_history)
        self.repair_asset_records(project)
        return super().restore_project(project,path,new_history=new_history)
    def library_tab_changed(self,event=None):
        if hasattr(self,'import_tab') and self.library_tabs.select()==str(self.import_tab):self.add_media()
    def add_media(self):
        from instrument_library_ui import DockedImport
        if not self.panel_states.get('Library',True):self.toggle_panel('Library')
        if not self.import_window or not self.import_window.winfo_exists():
            self.import_window=DockedImport(self.import_tab,self);self.import_window.pack(fill='both',expand=True)
        self.library_tabs.select(self.import_tab)
        self.import_window.path_entry.focus_set()
        self.register_drop(self.import_window.browser.canvas,lambda:self.import_window.albums.get(self.import_window.album.get(),'all'))
    def drop_paths(self,paths,album=None):
        target=album or self.album.get();self.add_media()
        w=self.import_window
        w.album.set(next((n for n,i in w.albums.items() if i==target),'All media'))
        w.add_paths(paths);self.update_status('Drop staged in '+w.album.get()+'. Check the items, then Import included. Existing files can be linked without reimporting.')
    def init_drop_support(self):
        if self.closing:return
        self.dnd_available=False
        # Recovery switch for X11/TkDnD faults during native negotiation, which
        # can occur before any Python callback. Ordinary Files… remains usable.
        import os
        if os.environ.get('NEOSPECTOR_NO_NATIVE_DROP')=='1':
            self.log('Native file drop disabled for this launch. Use Library → Import → Files… instead.')
            return
        try:
            from native_drop import require_native_drop
            require_native_drop(self);self.dnd_available=True
            self.register_drop(getattr(self,'project_media_folder',self.library_frame),lambda:self.album.get())
            self.register_drop(self.library.canvas,lambda:self.album.get())
            self.register_drop(self.album_box,lambda:self.album.get())
        except (ImportError,RuntimeError,OSError,tk.TclError) as exc:
            self.log('Native file drop unavailable: '+str(exc)+'. Folder/path import remains available.')
    def register_drop(self,widget,album):
        if not getattr(self,'dnd_available',False) or getattr(widget,'_neodrop',False):return
        try:
            from tkinterdnd2 import DND_FILES,COPY
            widget.drop_target_register(DND_FILES)
            def receive(event):
                paths=self.parse_drop(event.data)
                if paths:self.drop_paths(paths,album=album())
                return COPY
            widget.dnd_bind('<<Drop>>',receive);widget._neodrop=True
        except (ImportError,tk.TclError,AttributeError) as exc:self.log('File drop target: '+str(exc))
    def parse_drop(self,data):
        paths=[]
        try:parts=self.tk.splitlist(data)
        except tk.TclError:self.update_status('Could not read file drop. Use a folder path instead.');return paths
        for value in parts:
            if value.startswith('file:'):
                uri=urlparse(value)
                if uri.netloc not in ('','localhost'):continue
                value=unquote(uri.path)
                if __import__('os').name=='nt' and value.startswith('/') and len(value)>2 and value[2]==':':value=value[1:]
            path=Path(value).expanduser()
            if path.is_file() or path.is_dir():paths.append(str(path.resolve()))
        return list(dict.fromkeys(paths))
    def import_files(self,paths,as_song=False,album=None,staged=None,use='Library only'):
        if self.importing:return self.update_status('Finishing an import; the next selection can remain staged.')
        self.importing=True;pid=self.project.id;target=album or self.album.get();metadata=staged or {};assets=copy.deepcopy(list(self.project.assets.values()));paths=tuple(paths)
        if as_song:use='Add to sound queue'
        def work():
            from media_browser_model import fingerprint
            catalogue=project_from_dict({'assets':{a['id']:a for a in self.catalog.assets()}}).assets
            combined=dict(catalogue);combined.update({a.id:a for a in assets})
            index=IdentityIndex(combined.values());result=[];errors=[]
            for path in paths:
                try:
                    path=canonical(path);duplicate=index.find(path)
                    if duplicate:
                        a=next((a for a in index.assets if a.id==duplicate),None)
                        if a:result.append((path,a.kind,copy.deepcopy(a.metadata),duplicate));continue
                    cached=metadata.get(path)
                    info=copy.deepcopy(cached['info']) if cached and tuple(cached.get('fingerprint',()))==tuple(fingerprint(path)) else probe_media(path)
                    kind=kind_for_path(path)
                    if as_song and not info.get('has_audio'):raise ValueError('This file has no sound')
                    info.pop('existing_asset_id',None)
                    result.append((path,kind,info,None))
                    a=Asset('batch:'+path,path,kind,Path(path).name,info['duration'],info['width'],info['height'],info);index.assets.append(a);index.add(a)
                except Exception as exc:errors.append(Path(path).name+': '+str(exc))
            self.events.put(('call',lambda:self.accept_import_v03(pid,result,errors,as_song,target,use)))
        threading.Thread(target=work,name='Identify/import media',daemon=True).start();self.update_status('Checking file identity and importing · Programme continues…')
    def accept_import_v03(self,pid,result,errors,as_song,album,use='Library only'):
        self.importing=False
        if self.project.id!=pid:return self.update_status('Import cancelled: editing target changed. Nothing was added to the wrong project.')
        used=[];added=[];batch={}
        catalogue=project_from_dict({'assets':{a['id']:a for a in self.catalog.assets()}}).assets
        def commit():
            for path,kind,info,existing in result:
                existing=self.project.extra.get('asset_aliases',{}).get(existing,existing)
                a=batch.get(existing) if existing and existing.startswith('batch:') else self.project.asset(existing) if existing else None
                if a is None and existing in catalogue:
                    a=copy.deepcopy(catalogue[existing]);self.project.assets[a.id]=a
                if a is None:
                    a=next((old for old in self.project.assets.values() if old.kind==kind and canonical(old.path)==canonical(path)),None)
                if not a:
                    a=add_asset(self.project,path=path,kind=kind,name=Path(path).name,duration=info.get('duration',0),width=info.get('width',0),height=info.get('height',0),metadata=info)
                    added.append(a);batch['batch:'+path]=a
                used.append(a);self.selected_asset_id=a.id
            ids=list(dict.fromkeys(a.id for a in used))
            for key in ('library_hidden','library_removed'):
                self.project.extra[key]=[i for i in self.project.extra.get(key,[]) if i not in ids]
            if album!='all':
                albums=self.project.extra.setdefault('library_albums',{})
                if album not in albums:
                    found=next((a for a in self.catalog.albums() if a['id']==album),{'name':'Album'})
                    albums[album]={'name':found['name'],'ids':[]}
                albums[album]['ids']=list(dict.fromkeys(albums[album]['ids']+ids))
        if result:
            self.transaction('Import / reuse media',commit)
            ids=list(dict.fromkeys(a.id for a in used))
            for a in added:self.io.submit(self.catalog.put_asset,copy.deepcopy(a))
            self.refresh_library()
            from import_destinations import apply
            apply(self,ids,'Add to sound queue' if as_song else use)
            self.update_status(f'{len(added)} imported · {len(used)-len(added)} already in Library (reused) · '+use)
        if errors:self.log('\n'.join(errors));self.update_status(f'{len(errors)} unavailable source(s): '+errors[0])
        return list(dict.fromkeys(a.id for a in used))
    def check_media_health(self):
        if self.closing:return
        if not getattr(self,'_health_busy',False):
            self._health_busy=True;pid=self.project.id;refs=[(a.id,a.path) for a in self.project.assets.values() if a.kind in ('image','video','audio')]
            def scan():
                keys=tuple(aid for aid,path in refs if not Path(path).is_file())
                def done():
                    self._health_busy=False
                    if self.closing or self.project.id!=pid:return
                    if keys!=getattr(self,'_missing_key',None):
                        self._missing_key=keys
                        if keys:
                            self.missing_notice.configure(text=f'! {len(keys)} missing source(s) · Locate…   Pictures continue; unavailable sound is silent')
                            self.missing_notice.pack(fill='x',before=self.viewport)
                        else:self.missing_notice.pack_forget()
                        self.queue_deck.refresh(True)
                self.events.put(('call',done))
            threading.Thread(target=scan,name='Media availability',daemon=True).start()
        self.after(3000,self.check_media_health)
    def locate_missing(self):
        w=getattr(self,'relink_window',None)
        if w and w.winfo_exists():w.lift();return
        self.relink_window=RelinkWindow(self)
    def relink_asset(self,aid=None,path=None,on_done=None):
        aid=aid or self.selected_asset_id
        if not self.project.asset(aid):return self.update_status('Select a Library source to locate.')
        if path is None:path=filedialog.askopenfilename(parent=self,title='Locate '+self.project.asset(aid).name)
        if not path:return
        pid=self.project.id
        def work():
            try:
                info=probe_media(path);kind=kind_for_path(path)
                def done():
                    if self.project.id!=pid:return
                    a=self.project.asset(aid)
                    if not a:return
                    try:
                        # Validate before the transaction so a rejected replacement changes nothing.
                        apply_relink(copy.deepcopy(a),path,info,kind)
                        self.transaction('Locate '+a.name,lambda:(apply_relink(a,path,info,kind),self.repair_asset_records()))
                        self.io.submit(self.catalog.put_asset,copy.deepcopy(a));self._audio_analysis_key=None
                        self.prepare_sound_analysis();self.viewport.invalidate();self.viewport.request();self.queue_deck.refresh(True)
                        self.update_status('Relinked '+a.name+' · timing, effects and identity preserved')
                    except Exception as exc:self.update_status('Could not relink: '+str(exc))
                    if on_done:on_done()
                self.events.put(('call',done))
            except Exception as exc:
                msg=str(exc);self.events.put(('call',lambda:self.update_status('Could not inspect replacement: '+msg)))
        threading.Thread(target=work,name='Verify relink',daemon=True).start()

class RelinkWindow(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.title('Locate missing media · Neospector');self.geometry('740x420');self.transient(app)
        b=ttk.Frame(self,padding=14);b.pack(fill='both',expand=True)
        ttk.Label(b,text='Keep your edits. Reconnect moved files.',style='Title.TLabel').pack(anchor='w')
        ttk.Label(b,text='Playback continues with silence / transparency for unavailable sources. Export still requires them.',wraplength=690,style='Muted.TLabel').pack(fill='x',pady=7)
        self.tree=ttk.Treeview(b,columns=('type','path'),show='tree headings');self.tree.heading('#0',text='Source');self.tree.heading('type',text='Type');self.tree.heading('path',text='Expected location');self.tree.column('#0',width=170);self.tree.column('type',width=60,stretch=False);self.tree.column('path',width=420);self.tree.pack(fill='both',expand=True)
        row=ttk.Frame(b);row.pack(fill='x',pady=8)
        ttk.Button(row,text='Locate selected file…',style='Accent.TButton',command=self.locate).pack(side='left')
        ttk.Button(row,text='Find in folder…',command=self.folder).pack(side='left',padx=5)
        ttk.Button(row,text='Close',command=self.destroy).pack(side='right')
        self.note=tk.StringVar();ttk.Label(b,textvariable=self.note,style='Muted.TLabel').pack(fill='x');self.refresh()
        self.tree.bind('<Double-1>',lambda e:self.locate());self.bind('<Escape>',lambda e:self.destroy())
    def refresh(self):
        if not self.winfo_exists():return
        self.tree.delete(*self.tree.get_children())
        for a in unavailable(self.app.project):self.tree.insert('','end',iid=a.id,text=a.name,values=(a.kind,a.path))
        self.note.set('Select a missing item. Replacement is explicit; files are never guessed from names alone.')
    def locate(self):
        ids=self.tree.selection()
        if not ids:return
        path=filedialog.askopenfilename(parent=self,title='Select the relocated file')
        if path:self.app.relink_asset(ids[0],path,self.refresh)
    def folder(self):
        ids=self.tree.selection()
        if not ids:return self.note.set('Select the missing source to search for.')
        a=self.app.project.asset(ids[0]);folder=filedialog.askdirectory(parent=self)
        if not folder:return
        self.note.set('Searching the selected folder…')
        def work():
            import os
            candidates=[]
            for root,dirs,files in os.walk(folder,followlinks=False):
                dirs[:]=[x for x in dirs if not x.startswith('.')]
                if Path(a.path).name in files:candidates.append(str(Path(root)/Path(a.path).name))
                if len(candidates)>50:break
            def done():
                if not self.winfo_exists():return
                if len(candidates)==1:
                    if messagebox.askyesno('Confirm replacement','Use this file?\n\n'+candidates[0]+'\n\nName match only; confirm this is your original source.',parent=self):self.app.relink_asset(a.id,candidates[0],self.refresh)
                else:self.note.set(f'{len(candidates)} name matches. Use Locate selected file to choose explicitly.')
            self.app.events.put(('call',done))
        threading.Thread(target=work,name='Relink folder search',daemon=True).start()
