"""Explicit device controls and conversion of recorded performances into project media."""
from __future__ import annotations
import copy, threading, time
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from live_sources import enumerate_devices
from sequencer_model import add_asset,Clip,new_id
from media_engine import probe_media,_all_parameters
from editor_widgets import ScrollFrame


def add_take_to_project(project,take,*,replace_live=False,include_audio=False):
    """One caller-owned reversible transaction; raw take files remain on disk."""
    video=None;audio=None
    if take.get('video') and Path(take['video']).exists():
        info=probe_media(take['video']);video=add_asset(project,path=take['video'],kind='video',name=Path(take['video']).stem+' · camera take',duration=info['duration'],width=info['width'],height=info['height'],metadata={**info,'take':{k:v for k,v in take.items() if k!='analysis'}})
    if take.get('audio') and Path(take['audio']).exists():
        info=probe_media(take['audio']);audio=add_asset(project,path=take['audio'],kind='audio',name=Path(take['audio']).stem+' · microphone take',duration=info['duration'],metadata=info)
    if take.get('analysis'):
        # Freeze each take by identity. Recording another performance must never
        # replace the signal used by existing authored/locked effects.
        bank=project.extra.setdefault('recorded_analyses',{})
        if project.recorded_analysis:
            prior_id=new_id('take');bank[prior_id]=copy.deepcopy(project.recorded_analysis)
            for parameter in _all_parameters(project):
                if parameter.source in ('recorded','song_recorded') and not parameter.extra.get('recorded_take_id'):
                    parameter.extra['recorded_take_id']=prior_id
        take_id=new_id('take');bank[take_id]=copy.deepcopy(take['analysis'])
        project.recorded_analysis=copy.deepcopy(take['analysis'])
    project.extra.setdefault('takes',[]).append({k:v for k,v in take.items() if k!='analysis'})
    if audio:
        records=project.extra.setdefault('audio_takes',[])
        if not any(t.get('asset_id')==audio.id for t in records):records.append({'asset_id':audio.id,'start':take['start']+(take.get('audio_first') or 0),'gain':1.,'enabled':include_audio})
    if replace_live:
        start=float(take['start'])+(take.get('video_first') or 0);end=start+float(take['duration'])
        for layer in project.layers:
            if layer.locked:continue
            for c in layer.clips:
                asset=project.asset(c.asset_id)
                if asset and asset.kind=='camera' and video and not c.locked:
                    c.asset_id=video.id;c.in_point=max(0,c.start-start);c.source_policy='hold';c.manual=True
        for p in _all_parameters(project,editable_only=True):
            if p.mode=='react' and p.source in ('microphone','mix') and take.get('analysis'):
                p.source='recorded' if p.source=='microphone' else 'song_recorded';p.extra['recorded_take_id']=take_id
        project.duration=max(project.duration,end)
    return video,audio


