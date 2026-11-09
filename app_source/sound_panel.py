"""One source-strip grammar for the compact mixer and expanded input browser."""
from __future__ import annotations
import copy,time,threading
import tkinter as tk
from tkinter import ttk,simpledialog
from sound_routes import BUILTINS,default_route,ensure_route,source_id
from audio_bus import sound_events
from ui_chrome import tk_scale_theme_options
from editor_widgets import ScrollFrame

def source_order(app,routes,discovered,show_all=False):
    ids=['soundtrack'];p=getattr(app,'project',None)
    for rid in BUILTINS[1:]:
        role=rid.split(':',1)[1]
        layer=next((l for l in getattr(p,'layers',()) if l.extra.get('voice')==role),None)
        usable=bool(layer and any(p.asset(c.asset_id) and p.asset(c.asset_id).metadata.get('has_audio') for c in layer.clips))
        if rid in routes or usable or (show_all and role in ('A','B')):ids.append(rid)
    mic_device=getattr(app,'last_microphone_device','default')
    mic_id=source_id(mic_device)
    sources={s['id']:s for s in discovered}
    sources.setdefault(mic_id,dict(id=mic_id,device=mic_device,kind='microphone',label='Microphone'))
    ids.append(mic_id)
    ids.extend(k for k in routes if k not in ids)
    if show_all:ids.extend(k for k in sources if k not in ids)
    return ids,sources

def active_source_order(app,routes,discovered,states,has_audio_queue=False):
    """Desk view shows engaged routes, not the inventory of every possible input.

    Discovery stays in Sources and the + control. Physical inputs require a
    live/starting capture, avoiding silent strips for old disconnected routes.
    The audio queue is visible once it contains a track, even if paused.
    """
    ids,sources=source_order(app,routes,discovered,False)
    active=[]
    for rid in sources:
        if rid not in ids and states.get(rid,{}).get('state') in ('starting','live'):
            ids.append(rid)
    for rid in ids:
        route=routes.get(rid,{})
        state=states.get(rid,{}).get('state')
        if rid=='soundtrack':
            if has_audio_queue:active.append(rid)
        elif rid.startswith('voice:'):
            role=rid.split(':',1)[1]
            project=getattr(app,'project',None)
            layer=next((x for x in getattr(project,'layers',()) if x.extra.get('voice')==role),None)
            audible=bool(layer and any(project.asset(c.asset_id) and
                project.asset(c.asset_id).metadata.get('has_audio') for c in layer.clips))
            if route.get('enabled',False) and audible:active.append(rid)
        elif state in ('starting','live'):
            active.append(rid)
    return active,sources

