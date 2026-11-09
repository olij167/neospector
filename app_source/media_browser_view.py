"""Shared, bounded grid/list view. Inclusion is never conflated with focus.

Only one page of canvas objects and thumbnails is presented. The model retains all
folder entries and stable selection/inclusion through search, sorting and paging.
"""
from __future__ import annotations
import math, tkinter as tk
from tkinter import ttk
from media_browser_model import BrowserModel, BrowserItem

class MediaBrowser(ttk.Frame):
    PAGE_SIZE=120
    def __init__(self,parent,app,*,model=None,inclusion=False,on_visible=None,compact=False):
        super().__init__(parent);self.app=app;self.model=model or BrowserModel();self.inclusion=inclusion;self.on_visible=on_visible;self.page=0;self.photos={};self.hits=[];self._last_hit='';self._job=None;self._closed=False
        self.view=tk.StringVar(value='Grid');self.mode=self.view;self.query=tk.StringVar();self.kind=tk.StringVar(value='all');self.sound=tk.StringVar(value='all');self.ready=tk.StringVar(value='all');self.sort=tk.StringVar(value='name');self.reverse=tk.BooleanVar(value=False);self.thumb=tk.StringVar(value='Medium');self.count=tk.StringVar();self.page_label=tk.StringVar()
        self.columnconfigure(0,weight=1);self.rowconfigure(2,weight=1)
        bar=ttk.Frame(self);bar.grid(row=0,column=0,sticky='ew',pady=(0,5));bar.columnconfigure(1,weight=1)
        ttk.Label(bar,text='Search',style='Muted.TLabel').grid(row=0,column=0,padx=(0,4))
        entry=ttk.Entry(bar,textvariable=self.query,width=10);entry.grid(row=0,column=1,sticky='ew');app.add_tip(entry,'Search names and paths. Included sources remain included when hidden by a filter.')
        for col,label,value in [(2,'Grid','Grid'),(3,'List','List')]:ttk.Radiobutton(bar,text=label,variable=self.view,value=value,command=self.schedule).grid(row=0,column=col,padx=2)
        filters=ttk.Frame(self);filters.grid(row=1,column=0,sticky='ew',pady=(0,5))
        for var,values,width in ([(self.kind,['all','video','image','audio','colour','camera'],7),(self.sort,['name','type','duration','date','size'],8)] if compact else [(self.kind,['all','video','image','audio','colour','camera'],7),(self.sound,['all','with sound','silent'],10),(self.sort,['name','type','duration','date','size'],8)]):
            title='Type' if var is self.kind else 'Sound' if var is self.sound else 'Sort'
            ttk.Label(filters,text=title,style='Muted.TLabel').pack(side='left',padx=(0,3))
            box=ttk.Combobox(filters,textvariable=var,values=values,state='readonly',width=max(5,width-2) if compact else width);box.pack(side='left',padx=(0,3));box.bind('<<ComboboxSelected>>',self.refilter)
        self.more_button=ttk.Menubutton(filters,text='⋯',width=3);self.more_button.pack(side='right');menu=tk.Menu(self.more_button,tearoff=False);self.more_button.configure(menu=menu)
        for v in ['all','with sound','silent']:menu.add_radiobutton(label='Sound: '+v,variable=self.sound,value=v,command=self.refilter)
        menu.add_checkbutton(label='Descending sort',variable=self.reverse,command=self.refilter)
        for value in ['Small','Medium','Large']:menu.add_radiobutton(label=value+' thumbnails',variable=self.thumb,value=value,command=self.schedule)
        for value in ['all','ready','issues','included']:menu.add_radiobutton(label='Show '+value,variable=self.ready,value=value,command=self.refilter)
        box=ttk.Frame(self);box.grid(row=2,column=0,sticky='nsew');box.columnconfigure(0,weight=1);box.rowconfigure(0,weight=1)
        self.canvas=tk.Canvas(box,bg=app.ui_chrome['field_bg'],highlightthickness=0,takefocus=True);self.canvas.grid(row=0,column=0,sticky='nsew');self.scroll=ttk.Scrollbar(box,command=self.canvas.yview);self.scroll.grid(row=0,column=1,sticky='ns');self.canvas.configure(yscrollcommand=self.scroll.set)
        foot=ttk.Frame(self);foot.grid(row=3,column=0,sticky='ew',pady=4);ttk.Button(foot,text='‹',width=3,command=lambda:self.turn_page(-1)).pack(side='left');ttk.Label(foot,textvariable=self.page_label).pack(side='left',padx=4);ttk.Button(foot,text='›',width=3,command=lambda:self.turn_page(1)).pack(side='left');ttk.Label(foot,textvariable=self.count,style='Muted.TLabel').pack(side='right')
        self.canvas.bind('<Configure>',lambda e:self.schedule());self.canvas.bind('<Button-1>',self.press);self.canvas.bind('<space>',self.toggle_selected);self.canvas.bind('<Return>',lambda e:self.event_generate('<<ActivateMedia>>'))
        self.canvas.bind('<Button-4>',lambda e:self.canvas.yview_scroll(-3,'units'));self.canvas.bind('<Button-5>',lambda e:self.canvas.yview_scroll(3,'units'));self.canvas.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(-int(e.delta/120) or (-1 if e.delta>0 else 1),'units'))
        for key in ('<Control-a>','<Command-a>'):
            try:self.canvas.bind(key,self.select_all)
            except tk.TclError:pass
        for key,delta in [('<Left>',-1),('<Right>',1),('<Up>',-1),('<Down>',1)]:self.canvas.bind(key,lambda e,d=delta:self.move_focus(d,e))
        self.query.trace_add('write',lambda *_:self.refilter());self.bind('<Destroy>',self.cleanup,add='+');self.schedule()
    def visible(self):return self.rows()
    def rows(self):return self.model.visible(query=self.query.get(),kind=self.kind.get(),sound=self.sound.get(),readiness=self.ready.get(),sort=self.sort.get(),descending=self.reverse.get())
    def refilter(self,event=None):self.page=0;self.canvas.yview_moveto(0);self.schedule()
    def turn_page(self,d):self.page=max(0,min(max(0,(len(self.rows())-1)//self.PAGE_SIZE),self.page+d));self.canvas.yview_moveto(0);self.schedule()
    def schedule(self,*_):
        if self._closed:return
        if self._job:
            try:self.after_cancel(self._job)
            except tk.TclError:pass
        self._job=self.after(35,self.draw)
    def draw(self):
        self._job=None
        if self._closed:return
        theme=self.app.ui_chrome;cv=self.canvas;cv.configure(bg=theme['field_bg']);cv.delete('all');self.hits=[];rows=self.rows();pages=max(1,math.ceil(len(rows)/self.PAGE_SIZE));self.page=min(self.page,pages-1);page=rows[self.page*self.PAGE_SIZE:(self.page+1)*self.PAGE_SIZE];w=max(120,cv.winfo_width());grid=self.view.get()=='Grid';target={'Small':115,'Medium':155,'Large':210}[self.thumb.get()];cols=max(1,w//target) if grid else 1;cw=w/cols;ch=(cw*.57+53) if grid else 70
        for n,r in enumerate(page):
            x=(n%cols)*cw;y=(n//cols)*ch;sel=r.id in self.model.selected;bg=theme['selection_bg'] if sel else theme['panel_bg'];edge=theme['accent'] if sel else theme['panel_edge'];cv.create_rectangle(x+3,y+3,x+cw-4,y+ch-3,fill=bg,outline=edge,width=2 if sel else 1)
            photo=self.photos.get(r.id);left=x+12;top=y+10
            if grid:
                pw=min(cw-24,180);ph=min(ch-51,100);ix=x+cw/2;iy=y+ph/2+8
            else:pw=80;ph=45;ix=x+50;iy=y+34
            if photo:cv.create_image(ix,iy,image=photo,anchor='center')
            else:
                cv.create_rectangle(ix-pw/2,iy-ph/2,ix+pw/2,iy+ph/2,fill=theme['preview_bg'],outline='');cv.create_text(ix,iy,text={'audio':'♫','camera':'CAM','colour':'●'}.get(r.kind,'IMAGE' if r.kind=='image' else '▶'),fill=theme['muted_fg'],font=('TkDefaultFont',12,'bold'))
            textx=x+10 if grid else x+100;ty=y+ch-34 if grid else y+19;maxchars=max(7,int((cw-(20 if grid else 130))/7));title=r.name if len(r.name)<=maxchars else r.name[:maxchars-1]+'…'
            cv.create_text(textx,ty,text=title,anchor='w',fill=theme['foreground'],font=('TkDefaultFont',10,'bold'))
            dur=r.info.get('duration',0);subtitle=(f'{dur:.1f}s · ' if dur else '')+r.kind+(' + sound' if r.info.get('has_audio') and r.kind!='audio' else '')
            if r.error:subtitle='Unavailable · '+r.error[:40]
            elif r.info.get('existing_asset_id'):subtitle+=' · ALREADY IN LIBRARY'
            elif r.state=='pending':subtitle+=' · inspecting'
            if not grid:subtitle+=f' · {r.size/1048576:.1f} MB' if r.size else ''
            cv.create_text(textx,ty+18,text=subtitle[:maxchars+15],anchor='w',fill=theme['failure_fg'] if r.error else theme['muted_fg'],font=('TkDefaultFont',9))
            check=(x+7,y+7,x+29,y+29)
            if self.inclusion:
                cv.create_rectangle(*check,fill=theme['accent'] if r.id in self.model.checked else theme['field_bg'],outline=theme['foreground']);cv.create_text(x+18,y+18,text='✓' if r.id in self.model.checked else '',fill=theme['foreground'])
            self.hits.append((r.id,(x,y,x+cw,y+ch),check))
        cv.configure(scrollregion=(0,0,w,max(cv.winfo_height(),math.ceil(len(page)/cols)*ch)))
        if not rows:cv.create_text(w/2,max(55,cv.winfo_height()/2),text='Choose a folder or add files' if self.inclusion else 'Import media to start playing',fill=theme['muted_fg'],width=max(100,w-24),justify='center')
        self.page_label.set(f'{self.page+1}/{pages}');self.count.set(f'{len(rows)} items');self.event_generate('<<BrowserChanged>>')
        if self.on_visible:self.on_visible([r.id for r in page])
    def hit(self,x,y):
        y=self.canvas.canvasy(y)
        return next((h for h in self.hits if h[1][0]<=x<h[1][2] and h[1][1]<=y<h[1][3]),None)
    def press(self,e):
        self.canvas.focus_set();h=self.hit(e.x,e.y)
        if not h:return
        iid,rect,check=h;self._last_hit=iid;ids=[r.id for r in self.rows()]
        if self.inclusion and check[0]<=e.x<=check[2] and check[1]<=self.canvas.canvasy(e.y)<=check[3]:
            if not self.model.allow_existing and self.model.items[iid].info.get('existing_asset_id'):return
            if iid in self.model.checked:self.model.checked.remove(iid)
            else:self.model.checked.add(iid)
            self.model.focus=iid
        else:self.model.select(iid,ids,add=bool(e.state&4 or e.state&8 and self.tk.call('tk','windowingsystem')=='aqua'),extend=bool(e.state&1))
        self.event_generate('<<TreeviewSelect>>');self.schedule()
    def toggle_selected(self,e=None):
        if self.inclusion:self.model.toggle_selected();self.schedule()
        return 'break'
    def select_all(self,e=None):self.model.selected={r.id for r in self.rows()};self.event_generate('<<TreeviewSelect>>');self.schedule();return 'break'
    def move_focus(self,d,e):
        ids=[r.id for r in self.rows()]
        if not ids:return 'break'
        i=ids.index(self.model.focus) if self.model.focus in ids else 0;i=max(0,min(len(ids)-1,i+d));self.model.select(ids[i],ids,extend=bool(e.state&1));self.see(ids[i]);self.event_generate('<<TreeviewSelect>>');self.schedule();return 'break'
    def set_assets(self,assets):
        self.model.items={a.id:BrowserItem(a.id,a.path,a.kind,a.name,info={'duration':a.duration,**a.metadata},state='ready') for a in assets};self.model.selected.intersection_update(self.model.items);self.schedule()
    def selection(self):return tuple(i for i in self.model.items if i in self.model.selected)
    def selection_set(self,*ids):
        if len(ids)==1 and not isinstance(ids[0],str):ids=tuple(ids[0])
        self.model.selected=set(ids)&set(self.model.items);self.model.focus=next(iter(self.model.selected),None);self.schedule()
    def selection_remove(self,*ids):
        if len(ids)==1 and not isinstance(ids[0],str):ids=tuple(ids[0])
        self.model.selected.difference_update(ids);self.schedule()
    def get_children(self,*_):return tuple(r.id for r in self.rows())
    def exists(self,iid):return iid in self.model.items
    def delete(self,*ids):
        for iid in ids:self.model.items.pop(iid,None);self.photos.pop(iid,None)
        self.model.selected.difference_update(ids);self.schedule()
    def insert(self,parent,index,*,iid,text='',values=(),**_):
        self.model.items[iid]=BrowserItem(iid,'',name=text,state='ready');self.schedule();return iid
    def item(self,iid,option=None,**kwargs):
        if iid not in self.model.items:return {}
        if 'image' in kwargs and self.photos.get(iid) is not kwargs['image']:self.photos[iid]=kwargs['image'];self.schedule()
        if 'text' in kwargs:self.model.items[iid].name=kwargs['text'];self.schedule()
        values={'text':self.model.items[iid].name,'image':self.photos.get(iid)}
        return values.get(option) if option else values
    def see(self,iid):
        ids=[r.id for r in self.rows()]
        if iid in ids:self.page=ids.index(iid)//self.PAGE_SIZE;self.schedule()
    def identify_row(self,y):return self._last_hit
    def yview(self,*args):return self.canvas.yview(*args)
    def bind(self,sequence=None,func=None,add=None):
        if hasattr(self,'canvas') and sequence in ('<Double-1>','<Button-3>','<ButtonRelease-1>'):
            def forward(e):
                h=self.hit(e.x,e.y)
                if h:self._last_hit=h[0]
                return func(e)
            return self.canvas.bind(sequence,forward,add=add)
        return super().bind(sequence,func,add)
    def set_theme(self):self.schedule()
    def cleanup(self,e):
        if e.widget is not self:return
        self._closed=True
        if self._job:
            try:self.after_cancel(self._job)
            except tk.TclError:pass
