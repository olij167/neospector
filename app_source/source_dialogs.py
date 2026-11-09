"""Focused source, sequence and delivery dialogs, rather than permanent form walls."""
from __future__ import annotations
import copy, math
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox,filedialog,colorchooser
from sequencer_model import new_id
from media_engine import EXPORT_PROFILES,preflight_export

class AssetDialog(tk.Toplevel):
    def __init__(self,app,asset):
        super().__init__(app);self.app=app;self.asset=asset;self.metadata=copy.deepcopy(asset.metadata);self.title('Source · '+asset.name);self.transient(app);self.geometry('610x490')
        body=ttk.Frame(self,padding=15);body.pack(fill='both',expand=True);ttk.Label(body,text='Edit source',style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,text='All instances share source content; clip transforms and effects stay independent.',wraplength=570,style='Muted.TLabel').pack(anchor='w',pady=(3,10))
        self.name=tk.StringVar(value=asset.name);ttk.Entry(body,textvariable=self.name).pack(fill='x',pady=4)
        self.text=None;self.shape=None;self.font_size=None
        if asset.kind=='text':
            self.text=tk.Text(body,height=6,wrap='word',bg=app.ui_chrome['field_bg'],fg=app.ui_chrome['foreground'],insertbackground=app.ui_chrome['accent']);self.text.insert('1.0',asset.metadata.get('text',asset.name));self.text.pack(fill='both',expand=True,pady=5)
            row=ttk.Frame(body);row.pack(fill='x');ttk.Label(row,text='Font size').pack(side='left');self.font_size=tk.StringVar(value=str(asset.metadata.get('font_size',64)));ttk.Entry(row,textvariable=self.font_size,width=9).pack(side='left',padx=8);ttk.Button(row,text='Choose local font…',command=self.font).pack(side='left')
        if asset.kind=='shape':
            self.shape=tk.StringVar(value=asset.metadata.get('shape','ellipse'));ttk.Combobox(body,values=['rectangle','ellipse','triangle','polygon'],textvariable=self.shape,state='readonly').pack(fill='x',pady=6)
            ttk.Button(body,text='Draw / edit polygon…',command=self.polygon).pack(fill='x',pady=5)
            ttk.Label(body,text='Shapes remain editable vector points. A shape on an earlier layer can also be used as an alpha mask.',wraplength=565,style='Muted.TLabel').pack(anchor='w',pady=6)
        if asset.kind in ('text','shape','colour'):
            self.colour=tk.StringVar(value=self.metadata.get('colour','#ffffff'));row=ttk.Frame(body);row.pack(fill='x',pady=10);ttk.Label(row,text='Colour').pack(side='left');ttk.Entry(row,textvariable=self.colour,width=15).pack(side='left',padx=8);ttk.Button(row,text='Pick…',command=self.pick).pack(side='left')
        else:ttk.Label(body,text=asset.path,wraplength=560,style='Muted.TLabel').pack(fill='x',pady=8)
        foot=ttk.Frame(body);foot.pack(side='bottom',before=body.winfo_children()[0],fill='x',pady=12);ttk.Button(foot,text='Cancel',command=self.destroy).pack(side='left');ttk.Button(foot,text='Apply source',command=self.save).pack(side='right');self.grab_set()
    def font(self):
        file=filedialog.askopenfilename(parent=self,title='Use a local font without embedding it',filetypes=[('Font','*.ttf *.otf *.ttc')])
        if file:self.metadata['font_path']=file
    def pick(self):
        value=colorchooser.askcolor(self.colour.get(),parent=self)[1]
        if value:self.colour.set(value)
    def polygon(self):
        win=tk.Toplevel(self);win.title('Polygon · click points, drag to move');win.transient(self)
        canvas=tk.Canvas(win,width=530,height=300,bg=self.app.ui_chrome['field_bg']);canvas.pack(fill='both',expand=True)
        def cancel():
            win.destroy()
            if self.winfo_exists():self.grab_set()
        win.protocol('WM_DELETE_WINDOW',cancel);win.bind('<Escape>',lambda e:(cancel(),'break')[1])
        points=[list(p) for p in self.metadata.get('points',[])];drag=[None]
        def paint():
            canvas.delete('all');w=max(1,canvas.winfo_width());h=max(1,canvas.winfo_height())
            if len(points)>2:canvas.create_polygon(*[v for x,y in points for v in (x*w,y*h)],fill=self.app.ui_chrome['selection_bg'],outline=self.app.ui_chrome['accent'],width=2)
            for i,(x,y) in enumerate(points):canvas.create_oval(x*w-5,y*h-5,x*w+5,y*h+5,fill=self.app.ui_chrome['accent']);canvas.create_text(x*w+9,y*h,text=str(i+1),fill=self.app.ui_chrome['foreground'])
        def press(e):
            w=canvas.winfo_width();h=canvas.winfo_height();near=next((i for i,(x,y) in enumerate(points) if abs(x*w-e.x)<9 and abs(y*h-e.y)<9),None)
            if near is None:points.append([e.x/w,e.y/h]);near=len(points)-1
            drag[0]=near;paint()
        def move(e):
            if drag[0] is not None:points[drag[0]]=[max(0,min(1,e.x/canvas.winfo_width())),max(0,min(1,e.y/canvas.winfo_height()))];paint()
        canvas.bind('<Button-1>',press);canvas.bind('<B1-Motion>',move);canvas.bind('<ButtonRelease-1>',lambda e:drag.__setitem__(0,None));canvas.bind('<Configure>',lambda e:paint())
        row=ttk.Frame(win,padding=6);row.pack(fill='x')
        ttk.Button(row,text='Cancel',command=cancel).pack(side='left',padx=(0,6))
        ttk.Button(row,text='Remove last point',command=lambda:(points.pop() if points else None,paint())).pack(side='left')
        def apply():
            if len(points)<3:return messagebox.showerror('Polygon','Add at least three points.',parent=win)
            self.metadata['points']=points;self.shape.set('polygon');win.destroy();self.grab_set()
        ttk.Button(row,text='Use polygon',command=apply).pack(side='right');win.grab_set()
    def save(self):
        try:
            name=self.name.get().strip()
            if not name:raise ValueError('Give the source a name')
            if hasattr(self,'colour'):
                from PIL import ImageColor
                ImageColor.getrgb(self.colour.get());self.metadata['colour']=self.colour.get()
            if self.text is not None:self.metadata['text']=self.text.get('1.0','end-1c');size=float(self.font_size.get());self.metadata['font_size']=max(1,min(2000,size))
            if self.shape:self.metadata['shape']=self.shape.get()
            def do():self.asset.name=name;self.asset.metadata=self.metadata
            self.app.transaction('Edit source',do);self.app.thumbnails.pop(self.asset.id,None);self.app.thumb_pending.discard(self.asset.id);self.app.refresh_library();self.destroy()
        except Exception as exc:messagebox.showerror('Source',str(exc),parent=self)