class SourceMixer(ttk.Frame):
    def __init__(self,parent,app,expanded=False):
        super().__init__(parent,padding=3);self.app=app;self.all=tk.BooleanVar(value=expanded);self.key=None;self.rows={};self.sources=[];self.notes=[];self.scan=False;self.after_id=None
        bar=ttk.Frame(self);bar.pack(fill='x',pady=(1,5));ttk.Label(bar,text='SOUND SOURCES',style='Title.TLabel').pack(side='left')
        ttk.Checkbutton(bar,text='All',variable=self.all,command=self.show_all).pack(side='right');ttk.Button(bar,text='+',width=3,command=self.add_menu).pack(side='right',padx=2)
        app.add_tip(bar,'ON is the simple path: Programme Sound + visual React + recording at this fader level. Advanced Routing can make a source React-only. Monitor is local only.')
        queue_frame=ttk.Frame(self,padding=(3,4));queue_frame.pack(fill='x');self.queue_label=tk.StringVar(value='Audio queue · empty');ttk.Label(queue_frame,textvariable=self.queue_label,wraplength=280,justify='left',style='Muted.TLabel').pack(fill='x')
        tools=ttk.Frame(queue_frame);tools.pack(fill='x',pady=3);ttk.Button(tools,text='Add from Library',command=app.queue_sound_selected).pack(side='left');ttk.Button(tools,text='Timing…',command=app.soundtrack_dialog).pack(side='right')
        self.scroll=ScrollFrame(self,app);self.scroll.pack(fill='both',expand=True)
        self.info=tk.StringVar(value='Inputs start OFF. Turn one ON for Programme + React + recording. Advanced Routing holds React-only / Monitor options.');ttk.Label(self,textvariable=self.info,style='Muted.TLabel',wraplength=300,justify='left').pack(fill='x',pady=4)
        self.refresh(True);self.after_id=self.after(120,self.tick);self.bind('<Destroy>',self.destroyed,add='+')
    def destroyed(self,event):
        if event.widget is self and self.after_id:
            try:self.after_cancel(self.after_id)
            except tk.TclError:pass
            self.after_id=None
    def tick(self):
        if self.app.closing:return
        if self.winfo_viewable():self.refresh()
        self.after_id=self.after(150,self.tick)
    def show_all(self):
        self.refresh(True)
        if self.all.get() and not self.sources:self.discover()
    def discover(self):
        if self.scan:return
        self.scan=True;self.info.set('Finding devices and currently playing application streams…')
        def work():
            from live_sources import enumerate_devices
            from system_audio import discover_audio_sources
            devices=enumerate_devices();sources,notes=discover_audio_sources()
            sources=[{'id':source_id(d),'device':d,'label':'Microphone · '+d,'kind':'microphone'} for d in devices['microphone'] if d!='test']+[{'id':source_id(s),'device':s,'label':s['label'],'kind':s['kind']} for s in sources]
            def ready():
                if not self.winfo_exists():return
                self.sources=sources;self.notes=notes;self.scan=False;self.all.set(True);self.key=None;self.refresh(True);self.info.set((' '.join(notes) or 'Choose a source and turn it ON when you want it in Programme. Nothing is enabled automatically.')[:500])
            self.app.events.put(('call',ready))
        threading.Thread(target=work,name='Find sound inputs',daemon=True).start()
    def add_menu(self):
        menu=tk.Menu(self,tearoff=False);menu.add_command(label='Microphone · one press',command=self.app.quick_microphone);menu.add_command(label='Find device / application audio…',command=self.discover);menu.add_command(label='Import audio / video files…',command=self.app.add_media)
        menu.add_separator();menu.add_command(label='Stop all inputs',command=self.app.stop_inputs)
        from contextual_surface import post_native_menu
        post_native_menu(self.app,menu,self)
    def order_sources(self,routes,states):
        return source_order(self.app,routes,self.sources,self.all.get())
    def refresh(self,force=False):
        p=self.app.project;states=self.app.live.source_states() if hasattr(self.app.live,'source_states') else {}
        routes=p.extra.get('sound_routes',{})
        ids,sources=self.order_sources(routes,states);key=(p.id,tuple(ids))
        if force or key!=self.key:
            self.key=key;self.rows={}
            for w in self.scroll.body.winfo_children():w.destroy()
            if isinstance(self,DeskFaderMixer):
                if ids:
                    self.empty_status.pack_forget()
                    if not self.scroll.winfo_manager():self.scroll.pack(fill='both',expand=True,after=self.controls)
                    if not self.notice.winfo_manager():self.notice.pack(fill='x',pady=(2,0))
                else:
                    self.scroll.pack_forget();self.notice.pack_forget()
                    if not self.empty_status.winfo_manager():self.empty_status.pack(fill='x',pady=(6,1))
            for rid in ids:self.make_row(rid,routes.get(rid,default_route(rid,sources.get(rid,{}).get('label',''))),sources.get(rid))
            if isinstance(self,DeskFaderMixer) and hasattr(self.app,'sidebar'):
                self.app.sidebar.request_fit()
        now=self.app.playhead
        try:
            signature=(id(p),self.app.revision)
            if getattr(self,'_audio_key',None)!=signature:self._audio_events=[e for e in sound_events(p) if e.get('route_id')=='soundtrack'];self._audio_key=signature
            events=self._audio_events;current=next((e for e in reversed(events) if e['start']<=now<e['start']+e['duration']),None);up=next((e for e in events if e['start']>now),None)
            def name(e):return p.asset(e['asset_id']).name if e and p.asset(e['asset_id']) else '—'
            self.queue_label.set('CURRENT  '+name(current)+'\nNEXT  '+name(up))
        except Exception:self.queue_label.set('Audio queue · open Timing to repair a missing source')
        for rid,row in self.rows.items():
            r=routes.get(rid,default_route(rid));state=states.get(rid,{});active=row['active']
            if not active and self.app.focus_get() is not row.get('entry'):row['level'].set(r.get('gain',1));row['numeric'].set(f"{r.get('gain',1):.2f}")
            row['muted'].set(r.get('muted',False));row['enabled'].set(bool(r.get('enabled',False)) if rid in BUILTINS else bool(r.get('enabled',False) and state.get('state') in ('starting','live')))
            purposes=[]
            if r.get('sound'):purposes.append('Sound + Record')
            if r.get('react'):purposes.append('React')
            if r.get('monitor'):purposes.append('Monitor')
            row['route'].configure(text='⋯' if row.get('compact') else 'Advanced · '+(' + '.join(purposes) if purposes else 'not routed'))
            row['meter']['value']=min(1.,(state.get('level',0) if rid not in BUILTINS else self.app.audio_bus.levels.get(rid,0) if self.app.playing else 0)*4)
            if rid not in BUILTINS:
                st=state.get('state','stopped');row['state'].set(('ON · '+st.title()) if st in ('starting','live') else (st.title() if not state.get('error') else 'Input error · '+state['error'][:70]))
    def make_row(self,rid,r,source=None):
        body=ttk.Frame(self.scroll.body,padding=(5,6));body.pack(fill='x',pady=3);body.columnconfigure(0,weight=1)
        name=ttk.Frame(body);name.grid(row=0,column=0,columnspan=3,sticky='ew');name.columnconfigure(0,weight=1)
        ttk.Label(name,text=r.get('label',rid),wraplength=220).grid(row=0,column=0,sticky='w')
        enabled=tk.BooleanVar(value=False)
        def toggle_enabled():
            device=source['device'] if source else self.app.project.extra.get('sound_routes',{}).get(rid,{}).get('device')
            self.app.set_sound_source_enabled(rid,enabled.get(),device=device,label=(source or r).get('label',rid))
        on=ttk.Checkbutton(name,text='ON',variable=enabled,command=toggle_enabled);on.grid(row=0,column=1);self.app.add_tip(on,'One control for normal use: ON = audible Programme Sound + visual React + included in recordings. Use Advanced only for a deliberate React-only or Monitor route.')
        level=tk.DoubleVar(value=r.get('gain',1));numeric=tk.StringVar(value=f'{level.get():.2f}');muted=tk.BooleanVar(value=r.get('muted',False));row={'active':False,'level':level,'numeric':numeric,'muted':muted,'enabled':enabled}
        def begin(event=None):
            row['active']=True;self.app.begin_gesture('Source level')
        def end(event=None):
            if row['active']:self.app.edit_sound_route(rid,{'gain':level.get()},gesture=True);row['active']=False;self.app.end_gesture()
        def change(v):
            if row['active']:numeric.set(f'{float(v):.2f}');self.app.edit_sound_route(rid,{'gain':float(v)},gesture=True)
        fader=tk.Scale(body,variable=level,from_=0,to=2,resolution=.01,showvalue=False,orient='horizontal',command=change,**tk_scale_theme_options(self.app.ui_chrome));fader.grid(row=1,column=0,sticky='ew')
        fader.bind('<ButtonPress-1>',begin);fader.bind('<ButtonRelease-1>',end);fader.bind('<KeyPress>',begin,add='+');fader.bind('<KeyRelease>',end,add='+');fader.bind('<MouseWheel>',lambda e:'break');fader.bind('<Button-4>',lambda e:'break');fader.bind('<Button-5>',lambda e:'break')
        entry=ttk.Entry(body,textvariable=numeric,width=5);entry.grid(row=1,column=1,padx=4);row['entry']=entry
        def enter(event=None):
            try:self.app.edit_sound_route(rid,{'gain':float(numeric.get())})
            except ValueError:self.info.set('Enter a source gain between 0 and 2×')
            return 'break'
        entry.bind('<Return>',enter);ttk.Checkbutton(body,text='Mute',variable=muted,command=lambda:self.app.edit_sound_route(rid,{'muted':muted.get()})).grid(row=1,column=2)
        meter=ttk.Progressbar(body,maximum=1,length=80);meter.grid(row=2,column=0,columnspan=3,sticky='ew',pady=(0,4));row['meter']=meter
        footer=ttk.Frame(body);footer.grid(row=3,column=0,columnspan=3,sticky='ew');route=ttk.Button(footer,text='',command=lambda:self.route_menu(rid,body));route.pack(side='left');row['route']=route
        if rid not in BUILTINS:
            state=tk.StringVar();ttk.Label(body,textvariable=state,style='Muted.TLabel',wraplength=270).grid(row=4,column=0,columnspan=3,sticky='ew');row['state']=state
        self.rows[rid]=row
    def route_menu(self,rid,anchor):
        p=self.app.project;r=ensure_route(p,rid);menu=tk.Menu(self,tearoff=False)
        for key,title in [('sound','Programme Sound · recorded'),('react','Drive visual Reaction'),('monitor','Monitor locally only')]:
            value=tk.BooleanVar(value=r.get(key,False));menu.add_checkbutton(label=title,variable=value,command=lambda k=key,v=value:self.app.edit_sound_route(rid,{k:v.get(),'routing_custom':True}));menu._vars=getattr(menu,'_vars',[])+[value]
        menu.add_separator();menu.add_command(label='Use only this source',command=lambda:self.app.only_sound_source(rid));menu.add_command(label='Exclude, keep settings',command=lambda:self.app.edit_sound_route(rid,{'enabled':False}))
        menu.add_command(label='Precise contribution levels…',command=lambda:self.precise(rid))
        from contextual_surface import post_native_menu
        post_native_menu(self.app,menu,anchor)
    def precise(self,rid):
        r=ensure_route(self.app.project,rid);w=tk.Toplevel(self.app);w.title('Sound / Reaction / Monitor');w.transient(self.app);frame=ttk.Frame(w,padding=14);frame.pack(fill='both',expand=True);values={}
        ttk.Label(frame,text='Advanced per-purpose levels. The normal mixer fader is the recording mix control; use these only when deliberately separating Sound / React / Monitor.',wraplength=350).pack(pady=6)
        for purpose in ('sound','react','monitor'):
            row=ttk.Frame(frame);row.pack(fill='x',pady=4);ttk.Label(row,text=purpose.title(),width=15).pack(side='left');v=tk.StringVar(value=str(r.get(purpose+'_gain',r.get('gain',1))));values[purpose+'_gain']=v;ttk.Entry(row,textvariable=v,width=10).pack(side='left')
        error=tk.StringVar();ttk.Label(frame,textvariable=error,style='Muted.TLabel',wraplength=350).pack(fill='x',pady=4)
        def apply():
            try:self.app.edit_sound_route(rid,{**{k:float(v.get()) for k,v in values.items()},'routing_custom':True});w.destroy()
            except ValueError:error.set('Enter a level from 0 to 2 for each purpose. Your entries are kept.')
        ttk.Button(frame,text='Apply',command=apply).pack(side='right');ttk.Button(frame,text='Cancel',command=w.destroy).pack(side='left')

