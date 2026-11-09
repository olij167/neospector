"""Source-local project browser. One project catalogue, three filtered presentations.

Selection never changes the programme. Import and assignment are distinct.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk,messagebox

class SourceMediaBrowser(ttk.Frame):
    def __init__(self,parent,app,role):
        super().__init__(parent,padding=(3,3));self.app=app;self.role=role
        self.query=tk.StringVar();self._snapshot=None
        top=ttk.Frame(self);top.pack(fill='x')
        ttk.Label(top,text='PROJECT FILES',style='PlayerName.TLabel').pack(side='left')
        ttk.Button(top,text='Import +',command=app.add_media,width=8).pack(side='right')
        q=ttk.Entry(self,textvariable=self.query);q.pack(fill='x',pady=3)
        self.query.trace_add('write',lambda *_:self.refresh(force=True))
        self.items=ttk.Treeview(self,columns=('kind',),show='tree',height=5,selectmode='extended')
        scroll=ttk.Scrollbar(self,orient='vertical',command=self.items.yview)
        self.items.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.items.pack(fill='both',expand=True)
        self.items.bind('<Double-1>',lambda e:self.append())
        row=ttk.Frame(self);row.pack(fill='x',pady=(3,0))
        ttk.Button(row,text='+ Queue',command=self.append).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='Remove file',command=self.remove).pack(side='right')
        app.add_tip(self.items,'Source-local project media. Double-click to append to this queue; never takes an item live.')
        app.add_tip(row.winfo_children()[-1],'Remove from this project only, never from the computer.')

    def filtered(self):
        query=self.query.get().casefold().strip()
        removed=set(self.app.project.extra.get('library_removed',()))
        return sorted((a for a in self.app.project.assets.values()
            if a.kind!='camera' and a.id not in removed and (a.kind=='audio')==(self.role=='Music')
            and (not query or query in a.name.casefold() or query in a.path.casefold())),
            key=lambda a:a.name.casefold())

    def refresh(self,force=False):
        assets=self.filtered();signature=tuple((a.id,a.name,a.kind) for a in assets)
        if signature==self._snapshot and not force:return
        keep=set(self.items.selection());self._snapshot=signature
        for row in self.items.get_children():self.items.delete(row)
        for asset in assets:self.items.insert('', 'end',iid=asset.id,text=asset.name)
        for aid in keep:
            if self.items.exists(aid):self.items.selection_add(aid)

    def append(self):
        ids=list(self.items.selection())
        if not ids:return self.app.update_status('Select a project file to add to '+self.role+'.')
        if self.role=='Music':return self.app.queue_sound_selected(ids)
        return self.app.queue_selected(self.role,asset_ids=ids)

    def remove(self):
        ids=set(self.items.selection())
        if not ids:return
        from instrument_model import voice
        p=self.app.project
        referenced=set()
        for layer in p.layers:
            referenced.update(c.asset_id for c in layer.clips)
        referenced.update(s.get('asset_id') for s in p.extra.get('sound_events',[]))
        referenced.add(p.audio_asset_id)
        if ids&referenced:
            messagebox.showwarning('Still in a queue','Remove these items from A/B/MUSIC queues before removing them from the project.',parent=self.app);return
        if not messagebox.askyesno('Remove from project','Remove selected unreferenced project items?\nSource files on your computer will remain unchanged.',parent=self.app):return
        def apply():
            for aid in ids:p.assets.pop(aid,None)
            p.extra['library_removed']=sorted(set(p.extra.get('library_removed',()))|ids)
        self.app.transaction('Remove project media',apply)
        self.refresh(True)
