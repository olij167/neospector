"""Explicit recipe controls: these govern the next mutation, not silent retiming."""
from __future__ import annotations
import random, copy
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image,ImageDraw,ImageTk
from ui_chrome import CollapsibleSection,tk_scale_theme_options
from conductor import TRANSITIONS,SCOPES
from effects_engine import EFFECTS,transition_image
from sequencer_model import Transition
from editor_widgets import ScrollFrame

TITLES={'dissolve':'Cross-dissolve','fade_colour':'Fade through colour','wipe_left':'Wipe ←','wipe_right':'Wipe →','wipe_up':'Wipe ↑','wipe_down':'Wipe ↓','iris_open':'Iris opens','iris_close':'Iris closes','slide_left':'Slide ←','slide_right':'Slide →','pixel_dissolve':'Pixel dissolve'}

class ConductorView(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(6,3));self.app=app;self.loading=False;self.active=None;self.values={}
        top=ttk.Frame(self);top.pack(fill='x')
        ttk.Label(top,text='CONDUCTOR',style='Title.TLabel').pack(side='left')
        self.seed=tk.StringVar();ttk.Label(top,text='Seed').pack(side='left',padx=(14,3));self.seed_entry=ttk.Entry(top,textvariable=self.seed,width=11);self.seed_entry.pack(side='left');self.seed_entry.bind('<Return>',self.apply_seed)
        ttk.Button(top,text='Randomise',command=self.randomise).pack(side='left',padx=3)
        ttk.Label(top,text='Scope').pack(side='left',padx=(10,4));self.scope=tk.StringVar(value='sequence');ttk.Combobox(top,textvariable=self.scope,values=SCOPES,state='readonly',width=12).pack(side='left')
        self.mutate_button=ttk.Button(top,text='MUTATE',style='Accent.TButton',command=app.mutate);self.mutate_button.pack(side='left',padx=(8,4))
        ttk.Button(top,text='Preferences…',command=lambda:ConductorPreferences(app)).pack(side='right')
        self.expand=tk.BooleanVar(value=True);ttk.Checkbutton(top,text='Direction',variable=self.expand,command=self.toggle).pack(side='right',padx=8)
        ttk.Label(self,text='Next mutation only · manual edits and locks are protected · change effect sliders in the Control Deck to edit the result now.',style='Muted.TLabel').pack(anchor='w',pady=(2,0))
        self.controls=ttk.Frame(self);self.controls.pack(fill='x',pady=(1,0))
        for col,(key,label) in enumerate([('energy','Energy'),('intensity','Intensity'),('reaction','Reaction'),('layering','Layering'),('transition_usage','Transitions'),('variation','Variation')]):
            cell=ttk.Frame(self.controls);cell.grid(row=0,column=col,sticky='ew',padx=(0,8));self.controls.columnconfigure(col,weight=1)
            lab=ttk.Frame(cell);lab.pack(fill='x');ttk.Label(lab,text=label).pack(side='left');v=tk.DoubleVar();self.values[key]=v
            value_label=ttk.Label(lab,text='',style='Muted.TLabel');value_label.pack(side='right');self.values[key+'_label']=value_label
            scale=tk.Scale(cell,variable=v,from_=0,to=1,resolution=.01,orient='horizontal',showvalue=False,command=lambda val,k=key:self.changed(k,val),**tk_scale_theme_options(app.ui_chrome));scale.pack(fill='x');scale.bind('<ButtonPress-1>',lambda e,k=key:self.begin(k));scale.bind('<ButtonRelease-1>',lambda e:self.end());scale.bind('<KeyPress>',lambda e,k=key:self.begin(k));scale.bind('<KeyRelease>',lambda e:self.end())
            explanation={'energy':'Sets linked Intensity, Reaction and Layering. Manually moving one of those detaches it. Relink in Preferences.','intensity':'Strength of generated visual treatments; independent of shot length.','reaction':'Amount of audio modulation chosen by the generator.','layering':'Probability of additional foreground accents; never changes the layer ceiling.','transition_usage':'Share of eligible boundaries with a transition instead of a cut. Not shot frequency.','variation':'Source-in variation within each chosen asset.'}[key]
            app.add_tip(scale,explanation)
        row=ttk.Frame(self.controls);row.grid(row=1,column=0,columnspan=6,sticky='ew')
        ttk.Label(row,text='Clip length').pack(side='left');self.minimum=tk.StringVar();self.maximum=tk.StringVar()
        for v in (self.minimum,self.maximum):
            entry=ttk.Entry(row,textvariable=v,width=6);entry.pack(side='left',padx=3);entry.bind('<Return>',self.durations);entry.bind('<FocusOut>',self.durations)
        ttk.Label(row,text='seconds · min / max',style='Muted.TLabel').pack(side='left')
        self.summary=tk.StringVar();ttk.Label(row,textvariable=self.summary,style='Muted.TLabel').pack(side='right');self.refresh()
    def toggle(self):
        if self.expand.get():self.controls.pack(fill='x',pady=(1,0))
        else:self.controls.pack_forget()
    def refresh(self):
        if self.active:return
        self.loading=True;r=self.app.project.conductor;self.seed.set(str(self.app.project.mutation_seed))
        for key in ('energy','intensity','reaction','layering','transition_usage','variation'):
            self.values[key].set(getattr(r,key));linked=' ↗' if key in r.energy_links else '';self.values[key+'_label'].configure(text=f'{getattr(r,key):.0%}'+linked)
        self.minimum.set(f'{r.clip_min:g}');self.maximum.set(f'{r.clip_max:g}');self.summary.set(f'Transition {r.transition_min:g}–{r.transition_max:g}s  ·  up to {r.max_layers} layers');self.loading=False
    def begin(self,key):
        if self.active:return
        self.active=key;self.app.begin_gesture('conductor')
    def changed(self,key,value):
        if self.loading or self.active!=key:return
        r=self.app.project.conductor;v=float(value)
        if key=='energy':
            r.set_energy(v)
            for linked in r.energy_links:
                if linked in self.values:
                    self.values[linked].set(getattr(r,linked));self.values[linked+'_label'].configure(text=f'{getattr(r,linked):.0%} ↗')
        else:
            setattr(r,key,v)
            if key in r.energy_links:r.energy_links.remove(key)
        self.values[key+'_label'].configure(text=f'{v:.0%}');self.app.changed(redraw=False)
    def end(self):
        if not self.active:return
        self.changed(self.active,self.values[self.active].get());self.active=None;self.app.end_gesture();self.refresh()
    def apply_seed(self,event=None):
        try:
            seed=int(self.seed.get());self.app.transaction('Set seed',lambda:setattr(self.app.project,'mutation_seed',seed))
        except Exception:self.app.update_status('Seed must be an integer')
        return 'break'
    def randomise(self):
        self.seed.set(str(random.SystemRandom().randrange(1,2**31)));self.apply_seed();self.app.update_status('Seed changed. Press MUTATE to generate; existing edits are unchanged.')
    def durations(self,event=None):
        try:
            lo=float(self.minimum.get());hi=float(self.maximum.get())
            if not (.15<=lo<=120 and lo<=hi<=240):raise ValueError('Choose a minimum of 0.15–120 seconds and a maximum between that minimum and 240 seconds')
            def apply():self.app.project.conductor.clip_min=lo;self.app.project.conductor.clip_max=hi
            self.app.transaction('Recipe clip range',apply)
        except Exception as exc:messagebox.showerror('Clip length',str(exc),parent=self)
        return 'break'