class AssetPreferences(tk.Toplevel):
    def __init__(self,app,asset):
        super().__init__(app);self.app=app;self.asset=asset;self.title('Source personality · '+asset.name);self.transient(app);self.vars={}
        body=ttk.Frame(self,padding=16);body.pack(fill='both',expand=True);ttk.Label(body,text=asset.name,style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,text='Blank fields inherit the Conductor. Overrides affect new mutations, not existing clips.',wraplength=530,style='Muted.TLabel').pack(anchor='w',pady=8)
        pref=asset.metadata.get('sequence_preferences',{});self.enabled=tk.BooleanVar(value=pref.get('enabled',True));ttk.Checkbutton(body,text='Include this source in the generation pool',variable=self.enabled).pack(anchor='w',pady=5)
        for key,label in [('clip_min','Minimum shot (seconds)'),('clip_max','Maximum shot (seconds)'),('intensity','Treatment intensity (0–1)')]:
            row=ttk.Frame(body);row.pack(fill='x',pady=4);ttk.Label(row,text=label,width=29).pack(side='left');v=tk.StringVar(value=str(pref[key]) if key in pref else '');self.vars[key]=v;ttk.Entry(row,textvariable=v,width=14).pack(side='right')
        self.pref_vars={};book=ttk.Notebook(body);book.pack(fill='both',expand=True,pady=8)
        for key,label in [('effect_preferences','Effects'),('reaction_preferences','Reaction')]:
            frame=ttk.Frame(book,padding=6);book.add(frame,text=label);self.pref_vars[key]={}
            for i,(name,default) in enumerate(getattr(app.project.conductor,key).items()):
                ttk.Label(frame,text=name.title(),width=18).grid(row=i,column=0,sticky='w',pady=2);v=tk.StringVar(value=pref.get(key,{}).get(name,'inherit'));self.pref_vars[key][name]=v;ttk.Combobox(frame,textvariable=v,values=['inherit','prefer','allow','avoid','exclude'],width=12,state='readonly').grid(row=i,column=1)
        ttk.Button(body,text='Save source preferences',command=self.save).pack(anchor='e',pady=8);self.grab_set()
    def save(self):
        try:
            p=copy.deepcopy(self.asset.metadata.get('sequence_preferences',{}));p['enabled']=self.enabled.get()
            for key,v in self.vars.items():
                if v.get().strip():
                    value=float(v.get())
                    if not math.isfinite(value):raise ValueError('Values must be finite')
                    if key=='intensity' and not 0<=value<=1:raise ValueError('Intensity must be between zero and one')
                    if key!='intensity' and not .15<=value<=240:raise ValueError('Clip lengths must be between 0.15 and 240 seconds')
                    p[key]=value
            if p.get('clip_max',self.app.project.conductor.clip_max)<p.get('clip_min',self.app.project.conductor.clip_min):raise ValueError('Maximum shot length must not be less than the minimum')
            for key,items in self.pref_vars.items():
                overrides={name:v.get() for name,v in items.items() if v.get()!='inherit'}
                if overrides:p[key]=overrides
            self.app.transaction('Source personality',lambda:self.asset.metadata.__setitem__('sequence_preferences',p));self.destroy()
        except Exception as exc:messagebox.showerror('Preferences',str(exc),parent=self)

