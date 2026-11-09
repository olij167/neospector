"""Explicit, two-phase Queue/Camera assignments. Hardware stays out of undo."""
import copy,threading,time
import tkinter as tk
from tkinter import ttk
from instrument_model import voice
from queue_model import mode_at,switch_source
from sequencer_model import add_asset
from visual_channels import strongest_channel,channels
from responsive_controls import PriorityToolbar

class ChannelCameraActions:
    def open_visual_source(self,role=None):
        from visual_source_ui import show
        if role is None:
            try:role=strongest_channel(self.project,self.playhead,self.signal_evaluator())
            except ValueError as exc:return self.update_status(str(exc))
        return show(self,role)
    def stop_visual_sharing(self):
        from visual_channels import channels
        now=self.programme_time() if self.playing else self.playhead
        selected=[]
        for layer in channels(self.project):
            state=mode_at(layer,now)
            asset=self.project.asset(state.get('camera_id','')) if state['mode']=='camera' else None
            if asset and asset.kind in ('screen','window'):selected.append(layer)
        if not selected:return self.update_status('No Screen or Window is sharing.')
        if self.live.recording:self.live.stop_recording()
        def stop():
            for layer in selected:switch_source(layer,'queue',now)
        self.transaction('Stop visual sharing · queues retained',stop)
        self.release_unassigned_cameras();self.refresh_primary_toolbar()
        self.update_status('Sharing stopped · visual queues retained. Audio inputs keep their separate routing.')
    def camera_task(self,name,work):
        workers=getattr(self,'camera_workers',[])
        self.camera_workers=[t for t in workers if t.is_alive()]
        thread=threading.Thread(target=work,daemon=True,name=name)
        self.camera_workers.append(thread);thread.start()
    def stop_camera_tasks(self):
        self._camera_closing=True
        getattr(self,'camera_tickets',{}).clear()
        for thread in getattr(self,'camera_workers',[]):thread.join(timeout=9)
        self.camera_workers=[]
    def open_channel_camera(self,role):
        windows=getattr(self,'channel_camera_windows',{});self.channel_camera_windows=windows
        old=windows.get(role)
        if old and old.winfo_exists():old.deiconify();old.lift();return old
        layer=voice(self.project,role);pid=self.project.id
        w=tk.Toplevel(self);windows[role]=w;w.title('Channel '+role+' · Camera');w.transient(self);w.geometry('480x255');w.minsize(420,230)
        box=ttk.Frame(w,padding=12);box.pack(fill='both',expand=True)
        ttk.Label(box,text='Camera · channel '+role,style='Title.TLabel').pack(anchor='w')
        ttk.Label(box,text='Choose a device for this channel. Opening these settings does not start capture.',style='Muted.TLabel',wraplength=430).pack(anchor='w',pady=6)
        stored=layer.extra.get('camera_device',self.last_camera_device)
        device=tk.StringVar(value=stored if isinstance(stored,str) else self.last_camera_device)
        combo=ttk.Combobox(box,textvariable=device,values=[device.get(),'test']);combo.pack(fill='x')
        status=tk.StringVar(value='Refresh lists available devices; it does not start them.')
        ttk.Label(box,textvariable=status,style='Muted.TLabel',wraplength=410).pack(fill='x',pady=4)
        row=PriorityToolbar(box,gap=4);row.pack(fill='x',pady=6)
        def discover():
            status.set('Finding camera devices…')
            def work():
                from live_sources import enumerate_devices
                try:
                    result=enumerate_devices()['camera']
                    def done():
                        if w.winfo_exists():combo.configure(values=result);status.set('Choose the camera to assign.')
                    self.events.put(('call',done))
                except Exception as exc:self.events.put(('status','Device list: '+str(exc)))
            self.camera_task('List cameras',work)
        def apply(start=False):
            if self.project.id!=pid:w.destroy();return
            value=device.get().strip()
            if not value:return status.set('Choose a camera identifier.')
            if start or mode_at(layer,self.playhead)['mode']=='camera':self.toggle_channel_camera(role,value)
            else:self.transaction('Assign camera to '+role,lambda:layer.extra.__setitem__('camera_device',value))
            w.destroy()
        row.add_action('Screen / Window…',lambda:(w.destroy(),self.open_visual_source(role)),priority=30)
        row.add_action('Refresh',discover,priority=80)
        row.add_action('Assign device',apply,priority=20)
        row.add_action('Use camera',lambda:apply(True),priority=0,pinned=True,style='Accent.TButton')
        w.bind('<Escape>',lambda e:w.destroy());return w
    def camera_assignments_in_use(self):
        devices=[]
        # Source commits use the Programme clock. UI playhead can be one tick
        # behind: sampling it here would immediately close a newly ready camera.
        now=self.programme_time() if self.playing else self.playhead
        for layer in self.project.layers:
            state=mode_at(layer,now)
            if state['mode']=='camera':
                asset=self.project.asset(state.get('camera_id',''))
                if asset:devices.append(asset.metadata.get('device'))
            # Live queue occurrences on A/B use FrameSources just like the
            # dedicated Camera layer. Retain their ready capture until removal.
            for clip in layer.clips:
                asset=self.project.asset(clip.asset_id)
                if asset and asset.kind in ('camera','screen','window'):
                    devices.append(asset.metadata.get('device'))
        return [d for d in devices if d is not None]
    def toggle_channel_camera(self,role,device=None):
        if self.reviewing:return self.update_status('Return to Programme before assigning a physical camera; Draft review never opens a device.')
        layer=voice(self.project,role)
        if layer.locked:return self.update_status('Unlock channel '+role+' before changing its source.')
        tickets=getattr(self,'camera_tickets',{});self.camera_tickets=tickets
        if role in tickets:
            tickets.pop(role,None);return self.update_status('Camera preparation cancelled for '+role+'. Current source preserved.')
        now=self.programme_time() if self.playing else self.playhead
        # A queued camera is an active camera, not merely an upcoming file.
        # Pressing its top-bar toggle advances to the next queue occurrence;
        # no new capture and no destructive queue edit are involved.
        from ux25_source_state import active_queued_camera,advance_queued_camera
        if device is None and active_queued_camera(self.project,layer,now):
            self.transaction('Advance past queued camera · '+role,
                lambda:advance_queued_camera(layer,now))
            self.release_unassigned_cameras()
            if hasattr(self,'sidebar'):self.sidebar.signal(role)
            self.refresh_primary_toolbar()
            return
        if device is None and mode_at(layer,now)['mode']=='camera':
            self.transaction('Resume '+role+' queue',lambda:switch_source(layer,'queue',now))
            self.release_unassigned_cameras()
            if hasattr(self,'sidebar'):self.sidebar.signal(role)
            self.refresh_primary_toolbar()
            return
        device=copy.deepcopy(device if device is not None else layer.extra.get('camera_device',self.last_camera_device))
        pid=self.project.id;ticket=object();tickets[role]=ticket
        self.update_status('Preparing camera for '+role+' · current source stays on air')
        def ready(capture):
            if self.closing or getattr(self,'_camera_closing',False):return
            if self.project.id!=pid or tickets.get(role) is not ticket:
                self.release_unassigned_cameras();return
            tickets.pop(role,None)
            layer=voice(self.project,role)
            if layer.locked:return self.update_status('Camera ready; unlock '+role+' to assign it.')
            def commit():
                kind=device.get('kind','camera') if isinstance(device,dict) else 'camera'
                name=device.get('name',kind) if isinstance(device,dict) else str(device)
                asset=next((a for a in self.project.assets.values() if a.kind==kind and a.metadata.get('device')==device),None)
                if asset is None:asset=add_asset(self.project,path='live:'+kind,kind=kind,name=kind.title()+' · '+str(name),metadata={'device':device})
                switch_source(layer,'camera',self.programme_time() if self.playing else self.playhead,camera_id=asset.id)
                layer.extra['camera_device']=device
                if kind=='camera':self.last_camera_device=device
            self.transaction('Use camera on '+role+' · queue retained',commit)
            self.release_unassigned_cameras()
            if hasattr(self,'sidebar'):self.sidebar.signal(role)
            self.refresh_primary_toolbar()
            if not self.playing:self.play_assigned_media()
            self.update_status(('Camera' if not isinstance(device,dict) else device['kind'].title())+' on '+role+' · Queue resumes its saved position')
        def work():
            try:
                capture=self.live.acquire_camera(device);deadline=time.monotonic()+7
                while capture.state=='starting' and time.monotonic()<deadline and not self.closing and not getattr(self,'_camera_closing',False):time.sleep(.025)
                if capture.state!='live':raise RuntimeError(capture.error or 'No ready frames; check permissions and the selected device.')
                self.events.put(('call',lambda:ready(capture)))
            except Exception as exc:
                message=str(exc)
                def failed():
                    if tickets.get(role) is ticket:tickets.pop(role,None)
                    self.release_unassigned_cameras();self.update_status('Camera '+role+': '+message+' · previous source preserved')
                self.events.put(('call',failed))
        self.camera_task('Prepare camera '+role,work)
    def release_unassigned_cameras(self):
        if getattr(self,'camera_tickets',{}):return
        devices=self.camera_assignments_in_use();epoch=self.live.camera_epoch
        # Closing FFmpeg readers is not a Tk callback operation.
        self.camera_task('Release unused cameras',lambda:self.live.release_unused_cameras(devices,expected_epoch=epoch))
    def quick_camera(self,role='A',device=None):return self.toggle_channel_camera(role,device)
    def toggle_camera_layer(self,device=None):
        try:role=strongest_channel(self.project,self.playhead,self.signal_evaluator())
        except ValueError as exc:return self.update_status(str(exc))
        return self.toggle_channel_camera(role,device)
