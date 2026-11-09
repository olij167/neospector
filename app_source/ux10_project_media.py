"""UX10 project-local media folder; importing and queue assignment are distinct."""
from __future__ import annotations
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from media_browser_view import MediaBrowser


class FolderBrowser(MediaBrowser):
    def __init__(self,parent,app):
        super().__init__(parent,app,compact=True,on_visible=lambda ids:app.browser_visible(self,ids))
        self.media_kind='Project'
        self.view.set('List');self.thumb.set('Small')
        self.filter_kind=tk.StringVar(value='All')
        self.sort.set('name')
        for row in (0,1,3):
            for widget in self.grid_slaves(row=row):widget.grid_remove()

    def rows(self):
        query=self.query.get().casefold().strip()
        rows=[r for r in self.model.items.values() if not query or query in r.name.casefold() or query in r.path.casefold()]
        kind=self.filter_kind.get()
        if kind=='Visual':rows=[r for r in rows if r.kind!='audio']
        elif kind=='Audio':rows=[r for r in rows if r.kind=='audio']
        if self.sort.get()=='duration':rows.sort(key=lambda r:(r.info.get('duration',0),r.name.casefold()))
        elif self.sort.get()=='date':rows.sort(key=lambda r:(Path(r.path).stat().st_mtime if Path(r.path).is_file() else 0,r.name.casefold()),reverse=True)
        else:rows.sort(key=lambda r:r.name.casefold())
        return rows


class ProjectMediaFolder(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(5,5))
        self.app=app
        heading=ttk.Frame(self);heading.pack(fill='x',pady=(0,3))
        ttk.Label(heading,text='PROJECT MEDIA',style='PlayerName.TLabel').pack(side='left')
        ttk.Button(heading,text='+ Import',width=9,command=app.add_media,style='Accent.TButton').pack(side='right')
        search=ttk.Frame(self);search.pack(fill='x')
        ttk.Label(search,text='⌕',width=2).pack(side='left')
        self.browser=FolderBrowser(self,app)
        ttk.Entry(search,textvariable=self.browser.query).pack(side='left',fill='x',expand=True)
        filters=ttk.Frame(self);filters.pack(fill='x',pady=3)
        for kind in ('All','Visual','Audio'):
            ttk.Radiobutton(filters,text=kind,variable=self.browser.filter_kind,value=kind,command=self.browser.refilter).pack(side='left',padx=(0,2))
        self.sort_button=ttk.Button(filters,text='A–Z',width=4,command=self.cycle_sort)
        self.sort_button.pack(side='right')
        # Browser is packed last, after persistent queue/drop/remove actions,
        # so a short panel cannot clip its important buttons.
        self.browser.bind('<<TreeviewSelect>>',lambda e:self.selected(),add='+')
        self.browser.bind('<Double-1>',lambda e:self.selected(),add='+')
        actions=ttk.Frame(self);actions.pack(fill='x',pady=(4,0))
        for role in ('A','B','Music'):
            b=ttk.Button(actions,text='+ '+role,width=6,command=lambda r=role:self.assign(r));b.pack(side='left',padx=(0,3))
            app.add_tip(b,'Append selected project media to '+role+'; never automatically take it live.')
        self.remove_button=ttk.Button(actions,text='Remove',command=self.remove,width=7)
        self.remove_button.pack(side='right')
        app.add_tip(self.remove_button,'Remove unused media from this project only. Never delete its source file.')
        self.summary=tk.StringVar(value='Import files to begin')
        ttk.Label(self,textvariable=self.summary,style='Muted.TLabel').pack(fill='x')
        self.browser.pack(fill='both',expand=True,pady=(4,0))

    def cycle_sort(self):
        values=('name','date','duration');next_value=values[(values.index(self.browser.sort.get())+1)%len(values)]
        self.browser.sort.set(next_value);self.sort_button.configure(text={'name':'A–Z','date':'Recent','duration':'Length'}[next_value]);self.browser.refilter()

    def refresh_assets(self):
        project=self.app.project
        removed=set(project.extra.get('library_removed',()))
        self.browser.set_assets([a for a in project.assets.values() if a.id not in removed and a.kind!='camera'])
        self.summary.set(str(len(self.browser.model.items))+' project files · originals remain on your computer')

    def selected(self):
        self.app.library=self.browser
        ids=self.browser.selection()
        self.app.selected_asset_id=next(iter(ids),None)
        self.summary.set((str(len(ids))+' selected · choose a destination below') if ids else str(len(self.browser.model.items))+' project files')

    def assign(self,role):
        self.selected()
        ids=list(self.browser.selection())
        if not ids:return self.app.update_status('Select a project file first.')
        if role=='Music':return self.app.queue_sound_selected(ids)
        return self.app.queue_selected(role,asset_ids=ids)

    def remove(self):
        self.selected();ids=set(self.browser.selection())
        if not ids:return
        p=self.app.project
        referenced=set()
        for layer in p.layers:
            referenced.update(c.asset_id for c in layer.clips if c.asset_id)
        referenced.update(s.get('asset_id') for s in p.extra.get('sound_events',[]) if s.get('asset_id'))
        referenced.update(x for x in (p.audio_asset_id,) if x)
        used=ids&referenced
        if used:
            return messagebox.showwarning('Used in this project','Remove these files from A/B/Music queues before removing them from the project folder. No source file has been touched.',parent=self.app)
        if not messagebox.askyesno('Remove from project','Remove '+str(len(ids))+' unreferenced project file(s)?\n\nThe originals on your computer will not be changed.',parent=self.app):return
        def remove():
            for asset_id in ids:p.assets.pop(asset_id,None)
            p.extra['library_removed']=sorted(set(p.extra.get('library_removed',()))|ids)
        self.app.transaction('Remove unused project media',remove)
        self.refresh_assets()
