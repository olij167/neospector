"""A shared Conductor controller with full, rack and queue-side instruments."""
from __future__ import annotations
from conductor_targets import DEFAULTS
import tkinter as tk
from tkinter import ttk
from conductor_view import ConductorView,ConductorPreferences
from conductor import SCOPES
from ui_chrome import tk_scale_theme_options
from editor_widgets import ScrollFrame
from responsive_controls import AdaptiveGrid,FlowRow

LABELS={'energy':'Energy','intensity':'FX strength','reaction':'Reaction','layering':'Layering','transition_usage':'Transitions','variation':'Variation'}
TIPS={
 'energy':'Steers linked FX strength, Reaction and visual layering. A manual change detaches its control.',
 'intensity':'Strength of the next generated treatment. Does not alter shot duration.',
 'reaction':'Amount of audio-driven movement in the next generated treatment.',
 'layering':'Probability that generated material uses an additional visual layer. Existing layers are never hidden by this control.',
 'transition_usage':'Share of eligible boundaries using transitions instead of cuts.',
 'variation':'How far selection and source-in choices vary. Locks remain protected.'}

class PolicyControl(ttk.Frame):
    """One small playable policy control, sharing its existing Tk variable."""
    def __init__(self,parent,controller,key,*,primary=False):
        super().__init__(parent,padding=(6,2));self.c=controller;self.key=key
        line=ttk.Frame(self);line.pack(fill='x')
        ttk.Label(line,text=LABELS[key]).pack(side='left')
        self.label=ttk.Label(line,style='Muted.TLabel',width=6,anchor='e');self.label.pack(side='right')
        self.value=controller.values[key]
        self.scale=tk.Scale(self,from_=0,to=1,resolution=.01,orient='horizontal',showvalue=False,length=150,
            variable=self.value,command=lambda value:controller.changed(key,value),**tk_scale_theme_options(controller.app.ui_chrome))
        self.scale.pack(fill='x');self.scale.bind('<ButtonPress-1>',lambda e:controller.begin(key));self.scale.bind('<ButtonRelease-1>',lambda e:controller.end())
        self.scale.bind('<KeyPress>',lambda e:controller.begin(key));self.scale.bind('<KeyRelease>',lambda e:controller.end())
        controller.app.add_tip(self.scale,TIPS[key])
        if primary:controller.values[key+'_label']=self.label
        self.trace=self.value.trace_add('write',self.show_value);self.show_value()
    def show_value(self,*_):
        try:self.label.configure(text=f'{self.value.get():.0%}')
        except (ValueError,tk.TclError):pass
    def destroy(self):
        try:self.value.trace_remove('write',self.trace)
        except tk.TclError:pass
        super().destroy()

def timing_controls(parent,c):
    box=ttk.Frame(parent,padding=(6,4));ttk.Label(box,text='Clip length · seconds',style='Muted.TLabel').pack(anchor='w')
    line=FlowRow(box,gap=4);line.pack(fill='x')
    pair=ttk.Frame(line)
    for i,var in enumerate((c.minimum,c.maximum)):
        if i:ttk.Label(pair,text=' to ').pack(side='left')
        entry=ttk.Entry(pair,textvariable=var,width=5);entry.pack(side='left');entry.bind('<Return>',c.durations)
    line.add(pair);line.add(ttk.Button(line,text='Set',width=4,command=c.durations))
    return box

