"""One modeless browser for device media, archived albums and edited revisions.

The scanner/identity/thumbnail worker is shared with the retained import service.
A single inclusion basket survives source changes, filtering, grid/list and scan
cancellation. Catalogue removal is a reversible metadata action, never file I/O.
"""
from __future__ import annotations
import copy, threading, queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, simpledialog
from instrument_library_ui import ImportSurface
from media_browser_model import BrowserModel, BrowserItem
from media_browser_view import MediaBrowser


class SourceBrowser(MediaBrowser):
    def __init__(self,*args,**kwargs):
        self.source_ids=None
        super().__init__(*args,**kwargs)
    def rows(self):
        rows=super().rows()
        return rows if self.source_ids is None else [r for r in rows if r.id in self.source_ids]


class UnifiedMediaBrowser(ImportSurface,tk.Toplevel):
    THUMBNAIL_LIMIT=240
    def __init__(self,app,paths=(),pending_randomise=None):
        tk.Toplevel.__init__(self,app)
        self.title('Media Browser · Neospector');self.geometry('1040x700');self.minsize(740,500);self.transient(app)
        self.initialise_services(app)
        self._visible_thumbnail_ids=set();self._drop_after=None
        self.project_id=app.project.id;self.pending_randomise=copy.deepcopy(pending_randomise)
        self.catalogue_rows={};self.device_ids=set();self.source='device';self.source_nodes={};self.album_undo=[]
        self.folder=tk.StringVar(value=getattr(app,'last_import_folder',''));self.recursive=tk.BooleanVar(value=True)
        self.summary=tk.StringVar();self.focus_info=tk.StringVar();self.source_title=tk.StringVar(value='Device selection')
        self.show_removed=tk.BooleanVar(value=False);self.album=tk.StringVar(value='All media');self.use=tk.StringVar(value='Library only')
        self.albums={'All media':'all',**{a['name']+' · '+a['id'][-5:]:a['id'] for a in app.catalog.albums()}}
        self.model=BrowserModel(allow_existing=True)
        body=ttk.Frame(self,padding=8);body.pack(fill='both',expand=True)
        body.rowconfigure(1,weight=1);body.columnconfigure(0,weight=1)
        location=ttk.Frame(body);location.grid(row=0,column=0,sticky='ew',pady=(0,6));location.columnconfigure(2,weight=1)
        ttk.Button(location,text='Folder…',command=self.choose_folder).grid(row=0,column=0)
        ttk.Button(location,text='Files…',command=self.more).grid(row=0,column=1,padx=4)
        self.path_entry=ttk.Combobox(location,textvariable=self.folder,values=app.read_preferences().get('recent_import_folders',[]))
        self.path_entry.grid(row=0,column=2,sticky='ew');self.path_entry.bind('<Return>',lambda e:self.open_folder())
        ttk.Button(location,text='↑',width=3,command=self.up_folder).grid(row=0,column=3,padx=3)
        ttk.Button(location,text='Scan',command=self.open_folder,width=6).grid(row=0,column=4)
        ttk.Checkbutton(location,text='Subfolders',variable=self.recursive).grid(row=0,column=5,padx=5)
        ttk.Button(location,text='Stop',width=5,command=self.cancel_scan).grid(row=0,column=6)
        panes=ttk.Panedwindow(body,orient='horizontal');panes.grid(row=1,column=0,sticky='nsew')
        side=ttk.Frame(panes,width=225);main=ttk.Frame(panes);panes.add(side,weight=0);panes.add(main,weight=1)
        side.rowconfigure(1,weight=1);side.columnconfigure(0,weight=1)
        ttk.Label(side,text='Sources',style='Title.TLabel').grid(row=0,column=0,sticky='w',pady=(1,7))
        self.source_tree=ttk.Treeview(side,columns=('access',),selectmode='extended',show='tree headings')
        self.source_tree.heading('#0',text='Browse');self.source_tree.heading('access',text='Library')
        self.source_tree.column('#0',width=157,minwidth=95);self.source_tree.column('access',width=61,minwidth=54,stretch=False)
        self.source_tree.grid(row=1,column=0,sticky='nsew');scroll=ttk.Scrollbar(side,command=self.source_tree.yview);scroll.grid(row=1,column=1,sticky='ns');self.source_tree.configure(yscrollcommand=scroll.set)
        self.source_tree.bind('<<TreeviewSelect>>',self.source_selected);self.source_tree.bind('<Button-1>',self.access_click,add='+')
        self.source_tree.bind('<Button-3>',self.album_menu);self.source_tree.bind('<space>',self.toggle_selected_access)
        tools=ttk.Frame(side);tools.grid(row=2,column=0,sticky='ew',pady=5)
        manage=ttk.Menubutton(tools,text='Albums…');manage.pack(side='left');self.manage_menu=tk.Menu(manage,tearoff=False);manage.configure(menu=self.manage_menu)
        for label,fn in [('Show / hide in Library',self.toggle_selected_access),('Rename…',self.rename_selected),('Remove from browser',self.remove_selected),('Restore selected',lambda:self.remove_selected(False)),('Find duplicate albums',self.find_duplicates),('Undo album action',self.undo_album_action)]:self.manage_menu.add_command(label=label,command=fn)
        ttk.Checkbutton(side,text='Show removed albums',variable=self.show_removed,command=self.refresh_sources).grid(row=3,column=0,sticky='w')
        app.add_tip(self.source_tree,'Choose an album to browse. Click its Library column to make it available without importing. Right-click for rename, remove and restore. Removing an album never deletes source files.')
        main.columnconfigure(0,weight=1);main.rowconfigure(1,weight=1)
        title=ttk.Frame(main);title.grid(row=0,column=0,sticky='ew',pady=(0,5));ttk.Label(title,textvariable=self.source_title,style='Title.TLabel').pack(side='left')
        ttk.Button(title,text='Basket',command=self.show_basket).pack(side='right')
        self.browser=SourceBrowser(main,app,model=self.model,inclusion=True,on_visible=self.visible);self.browser.grid(row=1,column=0,sticky='nsew');self.tree=self.browser
        self.browser.bind('<<TreeviewSelect>>',self.selection);self.browser.bind('<<BrowserChanged>>',self.selection)
        self.browser.bind('<<ActivateMedia>>',self.preview);self.browser.canvas.bind('<Double-1>',self.preview,add='+')
        selection=ttk.Frame(body);selection.grid(row=2,column=0,sticky='ew',pady=(6,3))
        for label,op in [('Include visible','include'),('Exclude visible','exclude'),('Invert','invert'),('Clear basket','clear')]:ttk.Button(selection,text=label,command=lambda v=op:self.include(v)).pack(side='left',padx=(0,4))
        ttk.Label(selection,textvariable=self.summary,style='Muted.TLabel').pack(side='right')
        ttk.Label(body,textvariable=self.focus_info,style='Muted.TLabel',anchor='w').grid(row=3,column=0,sticky='ew',pady=(1,4))
        foot=ttk.Frame(body);foot.grid(row=4,column=0,sticky='ew');foot.columnconfigure(1,weight=1)
        ttk.Label(foot,text='To album').grid(row=0,column=0,padx=(0,4))
        ttk.Combobox(foot,textvariable=self.album,values=list(self.albums),state='readonly',width=16).grid(row=0,column=1,sticky='ew')
        from import_destinations import choices
        self.use_box=ttk.Combobox(foot,textvariable=self.use,values=choices(app.project),state='readonly',width=24)
        self.use_box.grid(row=0,column=2,padx=5)
        self.import_button=ttk.Button(foot,text='Import selected',style='Accent.TButton',command=self.commit);self.import_button.grid(row=0,column=3,padx=3)
        ttk.Button(foot,text='Cancel',command=self.destroy).grid(row=0,column=4)
        self.bind('<Escape>',lambda e:self.destroy());self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.worker=threading.Thread(target=self.work,name='Media browser inspection',daemon=True);self.worker.start()
        self.refresh_sources();self.add_paths(paths);self.set_pending(pending_randomise);self.poll();self.selection()
        self.setup_drop()
        self._drop_after=self.after(400,self.setup_drop)
    def setup_drop(self):
        self._drop_after=None
        if self.closed or not getattr(self.app,'dnd_available',False):return
        try:
            from tkinterdnd2 import DND_FILES
            for target in (self,self.browser.canvas):
                target.drop_target_register(DND_FILES);target.dnd_bind('<<Drop>>',self.receive_drop)
        except (ImportError,AttributeError,tk.TclError):pass
    def receive_drop(self,event):
        self.add_paths(self.app.parse_drop(event.data))
        return 'copy'
    def retain_thumbnail(self,iid):return iid in self._visible_thumbnail_ids
    def visible(self,ids):
        current=set(ids)
        if current!=self._visible_thumbnail_ids:
            self._visible_thumbnail_ids=current
            # Discard queued off-page preview work, never metadata or basket rows.
            retained=[]
            while True:
                try:job=self.thumb_jobs.get_nowait()
                except queue.Empty:break
                if job[1] in current:retained.append(job)
            for job in retained:self.thumb_jobs.put(job)
            self.pending_thumbs.intersection_update(current|set(self.photos))
        self.trim_thumbnails();super().visible(ids)
    def trim_thumbnails(self):
        excess=max(0,len(self.photos)-self.THUMBNAIL_LIMIT)
        for key in tuple(self.photos):
            if not excess:break
            if key in self._visible_thumbnail_ids:continue
            self.photos.pop(key,None);self.browser.photos.pop(key,None);excess-=1
        self.pending_thumbs.intersection_update(self._visible_thumbnail_ids|set(self.photos))
    def poll(self):
        super().poll()
        if not self.closed:self.trim_thumbnails()
    def set_pending(self,request):
        if request is not None:self.pending_randomise=copy.deepcopy(request)
        pending=bool(self.pending_randomise)
        self.import_button.configure(text='Import & Randomise' if pending else 'Import selected')
        self.use_box.configure(state='disabled' if pending else 'readonly')
        if pending:self.focus_info.set('Choose media for '+str(self.pending_randomise.get('only_role') or 'the queues')+'. Cancel leaves the performance unchanged.')
    def refresh_sources(self):
        selected=self.source_tree.selection();self.source_tree.delete(*self.source_tree.get_children());self.source_nodes={}
        self.source_tree.insert('','end',iid='device',text='Device selection',values=('',));self.source_tree.insert('','end',iid='basket',text='Import basket',values=('',))
        self.source_tree.insert('','end',iid='archives',text='Previous albums',open=True,values=('',))
        enabled=self.app.catalog.browser_album_ids();removed=self.app.catalog.removed_album_ids()
        for a in self.app.catalog.albums(include_removed=self.show_removed.get()):
            aid=a['id'];node='album:'+aid
            self.source_nodes[node]=(aid,'original')
            self.source_tree.insert('archives','end',iid=node,text=a['name'],values=('Removed' if aid in removed else '☑' if aid in enabled else '☐',))
            for version in self.app.catalog.album_versions(aid)[1:]:
                rev=version['revision'];iid=node+':'+rev;self.source_nodes[iid]=(aid,rev)
                self.source_tree.insert(node,'end',iid=iid,text='Edited · '+version.get('project','')[-8:],values=('',))
        self.source_tree.insert('','end',iid='unsorted',text='Previous unsorted',values=('☑' if '__unsorted__' in enabled else '☐',))
        for node in selected:
            if self.source_tree.exists(node):self.source_tree.selection_add(node)
    def source_selected(self,event=None):
        selected=self.source_tree.selection()
        if not selected:return
        node=selected[0]
        if node in self.source_nodes:self.show_album(*self.source_nodes[node])
        elif node=='device':self.show_device()
        elif node=='basket':self.show_basket()
        elif node=='unsorted':self.show_album(None)
    def show_device(self):
        self.source='device';self.browser.source_ids=self.device_ids;self.source_title.set('Device selection');self.browser.refilter();self.selection()
    def show_basket(self):
        self.source='basket';self.browser.source_ids=self.model.checked;self.source_title.set('Import basket');self.browser.refilter();self.selection()
    def show_album(self,album,revision='original'):
        raw={a['id']:a for a in self.app.catalog.assets()}
        if album:
            version=self.app.catalog.album_revision(album,revision);raw.update(version.get('assets',{}));ids=version['ids']
            name=next((a['name'] for a in self.app.catalog.albums(True) if a['id']==album),'Album')
        else:
            grouped={i for a in self.app.catalog.albums(True) for i in self.app.catalog.member_ids(a['id'])};ids=set(raw)-grouped;name='Previous unsorted'
        shown=set()
        for aid in ids:
            if aid not in raw:continue
            a=raw[aid];iid='catalogue:'+str(album)+':'+revision+':'+aid;shown.add(iid)
            if iid in self.model.items:continue
            path=a.get('path','');kind=a.get('kind','image');info={**a.get('metadata',{}),'duration':a.get('duration',0),'width':a.get('width',0),'height':a.get('height',0)}
            info.pop('existing_asset_id',None)
            exists=kind not in ('image','video','audio') or Path(path).is_file()
            item=BrowserItem(iid,path,kind,a.get('name','Media'),info=info,state='ready' if exists else 'error',error='' if exists else 'Source file is missing')
            self.model.add(item);self.catalogue_rows[iid]=(aid,album,revision)
        self.source='album';self.browser.source_ids=shown;self.source_title.set(name+(' · edited' if revision!='original' else ''));self.browser.refilter();self.selection()
    def add_item(self,item):
        self.device_ids.add(item.id);super().add_item(item)
    def add_paths(self,paths):
        if not paths:return
        self.include_new=True;self.show_device();super().add_paths(paths);self.selection()
    def open_folder(self,path=None):
        if path is not None:self.folder.set(str(path))
        p=Path(self.folder.get()).expanduser()
        if not p.is_dir():self.focus_info.set('Choose an existing readable folder.');return
        self.scan_stop.set();self.scan_stop=threading.Event()
        self.app.last_import_folder=str(p.resolve());self.app.recent_import_folders=list(dict.fromkeys([str(p.resolve()),*getattr(self.app,'recent_import_folders',[])]))[:12]
        self.add_paths([str(p)])
    def up_folder(self):self.open_folder(Path(self.folder.get() or Path.home()).expanduser().parent)
    def selection(self,event=None):
        if self.closed:return
        self.import_button.configure(state='normal' if self.model.checked else 'disabled')
        pending=sum(r.state=='pending' for r in self.model.items.values())
        self.summary.set(f'{len(self.model.checked)} included'+(' · scanning' if self.scanning else '')+(f' · {pending} inspecting' if pending else ''))
        r=self.model.items.get(self.model.focus)
        if r:self.focus_info.set((r.error or r.path)[-135:])
    def selected_albums(self):return list(dict.fromkeys(self.source_nodes[n][0] for n in self.source_tree.selection() if n in self.source_nodes))
    def access_click(self,event):
        if self.source_tree.identify_column(event.x)!='#1':return
        node=self.source_tree.identify_row(event.y)
        if node in self.source_nodes or node=='unsorted':
            self.source_tree.selection_set(node);self.toggle_selected_access();return 'break'
    def toggle_selected_access(self,event=None):
        ids=self.selected_albums()
        if 'unsorted' in self.source_tree.selection():ids.append('__unsorted__')
        if not ids:return 'break'
        enabled=self.app.catalog.browser_album_ids();enable=not all(i in enabled for i in ids)
        self.album_undo.append(('visibility',{i:i in enabled for i in ids}))
        for aid in ids:self.app.catalog.set_album_visible(aid,enable)
        self.refresh_sources();self.app.refresh_library();return 'break'
    def album_menu(self,event):
        node=self.source_tree.identify_row(event.y)
        if node and node not in self.source_tree.selection():self.source_tree.selection_set(node)
        from contextual_surface import post_native_menu
        post_native_menu(self.app,self.manage_menu,self.source_tree,event,dispose_menu=False)
    def remove_selected(self,removed=True):
        ids=self.selected_albums()
        if not ids:return
        previous=self.app.catalog.removed_album_ids();self.album_undo.append(('removed',{i:i in previous for i in ids}))
        self.app.catalog.archive_albums(ids,removed);self.refresh_sources();self.app.refresh_library()
        self.focus_info.set('Album entries '+('removed' if removed else 'restored')+'. Source files and existing queues are unchanged. Albums → Undo restores this action.')
    def rename_selected(self):
        ids=self.selected_albums()
        if len(ids)!=1:return self.focus_info.set('Select one album to rename.')
        aid=ids[0];old=next(a['name'] for a in self.app.catalog.albums(True) if a['id']==aid)
        name=simpledialog.askstring('Rename album','Name:',initialvalue=old,parent=self)
        if not name:return
        try:self.app.catalog.rename_album(aid,name)
        except ValueError as exc:return self.focus_info.set(str(exc))
        self.album_undo.append(('name',{aid:old}));self.refresh_sources();self.app.refresh_library()
    def undo_album_action(self):
        if not self.album_undo:return
        kind,values=self.album_undo.pop()
        for aid,value in values.items():
            if kind=='removed':self.app.catalog.archive_albums([aid],value)
            elif kind=='visibility':self.app.catalog.set_album_visible(aid,value)
            else:self.app.catalog.rename_album(aid,value)
        self.refresh_sources();self.app.refresh_library()
    def find_duplicates(self):
        groups=self.app.catalog.duplicate_albums();nodes=['album:'+i for group in groups for i in group]
        self.source_tree.selection_set(nodes)
        self.focus_info.set(f'{len(groups)} duplicate membership groups. Review selected albums, keep a preferred copy and remove the others. No files are deleted.')
    def commit(self):
        if self.app.project.id!=self.project_id:return self.focus_info.set('The project changed. Close this browser and reopen it in the intended project.')
        if self.app.importing:return self.focus_info.set('An import is finishing. Your basket is retained; try again when it finishes.')
        chosen=self.model.snapshot(sort=self.browser.sort.get(),descending=self.browser.reverse.get())
        if not chosen:return self.focus_info.set('Include at least one readable source.')
        groups={};device=[]
        for row in chosen:
            if row.id in self.catalogue_rows:
                aid,album,revision=self.catalogue_rows[row.id];groups.setdefault((album,revision),[]).append(aid)
            else:device.append(row)
        for (album,revision),ids in groups.items():self.app.include_previous(ids,album,revision=None if revision=='original' else revision)
        request=copy.deepcopy(self.pending_randomise)
        archive_ids=list(dict.fromkeys(aid for ids in groups.values() for aid in ids))
        destination=self.albums.get(self.album.get(),'all')
        if archive_ids and destination!='all':self.app._change_members(destination,archive_ids,True)
        if device:
            metadata={r.path:{'info':dict(r.info),'fingerprint':tuple(r.fingerprint),'kind':r.kind} for r in device if r.metadata_valid()}
            self.app._media_browser_completion=dict(project_id=self.project_id,request=request,archive_ids=archive_ids,use=self.use.get())
            self.app.import_files([r.path for r in device],album=destination,staged=metadata,use='Library only')
        elif request:self.app.randomise_playable(**request)
        else:self.app.place_browser_selection(archive_ids,self.use.get())
        self.destroy()
    def destroy(self):
        if self.closed:return
        if self._drop_after:
            self.after_cancel(self._drop_after);self._drop_after=None
        super().destroy()
        if getattr(self.app,'import_window',None) is self:self.app.import_window=None
