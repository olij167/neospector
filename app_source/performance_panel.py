"""Right-side front panel; all controls reference existing application state."""
from conductor_targets import DEFAULTS
import tkinter as tk
from tkinter import ttk
from responsive_controls import FlowRow,AdaptiveGrid
from flow_conductor import ConductorPane,LABELS,TIPS
from performance_dials import PerformanceDial
from ui_chrome import tk_scale_theme_options
from playable_intent import load_intent

HELP={
 'randomise':'Try another arrangement and treatment. Keeps your chosen song, devices and locked work.',
 'play':'Play this instrument. File queues and explicitly started live inputs share this transport.',
 'keep':'Save this configuration as a reusable ingredient without stopping Programme.',
 'evolve':'Let Conductor make new choices while playing. Switching off keeps queue progression and reaction.',
 'pace':'Linked pace: 0 = 12–24 second clips / 24 second treatment interval; 1 = 1–3 second clips / 3 second treatment interval. Editing precise timing detaches this macro.',
}

class PerformancePanel(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(6,4));self.app=app
        self.columnconfigure(0,weight=1);self.rowconfigure(5,weight=1)
        ttk.Label(self,text='PERFORMANCE',style='Title.TLabel').grid(row=0,column=0,sticky='w',pady=(0,4))
        src=ttk.Frame(self);src.grid(row=1,column=0,sticky='ew');src.columnconfigure(1,weight=1)
        app.source_labels={}
        for n,kind in enumerate(('music','visuals')):
            ttk.Label(src,text=kind.title(),width=7).grid(row=n,column=0,sticky='w')
            v=tk.StringVar(value='All suitable Library media');app.source_labels[kind]=v
            b=ttk.Menubutton(src,textvariable=v,width=24);b.grid(row=n,column=1,sticky='ew',pady=2)
            m=tk.Menu(b,tearoff=False);b.configure(menu=m)
            m.add_command(label='All suitable Library media',command=lambda k=kind:app.set_source_mode(k,'auto'))
            m.add_command(label='Use Library album',command=lambda k=kind:app.use_source_album(k))
            if kind=='music':m.add_command(label='Use selected song',command=app.use_song)
            m.add_command(label='Live audio · no auto Music' if kind=='music' else 'Camera · no auto visuals',command=lambda k=kind:app.set_source_mode(k,'live'))
            m.add_command(label='Off · leave queue intact',command=lambda k=kind:app.set_source_mode(k,'off'))
            m.add_separator();m.add_command(label='Sound faders…' if kind=='music' else 'Camera controls…',command=app.open_live if kind=='music' else app.toggle_camera_layer)
            app.add_tip(b,'Choose the source pool. Live choices never start or unmute a device; use Mic or Camera explicitly.')
        actions=ttk.Frame(self);actions.grid(row=2,column=0,sticky='ew',pady=(7,3));actions.columnconfigure(0,weight=1)
        app.randomise_label=tk.StringVar(value='Randomise All')
        app.randomise_button=ttk.Button(actions,textvariable=app.randomise_label,style='Accent.TButton',command=app.randomise_playable);app.randomise_button.grid(row=0,column=0,sticky='ew')
        split=ttk.Menubutton(actions,text='▾',width=2);split.grid(row=0,column=1,sticky='ns')
        m=tk.Menu(split,tearoff=False);split.configure(menu=m)
        for scope in ('queues','effects','all'):m.add_command(label='Randomise '+scope.title(),command=lambda s=scope:app.randomise_playable(s))
        app.play_button=ttk.Button(actions,text='▶ PLAY',width=7,style='TransportPlay.TButton',command=app.toggle_play);app.play_button.grid(row=0,column=2,padx=(5,0))
        secondary=FlowRow(self,gap=3);secondary.grid(row=3,column=0,sticky='ew')
        app.stop_button=ttk.Button(secondary,text='■ STOP',width=6,style='TransportStop.TButton',command=app.stop_session);secondary.add(app.stop_button)
        secondary.add(ttk.Button(secondary,text='Undo',command=app.undo,width=5))
        keep=ttk.Button(secondary,text='Keep',command=lambda:app.keep_ingredient('patch'),width=5);secondary.add(keep)
        app.precision_button=ttk.Button(secondary,text='Timing ▸',command=app.toggle_precision,width=8);secondary.add(app.precision_button)
        summary=ttk.Frame(self);summary.grid(row=4,column=0,sticky='ew',pady=3)
        app.performance_status=tk.StringVar(value='Choose music + visuals → Randomise → Play')
        app.transport_queue_caption=tk.StringVar();app.music_transport_caption=tk.StringVar()
        for v in (app.transport_time,app.performance_status,app.music_transport_caption,app.transport_queue_caption):
            label=ttk.Label(summary,textvariable=v,style='Muted.TLabel',wraplength=310);label.pack(fill='x')
            summary.bind('<Configure>',lambda e,w=label:w.configure(wraplength=max(140,e.width-8)),add='+')
        # Queue, timing and details occupy the same contextual area, never the rack.
        app.queue_content=ttk.Frame(self);app.queue_content.grid(row=5,column=0,sticky='nsew');app.queue_content.rowconfigure(0,weight=1);app.queue_content.columnconfigure(0,weight=1)
        app.playback_split=app.queue_content  # compatibility owner, no second horizontal timeline
        app.conductor_mini_visible=tk.BooleanVar(value=True);app.queue_conductor_visible=tk.BooleanVar(value=False)
        app.conductor_tab=ttk.Frame(app.queue_content)
        app.conductor=ConductorPane(app.conductor_tab,app);app.conductor.pack(fill='both',expand=True)
        app.conductor_mini=ConductorStrip(self,app,app.conductor);app.conductor_mini.grid(row=6,column=0,sticky='ew',pady=(4,0))
        app.queue_conductor=app.conductor_tab
        app.queue_conductor.controller=app.conductor
        app.queue_conductor_button=app.conductor_mini.details
        for w,key in ((app.randomise_button,'randomise'),(app.play_button,'play'),(keep,'keep')):app.add_tip(w,HELP[key])