class ConductorPane(ConductorView):
    def __init__(self,parent,app):
        ttk.Frame.__init__(self,parent,padding=(8,5));self.app=app;self.loading=False;self.active=None
        self.values={key:tk.DoubleVar() for key in LABELS};self.seed=tk.StringVar();self.scope=tk.StringVar(value='sequence');self.expand=tk.BooleanVar(value=True)
        self.minimum=tk.StringVar();self.maximum=tk.StringVar();self.summary=tk.StringVar()
        # Everything remains reachable in a short panel; only details scroll.
        self.scroll=ScrollFrame(self,app);self.scroll.pack(fill='both',expand=True);body=self.scroll.body;self.controls=body
        top=FlowRow(body);top.pack(fill='x',pady=(0,4));self.header_row=top
        brand=ttk.Label(top,text='CONDUCTOR',style='Title.TLabel');top.add(brand)
        seeds=ttk.Frame(top);ttk.Label(seeds,text='Seed',style='Muted.TLabel').pack(side='left',padx=3)
        self.seed_entry=ttk.Entry(seeds,textvariable=self.seed,width=10);self.seed_entry.pack(side='left');self.seed_entry.bind('<Return>',self.apply_seed)
        ttk.Button(seeds,text='New seed',command=self.randomise).pack(side='left',padx=3);top.add(seeds)
        generate=ttk.Frame(top);ttk.Combobox(generate,textvariable=self.scope,values=SCOPES,width=11,state='readonly').pack(side='left')
        self.mutate_button=ttk.Button(generate,text='Generate',style='Accent.TButton',command=app.mutate);self.mutate_button.pack(side='left',padx=3);top.add(generate)
        toggles=ttk.Frame(top);ttk.Checkbutton(toggles,text='Evolve',variable=app.evolve,command=app.toggle_evolve).pack(side='left');ttk.Checkbutton(toggles,text='Front controls',variable=app.conductor_mini_visible,command=app.show_conductor_mini).pack(side='left');top.add(toggles)
        note=ttk.Label(body,text='Steer upcoming choices while Programme plays. Edit pedals to change the current picture.',style='Muted.TLabel',wraplength=620)
        note.pack(fill='x',pady=(0,3));body.bind('<Configure>',lambda e:note.configure(wraplength=max(130,e.width-16)),add='+')
        self.primary_grid=AdaptiveGrid(body,minimum=170,maximum=310,max_columns=3);self.primary_grid.pack(fill='x')
        for key in LABELS:self.primary_grid.add(PolicyControl(self.primary_grid,self,key,primary=True))
        more=FlowRow(body);more.pack(fill='x',pady=3);more.add(timing_controls(more,self))
        pref=ttk.Frame(more);ttk.Button(pref,text='Preferences & weights…',command=lambda:ConductorPreferences(app)).pack(padx=5,pady=10);more.add(pref)
        policies=FlowRow(body);policies.pack(fill='x');self.policies={}
        for key,title,default in [('evolve_treatment','Evolve FX',True),('evolve_sources','Evolve footage',False),('evolve_sound','Continue Music',False)]:
            v=tk.BooleanVar(value=app.project.conductor.extra.get(key,default));self.policies[key]=v
            policies.add(ttk.Checkbutton(policies,text=title,variable=v,command=lambda k=key,v=v:app.transaction('Evolution policy',lambda:app.project.conductor.extra.__setitem__(k,v.get()))))
        pools=FlowRow(body);pools.pack(fill='x',pady=4)
        pools.add(ttk.Button(pools,text='Use selected album',command=app.use_album_pool))
        pools.add(ttk.Button(pools,text='Use all media',command=lambda:app.transaction('All media pool',lambda:app.project.conductor.extra.pop('pool_ids',None))))
        summary=ttk.Label(body,textvariable=self.summary,style='Muted.TLabel',wraplength=620);summary.pack(fill='x',padx=6,pady=3)
        body.bind('<Configure>',lambda e:summary.configure(wraplength=max(130,e.width-16)),add='+')
        self.refresh()
    def recipe(self):
        if hasattr(self.app,'performance_panel'):
            if not self.app.queue_conductor_visible.get():self.app.toggle_queue_conductor()
        else:self.app.shell.show('Conductor')
    def randomise(self):
        super().randomise();self.app.update_status('Seed changed. Generate once or enable Evolve; existing edits are unchanged.')
    def refresh(self):
        if self.active:return
        focus=self.app.focus_get()
        if isinstance(focus,ttk.Entry) and str(focus.cget('textvariable')) in [str(v) for v in (self.seed,self.minimum,self.maximum)]:return
        super().refresh()
        for key,v in getattr(self,'policies',{}).items():v.set(bool(self.app.project.conductor.extra.get(key,DEFAULTS[key])))

class ConductorMini(ttk.Frame):
    def __init__(self,parent,app,conductor):
        super().__init__(parent,padding=(5,2));self.app=app;self.c=conductor
        top=FlowRow(self);top.pack(fill='x')
        top.add(ttk.Button(top,text='Conductor · rack direction ▸',command=conductor.recipe))
        top.add(ttk.Checkbutton(top,text='Evolve',variable=app.evolve,command=app.toggle_evolve))
        self.primary_grid=AdaptiveGrid(self,minimum=145,maximum=260,max_columns=3,gap=4);self.primary_grid.pack(fill='x')
        for key in ('intensity','reaction','variation'):self.primary_grid.add(PolicyControl(self.primary_grid,conductor,key))

class QueueConductor(ttk.Frame):
    """An unfoldable queue companion, not a second copied policy dialog."""
    def __init__(self,parent,app,conductor):
        super().__init__(parent,padding=(4,2));self.controller=conductor;self.app=app
        sf=ScrollFrame(self,app);sf.pack(fill='both',expand=True)
        bar=ttk.Frame(sf.body);bar.pack(fill='x')
        ttk.Label(bar,text='CONDUCTOR',style='Muted.TLabel').pack(side='left')
        ttk.Button(bar,text='×',width=2,command=app.toggle_queue_conductor).pack(side='right')
        ttk.Checkbutton(sf.body,text='Evolve queue',variable=app.evolve,command=app.toggle_evolve).pack(anchor='w')
        timing_controls(sf.body,conductor).pack(fill='x')
        for key in ('transition_usage','variation'):PolicyControl(sf.body,conductor,key).pack(fill='x')
        ttk.Button(sf.body,text='Full controls ▸',command=conductor.recipe).pack(fill='x',padx=5,pady=4)
        note=ttk.Label(sf.body,text='One shared policy. Locks and manual choices stay protected.',style='Muted.TLabel',wraplength=180);note.pack(fill='x',padx=5)
        sf.body.bind('<Configure>',lambda e:note.configure(wraplength=max(120,e.width-14)),add='+')
