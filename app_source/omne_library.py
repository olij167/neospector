"""Project-scoped media browsing with an explicitly included historical catalogue."""
from __future__ import annotations
import copy, json, tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, simpledialog
from sequencer_model import project_from_dict, new_id
from media_browser_view import MediaBrowser
from responsive_controls import FlowRow

class ProjectBrowser(MediaBrowser):
    def __init__(self,parent,app,kind):
        self.media_kind=kind
        super().__init__(parent,app,compact=True,on_visible=lambda ids:app.browser_visible(self,ids))
        self.thumb.set('Small')
        self.thumb_px=tk.IntVar(value=115)
        self.pager=self.grid_slaves(row=3)[0]
        self.bind('<<BrowserChanged>>',self.update_pager,add='+')
        # Search, presentation and sort are one toolbar; file kind is the tab.
        for w in self.grid_slaves(row=1):w.grid_remove()
        bar=self.grid_slaves(row=0)[0];self.search_bar=bar
        self.presentation_buttons=[w for w in bar.winfo_children() if isinstance(w,ttk.Radiobutton)]
        more=ttk.Menubutton(bar,text='⋯',width=2);more.grid(row=0,column=4)
        menu=tk.Menu(more,tearoff=False);more.configure(menu=menu)
        for view in ('Grid','List'):menu.add_radiobutton(label=view+' view',variable=self.view,value=view,command=self.schedule)
        menu.add_separator()
        for kind in ('name','type','duration','date','size'):
            menu.add_radiobutton(label='Sort by '+kind,variable=self.sort,value=kind,command=self.refilter)
        menu.add_separator()
        for size in ('Small','Medium','Large'):
            menu.add_radiobutton(label=size+' thumbnails',variable=self.thumb,value=size,command=self.schedule)
        menu.add_checkbutton(label='Show hidden media',variable=app.library_show_hidden,command=app.refresh_library)
    def update_pager(self,event=None):
        # A one-page library needs no permanent previous/next navigation row.
        if self.collection_pages()>1:self.pager.grid()
        else:self.pager.grid_remove()
    def rows(self):
        return [r for r in super().rows() if (self.media_kind=='All' or (r.kind=='audio')==(self.media_kind=='Audio')) and r.kind!='camera']

    def collection_pages(self):
        if not hasattr(self,'sections'):return max(1,(len(self.rows())+self.PAGE_SIZE-1)//self.PAGE_SIZE)
        visible={r.id for r in self.rows()}
        largest=max((sum(i in visible for i in section['ids']) for section in self.sections),default=0)
        return max(1,(largest+self.PAGE_SIZE-1)//self.PAGE_SIZE)
    def turn_page(self,delta):
        self.page=max(0,min(self.collection_pages()-1,self.page+delta));self.canvas.yview_moveto(0);self.schedule()
    def set_assets(self,assets):
        super().set_assets(assets)
        for item in self.model.items.values():
            if item.kind in ('audio','image','video') and not Path(item.path).is_file():item.error='Source file missing'
    def set_collections(self,sections,versions=None):
        self.sections=sections;self.versions=versions or {};self.open_sections=getattr(self,'open_sections',{})
        self.open_versions=getattr(self,'open_versions',set())
        for section in sections:self.open_sections.setdefault(section['id'],section['current'])
        self.schedule()
    def draw(self):
        if not hasattr(self,'sections'):return super().draw()
        self._job=None
        if self._closed:return
        cv=self.canvas;theme=self.app.ui_chrome;cv.configure(bg=theme['field_bg']);cv.delete('all')
        self.hits=[];self.header_hits=[];self.version_hits=[];self.queue_hits=[];rows={r.id:r for r in self.rows()};w=max(120,cv.winfo_width());y=0;shown=[]
        query=self.query.get().casefold().strip();grid=self.view.get()=='Grid';target=max(84,min(240,int(self.thumb_px.get())))
        cols=max(1,w//target) if grid else 1;cw=w/cols;ch=(cw*.57+53) if grid else 64
        for section in self.sections:
            members=[rows[i] for i in section['ids'] if i in rows]
            if query and not members and query not in section['name'].casefold():continue
            expanded=self.open_sections.get(section['id'],False) or bool(query)
            cv.create_rectangle(0,y,w,y+30,fill=theme['panel_bg'],outline=theme['panel_edge'])
            cv.create_text(8,y+15,anchor='w',text=('▾ ' if expanded else '▸ ')+section['name']+'  '+str(len(members)),fill=theme['foreground'],font=('TkDefaultFont',10,'bold'))
            self.header_hits.append((section['id'],y,y+30));y+=33
            if not expanded:continue
            if not members and section['id']=='project-files':
                cv.create_text(12,y+18,anchor='w',text='Click to browse or drop files here',fill=theme['muted_fg'])
                self.header_hits.append(('browse',y,y+38));y+=42
            # Bound rendering to one page per collection; disclosure itself is cheap.
            page=members[self.page*self.PAGE_SIZE:(self.page+1)*self.PAGE_SIZE]
            for n,r in enumerate(page):
                x=(n%cols)*cw;top=y+(n//cols)*ch;selected=r.id in self.model.selected
                cv.create_rectangle(x+3,top+2,x+cw-4,top+ch-3,fill=theme['selection_bg'] if selected else theme['field_bg'],outline=theme['accent'] if selected else theme['panel_edge'])
                photo=self.photos.get(r.id);ix=x+cw/2 if grid else x+38;iy=top+(ch-40)/2 if grid else top+28
                if photo:cv.create_image(ix,iy,image=photo)
                else:cv.create_text(ix,iy,text='♫' if r.kind=='audio' else '▶',fill=theme['muted_fg'],font=('TkDefaultFont',16))
                tx=x+8 if grid else x+78;ty=top+ch-29 if grid else top+20
                width=max(30,cw-16 if grid else cw-87);limit=max(6,int(width/7))
                cv.create_text(tx,ty,anchor='w',text=r.name[:limit],fill=theme['foreground'],font=('TkDefaultFont',10,'bold'))
                cv.create_text(tx,ty+16,anchor='w',text=('Missing / Locate' if r.error else r.kind+(' · '+str(round(r.info.get('duration',0),1))+'s' if r.info.get('duration') else '')),fill=theme['muted_fg'],font=('TkDefaultFont',9))
                self.hits.append((r.id,(x,top,x+cw,top+ch),(0,0,0,0)));shown.append(r.id)
                if getattr(self,'queue_action',None):
                    cv.create_text(x+cw-40,top+12,text='+ Queue',fill=theme['accent'],font=('TkDefaultFont',9,'bold'))
                    self.queue_hits.append((r.id,x+cw-70,top,x+cw-7,top+24))
                variants=self.versions.get(r.id,[])
                if len(variants)>1:
                    cv.create_text(x+14,top+12,text='▾' if r.id in self.open_versions else '▸',fill=theme['accent'])
                    self.version_hits.append((r.id,x,top,x+28,top+25))
            y+=((len(page)+cols-1)//cols)*ch
            for r in page:
                if r.id not in self.open_versions:continue
                for version in self.versions.get(r.id,[]):
                    label='Original' if version['revision']=='original' else 'Edited in '+str(version['project'])[-8:]
                    cv.create_text(24,y+12,anchor='w',text=r.name+' / '+label,fill=theme['muted_fg']);y+=25
            revisions=section.get('revisions',[])
            if len(revisions)>1:
                for revision in revisions:
                    sid=section['id']+':revision:'+revision['revision'];opened=self.open_sections.get(sid,False)
                    label='Original' if revision['revision']=='original' else 'Edited in '+revision.get('project','')[-8:]
                    cv.create_text(24,y+13,anchor='w',text=('▾ ' if opened else '▸ ')+label,fill=theme['muted_fg'])
                    self.header_hits.append((sid,y,y+27));y+=27
                    if opened:
                        for aid in revision['ids'][:self.PAGE_SIZE]:
                            raw=revision.get('assets',{}).get(aid,{})
                            name=raw.get('name') or (self.model.items[aid].name if aid in self.model.items else aid)
                            cv.create_text(42,y+12,anchor='w',text=name,fill=theme['muted_fg']);y+=25
            if len(members)>self.PAGE_SIZE:
                cv.create_text(12,y+14,anchor='w',text=str(len(members))+' items · use pages or search',fill=theme['muted_fg']);y+=30
        cv.configure(scrollregion=(0,0,w,max(y,cv.winfo_height())));self.count.set(str(len(shown))+' items');self.page_label.set(str(self.page+1)+'/'+str(self.collection_pages()));self.event_generate('<<BrowserChanged>>')
        if self.on_visible:self.on_visible(shown)
    def press(self,e):
        y=self.canvas.canvasy(e.y)
        # Header presses may become collection drags. Item presses clear this
        # immediately so a normal media drag keeps its exact selection.
        self.drag_collection_ids=None
        for aid,x0,y0,x1,y1 in getattr(self,'queue_hits',[]):
            if x0<=e.x<x1 and y0<=y<y1:self.queue_action([aid]);return
        for aid,x0,y0,x1,y1 in getattr(self,'version_hits',[]):
            if x0<=e.x<x1 and y0<=y<y1:
                if aid in self.open_versions:self.open_versions.remove(aid)
                else:self.open_versions.add(aid)
                self.schedule();return
        for sid,y0,y1 in getattr(self,'header_hits',[]):
            if y0<=y<y1:
                if sid=='browse':self.app.add_media()
                else:
                    section=next((section for section in self.sections if section['id']==sid),None)
                    if section is not None:self.drag_collection_ids=list(section.get('ids',()))
                    self.open_sections[sid]=not self.open_sections.get(sid,False);self.schedule()
                return
        return super().press(e)

class OmneLibrary:
    def load_catalogue_assets(self):
        """Do not promote the user's entire catalogue into a new project."""
        self.repair_asset_records()
        # Old projects already carry their membership; synthesise local album views.
        if 'library_albums' not in self.project.extra:
            self.project.extra['library_albums']={a['id']:{'name':a['name'],'ids':sorted(self.catalog.member_ids(a['id'])&set(self.project.assets))}
                for a in self.catalog.albums() if self.catalog.member_ids(a['id'])&set(self.project.assets)}

    def ensure_project_media(self,ids):
        """Adopt referenced catalogue media only when the user actually uses it.

        Historical albums stay lightweight until a Queue/Programme drop.  Adoption
        preserves the catalogue asset identity and records the source album locally,
        so the project becomes portable without cloning unrelated imports.
        """
        ids=list(dict.fromkeys(ids))
        missing=[aid for aid in ids if self.project.asset(aid) is None]
        if not missing:return ids
        raw={a['id']:a for a in self.catalog.assets() if a.get('id') in missing}
        decoded=project_from_dict({'assets':raw}).assets if raw else {}
        available=[aid for aid in missing if aid in decoded]
        if not available:return [aid for aid in ids if self.project.asset(aid)]
        albums=self.catalog.albums();members={a['id']:self.catalog.member_ids(a['id']) for a in albums}
        def adopt():
            for aid in available:self.project.assets[aid]=copy.deepcopy(decoded[aid])
            local=self.project.extra.setdefault('library_albums',{})
            for album in albums:
                used=[aid for aid in available if aid in members[album['id']]]
                if not used:continue
                row=local.setdefault(album['id'],{'name':album['name'],'ids':[]})
                row['ids']=list(dict.fromkeys(list(row.get('ids',()))+used))
        self.transaction('Add Library media to this project',adopt)
        for album in albums:
            if any(aid in members[album['id']] for aid in available):self.catalog.touch_album(album['id'])
        self.refresh_library()
        return [aid for aid in ids if self.project.asset(aid)]

    def build_library(self,parent):
        body=ttk.Frame(parent,padding=(6,4));body.pack(fill='both',expand=True)
        self.library_modes=ttk.Notebook(body);self.library_modes.pack(fill='both',expand=True)
        self.library_mode_frames={}
        for mode in ('modules','patches'):
            frame=ttk.Frame(self.library_modes);self.library_modes.add(frame,text='Racks' if mode=='patches' else mode.title());self.library_mode_frames[mode]=frame
        media_body=body;self.library_media_body=body
        # Import occupies the existing panel header, not a competing form row.
        header=self.shell.headers['panel.library']
        self.import_media_button=ttk.Button(header,text='↓ Import…',command=self.add_media,style='Accent.TButton')
        self.import_media_button.pack(side='right',after=self.shell.menus['panel.library'],padx=3)
        albumbar=ttk.Frame(media_body);albumbar.pack(fill='x',pady=(0,4));self.library_albumbar=albumbar
        self._library_compact=None;self._library_expanded_views={}
        self.album_box=ttk.Combobox(albumbar,textvariable=self.album_label,state='readonly',width=12)
        self.album_box.pack(side='left',fill='x',expand=True);self.album_box.bind('<<ComboboxSelected>>',lambda e:self.choose_album())
        ttk.Button(albumbar,text='+',width=2,command=self.new_album).pack(side='left',padx=2)
        self.library_show_hidden=tk.BooleanVar(value=False)
        self.library_tabs=self.library_modes
        self.media_browsers={};self.media_tabs={}
        for kind in ('Audio','Visuals'):
            tab=ttk.Frame(self.library_tabs);self.library_tabs.add(tab,text=kind);self.media_tabs[kind]=tab
            browser=ProjectBrowser(tab,self,kind);browser.pack(fill='both',expand=True);self.media_browsers[kind]=browser
            browser.bind('<<TreeviewSelect>>',lambda e,b=browser:self.browser_selected(b))
            browser.bind('<Double-1>',lambda e,b=browser:(self.browser_selected(b),self.queue_library_selection()))
            browser.bind('<Button-3>',lambda e,b=browser:self.library_queue_menu(e,browser=b))
            browser.canvas.bind('<ButtonPress-1>',lambda e,b=browser:self.begin_media_drag(e,b),add='+')
            browser.canvas.bind('<B1-Motion>',self.motion_media_drag,add='+')
            browser.canvas.bind('<ButtonRelease-1>',self.end_media_drag,add='+')
        self.library=self.media_browsers['Audio'];self.library_media_tab=self.media_tabs['Visuals'];self.search=self.library.query
        self.library_mode_frames['media']=self.media_tabs['Audio']
        self.library_tabs.insert(0,self.media_tabs['Audio']);self.library_tabs.insert(1,self.media_tabs['Visuals'])
        self.library_tabs.select(self.media_tabs['Audio'])
        self.place_mode=tk.StringVar(value='place');self.asset_summary=tk.StringVar(value='This project · no media yet')
        patches=self.library_mode_frames['patches'];self.patches_tab=patches
        self.ingredients_tree=ttk.Treeview(patches,columns=('kind',),show='tree headings',selectmode='browse')
        self.ingredients_tree.heading('#0',text='Patch / ingredient');self.ingredients_tree.heading('kind',text='Type')
        self.ingredients_tree.column('#0',width=155);self.ingredients_tree.column('kind',width=64,stretch=False)
        self.ingredients_tree.pack(fill='both',expand=True);self.ingredients_tree.bind('<Double-1>',lambda e:self.apply_selected_ingredient())
        row=FlowRow(patches,gap=3);row.pack(fill='x',pady=3)
        for name,fn in [('Apply',self.apply_selected_ingredient),('Keep…',self.keep_ingredient),('Import',self.import_ingredient),('Export',self.export_ingredient)]:
            row.add(ttk.Button(row,text=name,command=fn))
        self.library_footer=ttk.Frame(media_body);self.library_footer.pack(fill='x',pady=(3,0))
        actions=ttk.Frame(self.library_footer);actions.pack(fill='x');self.library_actions=actions
        self.library_destination=tk.StringVar(value='A');self._library_visual_destination='A';self._library_dest_kind='Visuals'
        self.queue_media_button=ttk.Button(media_body,text='Add to A',width=0,style='Accent.TButton',command=self.queue_library_selection)
        self.queue_media_button.grid(in_=actions,row=0,column=0,sticky='w')
        self.library_destination_button=ttk.Button(media_body,text='▾',width=2,command=self.choose_library_destination);self.library_destination_button.grid(in_=actions,row=0,column=1,sticky='w')
        self.library_settings_button=ttk.Button(actions,text='Settings',width=0,command=lambda:self.open_media_settings(list(self.library.selection()),'General'))
        self.library_settings_button.grid(row=0,column=2,sticky='w',padx=3)
        self.library_audition_button=ttk.Button(actions,text='Audition',width=0,command=self.audition_library_selection)
        self._library_audition_process=None;self._library_audition_after=None;self._library_audition_project=None
        self.bind('<Destroy>',lambda event:self.stop_library_audition() if event.widget is self else None,add='+')
        more=ttk.Menubutton(actions,text='⋯',width=2);more.grid(row=0,column=4,sticky='e')
        actions.columnconfigure(4,weight=1);self.library_action_more=more
        actions.bind('<Configure>',lambda event:self.layout_library_actions(),add='+')
        sizebar=ttk.Frame(self.library_footer);sizebar.pack(fill='x',pady=(3,0));self.library_sizebar=sizebar
        ttk.Label(sizebar,text='Preview',style='Muted.TLabel').pack(side='left')
        self.library_preview_size=tk.IntVar(value=115)
        self.library_preview_scale=ttk.Scale(sizebar,from_=84,to=240,variable=self.library_preview_size,command=self.resize_library_previews)
        self.library_preview_scale.pack(side='left',fill='x',expand=True,padx=5)
        ttk.Label(sizebar,text='−   +',style='Muted.TLabel').pack(side='right')
        self.add_tip(self.library_preview_scale,'Resize Library previews without changing the imported media or project.')
        m=tk.Menu(more,tearoff=False);more.configure(menu=m)
        m.add_command(label='Queue / take options…',command=self.library_queue_menu)
        m.add_command(label='Album membership…',command=self.membership)
        m.add_command(label='Hide selected media',command=self.hide_selected_media)
        m.add_command(label='Media settings…',command=lambda:self.open_media_settings(list(self.library.selection()),'General'))
        m.add_command(label='Unhide selected media',command=lambda:self.hide_selected_media(False))
        m.add_command(label='Remove from this project',command=self.remove_selected_media)
        m.add_command(label='Locate missing media…',command=self.locate_missing)
        m.add_checkbutton(label='Show hidden media',variable=self.library_show_hidden,command=self.refresh_library)
        self.library_tabs.bind('<<NotebookTabChanged>>',self.library_tab_changed)
        self.library_tabs.pack_forget();self.library_footer.pack_forget()
        self.library_footer.pack(side='bottom',fill='x',pady=(3,0));self.library_tabs.pack(fill='both',expand=True)
        from module_library import ModuleLibraryPanel
        self.module_library=ModuleLibraryPanel(self.library_mode_frames['modules'],self);self.module_library.pack(fill='both',expand=True)
        self.library_modes.bind('<<NotebookTabChanged>>',self.library_mode_changed,add='+')
        media_body.bind('<Configure>',self.layout_library_media,add='+')
        # Draft catalogue is not a Library tab. It remains a live modeless file view.
        self.drafts_window=tk.Toplevel(self);self.drafts_window.withdraw();self.drafts_window.title('Drafts · Neospector')
        self.drafts_window.geometry('560x390');self.drafts_window.protocol('WM_DELETE_WINDOW',self.drafts_window.withdraw)
        frame=ttk.Frame(self.drafts_window,padding=12);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='DRAFTS',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Review is independent. Programme keeps playing.',style='Muted.TLabel').pack(anchor='w',pady=5)
        self.take_tree=ttk.Treeview(frame,show='tree',selectmode='browse');self.take_tree.pack(fill='both',expand=True)
        self.take_tree.bind('<Double-1>',lambda e:self.open_selected_take())
        row=ttk.Frame(frame);row.pack(fill='x',pady=8)
        ttk.Button(row,text='Open saved Draft…',command=self.open_take_file).pack(side='left')
        ttk.Button(row,text='Review selected',command=self.open_selected_take,style='Accent.TButton').pack(side='right')
    def layout_library_media(self,event=None,*,force=False):
        """Shallow docks show media, not chrome; all hidden actions stay in ⋯."""
        self._library_compact=False
        self.library_albumbar.pack_forget();self.library_sizebar.pack_forget()
        selected=self.library_tabs.select()
        media=any(selected==str(tab) for tab in self.media_tabs.values())
        if media:self.library_footer.pack(side='bottom',fill='x',pady=(3,0),before=self.library_tabs)
        else:self.library_footer.pack_forget()
        self.layout_library_actions()

    def populate_library_menu(self,menu):
        """Non-drag, shallow-dock access to the same media commands."""
        menu.add_command(label='Import media…',command=self.add_media)
        menu.add_command(label='Queue…',command=self.library_queue_menu)
        albums=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Albums',menu=albums)
        def choose(label):self.album_label.set(label);self.choose_album()
        for label in getattr(self,'_albums',{'This project':'all'}):
            albums.add_command(label=label,command=lambda text=label:choose(text))
        albums.add_separator();albums.add_command(label='New album…',command=self.new_album)
        albums.add_command(label='Media browser / albums…',command=self.previous_imports)
        albums.add_command(label='Selected media membership…',command=self.membership)
        preview=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Preview size',menu=preview)
        for size in (84,115,160,200,240):
            preview.add_radiobutton(label=str(size)+' px',variable=self.library_preview_size,value=size,command=self.resize_library_previews)
        menu.add_command(label='Media settings…',command=lambda:self.open_media_settings(list(self.library.selection()),'General'))
        menu.add_command(label='Hide selected media',command=self.hide_selected_media)
        menu.add_command(label='Unhide selected media',command=lambda:self.hide_selected_media(False))
        menu.add_command(label='Remove from this project',command=self.remove_selected_media)
        menu.add_command(label='Locate missing media…',command=self.locate_missing)
        menu.add_checkbutton(label='Show hidden media',variable=self.library_show_hidden,command=self.refresh_library)

    def resize_library_previews(self,value=None):
        try:size=max(84,min(240,int(float(self.library_preview_size.get() if value is None else value))))
        except (ValueError,tk.TclError):return
        for browser in getattr(self,'media_browsers',{}).values():
            if hasattr(browser,'thumb_px'):
                browser.thumb_px.set(size);browser.schedule()

    def show_drafts(self):
        self.refresh_takes();self.drafts_window.deiconify();self.drafts_window.lift()
    def library_tab_changed(self,event=None):
        if not hasattr(self,'media_tabs'):return
        selected=self.library_tabs.select()
        for name,tab in self.media_tabs.items():
            if selected==str(tab):
                self.library=self.media_browsers[name];self.search=self.library.query
                self.layout_library_media(force=True);self.browser_selected(self.library);self.library.schedule();self.refresh_album_options();return
        self.library_footer.pack_forget();self.refresh_album_options()

    def _active_library_kind(self):
        if not hasattr(self,'library_tabs'):return 'Visuals'
        selected=self.library_tabs.select()
        if hasattr(self,'library_modes') and self.library_modes.select()==str(self.patches_tab):return 'Patches'
        if selected==str(self.library_mode_frames.get('modules','')):return 'Modules'
        return next((name for name,tab in self.media_tabs.items() if selected==str(tab)),'Visuals')

    def _album_has_kind(self,ids,kind):
        ids=set(ids)
        if not ids:return False
        if kind=='Patches':
            known={e['id'] for e in self.catalog.ingredients()}
            return bool(ids&known)
        raw={a.id:a for a in self.project.assets.values()}
        try:
            for item in self.catalog.assets():
                if item['id'] in ids and item['id'] not in raw:
                    parsed=project_from_dict({'assets':{item['id']:item}}).assets.get(item['id'])
                    if parsed:raw[item['id']]=parsed
        except (KeyError,ValueError):pass
        for aid in ids:
            asset=raw.get(aid)
            if asset is None:continue
            if kind=='Audio' and asset.kind=='audio':return True
            if kind=='Visuals' and asset.kind not in ('audio','camera'):return True
        return False

    def refresh_album_options(self):
        if not hasattr(self,'album_box'):return
        kind=self._active_library_kind();albums=self.project.extra.get('library_albums',{})
        options={'This project':'all'}
        for aid,data in albums.items():
            if not self._album_has_kind(data.get('ids',[]),kind):continue
            name=data.get('name','Album');label=name if name not in options else name+' · '+aid[-4:];options[label]=aid
        self._albums=options
        current=self.album.get()
        if current!='all' and current not in options.values():
            self.album.set('all');current='all'
        self.album_box.configure(values=list(options));self.album_label.set(next((n for n,i in options.items() if i==current),'This project'))
    def browser_selected(self,browser):
        self.library=browser;ids=browser.selection();self.selected_asset_id=ids[0] if ids else None
        self.asset_summary.set(f'{len(ids)} selected' if ids else 'Select material')
        if hasattr(self,'queue_media_button'):self.refresh_library_destination()

    def refresh_library_destination(self):
        """Show the actual next Add destination before the performer commits."""
        if not hasattr(self,'library_destination'):return
        from visual_channels import channels
        roles=[layer.extra['voice'] for layer in channels(self.project)]
        kind=getattr(self.library,'media_kind','Visuals');destination=self.library_destination.get()
        if kind=='Audio':destination='Music'
        elif kind!=self._library_dest_kind and destination=='Music':destination=self._library_visual_destination
        if destination not in roles+['Music']:destination=roles[0] if roles else 'Music'
        if destination!='Music':self._library_visual_destination=destination
        self._library_dest_kind=kind;self.library_destination.set(destination)
        ids=list(self.library.selection())
        if self._library_audition_process is not None and (not ids or ids[0]!=getattr(self,'_library_audition_asset',None)):self.stop_library_audition()
        self.queue_media_button.configure(text='Add to '+destination,state='normal' if ids else 'disabled')
        selected=[self.library.model.items[i] for i in ids if i in self.library.model.items]
        audible=bool(selected and all(item.kind in ('audio','video') for item in selected))
        self.library_audition_button.grid(row=0,column=3,sticky='w',padx=2)
        self.library_audition_button.configure(state='normal' if audible else 'disabled')
        self.layout_library_actions()

    def layout_library_actions(self):
        # Keep the primary destination action intact; preview/settings wrap as
        # a whole row when audio context would otherwise clip its audition.
        if not hasattr(self,'library_action_more'):return
        row=self.library_actions
        audible=bool(self.library_audition_button.winfo_manager())
        buttons=[self.queue_media_button,self.library_destination_button,self.library_settings_button,self.library_action_more]
        needed=sum(w.winfo_reqwidth() for w in buttons)+6
        if audible:needed+=self.library_audition_button.winfo_reqwidth()+4
        shallow=bool(self._library_compact)
        if shallow:
            bar=self.library.search_bar
            for browser in self.media_browsers.values():
                for button in browser.presentation_buttons:button.grid_remove()
            self.queue_media_button.grid(in_=bar,row=0,column=2,columnspan=1,sticky='w')
            self.library_destination_button.grid(in_=bar,row=0,column=3,columnspan=1,sticky='w')
            if audible:
                self.library_footer.pack(side='bottom',fill='x',pady=(3,0),before=self.library_tabs)
                self.library_settings_button.grid_configure(row=0,column=0,columnspan=1)
                self.library_audition_button.grid_configure(row=0,column=2,columnspan=1)
            else:self.library_footer.pack_forget()
            return
        for browser in self.media_browsers.values():
            for button in browser.presentation_buttons:button.grid()
        self.queue_media_button.grid(in_=row,row=0,column=0,columnspan=1,sticky='w')
        self.library_destination_button.grid(in_=row,row=0,column=1,columnspan=1,sticky='w')
        compact=audible and row.winfo_width()<needed
        self.library_settings_button.grid_configure(row=1 if compact else 0,column=0 if compact else 2,columnspan=2 if compact else 1)
        if audible:self.library_audition_button.grid_configure(row=1 if compact else 0,column=2 if compact else 3,columnspan=2 if compact else 1)

    def audition_library_selection(self):
        if self._library_audition_process is not None:return self.stop_library_audition()
        ids=list(self.library.selection())
        item=self.library.model.items.get(ids[0]) if ids else None
        if item is None:return self.update_status('Select audio or video to audition independently of Programme.')
        if not Path(item.path).is_file():return self.update_status('Locate the missing source before auditioning.')
        import subprocess
        from media_engine import FFPLAY
        from process_tools import popen_options
        try:
            self._library_audition_process=subprocess.Popen([FFPLAY,'-hide_banner','-loglevel','error','-autoexit','-nodisp',item.path],**popen_options(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError as exc:return self.update_status('Audition could not start: '+str(exc))
        self._library_audition_project=self.project
        self._library_audition_asset=ids[0]
        self.library_audition_button.configure(text='Stop preview')
        self.update_status('Audition · '+item.name+' · Programme and recording are unchanged.')
        self._library_audition_after=self.after(150,self.poll_library_audition)

    def poll_library_audition(self):
        self._library_audition_after=None;player=self._library_audition_process
        if player is None:return
        if self.project is not self._library_audition_project:return self.stop_library_audition()
        result=player.poll()
        if result is not None:
            self.stop_library_audition()
            if result:self.update_status('Audition could not play this source. Check its file and audio output; Programme is unchanged.')
        else:self._library_audition_after=self.after(150,self.poll_library_audition)

    def stop_library_audition(self):
        after=getattr(self,'_library_audition_after',None)
        if after:
            try:self.after_cancel(after)
            except tk.TclError:pass
        self._library_audition_after=None
        player=getattr(self,'_library_audition_process',None)
        if player is not None and player.poll() is None:player.terminate()
        self._library_audition_process=None;self._library_audition_project=None;self._library_audition_asset=None
        try:self.library_audition_button.configure(text='Audition')
        except (AttributeError,tk.TclError):pass

    def choose_library_destination(self):
        from visual_channels import channels
        menu=tk.Menu(self,tearoff=False)
        for role in [layer.extra['voice'] for layer in channels(self.project)]+['Music']:
            menu.add_radiobutton(label=role+' queue',variable=self.library_destination,value=role,command=self.refresh_library_destination)
        self.popup_menu(menu,self.library_destination_button)

    def queue_library_selection(self):
        self.refresh_library_destination();ids=list(self.library.selection())
        if not ids:return self.update_status('Select media in Library, then Add to its named queue.')
        role=self.library_destination.get();result=self.queue_library_media(ids,role)
        if result:self.update_status(str(len(result))+' added to '+role+' queue · Undo restores the previous queue.')
        return result
    def asset_selected(self,event=None):self.browser_selected(self.library)
    def browser_visible(self,browser,ids):
        for aid in ids:
            asset=self.project.asset(aid)
            if asset is None:continue
            if aid in self.thumbnails:browser.item(aid,image=self.thumbnails[aid])
            else:self.request_thumbnail(asset)
    def refresh_library(self):
        if not hasattr(self,'media_browsers'):return
        if getattr(self,'_library_audition_project',None) is not None and self._library_audition_project is not self.project:self.stop_library_audition()
        from media_browser_model import collection_sections
        from sequencer_model import _encode
        albums=self.project.extra.get('library_albums',{})
        self.sync_album_archive(albums)
        hidden=set(self.project.extra.get('library_hidden',[]));removed=set(self.project.extra.get('library_removed',[]))
        key=(self.project.id,self.library_show_hidden.get(),tuple((a.id,a.name,a.path,a.duration) for a in self.project.assets.values()),
             tuple(sorted(hidden)),tuple(sorted(removed)),json.dumps(albums,sort_keys=True),getattr(self.catalog,'generation',0),bool(getattr(self,'_audio_catalogue_browse',False)))
        if key!=getattr(self,'_browser_key',None):
            self._browser_key=key
            enabled=self.catalog.browser_album_ids();removed_albums=self.catalog.removed_album_ids()
            catalogue=[a for a in self.catalog.albums() if a['id'] in enabled or a['id'] in albums]
            members={a['id']:self.catalog.member_ids(a['id']) for a in catalogue}
            raw=self.catalog.assets();allowed={i for a in catalogue if a['id'] in enabled for i in members[a['id']]}
            previous_audio=set()
            if getattr(self,'_audio_catalogue_browse',False):
                archived={i for aid in removed_albums for i in self.catalog.member_ids(aid)}-allowed
                previous_audio={a['id'] for a in raw if a.get('kind')=='audio' and a['id'] not in archived}
                allowed.update(previous_audio)
            if '__unsorted__' in enabled:
                grouped={i for a in self.catalog.albums(True) for i in self.catalog.member_ids(a['id'])}
                allowed.update(a['id'] for a in raw if a['id'] not in grouped)
            originals=project_from_dict({'assets':{a['id']:a for a in raw if a['id'] in allowed}}).assets
            originals.update(self.project.assets)
            assets=[a for a in originals.values() if a.id not in removed and (self.library_show_hidden.get() or a.id not in hidden)]
            sections=collection_sections(self.project,catalogue,members,{a.id for a in assets},include_unsorted='__unsorted__' in enabled,removed_albums=removed_albums)
            represented={aid for section in sections for aid in section['ids']}
            historical=previous_audio-represented-{a.id for a in self.project.assets.values()}-hidden-removed
            if historical:sections.append({'id':'audio-history','name':'Previous audio','ids':sorted(historical),'current':False})
            for section in sections:
                if section['id'] in members:section['revisions']=self.catalog.album_versions(section['id'])
            versions={a.id:self.catalog.asset_versions(a.id) for a in assets}
            for browser in self.media_browsers.values():browser.set_assets(assets);browser.set_collections(sections,versions)
        self.refresh_album_options()
        if hasattr(self,'empty_preview'):self.refresh_empty_preview()
    def choose_album(self):
        aid=self._albums.get(self.album_label.get(),'all');self.album.set(aid)
        for browser in self.media_browsers.values():
            if aid!='all':browser.open_sections[aid]=True
            browser.schedule()
    def new_album(self):
        name=simpledialog.askstring('New album','Album name:',parent=self)
        if not name:return
        ids=list(self.library.selection())
        if hasattr(self,'patches_tab') and self.library_tabs.select()==str(self.patches_tab):
            ids=[self._patch_nodes[i][0] for i in self.ingredients_tree.selection() if i in self._patch_nodes]
        aid=self.transaction('Create album',lambda:self._create_local_album(name,ids))
        self.album.set(aid);self.refresh_library()
    def _create_local_album(self,name,ids=()):
        aid=self.catalog.create_album(name)
        members=list(dict.fromkeys(ids))
        self.project.extra.setdefault('library_albums',{})[aid]={'name':name,'ids':members,'catalogue_owner':self.project.id}
        self.catalog.add_members(aid,members)
        return aid
    def sync_album_archive(self,albums):
        from sequencer_model import _encode
        key=(self.project.id,json.dumps(albums,sort_keys=True),tuple((a.id,a.name,a.path,a.duration,json.dumps(a.metadata.get('sequence_preferences',{}),sort_keys=True)) for a in self.project.assets.values()))
        if key==getattr(self,'_album_archive_key',None):return
        self.catalog.persist_project_assets(self.project.id,list(self.project.assets.values()))
        self.catalog.sync_project_albums(self.project.id,albums,self.project.assets)
        self._album_archive_key=key
    def _change_members(self,album,ids,add):
        def change():
            local=self.project.extra.setdefault('library_albums',{})
            if album not in local:
                src=next((a for a in self.catalog.albums() if a['id']==album),None)
                local[album]={'name':src['name'] if src else 'Album','ids':[]}
            members=list(local[album]['ids'])
            local[album]['ids']=list(dict.fromkeys(members+list(ids))) if add else [i for i in members if i not in ids]
        self.transaction('Album membership',change);self.refresh_library()
    def membership(self):
        ids=list(self.library.selection())
        if not ids:return self.update_status('Select media before assigning an album.')
        menu=tk.Menu(self,tearoff=False)
        for aid,data in self.project.extra.get('library_albums',{}).items():
            menu.add_command(label='Add to '+data['name'],command=lambda a=aid:self._change_members(a,ids,True))
            if any(i in data['ids'] for i in ids):menu.add_command(label='Remove from '+data['name'],command=lambda a=aid:self._change_members(a,ids,False))
        menu.add_command(label='New album…',command=self.new_album)
        self.popup_menu(menu,self.queue_media_button)
    def add_media(self):return self.open_import_browser()
    def open_import_browser(self,paths=(),pending_randomise=None):
        from unified_media_browser import UnifiedMediaBrowser
        if self.import_window and self.import_window.winfo_exists():
            self.import_window.add_paths(paths);self.import_window.set_pending(pending_randomise);self.import_window.lift();return self.import_window
        self.import_window=UnifiedMediaBrowser(self,paths,pending_randomise=pending_randomise)
        return self.import_window
    def import_folder(self):return self.open_import_browser()
    def request_media_for_randomise(self,scope,only_role=None,play_after=False,settings=None):
        if scope=='effects':return False
        excluded=set(self.project.extra.get('library_removed',[]))|set(self.project.extra.get('library_hidden',[]))
        assets=[a for a in self.project.assets.values() if a.id not in excluded]
        def usable(a):
            if only_role=='Music':return a.kind=='audio' or (a.kind=='video' and a.metadata.get('has_audio'))
            if only_role:return a.kind in ('image','video','colour','shape','text')
            return a.kind in ('image','video','colour','shape','text','audio')
        if any(usable(a) for a in assets):return False
        self.open_import_browser(pending_randomise=dict(scope=scope,only_role=only_role,play_after=play_after,settings=copy.deepcopy(settings)))
        return True
    def drop_paths(self,paths,album=None):
        # Retain the existing cancellable, incremental folder scanner. Never walk
        # a large tree synchronously inside a drop callback.
        if any(Path(path).is_dir() for path in paths):
            self.open_import_browser(paths)
            selected=album or self.album.get()
            self.import_window.album.set(next((n for n,i in self.import_window.albums.items() if i==selected),'All media'))
        else:self.import_files(paths,album=album or self.album.get())
    def accept_import_v03(self,pid,result,errors,as_song,album,use='Library only'):
        completion=getattr(self,'_media_browser_completion',None)
        if completion and completion['project_id']==pid:self._media_browser_completion=None
        else:completion=None
        imported_ids=super().accept_import_v03(pid,result,errors,as_song,album,use) or []
        if self.project.id!=pid:return
        self._browser_key=None;self.refresh_library()
        if completion:
            ids=list(dict.fromkeys(completion['archive_ids']+imported_ids))
            if ids and completion['request']:self.randomise_playable(**completion['request'])
            elif ids:self.place_browser_selection(ids,completion['use'])
    def place_browser_selection(self,ids,use):
        from import_destinations import apply
        return apply(self,ids,use)
    def include_previous(self,ids,album_id=None,revision=None):
        raw={a['id']:a for a in self.catalog.assets()}
        if album_id and revision:raw.update(self.catalog.album_revision(album_id,revision).get('assets',{}))
        chosen=[i for i in ids if i in raw]
        parsed=project_from_dict({'assets':{i:raw[i] for i in chosen}}).assets
        def include():
            for aid,asset in parsed.items():
                if revision:self.project.assets[aid]=copy.deepcopy(asset)
                else:self.project.assets.setdefault(aid,copy.deepcopy(asset))
            for key in ('library_removed','library_hidden'):
                self.project.extra[key]=[i for i in self.project.extra.get(key,[]) if i not in chosen]
            if album_id:
                name=next((a['name'] for a in self.catalog.albums() if a['id']==album_id),'Included album')
                local=self.project.extra.setdefault('library_albums',{})
                prior=local.get(album_id,{}).get('ids',[])
                local[album_id]={'name':name,'ids':list(dict.fromkeys(prior+chosen))}
                self.catalog.touch_album(album_id)
        self.transaction('Include previous media',include);self.refresh_library()
    def previous_imports(self):return self.open_import_browser()
    def hide_selected_media(self,hide=True):
        ids=set(self.library.selection())
        def apply():
            old=set(self.project.extra.get('library_hidden',[]));old.update(ids) if hide else old.difference_update(ids)
            self.project.extra['library_hidden']=sorted(old)
        self.transaction('Hide media' if hide else 'Unhide media',apply);self.refresh_library()
        self.update_status('Browser and future random selection updated. Existing queue occurrences and source files are unchanged.')
    def remove_selected_media(self):
        ids=set(self.library.selection())
        if not ids:return
        def apply():self.project.extra['library_removed']=sorted(set(self.project.extra.get('library_removed',[]))|ids)
        self.transaction('Remove project membership',apply);self.refresh_library()
        self.update_status('Removed from this Library. Existing performance references and original files are retained; Undo restores membership.')
    def library_queue_menu(self,event=None,browser=None):
        if browser:self.browser_selected(browser)
        ids=list(self.library.selection())
        if not ids:return self.update_status('Select media first.')
        raw=project_from_dict({'assets':{a['id']:a for a in self.catalog.assets()}}).assets
        assets=[self.project.asset(i) or raw.get(i) for i in ids];visual=all(a and a.kind!='audio' for a in assets);audio=all(a and (a.kind=='audio' or a.metadata.get('has_audio')) for a in assets)
        menu=tk.Menu(self,tearoff=False)
        for role in (*[l.extra['voice'] for l in __import__('visual_channels').channels(self.project)],'Music'):
            state='normal' if (audio if role=='Music' else visual) else 'disabled'
            menu.add_command(label='Queue '+role,command=lambda r=role:self.queue_library_media(ids,r),state=state)
        menu.add_separator()
        for role in (('Music',) if audio and not visual else tuple(l.extra['voice'] for l in __import__('visual_channels').channels(self.project))):
            menu.add_command(label='Play now · '+role,command=lambda r=role:self.place_media(ids,r,'now'))
            menu.add_command(label='Conductor next · '+role,command=lambda r=role:self.place_media(ids,r,'next'))
        if len(ids)==1:
            versions=tk.Menu(menu,tearoff=False)
            for version in self.catalog.asset_versions(ids[0]):
                label='Original' if version['revision']=='original' else 'Edited in '+version['project'][-8:]
                versions.add_command(label=label,command=lambda v=version:self.use_media_version(v))
            menu.add_cascade(label='Versions',menu=versions)
        menu.add_separator();menu.add_command(label='Media settings…',command=lambda:self.open_media_settings(ids,'General'))
        menu.add_command(label='Use this album as visual pool',command=lambda:self.use_source_album('visuals'))
        menu.add_command(label='Use this album as Music pool',command=lambda:self.use_source_album('music'))
        self.popup_menu(menu,self.queue_media_button,event)
    def refresh_ingredients(self):
        if not hasattr(self,'ingredients_tree'):return
        # Preserve installed default ingredients, then expose all revisions.
        super().refresh_ingredients()
        entries=self.catalog.ingredients();uses=self.project.extra.get('ingredient_uses',[])
        albums=self.project.extra.get('library_albums',{})
        key=(self.project.id,tuple((e['id'],e['revision']) for e in entries),json.dumps(uses,sort_keys=True),json.dumps(albums,sort_keys=True))
        if key==getattr(self,'_patch_groups_key',None):return
        self._patch_groups_key=key;tree=self.ingredients_tree;opened={i for i in tree.get_children() if tree.item(i,'open')}
        tree.delete(*tree.get_children());self._patch_nodes={}
        current={u['id'] for u in uses};byid={e['id']:e for e in entries};filed={i for data in albums.values() for i in data['ids']}
        groups=[('patch-project','Project files',[i for i in current-filed if i in byid],True)]
        for aid,data in reversed(list(albums.items())):groups.append(('patch-'+aid,data['name'],[i for i in data['ids'] if i in byid],True))
        grouped=set(filed)
        for album in self.catalog.albums():
            if album['id'] in albums:continue
            ids=self.catalog.member_ids(album['id'])&set(byid);grouped.update(ids)
            if ids:groups.append(('patch-'+album['id'],album['name'],sorted(ids),False))
        recent=[e['id'] for e in entries if e['id'] not in current and e['id'] not in grouped]
        if recent:groups.append(('patch-recent','Recent',recent,False))
        for gid,name,ids,expanded in groups:
            parent=tree.insert('','end',iid=gid,text=name,open=expanded or gid in opened)
            for iid in ids:
                versions=self.catalog.ingredient_versions(iid);entry=byid[iid]
                node=tree.insert(parent,'end',text=entry['name'],values=(entry['kind'],),open=False)
                pinned=next((u['revision'] for u in reversed(uses) if u['id']==iid),versions[0]['revision'])
                self._patch_nodes[node]=(iid,pinned)
                for version in versions:
                    child=tree.insert(node,'end',text=('Original' if version is versions[0] else 'Revision '+str(version['revision'])),values=(entry['kind'],))
                    self._patch_nodes[child]=(iid,version['revision'])
    def apply_selected_ingredient(self):
        ids=self.ingredients_tree.selection()
        if ids and ids[0] in getattr(self,'_patch_nodes',{}):
            iid,revision=self._patch_nodes[ids[0]];return self.apply_ingredient(self.catalog.ingredient(iid,revision))
    def export_ingredient(self):
        ids=self.ingredients_tree.selection()
        if not ids or ids[0] not in getattr(self,'_patch_nodes',{}):return
        iid,revision=self._patch_nodes[ids[0]]
        path=filedialog.asksaveasfilename(parent=self,title='Export reusable ingredient',defaultextension='.omne-ingredient.json')
        if path:self.catalog.export_ingredient(iid,path,revision);self.update_status('Ingredient exported')
    def use_media_version(self,version):
        raw=copy.deepcopy(version['payload']);asset=project_from_dict({'assets':{raw['id']:raw}}).assets[raw['id']]
        self.transaction('Use media version',lambda:self.project.assets.__setitem__(asset.id,asset))
        self.refresh_library()
    def source_pool_choice(self,kind):
        from source_pool import source_pool_choice
        return source_pool_choice(self.project,kind)
    def set_source_pool(self,kind,choice):
        from source_pool import set_source_pool
        result=self.transaction('Change '+kind+' source pool',lambda:set_source_pool(self.project,kind,choice))
        if hasattr(self,'cancel_pending_play'):self.cancel_pending_play()
        return result
    def resolve_source_pool(self,project,choice,kind):
        from source_pool import resolve_source_pool
        return resolve_source_pool(project,choice,kind,self.catalog)
    def choose_source_pool(self,kind):
        w=tk.Toplevel(self);w.title('Select '+kind+' albums');w.geometry('520x400');w.transient(self)
        tree=ttk.Treeview(w,show='tree',selectmode='extended');tree.pack(fill='both',expand=True,padx=10,pady=10)
        nodes={};pid=self.project.id
        for album in self.catalog.albums():
            node=tree.insert('','end',text=album['name'],open=False)
            for version in self.catalog.album_versions(album['id']):
                label='Original' if version['revision']=='original' else 'Edited in '+version.get('project','')[-8:]
                child=tree.insert(node,'end',text=label)
                nodes[child]={'id':album['id'],'revision':version['revision'],'snapshot':copy.deepcopy(version)}
            nodes[node]={'id':album['id'],'revision':'original','snapshot':self.catalog.album_revision(album['id'])}
        def choose():
            if self.project.id!=pid:w.destroy();return
            selection=[nodes[i] for i in tree.selection() if i in nodes]
            self.set_source_pool(kind,{'mode':'albums','albums':selection});w.destroy()
        ttk.Button(w,text='Use selected albums',command=choose).pack(anchor='e',padx=10,pady=(0,10))
        w.bind('<Escape>',lambda e:w.destroy());return w
    def browse_audio(self):
        self._audio_catalogue_browse=True;self.refresh_library()
        self.select_library_mode('media');self.library_tabs.select(self.media_tabs['Audio'])
        self.library_tab_changed();self.shell.show('Library');self.media_browsers['Audio'].canvas.focus_set()
        return self.media_browsers['Audio']
    def queue_library_media(self,ids,role='Music',before=None):
        """Link selected sources and place occurrences as one undoable action."""
        from audio_bus import add_sound,sound_events
        from sound_routes import ensure_route
        from instrument_model import voice
        from queue_model import append_assets
        from music_queue import items,store,layout
        raw={a['id']:a for a in self.catalog.assets()}
        now=self.programme_time() if self.playing and not self.reviewing else self.playhead
        def place():
            parsed=project_from_dict({'assets':{i:raw[i] for i in ids if i in raw and i not in self.project.assets}}).assets
            for aid,asset in parsed.items():self.project.assets[aid]=copy.deepcopy(asset)
            chosen=[i for i in ids if self.project.asset(i)]
            for key in ('library_hidden','library_removed'):
                self.project.extra[key]=[i for i in self.project.extra.get(key,[]) if i not in chosen]
            if role!='Music':return append_assets(self.project,voice(self.project,role).id,chosen,before=before)
            if any(self.project.asset(i).kind!='audio' and not self.project.asset(i).metadata.get('has_audio') for i in chosen):raise ValueError('Choose sources with audio.')
            events=items(self.project);idx=next((i for i,e in enumerate(events) if e['id']==before),None) if before else None
            if before and (idx is None or events[idx]['start']<=now):raise ValueError('Choose an upcoming Music position.')
            if idx is not None and any(e.get('locked') or e.get('timing_locked') or e.get('pinned') for e in events[idx:]):raise ValueError('Unpin or unlock affected Music items before inserting.')
            ensure_route(self.project,'soundtrack').update(enabled=True,sound=True,react=True,monitor=True)
            cursor=max([now]+[e['start']+e['duration'] for e in sound_events(self.project)]);created=[]
            for aid in chosen:
                event=add_sound(self.project,aid,start=cursor);event['manual']=True;created.append(event);cursor+=event['duration']
            if idx is not None:store(self.project,events[:idx]+layout(created+events[idx:],events[idx]['start']))
            return created
        result=self.transaction('Link and queue media',place)
        if role=='Music':self.prepare_sound_analysis();self.configure_sound_sources()
        self.queue_deck.show_role(role);return result

    def select_library_mode(self,mode):
        if mode not in self.library_mode_frames:return False
        self.library_modes.select(self.library_mode_frames[mode])
        if hasattr(self,'shell'):self.shell.state.library_mode=mode
        return True
    def library_mode_changed(self,event=None):
        mode=next((k for k,v in self.library_mode_frames.items() if str(v)==self.library_modes.select()),'media')
        if hasattr(self,'shell'):self.shell.state.library_mode=mode
        if mode=='media':
            self.import_media_button.pack(side='right',after=self.shell.menus['panel.library'],padx=3)
            self.layout_library_media(force=True)
        else:self.layout_library_media(force=True)
        if mode=='modules':self.module_library.refresh()
        else:self.refresh_album_options()
        if hasattr(self,'queue_deck'):self.save_preferences()

class AudioLibraryBrowser(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.pid=app.project.id;self.player=None
        self.title('Browse Audio');self.geometry('650x520');self.transient(app)
        self.browser=ProjectBrowser(self,app,'Audio');self.browser.queue_action=lambda ids:self.queue(ids=ids);self.browser.pack(fill='both',expand=True,padx=10,pady=8)
        self.refresh()
        self.browser.canvas.bind('<Double-1>',lambda e:self.queue())
        self.browser.canvas.bind('<ButtonPress-1>',self.begin_drag,add='+')
        self.browser.canvas.bind('<B1-Motion>',self.motion_drag,add='+')
        self.browser.canvas.bind('<ButtonRelease-1>',self.end_drag,add='+')
        foot=ttk.Frame(self);foot.pack(fill='x',padx=10,pady=(0,10))
        ttk.Button(foot,text='+ Queue',style='Accent.TButton',command=self.queue).pack(side='left')
        ttk.Button(foot,text='Audition',command=self.audition).pack(side='left',padx=5)
        ttk.Button(foot,text='Stop audition',command=self.stop_audition).pack(side='left')
        ttk.Button(foot,text='Close',command=self.destroy).pack(side='right')
        self.protocol('WM_DELETE_WINDOW',self.destroy);self.bind('<Escape>',lambda e:self.destroy())
    def refresh(self):
        """Refresh source metadata on explicit browse, retaining local filters."""
        app=self.app
        if getattr(self,'_project_context',app.project) is not app.project:
            self.stop_audition();self.dragging=False;self.entered=None
            self.browser.model.selected.clear()
        self._project_context=app.project;self.pid=app.project.id
        assets=project_from_dict({'assets':{a['id']:a for a in app.catalog.assets()}}).assets;assets.update(app.project.assets)
        hidden=set(app.project.extra.get('library_removed',[]))
        if not app.library_show_hidden.get():hidden.update(app.project.extra.get('library_hidden',[]))
        assets={i:a for i,a in assets.items() if i not in hidden}
        self.browser.set_assets(assets.values())
        from media_browser_model import collection_sections
        albums=app.catalog.albums();members={a['id']:app.catalog.member_ids(a['id']) for a in albums}
        sections=collection_sections(app.project,albums,members,assets)
        for section in sections:
            if section['id'] in members:section['revisions']=app.catalog.album_versions(section['id'])
        self.browser.set_collections(sections,{i:app.catalog.asset_versions(i) for i in assets})
    def queue(self,before=None,ids=None):
        if self.app.project is not self._project_context or self.app.project.id!=self.pid:self.destroy();return
        ids=list(ids if ids is not None else self.browser.selection())
        if ids:self.app.queue_library_media(ids,'Music',before)
    def audition(self):
        self.stop_audition();ids=self.browser.selection()
        if not ids:return
        import subprocess
        from media_engine import FFPLAY
        from process_tools import popen_options
        item=self.browser.model.items[ids[0]]
        if not Path(item.path).is_file():return self.app.update_status('Locate the missing source before auditioning.')
        self.player=subprocess.Popen([FFPLAY,'-hide_banner','-loglevel','error','-autoexit','-nodisp',item.path],
            **popen_options(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def stop_audition(self):
        if self.player and self.player.poll() is None:self.player.terminate()
        self.player=None
    def begin_drag(self,event):
        self.origin=(event.x_root,event.y_root);self.dragging=False;self.entered=None
    def motion_drag(self,event):
        import time
        if not hasattr(self,'origin'):return
        self.dragging=abs(event.x_root-self.origin[0])+abs(event.y_root-self.origin[1])>8
        if not self.dragging:return
        target=self.app.drop_destination(event.x_root,event.y_root)
        if target and target[0]=='queue' and target[1]=='Music':
            if self.entered is None:self.entered=time.monotonic()
            self.app.queue_drop_plan(target[2],event.x_root,event.y_root,time.monotonic()-self.entered)
        else:self.entered=None;self.app.clear_drag_cue()
    def end_drag(self,event):
        import time
        if not getattr(self,'dragging',False):return
        target=self.app.drop_destination(event.x_root,event.y_root)
        if target and target[0]=='queue' and target[1]=='Music':
            kind,before=self.app.queue_drop_plan(target[2],event.x_root,event.y_root,time.monotonic()-(self.entered or time.monotonic()))
            self.queue(before if kind=='insert' else None)
        self.dragging=False;self.app.clear_drag_cue()
    def destroy(self):
        self.stop_audition();super().destroy()