class ConductorStrip(ttk.Frame):
    def __init__(self,parent,app,c):
        super().__init__(parent);self.c=c;self.app=app
        row=FlowRow(self);row.pack(fill='x')
        evolve=ttk.Checkbutton(row,text='Evolve',variable=app.evolve,command=app.toggle_evolve);row.add(evolve);app.add_tip(evolve,HELP['evolve'])
        self.details=ttk.Button(row,text='Conductor details ▸',command=app.toggle_queue_conductor);row.add(self.details)
        grid=AdaptiveGrid(self,minimum=118,maximum=230,max_columns=2,gap=2);grid.pack(fill='x');self.primary_grid=grid
        self.dials=[]
        for key in ('intensity','reaction','variation'):
            dial=PerformanceDial(grid,app,LABELS[key],c.values[key],lambda k=key:c.begin(k),lambda value,k=key:c.changed(k,value),c.end,TIPS[key]);grid.add(dial);self.dials.append(dial)
        self.pace=tk.DoubleVar(value=.5);self.active=False
        self.pace_control=PerformanceDial(grid,app,'Pace',self.pace,self.begin_pace,self.change_pace,self.end_pace,HELP['pace']);grid.add(self.pace_control);self.dials.append(self.pace_control);self.scale=self.pace_control.canvas
        self.scope=tk.StringVar(value='Next choices · existing reaction continues');label=ttk.Label(self,textvariable=self.scope,style='Muted.TLabel',wraplength=310);label.pack(fill='x');self.bind('<Configure>',lambda e:label.configure(wraplength=max(140,e.width-8)))
    def begin_pace(self):
        if not self.active:self.active=True;self.app.begin_gesture('conductor')
    def change_pace(self,value):
        if not self.active:return
        v=float(value);r=self.app.project.conductor;r.clip_min=12-11*v;r.clip_max=24-21*v;r.extra['treatment_interval']=24-21*v;r.extra['playable_pace']={'value':v,'clip_min':r.clip_min,'clip_max':r.clip_max};self.app.changed(False)
    def end_pace(self):
        if self.active:self.change_pace(self.pace.get());self.active=False;self.app.end_gesture();self.c.refresh()
    def refresh(self):
        r=self.app.project.conductor;o=r.extra;parts=[]
        if o.get('evolve_sources',DEFAULTS['evolve_sources']):parts.append('footage')
        if o.get('evolve_treatment',DEFAULTS['evolve_treatment']):parts.append('effects')
        if o.get('evolve_sound',DEFAULTS['evolve_sound']):parts.append('Music')
        pace=o.get('playable_pace',{});linked=pace and abs(r.clip_min-pace['clip_min'])<1e-6 and abs(r.clip_max-pace['clip_max'])<1e-6
        label='Next choices · '+(', '.join(parts) if parts else 'held')+(' · custom timing' if not linked else '')
        if self.scope.get()!=label:self.scope.set(label)
        if not self.active:self.pace_control.set_custom(not linked)
        if linked and not self.active and self.pace.get()!=pace['value']:self.pace.set(pace['value'])
    def retheme(self):
        for dial in self.dials:dial.retheme()
