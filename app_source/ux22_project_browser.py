"""UX22 shared project media shelf and explicit, eligibility-aware placement.

This view never deletes source files or changes playback on selection. It is
mounted once in the right source stack and used by all three channels.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk,messagebox


def eligible_destinations(asset):
    """A silent visual may feed A/B; only sound-bearing assets may feed AUDIO."""
    if asset is None or asset.kind in ('camera','screen','window'):return ()
    if asset.kind=='audio':return ('Music',)
    if asset.kind in ('video','image','picture'):
        return ('A','B','Music') if asset.kind=='video' and bool(asset.metadata.get('has_audio')) else ('A','B')
    return ()


class SharedProjectBrowser(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(6,5));self.app=app;self._revision=None
        self.destination='A';self.query=tk.StringVar(value='');self.status=tk.StringVar(value='Choose a file, then a destination')
        heading=ttk.Frame(self);heading.pack(fill='x')
        ttk.Label(heading,text='PROJECT MEDIA',style='PlayerName.TLabel').pack(side='left')
        ttk.Button(heading,text='×',width=3,command=lambda:app.sidebar.close_browser()).pack(side='right')
        ttk.Button(heading,text='＋ Import',width=9,command=app.add_media).pack(side='right',padx=(0,4))
        ttk.Entry(self,textvariable=self.query).pack(fill='x',pady=(4,3))
        self.query.trace_add('write',lambda *_:self.refresh(force=True))
        self.list_host=ttk.Frame(self)
        self.items=ttk.Treeview(self.list_host,columns=('now','next','end'),show='tree',
            selectmode='extended',height=4)
        for key in ('now','next','end'):
            self.items.column(key,width=31,minwidth=31,stretch=False,anchor='center')
        self.items.column('#0',minwidth=125,stretch=True)
        scroll=ttk.Scrollbar(self.list_host,orient='vertical',command=self.items.yview)
        self.items.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.items.pack(fill='both',expand=True)
        self.items.bind('<<TreeviewSelect>>',self._selection_changed)
        self.items.bind('<ButtonRelease-1>',self._row_action,add='+')
        for key,action in (('<Alt-1>','now'),('<Alt-2>','next'),('<Alt-3>','queue')):
            self.items.bind(key,lambda event,a=action:(self.place(a),'break')[1])
        self.items.bind('<Double-1>',lambda _e:self.place('queue'))
        self.status_label=ttk.Label(self,textvariable=self.status,style='Muted.TLabel',wraplength=310)
        self.status_label.pack(fill='x',pady=(4,1))
        self.dest_row=ttk.Frame(self);self.dest_row.pack(fill='x',pady=2)
        self.dest_buttons={}
        for role,title in (('A','A'),('B','B'),('Music','AUDIO')):
            b=ttk.Button(self.dest_row,text=title,command=lambda r=role:self.choose_destination(r),width=7)
            b.pack(side='left',padx=(0,3));self.dest_buttons[role]=b
        self.actions_frame=ttk.Frame(self);actions=self.actions_frame  # compatibility, no footer actions
        self.action_buttons={}
        for key,title in (('now','▶ Now'),('next','↑ Next'),('queue','＋ End')):
            b=ttk.Button(actions,text=title,width=9,command=lambda a=key:self.place(a))
            b.pack(side='left',fill='x',expand=True,padx=(0,2));self.action_buttons[key]=b
        self.remove_button=ttk.Button(self,text='Remove from project',command=self.remove)
        self.remove_button.pack(anchor='e',pady=(3,0))
        # Pack the resizable list *before* the fixed action footer. The footer
        # retains a reserved height even if the host sidebar becomes short.
        for child in (self.status_label,self.dest_row,self.actions_frame,self.remove_button):child.pack_forget()
        self.remove_button.pack(side='bottom',anchor='e',pady=(2,0))
        # Now / Next / End actions are glyphs at the end of every media row.
        self.dest_row.pack(side='bottom',fill='x',pady=2)
        self.status_label.pack(side='bottom',fill='x',pady=(3,0))
        self.list_host.pack(fill='both',expand=True,pady=(1,0))
        self.refresh(force=True)
        app.add_tip(self.items,'Click ▶ in a row to play now, ⏭ to schedule next, or ＋ to append. Alt+1/2/3 also work. Selecting a row never starts playback.')
    def assets(self):
        removed=set(self.app.project.extra.get('library_removed',()))
        term=self.query.get().strip().casefold()
        return sorted((a for a in self.app.project.assets.values()
            if a.id not in removed and (not term or term in a.name.casefold() or term in (a.path or '').casefold())),
            key=lambda a:a.name.casefold())
    def refresh(self,force=False):
        assets=self.assets();revision=tuple((a.id,a.name,a.kind,bool(a.metadata.get('has_audio'))) for a in assets)
        if revision!=self._revision or force:
            self._revision=revision
            # Reconcile rows by stable asset IDs instead of clearing the whole
            # Treeview (which visibly blanks the shelf and resets scroll).
            wanted={a.id for a in assets}
            for iid in self.items.get_children():
                if iid not in wanted:self.items.delete(iid)
            for index,a in enumerate(assets):
                kind='♫' if a.kind=='audio' else '▣' if a.kind=='video' else '▧'
                title=f'{kind}  {a.name}';values=('▶','⏭','＋')
                if not self.items.exists(a.id):
                    self.items.insert('','end',iid=a.id,text=title,values=values)
                else:
                    if self.items.item(a.id,'text')!=title:self.items.item(a.id,text=title)
                    if tuple(self.items.item(a.id,'values'))!=values:self.items.item(a.id,values=values)
                if self.items.index(a.id)!=index:self.items.move(a.id,'',index)
        self._selection_changed()
    def _row_action(self,event):
        column=self.items.identify_column(event.x)
        action={'#1':'now','#2':'next','#3':'queue'}.get(column)
        row=self.items.identify_row(event.y)
        if not action or not row:return
        # Explicit icon click takes the clicked source; multi-selection stays
        # available via the keyboard shortcuts for a grouped placement.
        self.items.selection_set(row)
        self.items.focus(row)
        self.place(action,event=event)
        return 'break'

    def selected(self):
        return [self.app.project.asset(i) for i in self.items.selection() if self.app.project.asset(i)]
    def allowed(self):
        assets=self.selected()
        if not assets:return ()
        return tuple(r for r in ('A','B','Music') if all(r in eligible_destinations(a) for a in assets))
    def prefer(self,role):
        # Remember the requesting channel even when no project file is yet
        # selected; a later selection must not silently choose A instead.
        if role in ('A','B','Music'):self.destination=role
        self.refresh(force=True)
    def choose_destination(self,role):
        if role in self.allowed():
            self.destination=role;self._selection_changed()
            shelf=getattr(getattr(self.app,'sidebar',None),'source_shelf',None)
            if shelf and shelf.destination!=role:shelf.prefer(role)
            if hasattr(self.app,'sidebar'):self.app.sidebar.signal(role)
    def _selection_changed(self,_event=None):
        from ux29_browser_model import file_destinations
        assets=self.selected();allowed=file_destinations(assets)
        for role,b in self.dest_buttons.items():
            b.configure(state='normal' if role in allowed else 'disabled')
        self.status.set('Choose a file, then ▶ / ⏭ / ＋' if not assets else
                        f'{len(assets)} selected · choose ▶ / ⏭ / ＋ on the row' if allowed else
                        'Selected files have no common playable destination')

    def offer_destinations(self,assets,action,anchor=None,event=None):
        """After the playback verb, ask only for compatible output channels."""
        from ux29_browser_model import file_destinations,ROLE_NAMES
        allowed=file_destinations(assets)
        if not allowed:return self.app.update_status('No compatible destination for this selection.')
        ids=tuple(a.id for a in assets)
        menu=tk.Menu(self,tearoff=False)
        for role in allowed:
            menu.add_command(label=ROLE_NAMES[role],command=lambda r=role:self.place_to(ids,r,action))
        from contextual_surface import post_native_menu
        previous=getattr(self.app,'_posted_native_menu',None)
        if previous:previous['dismiss']()  # a different row's choice replaces the prior menu
        post_native_menu(self.app,menu,anchor or self.items,event=event)
        return allowed

    def place_to(self,ids,role,action):
        self.destination=role
        result=self.app.place_media(list(ids),role,action=action)
        if hasattr(self.app,'sidebar'):self.app.sidebar.signal(role)
        return result

    def place(self,action,event=None):
        assets=self.selected()
        if not assets:return self.app.update_status('Select one or more files first.')
        return self.offer_destinations(assets,action,event=event)
    def remove(self):
        ids={a.id for a in self.selected()}
        if not ids:return
        p=self.app.project
        referenced={c.asset_id for layer in p.layers for c in layer.clips}
        referenced.update(s.get('asset_id') for s in p.extra.get('sound_events',[]))
        referenced.add(p.audio_asset_id)
        if referenced&ids:
            messagebox.showwarning('Used in a queue','Remove these items from their queues before removing them from the project.',parent=self.app);return
        if not messagebox.askyesno('Remove project media','Remove the selected files from this project? Original files will not be deleted.',parent=self.app):return
        def edit():
            for aid in ids:p.assets.pop(aid,None)
            p.extra['library_removed']=sorted(set(p.extra.get('library_removed',()))|ids)
        self.app.transaction('Remove project media',edit);self.refresh(force=True)
