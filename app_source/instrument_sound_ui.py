"""Small soundtrack-event editor, not a multitrack audio workstation."""
from __future__ import annotations
import copy,math
import tkinter as tk
from tkinter import ttk,messagebox
from audio_bus import sound_events,add_sound
from responsive_controls import PriorityToolbar, OverflowAdapter

class SoundtrackDialog(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.title('Soundtrack · picture and sound are independent');self.geometry('800x555');self.minsize(700,510);self.transient(app);self.vars={}
        body=ttk.Frame(self,padding=14);body.pack(fill='both',expand=True)
        ttk.Label(body,text='SOUNDTRACK  /  CROSSFADES',style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,text='Video sound is a valid source. Select media in the Library, then place its sound here.\nEdit earlier events in a held sequence or a captured take; live additions preserve history.',style='Muted.TLabel',justify='left').pack(anchor='w',pady=7)
        self.tree=ttk.Treeview(body,columns=('start','duration','in','out'),show='tree headings',height=6,selectmode='browse');self.tree.heading('#0',text='Source');self.tree.column('#0',width=270)
        for key,label in [('start','Start'),('duration','Length'),('in','Fade in'),('out','Fade out')]:self.tree.heading(key,text=label);self.tree.column(key,width=85,stretch=False)
        self.tree.pack(fill='both',expand=True);self.tree.bind('<<TreeviewSelect>>',self.choose)
        grid=ttk.Frame(body);grid.pack(fill='x',pady=9)
        for i,(key,label) in enumerate([('start','Start (s)'),('duration','Duration (s)'),('in_point','Source in (s)'),('fade_in','Fade in (s)'),('fade_out','Fade out (s)'),('gain','Gain (0–4)')]):
            row,col=divmod(i,3);v=tk.StringVar(value='');self.vars[key]=v;ttk.Label(grid,text=label).grid(row=row*2,column=col,sticky='w',padx=6)
            entry=ttk.Entry(grid,textvariable=v,width=18);entry.grid(row=row*2+1,column=col,sticky='ew',padx=6,pady=(0,5))
            entry.bind('<Return>',lambda event,k=key:self.apply_field(k));entry.bind('<FocusOut>',lambda event,k=key:self.apply_field(k));grid.columnconfigure(col,weight=1)
        row=PriorityToolbar(body,gap=4);row.pack(fill='x');self.curve=tk.StringVar(value='equal_power')
        self.curve_group=ttk.Frame(row);ttk.Label(self.curve_group,text='Fade curve').pack(side='left')
        curve=ttk.Combobox(self.curve_group,textvariable=self.curve,values=['equal_power','linear'],state='readonly',width=15);curve.bind('<<ComboboxSelected>>',self.apply_curve);curve.pack(side='left',padx=(4,0))
        row.add(self.curve_group,priority=10,overflow=OverflowAdapter.mirror('<<ComboboxSelected>>'))
        row.add_action('Remove event',self.remove,priority=40)
        add=ttk.LabelFrame(body,text='Selected Library source',padding=8);add.pack(fill='x',pady=8);self.fade=tk.StringVar(value='2');ttk.Label(add,text='Crossfade (s)').pack(side='left');ttk.Entry(add,textvariable=self.fade,width=6).pack(side='left',padx=5)
        ttk.Button(add,text='At playhead',command=lambda:self.place(False)).pack(side='left',padx=3);ttk.Button(add,text='Append next',command=lambda:self.place(True)).pack(side='left',padx=3)
        ttk.Button(body,text='Close · keep playing',command=self.destroy).pack(anchor='e');self.refresh()
    def refresh(self):
        selected=self.tree.selection();self.events=[e for e in sound_events(self.app.project) if e.get('route_id')=='soundtrack'];self.tree.delete(*self.tree.get_children())
        for i,e in enumerate(self.events):
            a=self.app.project.asset(e['asset_id']);self.tree.insert('','end',iid=str(i),text=a.name,values=tuple(f'{e[k]:.2f}' for k in ('start','duration','fade_in','fade_out')))
        if selected and self.tree.exists(selected[0]):self.tree.selection_set(selected)
    def chosen(self):
        selected=self.tree.selection();return self.events[int(selected[0])] if selected else None
    def choose(self,event=None):
        e=self.chosen()
        if e:
            for k,v in self.vars.items():v.set(f'{e[k]:g}')
            self.curve.set(e.get('curve','equal_power'))
    def mutable(self,e):
        if self.app.playing and not self.app.reviewing and e['start']<self.app.programme_time():
            self.app.update_status('Hold the sequence or review a captured take to change an already-playing soundtrack event.');return False
        return True
    def write_events(self,events,label):
        def do():self.app.project.extra['sound_events']=events;self.app.project.extra['audio_bus_enabled']=True
        self.app.transaction(label,do);self.app.prepare_sound_analysis();self.refresh()
    def apply(self):
        """Compatibility entry point: commit every edited field immediately."""
        for key in self.vars:self.apply_field(key)

    def apply_field(self,key):
        e=self.chosen()
        if not e or not self.mutable(e):return
        try:
            values={k:float(e[k]) for k in self.vars};values[key]=float(self.vars[key].get())
            if any(not math.isfinite(v) or v<0 for v in values.values()):raise ValueError('Use finite nonnegative values')
            if values['duration']<=0 or values['gain']>4:raise ValueError('Duration must be positive; gain is 0–4')
            if max(values['fade_in'],values['fade_out'])>values['duration']:raise ValueError('A fade cannot exceed this event duration')
            a=self.app.project.asset(e['asset_id'])
            if a.duration and values['in_point']+values['duration']>a.duration+.05:raise ValueError('The selected source range exceeds the available sound')
            if float(e[key])==values[key]:return
            events=copy.deepcopy(self.events);target=events[self.events.index(e)];target[key]=values[key]
            self.write_events(events,'Soundtrack '+key.replace('_',' ')+' updated')
        except Exception as exc:messagebox.showerror('Soundtrack',str(exc),parent=self)

    def apply_curve(self,event=None):
        e=self.chosen()
        if not e or not self.mutable(e) or e.get('curve','equal_power')==self.curve.get():return
        events=copy.deepcopy(self.events);events[self.events.index(e)]['curve']=self.curve.get()
        self.write_events(events,'Soundtrack fade curve updated')
    def remove(self):
        e=self.chosen()
        if e and self.mutable(e):self.write_events([copy.deepcopy(x) for x in self.events if x is not e],'Remove soundtrack event')
    def place(self,append):
        try:
            fade=float(self.fade.get())
            if not math.isfinite(fade) or not 0<=fade<=60:raise ValueError('Use a crossfade of 0–60 seconds')
            aid=self.app.selected_asset_id;a=self.app.project.asset(aid)
            if not a or (a.kind!='audio' and not a.metadata.get('has_audio')):raise ValueError('Select a source with sound in the Library first')
            now=self.app.programme_time() if self.app.playing and not self.app.reviewing else self.app.playhead
            finish=max((e['start']+e['duration'] for e in self.events),default=now);start=max(now,finish-fade) if append else now
            pref=a.metadata.get('sequence_preferences',{});source_in=float(pref.get('source_in',0));source_end=float(pref.get('source_out',a.duration))
            self.app.transaction('Place soundtrack source',lambda:add_sound(self.app.project,aid,start=start,fade=fade,in_point=source_in,duration=max(.01,source_end-source_in)));self.app.prepare_sound_analysis();self.refresh()
        except Exception as exc:messagebox.showerror('Sound source',str(exc),parent=self)
