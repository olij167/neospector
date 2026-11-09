"""Project-only, drop-first media. Existing render/queue transactions stay authoritative."""
import copy,os,threading
from pathlib import Path
from tkinter import filedialog,ttk,TclError
from sequencer_model import Asset,add_asset
from media_identity import IdentityIndex,canonical
from media_engine import probe_media,kind_for_path
from media_browser_model import media_kind

class ImmediateActions:
    def build_ui(self):
        super().build_ui()
        from immediate_inputs import InputBar
        self.input_bar=InputBar(self.queue_deck.sound,self)
        # Source actions are accessed from the adjacent MUSIC input selector.
        # Retain InputBar as an adapter for its existing, tested backend calls.
        self.input_bar.pack_forget()
        self.input_bar.video.pack_forget()
        self.import_media_button.configure(text='+ Files',command=self.add_media)
        m=self.library_action_more['menu']
        # Tk returns the menu pathname; configure through the existing widget.
        menu=self.nametowidget(str(m)) if isinstance(m,str) else m
        menu.delete(0,'end')
        menu.add_command(label='Media properties…',command=lambda:self.open_media_settings(list(self.library.selection()),'General'))
        menu.add_command(label='Locate missing file…',command=self.locate_missing)
        menu.add_command(label='Remove from project',command=self.remove_selected_media)
        self.library_settings_button.configure(text='⚙')
        self.library_destination_button.grid_remove()
        self.album_box.master.pack_forget()
        self.empty_preview.winfo_children()[0].configure(text='DROP VIDEO, PICTURES OR AUDIO')
        self.empty_preview.winfo_children()[2].configure(command=lambda:self.toggle_channel_camera(self.active_visual_role()))
        self.option_add('*TCombobox*Listbox.background','#151e27')
        self.option_add('*TCombobox*Listbox.foreground','#e2e8ef')
        self.option_add('*TCombobox*Listbox.selectBackground','#255970')
        self.option_add('*TCombobox*Listbox.selectForeground','#ffffff')
        self.refresh_library()
        self.library_modes.configure(style='Instrument.TNotebook')
        for browser in self.media_browsers.values():browser.media_kind='All'
        from responsive_controls import FlowRow
        nav=FlowRow(self.library_tabs.master,gap=5);nav.pack(fill='x',before=self.library_tabs)
        for label,mode in [('Project media','media'),('Effects','modules'),('Recipes','patches')]:
            button=ttk.Button(nav,text=label,command=lambda m=mode:self.select_library_mode(m));nav.add(button)
        self.shell.titles['panel.library'].configure(text='Ingredients')
        self.shell.titles['panel.queues'].configure(text='Sources')
        self.media_button.configure(text='Ingredients')
        self.shell.menus['panel.queues'].pack_forget()
        self.shell.menus['panel.library'].configure(text='× Close')
        self.visual_master_fader.winfo_children()[0].configure(text='PICTURE') if isinstance(self.visual_master_fader.winfo_children()[0],ttk.Label) else None
        self.save_project_button.configure(text='Save',width=5)
        self.play_button.configure(width=6)
        self.undo_button.configure(text='↶',width=3)
        self.redo_button.configure(text='↷',width=3)
        self.media_button.configure(width=11)
        self.export_project_button.configure(text='Export',width=7)
        for item in self.global_toolbar.items:
            if item['widget'] is self.export_project_button:item['pinned']=True;item['priority']=0
        self.global_toolbar.schedule()
        self.visual_master_fader.label.configure(text='PICTURE') if hasattr(self.visual_master_fader,'label') else None
        self.audio_now_label.configure(width=1)
        self.global_toolbar.set_available(self.audio_now_label,False)
        for widget in (self.play_button,self.undo_button,self.redo_button,
                       self.visual_master_fader,self.media_button):
            self.global_toolbar.set_available(widget,False)
        # UX21: Output View is already the one global command, added by the shell.
        self.global_toolbar.schedule()
    def _import_to_project(self):
        """Import into this project's media folder, without auto-playing or opening a legacy browser."""
        paths=filedialog.askopenfilenames(parent=self,title='Add files to Neospector project',filetypes=[('Supported media','*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tif *.tiff *.mp4 *.mov *.mkv *.webm *.avi *.wav *.mp3 *.flac *.ogg *.m4a *.opus *.aif *.aiff'),('All files','*.*')])
        if paths:
            from flow_media import MediaWorkflow
            MediaWorkflow.import_files(self,paths,use='Library only',album='all')

    def show_module_library(self):
        cell=self.deck.selected_cell()
        if cell is None:return False
        result=super().show_module_library()
        self.module_library.destination_caption.set('Add to '+self.deck.owner_title())
        return result
    def insert_module_from_library(self,fx,name,index=None,entry_type='Base'):
        # The selected A/B/Output rack is the only insertion target. It may
        # change while the module library remains open.
        return super().insert_module_from_library(fx,name,index,entry_type)
    def refresh_library_destination(self):
        if not hasattr(self,'queue_media_button'):return
        ids=list(self.library.selection());role=self.active_visual_role();self.library_destination.set(role)
        if self._library_audition_process is not None and (not ids or ids[0]!=getattr(self,'_library_audition_asset',None)):self.stop_library_audition()
        self.queue_media_button.configure(text='Add · Audio / '+role,state='normal' if ids else 'disabled')
        audible=bool(ids and all(self.project.asset(i) and self.project.asset(i).kind in ('audio','video') for i in ids))
        self.library_audition_button.grid(row=0,column=3,sticky='w',padx=2)
        self.library_audition_button.configure(state='normal' if audible else 'disabled')
        self.layout_library_actions()
    def queue_library_selection(self):
        ids=list(self.library.selection());role=self.active_visual_role()
        audio=[i for i in ids if self.project.asset(i) and self.project.asset(i).kind=='audio'];visual=[i for i in ids if self.project.asset(i) and self.project.asset(i).kind!='audio']
        if audio:self.queue_sound_selected(audio)
        if visual:self.queue_selected(role,asset_ids=visual)
        return ids
    def active_visual_role(self):
        cell=self.deck.selected_cell() if hasattr(self,'deck') else None
        if cell and cell.adapter.scope!='Master':
            owner=cell.adapter.parent if cell.adapter.scope=='Clip' else cell.adapter.owner
            return owner.extra.get('voice','A')
        role=getattr(getattr(self,'queue_deck',None),'active_role','A')
        return role if role in ('A','B','C','D') else 'A'
    def add_audio_files(self):
        paths=filedialog.askopenfilenames(parent=self,title='Add audio',filetypes=[('Audio','*.wav *.mp3 *.flac *.m4a *.ogg *.aiff *.aif *.opus')])
        if paths:
            from flow_media import MediaWorkflow
            return MediaWorkflow.import_files(self,paths,use='Library only',album='all')
    def add_media(self):return self._import_to_project()
    def open_import_browser(self,paths=(),pending_randomise=None):
        if paths:
            from flow_media import MediaWorkflow
            return MediaWorkflow.import_files(self,paths,use='Library only',album='all')
        return self.add_media()
    def import_folder(self):
        path=filedialog.askdirectory(parent=self,title='Add media folder')
        if path:self.drop_media([path],role=self.active_visual_role())
    def browse_audio(self):
        browser=self.project_media_folder.browser
        browser.filter_kind.set('Audio');browser.refilter()
        browser.focus_set()
    def load_catalogue_assets(self):self.repair_asset_records()
    def refresh_album_options(self):
        if not hasattr(self,'album_box'):return
        self._albums={'This project':'all'};self.album.set('all');self.album_label.set('This project');self.album_box.configure(values=['This project'])
    def refresh_library(self):
        if not hasattr(self,'media_browsers'):return
        if getattr(self,'_library_audition_project',None) is not None and self._library_audition_project is not self.project:self.stop_library_audition()
        hidden=set(self.project.extra.get('library_hidden',[]));removed=set(self.project.extra.get('library_removed',[]))
        assets=[a for a in self.project.assets.values() if a.id not in removed and (self.library_show_hidden.get() or a.id not in hidden)]
        key=(id(self.project),tuple((a.id,a.name,a.path,a.duration) for a in assets))
        if key!=getattr(self,'_immediate_library_key',None):
            self._immediate_library_key=key
            sections=[{'id':'current','name':'This project','ids':[a.id for a in assets],'current':True}]
            for browser in self.media_browsers.values():browser.set_assets(assets);browser.set_collections(sections,{})
        self.refresh_album_options()
        if hasattr(self,'empty_preview'):self.refresh_empty_preview()
        # ImmediateActions owns the effective refresh_library() in the MRO.
        # Never leave the visible project folder stale after import/relink/undo.
        if hasattr(self,'project_media_folder'):
            self.project_media_folder.refresh_assets()
            # This method wins the NeospectorApp MRO; refresh the visible
            # shared shelf HERE after imports, undo/redo and project restores.
            sidebar=getattr(self,'sidebar',None)
            if sidebar is not None:sidebar.source_shelf.media.refresh(force=True)
            self.library=self.project_media_folder.browser
            self.search=self.library.query
    def layout_library_actions(self):
        super().layout_library_actions()
        if hasattr(self,'library_settings_button'):self.library_settings_button.configure(text='⚙')
    def drop_paths(self,paths,album=None):return self.drop_media(paths,role=self.active_visual_role())
    def drop_media(self,paths,role=None):
        role=role or self.active_visual_role();pid=self.project.id
        if self.importing:
            self._direct_jobs=getattr(self,'_direct_jobs',[])+[(pid,tuple(paths),role)]
            return self.update_status('Adding files · next drop queued')
        self.importing=True;known=copy.deepcopy(list(self.project.assets.values()));paths=tuple(paths)
        self.update_status('Adding media…')
        def work():
            files=[];errors=[];seen=set()
            for raw in paths:
                p=Path(raw).expanduser()
                if p.is_dir():
                    for base,dirs,names in os.walk(p,followlinks=False):
                        dirs[:]=sorted(d for d in dirs if not d.startswith('.') and not (Path(base)/d).is_symlink())
                        for name in sorted(names):
                            file=Path(base)/name
                            if media_kind(file) and not file.is_symlink():files.append(file)
                        if len(files)>=2000:errors.append('Folder limited to 2000 files');break
                else:files.append(p)
            index=IdentityIndex(known);result=[]
            for p in files[:2000]:
                if self.closing:break
                try:
                    path=canonical(p)
                    if path in seen:continue
                    seen.add(path)
                    if not media_kind(path):raise ValueError('Unsupported media type')
                    existing=index.find(path)
                    if existing:
                        asset=next(a for a in index.assets if a.id==existing)
                        result.append((path,asset.kind,copy.deepcopy(asset.metadata),existing));continue
                    info=probe_media(path);kind=kind_for_path(path);result.append((path,kind,info,None))
                    asset=Asset('batch:'+path,path,kind,Path(path).name,info.get('duration',0),info.get('width',0),info.get('height',0),info)
                    index.assets.append(asset);index.add(asset)
                except Exception as exc:errors.append(p.name+': '+str(exc))
            self.events.put(('call',lambda:self.accept_direct_media(pid,result,errors,role)))
        threading.Thread(target=work,name='Add project media',daemon=True).start()
    def accept_direct_media(self,pid,result,errors,role):
        self.importing=False
        if self.project.id==pid:
            added=[]
            def commit():
                batch={}
                for path,kind,info,existing in result:
                    a=self.project.asset(existing) if existing else None
                    a=a or batch.get(existing)
                    if a is None:
                        a=add_asset(self.project,path=path,kind=kind,name=Path(path).name,duration=info.get('duration',0),width=info.get('width',0),height=info.get('height',0),metadata=info)
                        batch['batch:'+path]=a
                    added.append(a.id)
            if result:
                self.transaction('Add media',commit)
                audio=[i for i in added if self.project.asset(i).kind=='audio'];visual=[i for i in added if self.project.asset(i).kind!='audio']
                from instrument_model import voice
                if audio:self.queue_sound_selected(audio)
                if visual and voice(self.project,role):self.queue_selected(role,asset_ids=visual)
                self.refresh_library();self.queue_deck.refresh(True)
                self.update_status(f'Added {len(added)} · '+('Audio + Visual '+role if audio and visual else 'Audio' if audio else 'Visual '+role))
            if errors:self.log('\n'.join(errors));self.update_status('Some files could not be added: '+errors[0])
        else:self.update_status('Drop cancelled · project changed')
        jobs=getattr(self,'_direct_jobs',[])
        while jobs:
            target,paths,next_role=jobs.pop(0)
            if target==self.project.id:self.drop_media(paths,next_role);break
    def register_media_drop(self,widget,role):
        if not self.dnd_available:return
        try:
            from tkinterdnd2 import DND_FILES,COPY
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind('<<Drop>>',lambda e:(self.drop_media(self.parse_drop(e.data),role() if callable(role) else role),COPY)[1])
        except (ImportError,AttributeError,RuntimeError,TclError) as exc:self.log('Drop target: '+str(exc))
    def init_drop_support(self):
        super().init_drop_support()
        self.register_media_drop(self.viewport.canvas,self.active_visual_role)
        self.register_media_drop(self.library_frame,self.active_visual_role)
        for browser in self.media_browsers.values():self.register_media_drop(browser.canvas,self.active_visual_role)
        for role,page in self.queue_deck.pages.items():
            for widget in (page.canvas,page.current_canvas,page):self.register_media_drop(widget,role if role!='Music' else self.active_visual_role)
    def refresh_primary_toolbar(self):
        super().refresh_primary_toolbar()
        if hasattr(self,'input_bar'):self.input_bar.refresh()
