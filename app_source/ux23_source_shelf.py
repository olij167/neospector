"""UX29 shared media surface: browser-local Files / Sources, inline sequencing.

One source identity across visual and audio routing. The user chooses a verb
on a row, then one compatible destination. Merely browsing is always inert.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from ux22_project_browser import SharedProjectBrowser
from ux22_inline_sources import InlineSourceSettings
from ux23_live_placement import LiveVisualPlacement,AudioCueQueue
from ux29_browser_model import source_destinations,LIVE_ROLE_NAMES

class SourceShelf(ttk.Frame):
    MODES=(('files','Files'),('sources','Sources'))
    def __init__(self,parent,app):
        super().__init__(parent,padding=(5,4))
        self.app=app;self.mode='files';self.destination='A'
        self.live_visual=LiveVisualPlacement(app);self.audio_cues=AudioCueQueue(app)
        self.destination_choice=tk.StringVar(value='A')
        self._source_generation=0;self.source_rows={};self.source_notes=[]
        head=ttk.Frame(self);head.pack(fill='x',pady=(0,4))
        ttk.Label(head,text='MEDIA BROWSER',style='PlayerName.TLabel').pack(side='left')
        ttk.Button(head,text='×',width=3,command=lambda:app.sidebar.close_browser()).pack(side='right')
        # These are tabs *inside* the browser, not application sidebar tabs.
        nav=ttk.Frame(self);nav.pack(fill='x',pady=(0,5))
        self.tab_buttons={};self.tabs=self.tab_buttons
        for idx,(key,label) in enumerate(self.MODES):
            nav.columnconfigure(idx,weight=1,uniform='browser-nav')
            b=ttk.Button(nav,text=label,command=lambda k=key:self.show(k),style='UX28.QueueIdle.TButton')
            b.grid(row=0,column=idx,sticky='ew',padx=1)
            self.tab_buttons[key]=b
        controls=ttk.Frame(self);controls.pack(fill='x',pady=(0,4))
        self.import_button=ttk.Button(controls,text='＋ Import files',command=app.add_media,style='UX28.Insert.TButton')
        self.import_button.pack(side='left')
        self.refresh_button=ttk.Button(controls,text='↻ Refresh inputs',command=self.discover_sources)
        self.refresh_button.pack(side='right')
        self.media=SharedProjectBrowser(self,app)
        # The single browser owns search, listing and inline action glyphs;
        # destination buttons and a second header are never displayed.
        self.media.winfo_children()[0].pack_forget()
        self.media.dest_row.pack_forget()
        self.media.remove_button.configure(text='Remove selected files')
        self.media.query.set('')
        self.source_page=ttk.Frame(self)
        self.sources_query=tk.StringVar(value='')
        self.search=ttk.Entry(self.source_page,textvariable=self.sources_query)
        self.search.pack(fill='x',pady=(1,4))
        self.sources_query.trace_add('write',lambda *_:self._show_source_rows())
        box=ttk.Frame(self.source_page);box.pack(fill='both',expand=True)
        self.source_list=ttk.Treeview(box,show='tree',columns=('now','next','end'),selectmode='browse',height=7)
        self.source_list.column('#0',minwidth=105,stretch=True)
        for name in ('now','next','end'):self.source_list.column(name,minwidth=31,width=31,stretch=False,anchor='center')
        scroll=ttk.Scrollbar(box,orient='vertical',command=self.source_list.yview)
        self.source_list.configure(yscrollcommand=scroll.set)
        self.source_list.pack(side='left',fill='both',expand=True)
        scroll.pack(side='right',fill='y')
        self.source_list.bind('<ButtonRelease-1>',self._source_row_click)
        self.source_list.bind('<Double-1>',lambda e:self.place_source('queue',self.source_list.focus()))
        self.source_list.bind('<Return>',lambda e:self.place_source('queue',self.source_list.focus()))
        for key,action in (('<Alt-1>','now'),('<Alt-2>','next'),('<Alt-3>','queue')):
            self.source_list.bind(key,lambda e,k=action:(self.place_source(k,self.source_list.focus()),'break')[1])
        self.source_status=tk.StringVar(value='Open Sources to discover devices and playing applications. Browsing never starts capture.')
        ttk.Label(self.source_page,textvariable=self.source_status,style='Muted.TLabel',wraplength=310).pack(fill='x',pady=(3,1))
        # Retain advanced crop and source preference tools for explicit access;
        # they are not parallel navigation or the default placement workflow.
        self.inline=InlineSourceSettings(self,app,'A')
        self.audio_panel=ttk.Frame(self)
        self.placement=ttk.Frame(self)
        self.dest_row=ttk.Frame(self)
        self.action_bar=ttk.Frame(self.placement)
        self.actions={};self.dest_buttons={}
        self.info=tk.StringVar(value='Select a source row then its ▶ / ⏭ / ＋ action')
        self.audio_devices=[]
        self.show('files')

    def show(self,mode,role=None):
        if role in ('A','B','Music'):self.destination=role
        # Old callers requesting camera/screen/audio use the unified Sources
        # tab, without opening a conflicting picker or a placement footer.
        if mode in ('camera','screen','audio'):mode='sources'
        if mode not in ('files','sources'):raise ValueError('Unknown browser page')
        previous=self.mode
        self.mode=mode
        # An already-selected page retains its widgets, selection and scroll.
        # No-op tab navigation must not show an intermediate empty shelf.
        target=self.media if mode=='files' else self.source_page
        if target.winfo_manager()=='pack':
            return
        for widget in (self.media,self.source_page,self.inline,self.audio_panel,self.placement):
            if widget.winfo_manager():widget.pack_forget()
        if mode=='files':
            self.media.pack(fill='both',expand=True)
            self.media.refresh(force=True)
            self.import_button.pack(side='left')
            self.refresh_button.pack_forget()
        else:
            self.source_page.pack(fill='both',expand=True)
            self.import_button.pack_forget()
            self.refresh_button.pack(side='right')
            if previous!='sources' or not self.source_rows:self.discover_sources()
        for key,button in self.tab_buttons.items():
            button.configure(style='UX28.QueueOpen.TButton' if key==mode else 'UX28.QueueIdle.TButton')
        self._fit()

    def prefer(self,role):
        # Remember intent for feedback, not for hiding incompatible files.
        if role in ('A','B','Music'):
            self.destination=role;self.destination_choice.set(role);self.media.prefer(role)
        if hasattr(self.app,'sidebar'):self.app.sidebar.signal(self.destination)

    def discover_sources(self):
        import threading
        self._source_generation+=1
        generation=self._source_generation
        project_id=self.app.project.id
        self.source_status.set('Finding cameras, displays, microphones and application streams…')
        def work():
            try:
                from ux29_source_list import list_all_sources
                sources,notes=list_all_sources()
            except Exception as exc:sources=[];notes=[str(exc)]
            def deliver():
                if (self.app.closing or not self.winfo_exists() or generation!=self._source_generation
                        or self.app.project.id!=project_id):return
                self.populate_sources(sources,notes)
            self.app.events.put(('call',deliver))
        threading.Thread(target=work,name='Neospector live source listing',daemon=True).start()

    def populate_sources(self,sources,notes):
        self.source_rows={'src-%d'%i:dict(item) for i,item in enumerate(sources)}
        self.source_notes=list(notes)
        self._show_source_rows()
        if not sources:self.source_status.set('No inputs found · '+(' · '.join(notes) or 'Check device permissions'))
        else:self.source_status.set(f'{len(sources)} available sources · nothing started'+(' · '+notes[0] if notes else ''))
        self._fit()

    def _show_source_rows(self):
        term=self.sources_query.get().strip().casefold()
        keep=self.source_list.focus()
        for iid in self.source_list.get_children():self.source_list.delete(iid)
        for iid,record in self.source_rows.items():
            label=record.get('label','Unnamed input')
            if term and term not in label.casefold() and term not in record.get('kind',''):continue
            glyph={'camera':'◉','screen':'▣','window':'▣','microphone':'♫','system':'♫','application':'♫'}.get(record.get('kind'),'•')
            available=record.get('capture_available') is not False
            self.source_list.insert('','end',iid=iid,text=f'{glyph}  {label}',values=('▶','⏭','＋') if available else ('','', ''))
        if keep and self.source_list.exists(keep):self.source_list.focus(keep)

    def _source_row_click(self,event):
        row=self.source_list.identify_row(event.y)
        action={'#1':'now','#2':'next','#3':'queue'}.get(self.source_list.identify_column(event.x))
        if row and action:
            self.source_list.selection_set(row);self.source_list.focus(row)
            self.place_source(action,row,event=event)
            return 'break'

    def place_source(self,action,row=None,event=None):
        if not row or row not in self.source_rows:return self.source_status.set('Select a source first')
        source=self.source_rows[row]
        return self.offer_source_destinations(source,action,event=event)

    def offer_source_destinations(self,source,action,event=None):
        allowed=source_destinations(source)
        if not allowed:return self.source_status.set(source.get('capture_hint','This source cannot be routed here'))
        menu=tk.Menu(self,tearoff=False)
        for role in allowed:
            menu.add_command(label=LIVE_ROLE_NAMES[role],command=lambda r=role:self.place_selected_source(source,r,action))
        from contextual_surface import post_native_menu
        previous=getattr(self.app,'_posted_native_menu',None)
        if previous:previous['dismiss']()
        post_native_menu(self.app,menu,self.source_list,event=event)
        return allowed

    def place_selected_source(self,source,role,action):
        if role not in source_destinations(source):return self.source_status.set('Invalid source destination')
        device=source['device'];kind=source['kind']
        if kind in ('microphone','system','application'):
            result=self.audio_cues.enqueue(device,source['label'],action)
            if hasattr(self.app,'sidebar'):self.app.sidebar.signal('Music')
            return result
        if kind in ('screen','window'):
            from visual_capture import describe
            try:device=describe(device,(0.,0.,1.,1.),20,True)
            except (ValueError,KeyError,TypeError) as exc:
                return self.source_status.set('Select Refresh, then choose the source again: '+str(exc))
        result=self.live_visual.place(role,device,kind,action)
        if hasattr(self.app,'sidebar'):self.app.sidebar.signal(role)
        return result

    def place(self,action):
        if self.mode=='files':return self.media.place(action)
        return self.place_source(action,self.source_list.focus())

    def discover_audio(self):self.show('sources');self.discover_sources()
    def hardware_menu(self):self.show('sources')
    def software_menu(self):self.show('sources')
    def requested_height(self):return max(180,int(self.winfo_reqheight())+8)
    def _fit(self):
        if hasattr(self.app,'sidebar'):self.app.sidebar.request_fit();self.app.shell.schedule()
