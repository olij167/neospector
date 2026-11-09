"""Explicit camera, microphone, device-monitor and application-stream selection."""
from __future__ import annotations
import queue,threading,time,sys
import tkinter as tk
from tkinter import ttk,messagebox
from live_sources import enumerate_devices
from system_audio import discover_audio_sources,validate_application
from sequencer_model import add_asset

class InstrumentLivePanel(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.closed=False;self.discovering=False;self.busy=False;self.events=queue.Queue();self.poll_job=None;self.stop_job=None;self.sources={};self.title('Live inputs · camera / microphone / device audio');self.geometry('810x680');self.minsize(710,570);self.transient(app)
        b=ttk.Frame(self,padding=14);b.pack(fill='both',expand=True);ttk.Label(b,text='Local sources. One instrument.',style='Title.TLabel').pack(anchor='w')
        ttk.Label(b,text='Choose and start sources explicitly. Closing this panel keeps them running.\nNo drivers are installed and no application audio is rerouted.',style='Muted.TLabel',justify='left').pack(anchor='w',pady=8)
        self.cam_var=tk.StringVar(value='test' if app.test_mode else '/dev/video0' if sys.platform.startswith('linux') else '0');self.audio_var=tk.StringVar(value='test' if app.test_mode else 'default');self.states={}
        for kind,title,var in [('camera','CAMERA',self.cam_var),('microphone','AUDIO INPUT · mic / device / app',self.audio_var)]:
            f=ttk.LabelFrame(b,text=title,padding=10);f.pack(fill='x',pady=5);row=ttk.Frame(f);row.pack(fill='x');box=ttk.Combobox(row,textvariable=var,width=48);box.pack(side='left',fill='x',expand=True)
            if kind=='camera':self.cam_box=box
            else:self.audio_box=box
            ttk.Button(row,text='Start',width=7,command=lambda k=kind:self.start(k)).pack(side='left',padx=5);ttk.Button(row,text='Stop',width=7,command=lambda k=kind:self.stop(k)).pack(side='left')
            v=tk.StringVar(value='Stopped');self.states[kind]=v;ttk.Label(f,textvariable=v,style='Muted.TLabel',wraplength=700,justify='left').pack(anchor='w',pady=4)
            if kind=='camera':
                row=ttk.Frame(f);row.pack(fill='x',pady=(2,0))
                for text,role in [('Camera → A','A'),('Camera → B','B'),('Camera → C','C'),('Camera → D','D')]:ttk.Button(row,text=text,command=lambda r=role:self.assign_camera(r)).pack(side='left',padx=(0,5))
                ttk.Label(f,text='640 × 360 / 20 fps raw capture. The same racks process files and cameras.',style='Muted.TLabel').pack(anchor='w',pady=5)
            else:
                self.meter=ttk.Progressbar(f,maximum=1);self.meter.pack(fill='x',pady=5);ttk.Label(f,text='Parameter ≈ → Source: microphone uses this selected live input, including device/app audio.\nLive monitoring stays off to avoid speaker feedback.',style='Muted.TLabel',justify='left').pack(anchor='w')
        ttk.Button(b,text='Refresh devices and playing applications',command=self.refresh).pack(anchor='w',pady=5)
        self.notes=tk.StringVar(value='Discovering capture sources…');ttk.Label(b,textvariable=self.notes,wraplength=730,justify='left',style='Muted.TLabel').pack(fill='x',pady=5)
        capture=ttk.LabelFrame(b,text='Retain the performance',padding=10);capture.pack(fill='x',pady=7)
        ttk.Checkbutton(capture,text='Retain live inputs for Capture Recent (local segmented recordings)',variable=app.retain_armed,command=app.toggle_retention).pack(anchor='w')
        ttk.Checkbutton(capture,text='Record live knob and viewport gestures as editable automation',variable=app.record_automation).pack(anchor='w')
        ttk.Label(capture,text='Up to ten minutes of unpinned input history; captured takes receive durable copies.\nA device monitor can already contain the file soundtrack: avoid adding that mix twice.',style='Muted.TLabel',wraplength=700,justify='left').pack(anchor='w',pady=6)
        foot=ttk.Frame(b);foot.pack(side='bottom',fill='x',pady=6);ttk.Button(foot,text='Stop all inputs',command=self.stop_all).pack(side='left');ttk.Button(foot,text='Close panel · keep playing',command=self.destroy).pack(side='right')
        self.refresh();self.poll()
    def refresh(self):
        if self.discovering:return
        self.discovering=True
        def work():
            try:
                raw=enumerate_devices();devices,notes=discover_audio_sources();self.events.put(('devices',raw,devices,notes))
            except Exception as exc:self.events.put(('error',str(exc)))
            finally:self.discovering=False
        threading.Thread(target=work,name='Audio source discovery',daemon=True).start()
    def start(self,kind):
        if self.busy:return
        if self.app.live.recording:return self.app.update_status('Disarm retention and let its current segment finish before changing the input.')
        raw=self.cam_var.get() if kind=='camera' else self.audio_var.get();device=self.sources.get(raw,raw);self.busy=True
        def work():
            try:
                if isinstance(device,dict):validate_application(device)
                if kind=='camera':self.app.live.start_camera(device)
                else:self.app.live.start_microphone(device)
                self.events.put(('message','Input opened; waiting for samples'))
            except Exception as exc:self.events.put(('error',str(exc)))
            finally:self.busy=False
        threading.Thread(target=work,name='Open input',daemon=True).start()
    def stop(self,kind):
        if self.busy:return
        if self.app.live.recording:return self.app.update_status('Disarm retention before stopping an input; current recordings will be preserved.')
        self.busy=True
        def work():
            try:
                if kind=='camera':self.app.live.stop_camera()
                else:self.app.live.stop_microphone()
            except Exception as exc:self.events.put(('error',str(exc)))
            finally:self.busy=False
        threading.Thread(target=work,name='Stop input',daemon=True).start()
    def stop_all(self):
        if self.app.live.recording:self.app.retain_armed.set(False);self.app.toggle_retention();self.app.update_status('Finishing input history. Stop all again after the segment is saved.');return
        self.stop('camera')
        def then():
            if self.closed:return
            if self.busy:self.stop_job=self.after(100,then)
            else:self.stop('microphone')
        self.stop_job=self.after(100,then)
    def assign_camera(self,role):
        def add():
            a=next((a for a in self.app.project.assets.values() if a.kind=='camera'),None)
            if a is None:a=add_asset(self.app.project,path='',kind='camera',name='Live camera',width=640,height=360)
            self.app.selected_asset_id=a.id
        self.app.transaction('Camera source available',add);self.app.assign_selected(role)
    def poll(self):
        if self.closed:return
        for _ in range(8):
            try:e=self.events.get_nowait()
            except queue.Empty:break
            if e[0]=='devices':
                _,raw,devices,notes=e;self.cam_box.configure(values=raw['camera']);self.sources={d['label']:d for d in devices};self.audio_box.configure(values=[*raw['microphone'],*self.sources]);self.notes.set('\n'.join(notes) or 'Device and app audio available. An application must be playing to appear. “test” is a synthetic source.');self.app.log('Audio discovery: '+str(notes))
            elif e[0]=='error':self.notes.set(e[1]);self.app.log('Input: '+e[1])
            elif e[0]=='message':self.notes.set(e[1])
        for kind,info in self.app.live.state().items():
            device=info['device'];label=device.get('label','Device audio') if isinstance(device,dict) else str(device)
            self.states[kind].set(info['state'].title()+(' · '+label if label else '')+(' · '+info['error'][:250] if info['error'] else ''))
        self.meter['value']=self.app.live.signal()[0].get('full',0)
        self.poll_job=self.after(150,self.poll)
    def destroy(self):
        self.closed=True
        for job in (self.poll_job,self.stop_job):
            if job:
                try:self.after_cancel(job)
                except tk.TclError:pass
        super().destroy()
