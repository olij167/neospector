"""Always visible physical input switches; discovery never starts capture."""
import sys,threading
from tkinter import ttk
from sound_routes import source_id
from responsive_controls import FlowRow
class InputBar(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(8,4));self.app=app;self.pc_device=None
        self.video=video=FlowRow(self);video.pack(fill='x')
        video.add(ttk.Label(video,text='VIDEO',width=8))
        for label,callback,name in [('+ Files',app.add_media,'files'),('● Camera',lambda:app.toggle_channel_camera(app.active_visual_role()),'camera'),('▣ Screen / App',lambda:app.open_visual_source(app.active_visual_role()),'screen')]:
            b=ttk.Button(video,text=label,command=callback);video.add(b);setattr(self,name,b)
        self.audio=audio=FlowRow(self);audio.pack(fill='x',pady=(3,0));audio.add(ttk.Label(audio,text='REACT IN',width=8))
        for label,callback,name in [('+ Audio',app.add_audio_files,'music'),('● Mic',self.toggle_mic,'microphone'),('PC audio',lambda:self.discover(False),'pc'),('App…',lambda:self.discover(True),'application'),('⚙ Route',app.open_live,'settings')]:
            b=ttk.Button(audio,text=label,command=callback,width=7);audio.add(b);setattr(self,name,b)
        self.meter=ttk.Progressbar(audio,maximum=1,length=42);audio.add(self.meter)
    def toggle_device(self,device,label):
        sid=source_id(device)
        if self.app.live.source_states().get(sid,{}).get('state') in ('starting','live'):self.app.stop_sound_source(sid)
        else:self.app.start_sound_source(device,label,react_only=True)
    def toggle_mic(self):self.toggle_device(getattr(self.app,'last_microphone_device','default' if sys.platform.startswith('linux') else '0'),'Microphone')
    def discover(self,application):
        if not application and self.pc_device:
            return self.toggle_device(self.pc_device,'PC audio')
        from system_audio import discover_audio_sources
        from tkinter import Toplevel
        app=self.app;pid=app.project.id;app.update_status('Finding audio inputs…')
        def work():
            try:choices,notes=discover_audio_sources()
            except Exception as exc:choices,notes=[],[str(exc)]
            def ready():
                if app.closing or app.project.id!=pid:return
                options=[c for c in choices if c.get('kind')==('application' if application else 'system')]
                if not options:return app.update_status(' · '.join(notes) or 'No playing application found')
                if not application and len(options)==1:
                    self.pc_device=options[0];return self.toggle_device(options[0],'PC audio')
                win=Toplevel(app);win.title('Choose audio input');win.transient(app)
                for choice in options:
                    def select(c=choice):
                        if app.project.id==pid:
                            if not application:self.pc_device=c
                            self.toggle_device(c,c['label'])
                        win.destroy()
                    ttk.Button(win,text=choice['label'],command=select).pack(fill='x',padx=12,pady=6)
            app.events.put(('call',ready))
        threading.Thread(target=work,daemon=True).start()
    def refresh(self):
        app=self.app;role=app.active_visual_role()
        from live_parameter_controls import source_status
        try:self.meter['value']=source_status(app,'reaction_mix')[1]
        except (AttributeError,ValueError):self.meter['value']=0
        from instrument_model import voice
        from queue_model import mode_at
        layer=voice(app.project,role);on=bool(layer and mode_at(layer,app.playhead).get('mode')=='camera')
        pending=role in getattr(app,'camera_tickets',{})
        self.camera.configure(text=('◌ Camera…' if pending else '● Camera ON' if on else '● Camera')+' · '+role)
        device=getattr(app,'last_microphone_device','default' if sys.platform.startswith('linux') else '0')
        live=app.live.source_states()
        self.microphone.configure(text='Mic ON' if live.get(source_id(device),{}).get('state') in ('starting','live') else 'Mic')
        self.pc.configure(text='PC ON' if self.pc_device and live.get(source_id(self.pc_device),{}).get('state') in ('starting','live') else 'PC audio')