class ConductorPreferences(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app
        current=getattr(app,'conductor',None)
        if current is not None and hasattr(current,'advanced_button'):
            # R5 edits the one live recipe in local foldouts.  Keep this legacy
            # entry point harmless for old menus without showing a copied form.
            self.withdraw()
            if not current.expand.get():current.toggle_details()
            choices=getattr(current,'sections',{}).get('Choices')
            if choices:choices.set_expanded(True)
            current.focus_set();self.after_idle(self.destroy);return
        self.recipe=copy.deepcopy(app.project.conductor);self.title('Conductor · preferences');self.geometry('840x610');self.minsize(680,450);self.transient(app)
        body=ttk.Frame(self,padding=12);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Steer the next mutation',style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,text='Prefer = 4× · Allow = 1× · Avoid = 0.15× · Exclude = never. These are recipe choices, not immediate effects.',style='Muted.TLabel',wraplength=760).pack(anchor='w',pady=(3,10))
        book=ttk.Notebook(body);book.pack(fill='both',expand=True);self.preview_widgets=[];self.vars={}
        for attr,label in [('transition_preferences','Transitions'),('effect_preferences','Effects'),('reaction_preferences','Reaction')]:
            sf=ScrollFrame(book,app);book.add(sf,text=label);data=getattr(self.recipe,attr)
            keys=list(TRANSITIONS) if attr=='transition_preferences' else list(data)
            for i,key in enumerate(keys):
                box=ttk.LabelFrame(sf.body,text=TITLES.get(key,EFFECTS[key].label if key in EFFECTS else key.title()),padding=8);box.grid(row=i//3,column=i%3,sticky='nsew',padx=4,pady=4);sf.body.columnconfigure(i%3,weight=1)
                if attr=='transition_preferences':
                    img=tk.Label(box,bg=app.ui_chrome['panel_bg']);img.pack();self.preview_widgets.append((key,img))
                v=tk.StringVar(value=data.get(key,'allow'));self.vars[(attr,key)]=v;ttk.Combobox(box,values=['prefer','allow','avoid','exclude'],textvariable=v,state='readonly',width=14).pack(fill='x',pady=4)
        timing=ttk.Frame(book,padding=12);book.add(timing,text='Timing & links')
        self.nums={}
        for i,(key,label) in enumerate([('transition_min','Minimum transition (s)'),('transition_max','Maximum transition (s)'),('max_layers','Layer ceiling'),('repeat_gap','Media repeat gap'),('bpm','Grid BPM'),('beat_offset','Grid offset (s)')]):
            ttk.Label(timing,text=label).grid(row=i,column=0,sticky='w',pady=5);v=tk.StringVar(value=str(getattr(self.recipe,key)));self.nums[key]=v;ttk.Entry(timing,textvariable=v,width=14).grid(row=i,column=1,sticky='w',padx=10)
        self.beats=tk.BooleanVar(value=self.recipe.beat_sync);ttk.Checkbutton(timing,text='Snap generation to this editable beat grid (not automatically verified beats)',variable=self.beats).grid(row=6,column=0,columnspan=2,sticky='w',pady=8)
        self.links={}
        for i,key in enumerate(('intensity','reaction','layering')):
            v=tk.BooleanVar(value=key in self.recipe.energy_links);self.links[key]=v;ttk.Checkbutton(timing,text='Link '+key+' to Energy',variable=v).grid(row=7+i,column=0,columnspan=2,sticky='w')
        foot=ttk.Frame(body);foot.pack(side='bottom',before=body.winfo_children()[0],fill='x',pady=(10,0));ttk.Button(foot,text='Cancel',command=self.destroy).pack(side='left');ttk.Button(foot,text='Use changes',command=self.save).pack(side='right')
        self.before=time_monotonic();self.animation_job=None;self.animate();self.grab_set()
    def animate(self):
        if not self.winfo_exists():return
        t=(time_monotonic()-self.before)%3/3
        a=Image.new('RGBA',(150,64),'#633aad');b=Image.new('RGBA',(150,64),'#eed4a9');d=ImageDraw.Draw(a);d.ellipse((35,4,95,60),fill='#ffae51');ImageDraw.Draw(b).rectangle((65,12,135,48),fill='#22587b')
        for key,w in self.preview_widgets:
            image=transition_image(a,b,Transition('preview','a','b',kind=key,start=0,duration=1),t);photo=ImageTk.PhotoImage(image);w.configure(image=photo);w.image=photo
        self.animation_job=self.after(100,self.animate)
    def destroy(self):
        if getattr(self,'animation_job',None):
            try:self.after_cancel(self.animation_job)
            except tk.TclError:pass
            self.animation_job=None
        super().destroy()
    def save(self):
        try:
            for (attr,key),v in self.vars.items():getattr(self.recipe,attr)[key]=v.get()
            for key,v in self.nums.items():setattr(self.recipe,key,int(v.get()) if key in ('max_layers','repeat_gap') else float(v.get()))
            if self.recipe.transition_max<self.recipe.transition_min:raise ValueError('Transition maximum must be at least the minimum')
            self.recipe.beat_sync=self.beats.get();self.recipe.energy_links=[k for k,v in self.links.items() if v.get()];self.recipe.normalized()
            self.app.transaction('Conductor preferences',lambda:setattr(self.app.project,'conductor',self.recipe));self.grab_release();self.destroy()
        except Exception as exc:messagebox.showerror('Recipe',str(exc),parent=self)

def time_monotonic():
    import time
    return time.monotonic()