class LivePanel(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.title('Live Inputs · local sources');self.transient(app);self.geometry('760x720');self.minsize(680,570);self.busy=False;self.poll_job=None
        shell=ttk.Frame(self,padding=10);shell.pack(fill='both',expand=True);shell.columnconfigure(0,weight=1);shell.rowconfigure(0,weight=1)
        scroller=ScrollFrame(shell,app);scroller.grid(row=0,column=0,sticky='nsew');body=scroller.body
        ttk.Label(body,text='Live sources, ordinary layers',style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,text='Devices start OFF. Turn an input ON to include it in Programme Sound, visual reaction and recording. Monitoring remains a separate advanced choice to avoid microphone feedback.',wraplength=700,justify='left',style='Muted.TLabel').pack(anchor='w',pady=8)
        self.devices={};self.device_vars={};self.states={};self.boxes={}
        for kind,title in [('camera','Camera · visual source'),('microphone','Microphone · control signal')]:
            frame=ttk.LabelFrame(body,text=title,padding=10);frame.pack(fill='x',pady=6)
            row=ttk.Frame(frame);row.pack(fill='x');var=tk.StringVar(value='test' if app.test_mode else '/dev/video0' if kind=='camera' and __import__('sys').platform.startswith('linux') else 'default' if kind=='microphone' and __import__('sys').platform.startswith('linux') else '0');self.device_vars[kind]=var
            box=ttk.Combobox(row,textvariable=var,values=['test'],width=37);box.pack(side='left',fill='x',expand=True);self.boxes[kind]=box
            ttk.Button(row,text='Start',command=lambda k=kind:self.start(k)).pack(side='left',padx=5);ttk.Button(row,text='Stop',command=lambda k=kind:self.stop(k)).pack(side='left')
            state=tk.StringVar(value='Stopped');self.states[kind]=state;ttk.Label(frame,textvariable=state,style='Muted.TLabel',wraplength=650,justify='left').pack(fill='x',pady=(6,0))
            if kind=='camera':
                ttk.Button(frame,text='Add camera to current layer / channel',command=self.add_camera).pack(anchor='w',pady=(8,0))
                ttk.Label(frame,text='Capture / raw takes: 640 × 360 at 20 fps. Effects and transforms use the same Programme compositor.',style='Muted.TLabel',wraplength=650).pack(anchor='w',pady=4)
            else:
                self.meter=ttk.Progressbar(frame,maximum=1);self.meter.pack(fill='x',pady=6);ttk.Label(frame,text='Route a parameter to React → Microphone (or Mix) to use this signal.',style='Muted.TLabel').pack(anchor='w')
        row=ttk.Frame(body);row.pack(fill='x',pady=4);ttk.Button(row,text='Refresh devices',command=self.refresh_devices).pack(side='left');ttk.Label(row,text='“test” = synthetic pattern / sine tone, not physical hardware',style='Muted.TLabel').pack(side='left',padx=12)
        take=ttk.LabelFrame(body,text='Record a reusable take',padding=10);take.pack(fill='x',pady=8)
        row=ttk.Frame(take);row.pack(fill='x');self.folder=tk.StringVar(value=str(app.cache/'takes'));ttk.Entry(row,textvariable=self.folder).pack(side='left',fill='x',expand=True);ttk.Button(row,text='Folder…',command=self.choose_folder).pack(side='right',padx=4)
        row=ttk.Frame(take);row.pack(fill='x',pady=7);self.record_button=ttk.Button(row,text='● Record take',command=self.record);self.record_button.pack(side='left');ttk.Button(row,text='Stop & add to Library',command=self.finish).pack(side='left',padx=6)
        self.replace=tk.BooleanVar(value=True);self.audio=tk.BooleanVar(value=False)
        ttk.Checkbutton(take,text='Replace unlocked live camera clips with this recording; use recorded mic envelopes',variable=self.replace).pack(anchor='w')
        ttk.Checkbutton(take,text='Include recorded microphone audio in exported soundtrack',variable=self.audio).pack(anchor='w')
        ttk.Checkbutton(take,text='Record knob / viewport movements as keyframes',variable=app.record_automation).pack(anchor='w')
        self.take_state=tk.StringVar(value='Raw takes are saved locally; no recording is uploaded.');ttk.Label(take,textvariable=self.take_state,style='Muted.TLabel',wraplength=650,justify='left').pack(anchor='w',pady=5)
        foot=ttk.Frame(shell);foot.grid(row=1,column=0,sticky='ew',pady=(8,0));ttk.Button(foot,text='Stop all inputs',command=self.stop_all).pack(side='left');ttk.Button(foot,text='Close panel (keep inputs running)',command=self.destroy).pack(side='right')
        self.refresh_devices();self.poll()
    def choose_folder(self):
        directory=filedialog.askdirectory(parent=self,title='Raw take folder')
        if directory:self.folder.set(directory)
    def refresh_devices(self):
        def run():
            data=enumerate_devices()
            def accept():
                if not self.winfo_exists():return
                self.devices=data
                for key,box in self.boxes.items():box.configure(values=data[key])
                self.app.log('Capture enumeration: '+str(data))
            self.app.events.put(('call',accept))
        threading.Thread(target=run,daemon=True).start()
    def start(self,kind):
        try:
            if self.app.live.recording:raise ValueError('Finish the current take before changing devices')
            device=self.device_vars[kind].get().strip()
            if not device:raise ValueError('Choose a device first')
            if kind=='camera':self.app.live.start_camera(device)
            else:self.app.live.start_microphone(device)
            self.app.log('Capture started by user: '+kind+' '+device)
        except Exception as exc:messagebox.showerror('Live input',str(exc),parent=self)
    def stop(self,kind):
        try:
            if kind=='camera':self.app.live.stop_camera()
            else:self.app.live.stop_microphone()
        except Exception as exc:messagebox.showerror('Live input',str(exc),parent=self)
    def add_camera(self):
        def do():
            a=next((a for a in self.app.project.assets.values() if a.kind=='camera'),None)
            if a is None:a=add_asset(self.app.project,path='',kind='camera',name='Live camera',width=640,height=360)
            layer=self.app.selected_layer()
            if layer.locked:raise ValueError('Unlock the current layer before adding a camera')
            c=Clip(new_id('clp'),a.id,self.app.selected_channel.get(),self.app.playhead,max(30,self.app.project.max_end()-self.app.playhead),manual=True)
            layer.clips.append(c);self.app.project.duration=max(self.app.project.duration,c.end);self.app.selected_clip_id=c.id;self.app.selected_asset_id=a.id
        self.app.transaction('Add camera source',do)
    def record(self):
        try:
            self.app.live.start_recording(Path(self.folder.get()).expanduser(),self.app.playhead);self.take_state.set('Recording raw media and mic envelopes. Stop to make an editable take.')
            if not self.app.playing:self.app.toggle_play()
        except Exception as exc:messagebox.showerror('Record take',str(exc),parent=self)
    def finish(self):
        if self.busy or not self.app.live.recording:return
        self.busy=True;self.app.pause();replace=self.replace.get();audio=self.audio.get();pid=self.app.project.id
        self.take_state.set('Finalising take and measured reaction envelopes…')
        def work():
            try:
                take=self.app.live.stop_recording()
                def accept():
                    self.busy=False
                    if pid==self.app.project.id:self.app.transaction('Use recorded take',lambda:add_take_to_project(self.app.project,take,replace_live=replace,include_audio=audio));self.app.timeline.zoom_fit()
                    if self.winfo_exists():self.take_state.set(f'Saved {take["duration"]:.2f}s · '+take['manifest']+(' · '+take['error'] if take['error'] else ''))
                    self.app.log('TAKE '+take['manifest'])
                self.app.events.put(('call',accept))
            except Exception as exc:
                msg=str(exc)
                def fail():
                    self.busy=False;self.app.log(msg)
                    if self.winfo_exists():messagebox.showerror('Take finalisation',msg,parent=self)
                self.app.events.put(('call',fail))
        threading.Thread(target=work,daemon=True).start()
    def stop_all(self):
        if self.app.live.recording:self.finish();return self.app.update_status('Finishing take first. Press Stop all inputs again after it is saved.')
        self.app.live.stop_all();self.app.update_status('Camera and microphone stopped')
    def poll(self):
        if not self.winfo_exists():return
        for key,info in self.app.live.state().items():self.states[key].set(info['state'].title()+(' · '+str(info['device']) if info['device'] else '')+(' · '+info['error'][:250] if info['error'] else ''))
        self.meter['value']=self.app.live.signal()[0].get('full',0.)
        self.record_button.configure(state='disabled' if self.app.live.recording or self.busy else 'normal')
        if self.app.live.recording:self.take_state.set(f'Recording · {time.monotonic()-self.app.live.recording["clock"]:.1f}s · raw media + signal envelopes')
        self.poll_job=self.after(150,self.poll)
    def destroy(self):
        if getattr(self,'poll_job',None):
            try:self.after_cancel(self.poll_job)
            except tk.TclError:pass
            self.poll_job=None
        super().destroy()
