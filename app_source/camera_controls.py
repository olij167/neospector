"""A ready camera owns an optional layer; starting never rewrites A/B queues."""
from __future__ import annotations
import threading,time,copy
import tkinter as tk
from tkinter import ttk
from instrument_model import attach_camera_layer,set_camera_placement,camera_placement_at,voice
from sequencer_model import add_asset
from queue_model import mode_at
from responsive_controls import FlowRow
from ui_chrome import tk_scale_theme_options

PLACEMENTS={'Above all':'above','Between A & B':'between','Below all':'below'}

class CameraActions:
    def build_camera_strip(self,parent):
        self.camera_panel=FlowRow(parent,gap=5);self.camera_opacity=tk.DoubleVar(value=1.);self.camera_place=tk.StringVar(value='Above all');self.camera_visible=tk.BooleanVar(value=True);self._camera_slider_active=False
        title=ttk.Checkbutton(self.camera_panel,text='📷 Camera layer',variable=self.camera_visible,command=self.set_camera_visible)
        self.camera_panel.add(title)
        choices=ttk.Combobox(self.camera_panel,textvariable=self.camera_place,values=list(PLACEMENTS),width=15,state='readonly');choices.bind('<<ComboboxSelected>>',lambda e:self.set_camera_position(PLACEMENTS[self.camera_place.get()]));self.camera_panel.add(choices)
        self.add_tip(choices,'Above all: a foreground. Between A & B: over A before the A/B blend. Below all: visible through transparent or faded picture channels.')
        amount=ttk.Frame(self.camera_panel);ttk.Label(amount,text='Opacity').pack(side='left')
        scale=tk.Scale(amount,from_=0,to=1,resolution=.01,showvalue=False,orient='horizontal',variable=self.camera_opacity,length=115,command=self.camera_amount_changed,**tk_scale_theme_options(self.ui_chrome));scale.pack(side='left');self.camera_panel.add(amount)
        scale.bind('<ButtonPress-1>',self.begin_camera_amount);scale.bind('<ButtonRelease-1>',self.end_camera_amount);scale.bind('<KeyPress>',self.begin_camera_amount);scale.bind('<KeyRelease>',self.end_camera_amount)
        for event in ('<MouseWheel>','<Button-4>','<Button-5>'):scale.bind(event,lambda e:'break')
        self.camera_panel.add(ttk.Button(self.camera_panel,text='📷 Camera FX',command=lambda:self.focus_voice('Camera')))
    def camera_layer(self):return next((l for l in self.project.layers if l.extra.get('voice')=='Camera'),None)
    def refresh_camera_strip(self):
        if not hasattr(self,'camera_panel'):return
        layer=self.camera_layer();state=self.live.camera.state if self.live.camera else 'stopped'
        if layer:
            if not self.camera_panel.winfo_manager():
                options={'before':self.viewport} if self.camera_panel.master is self.viewport.master else {}
                self.camera_panel.pack(fill='x',padx=4,pady=(0,2),**options)
            self.camera_visible.set(layer.enabled)
            position=camera_placement_at(layer,self.playhead);self.camera_place.set(next((k for k,v in PLACEMENTS.items() if v==position),'Above all'))
            if not self._camera_slider_active:self.camera_opacity.set(layer.opacity.value)
        elif self.camera_panel.winfo_manager():self.camera_panel.pack_forget()
        self.camera_button.configure(text='📷 Camera ●' if state=='live' else '📷 Camera …' if getattr(self,'camera_starting',False) else '📷 Camera')
    def set_camera_position(self,position):
        if self.camera_layer() is None:return self.update_status('Start Camera first; its own layer will appear here.')
        now=self.programme_time() if self.playing and not self.reviewing else self.playhead
        self.transaction('Move Camera layer',lambda:set_camera_placement(self.project,position,now));self.refresh_camera_strip()
    def set_camera_visible(self):
        layer=self.camera_layer()
        if layer is None:return
        if layer.locked:return self.update_status('Unlock the Camera layer before changing it.')
        value=self.camera_visible.get()
        self.transaction('Show Camera' if value else 'Hide Camera',lambda:setattr(layer,'enabled',value))
        self.refresh_camera_strip();self.update_status('Camera '+('visible' if value else 'hidden')+' · input remains available. Camera button stops the input when not recording.')
    def begin_camera_amount(self,event=None):
        l=self.camera_layer()
        if l and not l.locked:self._camera_slider_active=True;self.begin_gesture('Camera opacity')
    def camera_amount_changed(self,value):
        if not self._camera_slider_active:return
        l=self.camera_layer()
        if l:l.opacity.value=float(value);self.changed()
    def end_camera_amount(self,event=None):
        if self._camera_slider_active:self._camera_slider_active=False;self.end_gesture()
    def toggle_camera_layer(self,device=None):
        if self.reviewing:return self.update_status('Return to Programme before starting or stopping the physical camera.')
        layer=self.camera_layer()
        if layer and layer.locked:return self.update_status('Unlock the Camera layer before changing its input.')
        state=self.live.camera.state if self.live.camera else 'stopped'
        if device is None and layer and layer.enabled and state=='live':
            self.transaction('Turn Camera layer off',lambda:setattr(layer,'enabled',False))
            used=any(l is not layer and l.enabled and (mode_at(l,self.playhead)['mode']=='camera' or any(self.project.asset(c.asset_id) and self.project.asset(c.asset_id).kind=='camera' for c in l.clips)) for l in self.project.layers)
            if self.live.recording or used:
                self.update_status('Camera layer hidden. Input stays live for recording or another channel; Stop Inputs closes it.')
            else:
                threading.Thread(target=self.live.stop_camera,name='Stop separate camera',daemon=True).start()
                self.update_status('Camera off · A/B queues and effects unchanged.')
            self.refresh_camera_strip();return
        device=device if device is not None else self.last_camera_device;pid=self.project.id
        if getattr(self,'camera_starting',False):return self.update_status('Camera is preparing…')
        def ready():
            if self.closing:return
            if self.project.id!=pid:return self.update_status('Camera ready for the previous session. Stop Inputs to close it.')
            def assign():
                asset=next((a for a in self.project.assets.values() if a.kind=='camera' and a.metadata.get('device')==device),None)
                if asset is None:asset=add_asset(self.project,path='live:camera',kind='camera',name='Camera',metadata={'device':copy.deepcopy(device)})
                now=self.programme_time() if self.playing else self.playhead
                layer=attach_camera_layer(self.project,asset.id,now);self.last_camera_device=copy.deepcopy(device)
            self.transaction('Add independent Camera layer',assign)
            self.refresh_camera_strip()
            if not self.playing:self.toggle_play()
            self.update_status('Camera layer ready · choose Above, Between or Below. The A/B queues are unchanged.')
        if self.live.camera and self.live.camera.device==device and state=='live':ready();return
        self.camera_starting=True;self.update_status('Preparing Camera · the current picture keeps playing.')
        def work():
            try:
                self.live.start_camera(device);deadline=time.monotonic()+7
                while self.live.camera and self.live.camera.state=='starting' and time.monotonic()<deadline:time.sleep(.03)
                if not self.live.camera or self.live.camera.state!='live':raise RuntimeError(getattr(self.live.camera,'error','') or 'No camera frames received. Check the selected device and permission.')
                self.events.put(('call',ready))
            except Exception as exc:self.events.put(('status','Camera: '+str(exc)))
            finally:self.camera_starting=False
        threading.Thread(target=work,name='Prepare independent Camera',daemon=True).start()
