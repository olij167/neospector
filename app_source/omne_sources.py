"""One radio beside its audio mixer. Visibility and device power stay separate."""
import tkinter as tk
from tkinter import ttk
from responsive_controls import PriorityToolbar
from sound_routes import source_id,default_route
from mixer_fader import MixerFader
from visual_channels import master_at,set_master

class SourceStrip(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=4);self.app=app;self.active=None;self.loading=False;self.gains={};self.roles={};self.faders={};self.input_enabled={};self.input_buttons={}
        row=PriorityToolbar(self,gap=3);self.toolbar=row;row.pack(fill='x',pady=(0,3))
        row.more_button.configure(text='⋯',width=3)
        self.queue_button=ttk.Button(row,text='Queue ▾',width=8,command=self.toggle_queue);row.add(self.queue_button,priority=0,pinned=True)
        app.audio_browse_button=ttk.Button(row,text='Music…',command=lambda:app.browse_audio());row.add(app.audio_browse_button,priority=5,pinned=True)
        # The microphone's ON switch beside its fader owns live power. Keep the
        # legacy command projection for integrations, without a second toggle.
        app.mic_button=ttk.Button(row,text='Mic',width=6,command=app.quick_microphone)
        app.live_button=ttk.Button(row,text='Inputs…',width=8,command=app.open_live);row.add(app.live_button,priority=20)
        app.add_tip(app.live_button,'Choose microphones, line inputs or application/monitor sources exposed by your operating system. Each has independent sound, reaction and monitor routing.')
        body=ttk.Frame(self);body.pack(fill='both',expand=True);self.body=body
        self.levels=ttk.Frame(body);self.levels.pack(fill='x',pady=(2,5))
        self.music_host=ttk.Frame(body);self.queue_expanded=False
        for i,(key,label) in enumerate((('music','Music'),('mic','Mic'),('master','Master'))):
            f=MixerFader(self.levels,app,label,lambda k=key:self.begin(k),lambda v,k=key:self.change(k,v),self.end,
                maximum=1. if key=='master' else 2.,length=70)
            self.levels.columnconfigure(i,weight=1);f.grid(row=0,column=i,sticky='n',padx=1);self.faders[key]=f;self.gains[key]=f.value;self.gains[key+'_label']=f.display
            app.add_tip(f.scale,{'music':'Music level. This same fader level is used in Programme recording.',
                'mic':'Microphone level. This same fader level is used in Programme recording when Mic is ON.',
                'master':'Master audio level for this performance, including recording/export and local monitoring. Does not change the system device volume or the analysis signal.'}[key])
            if key!='master':
                enabled=tk.BooleanVar(value=(key=='music'));self.input_enabled[key]=enabled
                button=ttk.Checkbutton(self.levels,text='ON',variable=enabled,command=lambda k=key:self.toggle_input(k));button.grid(row=1,column=i,pady=(2,0));self.input_buttons[key]=button
                app.add_tip(button,'One normal-use switch: ON = audible Programme Sound + visual React + included in recordings. Advanced Routing can deliberately change that combination.')
        self.route_state=tk.StringVar(value='Mic OFF · inputs never start automatically.')
        for event in ('<Map>','<Unmap>'):
            self.input_buttons['mic'].bind(event,lambda e:app.after_idle(app.refresh_primary_toolbar) if not app.closing else None,add='+')
        app.add_tip(self.input_buttons['mic'],'Mic ON includes Sound + React + Record. Inputs… exposes independent advanced routing. The live route state is shown there.')
        # Inputs… is the single route/device entry point; do not duplicate it
        # below the faders where it can be clipped in a short audio cell.
        # The old camera inspector remains reachable for legacy projects, but is no
        # longer a visible source switch in the audio instrument.
        self.camera_window=None
    def toggle_queue(self):
        self.show_queue(not self.queue_expanded)
    def show_queue(self,value=True):
        """Reveal the retained queue below its mixer, never squeeze it beside faders."""
        self.queue_expanded=bool(value)
        if value:self.music_host.pack(fill='both',expand=True)
        else:self.music_host.pack_forget()
        self.queue_button.configure(text='Queue ▴' if value else 'Queue ▾')
        if value and hasattr(self.app,'audio_scroll'):
            self.after_idle(lambda:self.app.audio_scroll.canvas.yview_moveto(1.))
    def rid(self,key):return source_id(self.app.last_microphone_device) if key=='mic' else 'soundtrack'
    def toggle_input(self,key):
        if key not in self.input_enabled:return
        rid=self.rid(key);enabled=bool(self.input_enabled[key].get())
        if key=='mic':
            self.app.set_sound_source_enabled(rid,enabled,device=self.app.last_microphone_device,label='Microphone')
        else:self.app.set_sound_source_enabled(rid,enabled,label='Audio queue')
    def begin(self,key):
        if self.active is not None:return
        self.active=key;self.app.begin_gesture('program');self.gesture_time=self.app.programme_time() if self.app.playing else self.app.playhead
    def change(self,key,value):
        if self.loading or self.active!=key:return
        if key=='master':set_master(self.app.project,'audio',value,self.gesture_time);self.app.changed()
        else:self.app.edit_sound_route(self.rid(key),{'gain':value},gesture=True)
    def end(self):
        if self.active is None:return
        self.active=None;self.app.end_gesture();self.refresh()
    def refresh(self):
        if self.active:return
        p=self.app.project
        for key,fader in self.faders.items():
            route=p.extra.get('sound_routes',{}).get(self.rid(key),default_route(self.rid(key)))
            value=master_at(p,'audio',self.app.playhead) if key=='master' else route.get('gain',1.)
            fader.sync(value)
        for key,var in self.input_enabled.items():
            rid=self.rid(key);route=p.extra.get('sound_routes',{}).get(rid,default_route(rid))
            on=bool(route.get('enabled',False))
            if key=='mic':on=on and self.app.live.source_states().get(rid,{}).get('state') in ('starting','live')
            if bool(var.get())!=on:var.set(on)
        route=p.extra.get('sound_routes',{}).get(self.rid('mic'),default_route(self.rid('mic')))
        if not route.get('enabled',False):text='Mic OFF · turn ON for Sound + React + Record'
        else:
            uses=[name for key,name in [('sound','Sound + Record'),('react','React'),('monitor','Monitor')] if route.get(key)]
            text='Mic ON · '+(' + '.join(uses) or 'not routed')
        if self.route_state.get()!=text:self.route_state.set(text)
    def toggle_camera_details(self):
        if hasattr(self.app,'open_channel_camera'):
            self.camera_window=self.app.open_channel_camera('A');return self.camera_window