class SequenceSettings(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.title('Sequence settings');self.transient(app);self.vars={};body=ttk.Frame(self,padding=16);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Canvas & time',style='Title.TLabel').pack(anchor='w');self.name=tk.StringVar(value=app.project.name);ttk.Entry(body,textvariable=self.name,width=45).pack(fill='x',pady=8)
        presets={'HD 16:9':(1280,720),'Full HD 16:9':(1920,1080),'Portrait 9:16':(1080,1920),'Square 1:1':(1080,1080),'Small 16:9':(640,360),'Portrait 4:5':(1080,1350)}
        choice=tk.StringVar(value='HD 16:9');box=ttk.Combobox(body,values=list(presets),textvariable=choice,state='readonly');box.pack(fill='x',pady=4)
        for key,label in [('width','Width'),('height','Height'),('fps','Frames per second'),('duration','Minimum duration (s)')]:
            row=ttk.Frame(body);row.pack(fill='x',pady=5);ttk.Label(row,text=label,width=25).pack(side='left');v=tk.StringVar(value=str(getattr(app.project,key)));self.vars[key]=v;ttk.Entry(row,textvariable=v,width=12).pack(side='right')
        box.bind('<<ComboboxSelected>>',lambda e:(self.vars['width'].set(str(presets[choice.get()][0])),self.vars['height'].set(str(presets[choice.get()][1]))))
        self.background=app.project.background
        def colour():
            c=colorchooser.askcolor(self.background,parent=self)[1]
            if c:self.background=c
        ttk.Button(body,text='Background colour…',command=colour).pack(fill='x',pady=5)
        ttk.Label(body,text='No silent crop or retiming: clips beyond the minimum duration extend the sequence. Use an export range to render only part of it. SDR colour; HDR inputs require conversion before import.',wraplength=450,style='Muted.TLabel').pack(fill='x',pady=8)
        ttk.Button(body,text='Apply settings',command=self.save).pack(anchor='e');self.grab_set()
    def save(self):
        try:
            values={k:float(v.get()) for k,v in self.vars.items()}
            if not all(math.isfinite(v) for v in values.values()):raise ValueError('Values must be finite')
            if not(16<=values['width']<=8192 and 16<=values['height']<=8192 and 1<=values['fps']<=120 and .1<=values['duration']<=86400):raise ValueError('Use dimensions 16–8192, FPS 1–120, and a duration up to 24 hours')
            def do():
                p=self.app.project;p.name=self.name.get().strip() or 'Untitled sequence';p.background=self.background
                for k,v in values.items():setattr(p,k,int(v) if k in ('width','height') else v)
            self.app.transaction('Sequence settings',do);self.app.timeline.zoom_fit();self.destroy()
        except Exception as exc:messagebox.showerror('Sequence',str(exc),parent=self)

class ExportDialog(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.title('Export · choose a scope');self.transient(app);self.geometry('620x550')
        self.snapshot=copy.deepcopy(app.project);self.now=app.playhead
        self.context='take' if getattr(app,'reviewing',False) else 'continuous' if self.snapshot.extra.get('playable_intent',{}).get('duration_mode')=='continuous' else 'finite'
        self.current_id=getattr(getattr(getattr(app,'queue_deck',None),'sound',None),'selected',None)
        body=ttk.Frame(self,padding=18);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Export your performance',style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,text=('Take: ' if self.context=='take' else 'Programme: ')+self.snapshot.name+' · frozen when opened',style='Muted.TLabel').pack(anchor='w',pady=5)
        self.scope=tk.StringVar(value='queue');row=ttk.Frame(body);row.pack(fill='x',pady=6)
        for name,value in [('Current song','song'),('Full queue','queue'),('Duration','duration')]:ttk.Radiobutton(row,text=name,value=value,variable=self.scope,command=self.resolve).pack(side='left',padx=(0,10))
        lengths=ttk.Frame(body);lengths.pack(fill='x',pady=5);ttk.Label(lengths,text='Length · seconds / m:ss').pack(side='left')
        self.duration=tk.StringVar(value='30');entry=ttk.Entry(lengths,textvariable=self.duration,width=9);entry.pack(side='left',padx=6);entry.bind('<KeyRelease>',lambda e:self.resolve())
        self.start_labels={'From beginning':'beginning','From playhead':'playhead','Recent history':'recent','Record next':'record_next'};self.start_mode=tk.StringVar(value='From beginning')
        box=ttk.Combobox(lengths,textvariable=self.start_mode,values=list(self.start_labels),state='readonly',width=18);box.pack(side='right');box.bind('<<ComboboxSelected>>',lambda e:self.resolve())
        self.range_value=tk.StringVar();self.range_text=ttk.Label(body,textvariable=self.range_value,wraplength=570,style='Muted.TLabel');self.range_text.pack(fill='x',pady=8)
        self.profile=tk.StringVar(value='web');self.labels={v['label']:k for k,v in EXPORT_PROFILES.items()};self.purpose=tk.StringVar(value=EXPORT_PROFILES['web']['label']);ttk.Combobox(body,values=list(self.labels),textvariable=self.purpose,state='readonly').pack(fill='x',pady=5)
        self.size=tk.StringVar(value='Project');row=ttk.Frame(body);row.pack(fill='x',pady=5);ttk.Label(row,text='Output size',width=17).pack(side='left');ttk.Combobox(row,values=['Project','Long edge 1920','Long edge 1280','Long edge 640'],textvariable=self.size,state='readonly').pack(side='right',fill='x',expand=True)
        self.output=tk.StringVar();row=ttk.Frame(body);row.pack(fill='x',pady=12);ttk.Entry(row,textvariable=self.output).pack(side='left',fill='x',expand=True);ttk.Button(row,text='Choose…',command=self.choose).pack(side='right',padx=(6,0))
        ttk.Label(body,text='Use retained history to render past live material. Unrecorded camera or microphone cannot be recreated. Record next captures future Programme output through the existing recorder.',wraplength=570,style='Muted.TLabel').pack(fill='x',pady=6)
        foot=ttk.Frame(body);foot.pack(side='bottom',fill='x',pady=4);ttk.Button(foot,text='Cancel',command=self.destroy).pack(side='left');self.export_button=ttk.Button(foot,text='Export',style='Accent.TButton',command=self.start);self.export_button.pack(side='right')
        self.bind('<Escape>',lambda e:self.destroy());self.resolve()
    def resolve(self):
        from export_scope import resolve_export_range
        try:
            self.resolved=resolve_export_range(self.snapshot,self.scope.get(),now=self.now,current_event_id=self.current_id,duration=self.duration.get(),start_mode=self.start_labels[self.start_mode.get()],context=self.context)
            r=self.resolved
            if r['action']=='unavailable':self.range_value.set(r['label']);self.export_button.configure(state='disabled');return
            self.range_value.set(f"{r['label']}\n{r['start']:.3f} → {r['end']:.3f}s · {r['end']-r['start']:.3f}s · source coverage checked before rendering")
            self.export_button.configure(state='normal',text='Record next…' if r['action']=='capture_first' else 'Export snapshot')
        except ValueError as exc:self.resolved=None;self.range_value.set(str(exc));self.export_button.configure(state='disabled')
    def choose(self):
        key=self.labels[self.purpose.get()];ext=EXPORT_PROFILES[key]['extension'];name=self.snapshot.name.replace('/','-').replace('\\','-')
        path=filedialog.asksaveasfilename(parent=self,title='Output file',initialfile=name+ext,defaultextension=ext,filetypes=[('Video','*'+ext)],confirmoverwrite=False)
        if path:self.output.set(path)
    def start(self):
        self.resolve();r=self.resolved
        if not r or r['action']=='unavailable':return
        if r['action']=='capture_first':
            if not hasattr(self.app,'record_next_duration'):return messagebox.showinfo('Record next','Use Record Output to capture live Programme, then stop after the desired duration.',parent=self)
            seconds=r['end']-r['start'];self.destroy();self.app.record_next_duration(seconds);return
        path=self.output.get().strip()
        if not path:self.choose();path=self.output.get().strip()
        if not path:return
        try:
            key=self.labels[self.purpose.get()];expected=EXPORT_PROFILES[key]['extension'];p=Path(path)
            if p.suffix.lower()!=expected:raise ValueError(f'This delivery profile needs an {expected} filename.')
            overwrite=p.exists()
            if overwrite and not messagebox.askyesno('Replace existing output?',f'Replace {p.name}? Previous output is preserved until validation.',parent=self):return
            size=None
            if self.size.get()!='Project':
                limit=int(self.size.get().split()[-1]);project=self.snapshot;factor=min(1,limit/max(project.width,project.height));size=(max(16,round(project.width*factor/2)*2),max(16,round(project.height*factor/2)*2))
            if hasattr(self.app,'reserve_history'):self.app.start_export(path,key,size,r['start'],r['end'],overwrite,snapshot=self.snapshot,descriptor=r)
            else:
                preflight_export(self.snapshot,p,overwrite=overwrite,start=r['start'],end=r['end']);self.app.start_export(path,key,size,r['start'],r['end'],overwrite)
            self.destroy()
        except Exception as exc:messagebox.showerror('Export preflight',str(exc),parent=self)