class SoundSourcesWindow(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.title('Sound · source faders');self.geometry('790x610');self.minsize(390,420);self.transient(app)
        self.mixer=FaderMixer(self,app,expanded=True);self.mixer.pack(fill='both',expand=True,padx=8,pady=6)
        buttons=ttk.Frame(self,padding=8);buttons.pack(side='bottom',fill='x');ttk.Button(buttons,text='Refresh devices / applications',command=self.mixer.discover).pack(side='left');ttk.Button(buttons,text='Stop all inputs',command=app.stop_inputs).pack(side='right')
        camera=ttk.Frame(self,padding=8);camera.pack(side='bottom',fill='x');ttk.Label(camera,text='Camera device').pack(side='left');v=tk.StringVar(value=getattr(app,'last_camera_device','/dev/video0'));ttk.Entry(camera,textvariable=v,width=20).pack(side='left',padx=4);ttk.Button(camera,text='Use Camera layer',command=lambda:app.toggle_camera_layer(v.get()) if hasattr(app,'toggle_camera_layer') else app.quick_camera('A',v.get())).pack(side='left')
        self.bind('<Escape>',lambda e:self.destroy());self.protocol('WM_DELETE_WINDOW',self.destroy)

class FaderMixer(SourceMixer):
    """An artist-facing bank of individually enabled sources, not a routing table.

    Reuses SourceMixer's authoritative routes, discovery, metering and controls.
    Resizing moves the same strips; it never recreates a source or changes gain.
    """
    def __init__(self,parent,app,expanded=False):
        ttk.Frame.__init__(self,parent,padding=8);self.app=app;self.all=tk.BooleanVar(value=False);self.key=None;self.rows={};self.sources=[];self.notes=[];self.scan=False;self.after_id=None
        from responsive_controls import FlowRow
        bar=FlowRow(self);bar.pack(fill='x',pady=(0,7))
        bar.add(ttk.Label(bar,text='SOUND · PLAY THE MIX',style='Title.TLabel'))
        bar.add(ttk.Button(bar,text='+ Microphone',command=app.quick_microphone))
        bar.add(ttk.Button(bar,text='+ Device / app',command=self.discover))
        bar.add(ttk.Checkbutton(bar,text='All available',variable=self.all,command=self.show_all))
        self.queue_label=tk.StringVar()  # Shared refresh uses it; no duplicate music queue here.
        self.scroll=ScrollFrame(self,app);self.scroll.pack(fill='both',expand=True)
        self.info=tk.StringVar(value='ON = Programme Sound + React + recording at this fader level. Inputs start OFF. Advanced Routing can make a source React-only; Monitor is local only.')
        note=ttk.Label(self,textvariable=self.info,wraplength=670,justify='left',style='Muted.TLabel');note.pack(fill='x',pady=(7,1))
        self.bind('<Configure>',lambda e:note.configure(wraplength=max(220,e.width-20)),add='+')
        self.refresh(True);self.after_id=self.after(120,self.tick);self.bind('<Destroy>',self.destroyed,add='+')
    def make_row(self,rid,r,source=None):
        from responsive_controls import AdaptiveGrid
        if not self.rows:
            self.fader_grid=AdaptiveGrid(self.scroll.body,minimum=164,maximum=212,max_columns=6,gap=10);self.fader_grid.pack(fill='x')
        body=ttk.Frame(self.fader_grid,padding=(8,8),relief='ridge',borderwidth=2);self.fader_grid.add(body)
        label=r.get('label',rid)
        if rid=='soundtrack':label='Music Queue'
        ttk.Label(body,text=label,style='Title.TLabel',wraplength=165,justify='center',anchor='center').pack(fill='x',pady=(0,7))
        enabled=tk.BooleanVar(value=False);muted=tk.BooleanVar(value=r.get('muted',False))
        line=ttk.Frame(body);line.pack(fill='x')
        def toggle_enabled():
            device=source['device'] if source else self.app.project.extra.get('sound_routes',{}).get(rid,{}).get('device')
            self.app.set_sound_source_enabled(rid,enabled.get(),device=device,label=(source or r).get('label',rid))
        enable=ttk.Checkbutton(line,text='ON',variable=enabled,command=toggle_enabled);enable.pack(side='left');self.app.add_tip(enable,'ON is the complete default route: audible Programme Sound + visual React + recorded output. Advanced Routing exposes deliberate exceptions.')
        ttk.Checkbutton(line,text='Mute',variable=muted,command=lambda:self.app.edit_sound_route(rid,{'muted':muted.get()})).pack(side='right')
        level=tk.DoubleVar(value=r.get('gain',1));numeric=tk.StringVar(value=f'{level.get():.2f}')
        row={'active':False,'level':level,'numeric':numeric,'muted':muted,'enabled':enabled,'enable_button':enable}
        def begin(event=None):row['active']=True;self.app.begin_gesture('Source level')
        def end(event=None):
            if row['active']:self.app.edit_sound_route(rid,{'gain':level.get()},gesture=True);row['active']=False;self.app.end_gesture()
        def change(value):
            if row['active']:numeric.set(f'{float(value):.2f}');self.app.edit_sound_route(rid,{'gain':float(value)},gesture=True)
        centre=ttk.Frame(body);centre.pack(fill='x',pady=5)
        fader=tk.Scale(centre,variable=level,from_=2,to=0,resolution=.01,showvalue=False,orient='vertical',length=142,width=21,sliderlength=29,command=change,**tk_scale_theme_options(self.app.ui_chrome));fader.pack(side='left',expand=True)
        meter=ttk.Progressbar(centre,orient='vertical',maximum=1,length=135);meter.pack(side='right',padx=(0,15));row.update(meter=meter,fader=fader)
        fader.bind('<ButtonPress-1>',begin);fader.bind('<ButtonRelease-1>',end);fader.bind('<KeyPress>',begin,add='+');fader.bind('<KeyRelease>',end,add='+')
        for event in ('<MouseWheel>','<Button-4>','<Button-5>'):fader.bind(event,lambda e:'break')
        number=ttk.Frame(body);number.pack(pady=(0,7));ttk.Label(number,text='Level ×').pack(side='left');entry=ttk.Entry(number,textvariable=numeric,width=6);entry.pack(side='left',padx=4);row['entry']=entry
        def enter(event=None):
            try:self.app.edit_sound_route(rid,{'gain':float(numeric.get())})
            except ValueError:self.info.set('Enter a level between 0 and 2×.')
            return 'break'
        entry.bind('<Return>',enter)
        route=ttk.Button(body,text='',command=lambda:self.route_menu(rid,body));route.pack(fill='x');row['route']=route
        if rid not in BUILTINS:
            state=tk.StringVar();ttk.Label(body,textvariable=state,wraplength=165,style='Muted.TLabel').pack(fill='x');row['state']=state
        else:ttk.Label(body,text='From the current sequence',style='Muted.TLabel',wraplength=160).pack(pady=(6,0))
        self.rows[rid]=row
    def tick(self):
        if self.app.closing:return
        try:self.refresh()
        except Exception as exc:self.app.log('Sound faders: '+str(exc))
        finally:
            if not self.app.closing and self.winfo_exists():self.after_id=self.after(150,self.tick)


class DeskFaderMixer(SourceMixer):
    """Performance faders for the Audio tray, sharing SourceMixer's routes.

    Each named input owns a stable vertical strip. Only routing exceptions use
    the context menu; the ordinary ON, mute and fader remain on the surface.
    """
    def add_sources(self):
        self.app.sidebar.open_browser('Music','sources')
        self.app.sidebar.source_shelf.show('sources',role='Music')
        self.app.sidebar.signal('Music')
        return self.app.sidebar.source_shelf

    def __init__(self,parent,app,expanded=False):
        ttk.Frame.__init__(self,parent,padding=(3,3))
        self.app=app;self.all=tk.BooleanVar(value=False);self.key=None;self.rows={}
        self.sources=[];self.notes=[];self.scan=False;self.after_id=None
        controls=ttk.Frame(self);self.controls=controls;controls.pack(fill='x',pady=(0,3))
        ttk.Label(controls,text='SOUND MIX',style='Title.TLabel').pack(side='left')
        ttk.Button(controls,text='↻',width=3,command=self.discover).pack(side='right',padx=(2,0))
        ttk.Button(controls,text='＋',width=3,command=self.add_sources).pack(side='right')
        self.queue_label=tk.StringVar()
        self.empty_status=ttk.Label(self,text='No active sources · use ＋ to add one',
                                    style='Muted.TLabel',wraplength=282)
        self.scroll=ttk.Frame(self);self.scroll.pack(fill='both',expand=True)
        canvas=tk.Canvas(self.scroll,background='#11141f',height=209,highlightthickness=0,bd=0)
        canvas.pack(fill='both',expand=True)
        self.scroll.body=ttk.Frame(canvas)
        self._window=canvas.create_window((0,0),window=self.scroll.body,anchor='nw')
        def fit(event=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
        self.scroll.body.bind('<Configure>',fit,add='+')
        xbar=ttk.Scrollbar(self.scroll,orient='horizontal',command=canvas.xview)
        xbar.pack(fill='x');canvas.configure(xscrollcommand=xbar.set)
        self.info=tk.StringVar(value='MIC and programme sound are independent. ON: sound + react + record.')
        self.notice=ttk.Label(self,textvariable=self.info,style='Muted.TLabel',wraplength=290)
        self.notice.pack(fill='x',pady=(2,0))
        self.refresh(True)
        self.after_id=self.after(120,self.tick)
        self.bind('<Destroy>',self.destroyed,add='+')
    def order_sources(self,routes,states):
        from audio_bus import sound_events
        cache_key=(id(self.app.project),getattr(self.app,'revision',0))
        if cache_key!=getattr(self,'_queue_presence_key',None):
            try:self._queue_has_tracks=any(event.get('route_id')=='soundtrack' for event in sound_events(self.app.project))
            except (ValueError,KeyError,AttributeError):self._queue_has_tracks=False
            self._queue_presence_key=cache_key
        tracks=self._queue_has_tracks
        return active_source_order(self.app,routes,self.sources,states,tracks)
    def make_row(self,rid,r,source=None):
        short={'soundtrack':'QUEUE','voice:A':'A SOUND','voice:B':'B SOUND','voice:C':'C SOUND','voice:D':'D SOUND'}.get(rid)
        if not short:short=('MIC' if source and source.get('kind')=='microphone' else str(r.get('label',source.get('label',rid) if source else rid)).replace('App · ','').replace('PC audio · ',''))
        body=ttk.Frame(self.scroll.body,padding=(3,4),width=92,relief='groove',borderwidth=1)
        body.pack(side='left',fill='y',padx=2,pady=2);body.pack_propagate(False)
        body.configure(height=204)
        title=ttk.Label(body,text=short[:13],style='Title.TLabel',anchor='center')
        title.pack(fill='x',pady=(0,3))
        self.app.add_tip(title,'Audio source: '+str((source or r).get('label',rid)))
        controls=ttk.Frame(body);controls.pack(fill='x')
        enabled=tk.BooleanVar(value=False);muted=tk.BooleanVar(value=r.get('muted',False))
        def toggle():
            device=source['device'] if source else self.app.project.extra.get('sound_routes',{}).get(rid,{}).get('device')
            self.app.set_sound_source_enabled(rid,enabled.get(),device=device,label=(source or r).get('label',rid))
        ttk.Checkbutton(controls,text='ON',variable=enabled,command=toggle).pack(side='left')
        ttk.Checkbutton(controls,text='M',variable=muted,command=lambda:self.app.edit_sound_route(rid,{'muted':muted.get()})).pack(side='right')
        level=tk.DoubleVar(value=r.get('gain',1));numeric=tk.StringVar(value=f'{level.get():.2f}')
        row={'active':False,'level':level,'numeric':numeric,'muted':muted,'enabled':enabled,'compact':True}
        centre=ttk.Frame(body);centre.pack(fill='both',expand=True,pady=(3,1))
        def begin(event=None):row['active']=True;self.app.begin_gesture('Source level')
        def end(event=None):
            if row['active']:
                self.app.edit_sound_route(rid,{'gain':level.get()},gesture=True)
                row['active']=False;self.app.end_gesture()
        def change(value):
            if row['active']:
                numeric.set(f'{float(value):.2f}')
                self.app.edit_sound_route(rid,{'gain':float(value)},gesture=True)
        fader=tk.Scale(centre,variable=level,from_=2,to=0,resolution=.01,showvalue=False,
                       orient='vertical',length=96,width=15,sliderlength=23,
                       command=change,**tk_scale_theme_options(self.app.ui_chrome))
        fader.pack(side='left',expand=True,padx=(4,0));row['fader']=fader
        meter=ttk.Progressbar(centre,orient='vertical',maximum=1,length=95)
        meter.pack(side='right',padx=(0,7));row['meter']=meter
        fader.bind('<ButtonPress-1>',begin);fader.bind('<ButtonRelease-1>',end)
        fader.bind('<KeyPress>',begin,add='+');fader.bind('<KeyRelease>',end,add='+')
        for ev in ('<MouseWheel>','<Button-4>','<Button-5>'):fader.bind(ev,lambda e:'break')
        footer=ttk.Frame(body);footer.pack(fill='x')
        entry=ttk.Entry(footer,textvariable=numeric,width=4,justify='center');entry.pack(side='left',fill='x',expand=True)
        row['entry']=entry
        def submit(event=None):
            try:self.app.edit_sound_route(rid,{'gain':float(numeric.get())})
            except ValueError:self.info.set('Gain must be between 0 and 2×')
            return 'break'
        entry.bind('<Return>',submit)
        route=ttk.Button(footer,text='⋯',width=2,command=lambda:self.route_menu(rid,body))
        route.pack(side='right');row['route']=route
        self.app.add_tip(route,'Sound / React / Monitor routing for this input.')
        if rid not in BUILTINS:
            row['state']=tk.StringVar(value='')
        self.rows[rid]=row
