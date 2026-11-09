"""Import and source-personality surfaces; folder browsing lives inside the overlay."""
from __future__ import annotations
import copy, math, queue, threading, time, os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from frame_sources import FrameSources
from media_engine import probe_media, kind_for_path
from sequencer_model import Asset
from media_browser_model import BrowserModel, BrowserItem, scan_folder, fingerprint
from media_browser_view import MediaBrowser

class ImportSurface:
    def initialise_services(self,app,compact=False):
        """Shared cancellable scanner/metadata/thumbnail service, independent of chrome."""
        self.compact=compact;self.app=app;self.closed=False;self.stop=threading.Event();self.scan_stop=threading.Event();self.jobs=queue.Queue();self.thumb_jobs=queue.Queue();self.results=queue.Queue(maxsize=256);self.photos={};self.paths={};self.info={};self.pending_thumbs=set();self.generation=0;self.scanning=False;self.include_new=True;self.poll_id=None
        self.identity_assets=copy.deepcopy(list(app.project.assets.values()));self.identity=None
    def initialise(self,app,paths=(),compact=False):
        self.initialise_services(app,compact)
        b=ttk.Frame(self,padding=5 if compact else 12);b.pack(fill='both',expand=True);b.columnconfigure(0,weight=1);b.rowconfigure(3,weight=1)
        ttk.Label(b,text='IMPORT INTO LIBRARY',style='Title.TLabel').grid(row=0,column=0,sticky='w')
        locations=ttk.Frame(b);locations.grid(row=1,column=0,sticky='ew',pady=(5,4));locations.columnconfigure(0,weight=1)
        self.folder=tk.StringVar(value=getattr(app,'last_import_folder',''));self.path_entry=ttk.Combobox(locations,textvariable=self.folder,values=app.read_preferences().get('recent_import_folders',[]));self.path_entry.grid(row=0,column=0,sticky='ew');self.path_entry.bind('<Return>',lambda e:self.open_folder())
        ttk.Button(locations,text='Scan',width=6,command=self.open_folder).grid(row=0,column=1,padx=(3,0))
        choose=ttk.Frame(locations);choose.grid(row=1,column=0,columnspan=2,sticky='ew',pady=4)
        ttk.Button(choose,text='Choose folder…',command=self.choose_folder).pack(side='left');ttk.Button(choose,text='Add files…',command=self.more).pack(side='left',padx=4)
        self.recursive=tk.BooleanVar(value=True)
        top=ttk.Frame(b);top.grid(row=2,column=0,sticky='ew',pady=(0,5));top.columnconfigure(1,weight=1)
        ttk.Checkbutton(top,text='Subfolders',variable=self.recursive,command=self.open_folder).grid(row=0,column=0,sticky='w')
        ttk.Button(top,text='Stop scan',command=self.cancel_scan).grid(row=0,column=1,sticky='e')
        albums=app.catalog.albums();self.albums={'All media':'all',**{a['name']:a['id'] for a in albums}};self.album=tk.StringVar(value=next((n for n,i in self.albums.items() if i==app.album.get()),'All media'))
        ttk.Label(top,text='To album').grid(row=1,column=0,sticky='w',pady=(4,0));ttk.Combobox(top,textvariable=self.album,values=list(self.albums),state='readonly',width=17).grid(row=1,column=1,sticky='ew',pady=(4,0))
        self.model=BrowserModel();self.browser=MediaBrowser(b,app,model=self.model,inclusion=True,on_visible=self.visible,compact=compact);self.browser.grid(row=3,column=0,sticky='nsew');self.tree=self.browser
        if compact:self.browser.thumb.set('Small')
        self.browser.bind('<<TreeviewSelect>>',self.selection);self.browser.bind('<<BrowserChanged>>',self.selection)
        self.browser.bind('<Double-1>',self.preview);self.browser.bind('<<ActivateMedia>>',self.preview)
        tools=ttk.Frame(b);tools.grid(row=4,column=0,sticky='ew',pady=4)
        for i,(label,op) in enumerate([('Include visible','include'),('Exclude visible','exclude'),('Invert visible','invert'),('Clear all','clear')]):
            tools.columnconfigure(i%2,weight=1);ttk.Button(tools,text=label,command=lambda v=op:self.include(v)).grid(row=i//2,column=i%2,sticky='ew',padx=1,pady=1)
        self.summary=tk.StringVar();ttk.Label(b,textvariable=self.summary,style='Muted.TLabel',wraplength=275 if compact else 950).grid(row=5,column=0,sticky='ew',pady=3)
        self.focus_info=tk.StringVar(value='Inspect a thumbnail; check to include. Space toggles. Drop files here or choose a folder.')
        ttk.Label(b,textvariable=self.focus_info,style='Muted.TLabel',wraplength=275 if compact else 950).grid(row=6,column=0,sticky='ew',pady=3)
        foot=ttk.Frame(b);foot.grid(row=7,column=0,sticky='ew',pady=(4,0));foot.columnconfigure(0,weight=1);self.use=tk.StringVar(value='Library only')
        from import_destinations import choices
        ttk.Combobox(foot,textvariable=self.use,values=choices(app.project),state='readonly',width=24).grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,4))
        ttk.Button(foot,text='Import included',style='Accent.TButton',command=self.commit).grid(row=1,column=0,sticky='ew')
        ttk.Button(foot,text='Back',command=self.destroy).grid(row=1,column=1,padx=(3,0))
        self.existing_button=ttk.Button(foot,text='Link existing items to this album',command=self.use_existing);self.existing_button.grid(row=2,column=0,columnspan=2,sticky='ew',pady=3);self.existing_button.grid_remove()
        self.worker=threading.Thread(target=self.work,name='Import inspection',daemon=True);self.worker.start();self.add_paths(paths);self.poll();self.path_entry.focus_set()
    def use_existing(self):
        rows=[r for r in self.model.items.values() if r.info.get('existing_asset_id')]
        if not rows:return self.focus_info.set('No existing items found yet. Unchanged duplicates are linked, never imported twice.')
        self.app.import_files([r.path for r in rows],album=self.albums.get(self.album.get(),'all'),use=self.use.get());self.destroy()
    def put(self,item):
        while not self.stop.is_set():
            try:self.results.put(item,timeout=.1);return
            except queue.Full:pass
    def choose_folder(self):
        path=filedialog.askdirectory(parent=self,title='Choose a media folder',initialdir=self.folder.get() or None)
        if path:self.folder.set(path);self.open_folder()
    def cancel_scan(self):self.scan_stop.set();self.scanning=False;self.selection()
    def open_folder(self,path=None):
        if path is not None:self.folder.set(str(path))
        path=Path(self.folder.get()).expanduser()
        if not path.is_dir():self.focus_info.set('Choose an existing readable folder.');return
        self.scan_stop.set();self.scan_stop=threading.Event();stop=self.scan_stop;self.generation+=1;gen=self.generation;self.scanning=True;self.include_new=True
        self.model.items.clear();self.model.checked.clear();self.model.selected.clear();self.paths.clear();self.info.clear();self.browser.photos.clear();self.photos.clear();self.pending_thumbs.clear();self.browser.refilter()
        self.app.last_import_folder=str(path.resolve())
        self.app.recent_import_folders=list(dict.fromkeys([str(path.resolve()),*getattr(self.app,'recent_import_folders',[])]))[:12]
        recursive=self.recursive.get()
        def scan():
            batch=[]
            for item in scan_folder(path,recursive=recursive,stop=stop):
                if self.stop.is_set():return
                batch.append(item)
                if len(batch)>=64:self.put(('scan',gen,batch));batch=[]
            if batch:self.put(('scan',gen,batch))
            self.put(('scan_done',gen,None))
        threading.Thread(target=scan,name='Folder discovery',daemon=True).start()
    def add_paths(self,paths):
        folders=[]
        for path in paths:
            if Path(path).is_dir():folders.append(str(path));continue
            self.add_item(BrowserItem.from_path(path))
        if folders:
            self.folder.set(folders[0]);self.scanning=True;gen=self.generation;recursive=self.recursive.get();stop=self.scan_stop
            def scan():
                batch=[]
                for folder in folders:
                    for item in scan_folder(folder,recursive=recursive,stop=stop):
                        if self.stop.is_set():return
                        batch.append(item)
                        if len(batch)>=64:self.put(('scan',gen,batch));batch=[]
                if batch:self.put(('scan',gen,batch))
                self.put(('scan_done',gen,None))
            threading.Thread(target=scan,name='Dropped folder scan',daemon=True).start()
        self.browser.schedule()
    def add_item(self,item):
        if not self.model.add(item):return
        self.paths[item.id]=item.path
        if self.include_new and not item.error:self.model.checked.add(item.id)
        if not item.error:self.jobs.put((self.generation,item.id,item.path))
    def more(self):
        paths=filedialog.askopenfilenames(parent=self,title='Add files to preview browser')
        if paths:self.add_paths(paths)
    def include(self,op):
        if op=='clear':self.include_new=False
        self.model.include_visible(self.browser.rows(),op);self.browser.schedule();self.selection()
    def selection(self,event=None):
        rows=self.browser.rows();hidden=self.model.hidden_checked(rows);pending=sum(r.state=='pending' for r in self.model.items.values())
        existing=sum(bool(r.info.get('existing_asset_id')) for r in self.model.items.values())
        if existing:self.existing_button.grid()
        else:self.existing_button.grid_remove()
        self.summary.set(f'{existing} already in Library · {len(self.model.checked)} included · {hidden} hidden by filters · {len(self.model.items)} discovered'+(' · scanning…' if self.scanning else '')+(f' · {pending} awaiting metadata' if pending else ''))
        if self.model.focus in self.model.items:
            r=self.model.items[self.model.focus];self.focus_info.set(r.error or ('Already in Library · ' if r.info.get('existing_asset_id') else '')+r.path+(' · sound available' if r.info.get('has_audio') else ''))
    def visible(self,ids):
        for iid in ids:
            r=self.model.items.get(iid)
            if r and r.state=='ready' and r.kind!='audio' and iid not in self.pending_thumbs and iid not in self.photos:
                self.pending_thumbs.add(iid);self.thumb_jobs.put((self.generation,iid,r.path,dict(r.info),r.kind))
    def work(self):
        from media_identity import IdentityIndex
        self.identity=IdentityIndex(self.identity_assets)
        frames=FrameSources(max_readers=1)
        try:
            while not self.stop.is_set():
                try:job=self.thumb_jobs.get_nowait();is_thumb=True
                except queue.Empty:
                    try:job=self.jobs.get(timeout=.1);is_thumb=False
                    except queue.Empty:continue
                gen,iid,path=job[:3]
                if gen!=self.generation:continue
                try:
                    if is_thumb:
                        info,kind=job[3:];a=Asset(iid,path,kind,Path(path).name,info['duration'],info['width'],info['height'],info)
                        img=frames.frame(a,min(1,a.duration/3),(128,72),fit='contain',reader_key=iid,project_size=(max(1,a.width),max(1,a.height)));self.put(('image',gen,(iid,img)))
                    else:
                        fp=fingerprint(path);duplicate=self.identity.find(path);info=probe_media(path)
                        if duplicate:info['existing_asset_id']=duplicate
                        self.put(('metadata',gen,(iid,kind_for_path(path),info,fp,'')))
                except Exception as exc:
                    if is_thumb:self.put(('thumbnail_error',gen,(iid,str(exc))))
                    else:self.put(('metadata',gen,(iid,'',{},(),str(exc))))
        finally:frames.close()
    def poll(self):
        if self.closed:return
        dirty=False
        for _ in range(24):
            try:typ,gen,payload=self.results.get_nowait()
            except queue.Empty:break
            if gen!=self.generation:continue
            if typ=='scan':
                for item in payload:self.add_item(item)
                dirty=True
            elif typ=='scan_done':self.scanning=False;dirty=True
            elif typ=='metadata':
                iid,kind,info,fp,error=payload;r=self.model.items.get(iid)
                if not r:continue
                r.kind=kind or r.kind;r.info=info;r.fingerprint=fp;r.error=error;r.state='error' if error else 'ready';self.info[iid]=(r.kind,info,error);dirty=True
                if info.get('existing_asset_id') and not self.model.allow_existing:self.model.checked.discard(iid)
            elif typ=='thumbnail_error':
                iid,error=payload
                if iid in self.model.items:self.model.items[iid].info['preview_error']=error;self.focus_info.set('Thumbnail unavailable; this source can still be imported.');dirty=True
            elif typ=='image':
                iid,img=payload
                if iid in self.model.items and getattr(self,'retain_thumbnail',lambda key:True)(iid):self.photos[iid]=ImageTk.PhotoImage(img);self.browser.photos[iid]=self.photos[iid];dirty=True
        if dirty:self.browser.schedule();self.selection()
        self.poll_id=self.after(70,self.poll)
    def preview(self,event=None):
        r=self.model.items.get(self.model.focus)
        if not r or not r.info or r.error:return
        from media_engine import FFPLAY
        from process_tools import popen_options
        import subprocess
        if not FFPLAY:return self.focus_info.set('Preview needs FFplay; source remains importable.')
        # Explicit audition is separate from Programme. The launched player owns itself.
        subprocess.Popen([FFPLAY,'-hide_banner','-loglevel','error','-autoexit','-window_title','Import audition · '+r.name,r.path],**popen_options(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def commit(self):
        chosen=self.model.snapshot(sort=self.browser.sort.get(),descending=self.browser.reverse.get())
        if not chosen:return messagebox.showinfo('Import','Include at least one readable source.',parent=self)
        metadata={r.path:{'info':dict(r.info),'fingerprint':tuple(r.fingerprint),'kind':r.kind} for r in chosen if r.metadata_valid()}
        self.app.import_files([r.path for r in chosen],album=self.albums[self.album.get()],staged=metadata,use=self.use.get());self.destroy()
    def destroy(self):
        if self.closed:return
        self.closed=True;self.stop.set();self.scan_stop.set()
        if self.poll_id:
            try:self.after_cancel(self.poll_id)
            except tk.TclError:pass
        super().destroy()

class ImportStage(ImportSurface,tk.Toplevel):
    def __init__(self,app,paths=()):
        tk.Toplevel.__init__(self,app);self.title('Import media');self.geometry('1040x760');self.minsize(700,540);self.transient(app);self.bind('<Escape>',lambda e:self.destroy());self.initialise(app,paths)

class DockedImport(ImportSurface,ttk.Frame):
    def __init__(self,parent,app,paths=()):
        ttk.Frame.__init__(self,parent);self.initialise(app,paths,compact=True)
    def destroy(self):
        if self.closed:return
        ImportSurface.destroy(self)
        if not self.app.closing:
            self.app.import_window=None
            self.app.library_tabs.select(self.app.library_media_tab)


class PersonalityDialog(tk.Toplevel):
    def __init__(self,app,ids):
        super().__init__(app);self.app=app;self.ids=ids;self.title('Source personality · defaults for future use');self.transient(app);self.geometry('680x610');self.minsize(610,520);self.values={};self.roles={}
        b=ttk.Frame(self,padding=14);b.pack(fill='both',expand=True)
        assets=[app.project.asset(i) for i in ids if app.project.asset(i)];self.assets=assets
        ttk.Label(b,text=assets[0].name if len(assets)==1 else f'{len(assets)} source personalities',style='Title.TLabel').pack(anchor='w')
        ttk.Label(b,text='Defaults guide future generation. Existing occurrences remain unchanged.\nMixed / blank values are left alone; Reset inheritance is a separate action.',style='Muted.TLabel',justify='left').pack(anchor='w',pady=8)
        def common(key,default=''):
            vals=[a.metadata.get('sequence_preferences',{}).get(key,default) for a in assets]
            return vals[0] if all(v==vals[0] for v in vals) else ''
        self.enabled=tk.StringVar(value=str(common('enabled',True)));row=ttk.Frame(b);row.pack(fill='x');ttk.Label(row,text='Generation pool',width=26).pack(side='left');ttk.Combobox(row,textvariable=self.enabled,values=['True','False',''],state='readonly',width=15).pack(side='left')
        for key,title,default in [('weight','Probability weight (0 = off)',1),('clip_min','Minimum occurrence (s)',''),('clip_max','Maximum occurrence (s)',''),('source_in','Usable source start (s)',''),('source_out','Usable source end (s)',''),('intensity','Effect intensity (0–1)','')]:
            row=ttk.Frame(b);row.pack(fill='x',pady=3);ttk.Label(row,text=title,width=27).pack(side='left');v=tk.StringVar(value=str(common(key,default)));self.values[key]=v;ttk.Entry(row,textvariable=v,width=15).pack(side='left')
        row=ttk.Frame(b);row.pack(fill='x',pady=5);ttk.Label(row,text='End of source',width=27).pack(side='left');self.policy=tk.StringVar(value=str(common('source_policy','loop')));ttk.Combobox(row,textvariable=self.policy,values=['loop','hold',''],state='readonly',width=15).pack(side='left')
        row=ttk.Frame(b);row.pack(fill='x',pady=5);ttk.Label(row,text='Conductor voice roles',width=27).pack(side='left')
        common_roles=common('roles',['A','B']);self.roles_mixed=not isinstance(common_roles,list)
        for role in ('A','B','C','D'):
            v=tk.BooleanVar(value=self.roles_mixed or role in common_roles);self.roles[role]=v;ttk.Checkbutton(row,text=role,variable=v,command=lambda:setattr(self,'roles_mixed',False)).pack(side='left')
        if len(assets)==1:ttk.Button(b,text='Detailed effect / reaction preferences…',command=self.detail).pack(anchor='w',pady=7)
        ttk.Label(b,text='Manual assignment is always allowed. Voice roles restrict procedural choice.\nUse the clip controls to trim an existing occurrence or replace its media.',style='Muted.TLabel',justify='left').pack(anchor='w',pady=10)
        row=ttk.Frame(b);row.pack(side='bottom',fill='x');ttk.Button(row,text='Reset inheritance',command=self.reset).pack(side='left');ttk.Button(row,text='Apply defaults',style='Accent.TButton',command=self.save).pack(side='right');ttk.Button(row,text='Cancel',command=self.destroy).pack(side='right',padx=5)
    def detail(self):
        from source_dialogs import AssetPreferences
        AssetPreferences(self.app,self.assets[0])
    def reset(self):
        self.app.transaction('Restore source inheritance',lambda:[a.metadata.pop('sequence_preferences',None) for a in self.assets]);self.destroy()
    def save(self):
        try:
            updates={}
            for key,var in self.values.items():
                if not var.get().strip():continue
                value=float(var.get())
                if not math.isfinite(value) or value<0:raise ValueError('Use finite, nonnegative values')
                if key=='intensity' and value>1:raise ValueError('Intensity is 0–1')
                if key=='weight' and value>1000:raise ValueError('Probability weight must be 0–1000')
                if key in ('clip_min','clip_max') and not .15<=value<=240:raise ValueError('Occurrence duration is 0.15–240 seconds')
                updates[key]=value
            if self.enabled.get() in ('True','False'):updates['enabled']=self.enabled.get()=='True'
            if self.policy.get():updates['source_policy']=self.policy.get()
            if not self.roles_mixed:updates['roles']=[r for r,v in self.roles.items() if v.get()]
            prepared=[]
            for a in self.assets:
                p={**copy.deepcopy(a.metadata.get('sequence_preferences',{})),**updates}
                if p.get('clip_min',self.app.project.conductor.clip_min)>p.get('clip_max',self.app.project.conductor.clip_max):raise ValueError('Maximum occurrence must be at least the minimum')
                if p.get('source_out',a.duration or math.inf)<=p.get('source_in',0):raise ValueError('Source end must follow source start')
                if a.duration and p.get('source_out',a.duration)>a.duration+.05:raise ValueError('Source end exceeds '+a.name+' duration')
                prepared.append((a,p))
            self.app.transaction('Source defaults saved',lambda:[a.metadata.__setitem__('sequence_preferences',p) for a,p in prepared]);self.destroy()
        except Exception as exc:messagebox.showerror('Source personality',str(exc),parent=self)
