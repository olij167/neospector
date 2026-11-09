"""The Programme monitor is never replaced by a selected raw source clip."""
from __future__ import annotations
import threading, time, traceback
import tkinter as tk
from tkinter import ttk
from PIL import Image,ImageTk
from programme_renderer import ProgrammeRenderer


class ProgrammeWorker:
    def __init__(self,events,live):
        self.events=events;self.condition=threading.Condition();self.pending=None;self.stopping=False;self.live=live
        self.thread=threading.Thread(target=self.run,name='Programme compositor',daemon=True);self.thread.start()
    def submit(self,revision,project,t,size,bypass=False,stamp=None):
        with self.condition:self.pending=(revision,project,t,size,bypass,stamp);self.condition.notify()
    def run(self):
        renderer=ProgrammeRenderer(live_camera=self.live.camera_frame,live_microphone=self.live.signal,missing_policy='transparent')
        try:
            while True:
                with self.condition:
                    while self.pending is None and not self.stopping:self.condition.wait()
                    if self.stopping:return
                    revision,project,t,size,bypass,stamp=self.pending;self.pending=None
                before=time.monotonic()
                try:
                    image=renderer.render(project,t,size,bypass_effects=bypass)
                    image.info['omne_monitor_bypass']=bool(bypass)
                    image.info['missing_media']=dict(renderer.missing)
                    if stamp is not None:image.info['neoscope_stamp']=stamp
                    self.events.put(('programme',revision,t,image,time.monotonic()-before))
                except Exception as exc:
                    self.events.put(('programme_error',revision,t,str(exc),traceback.format_exc()))
        finally:renderer.close()
    def close(self):
        with self.condition:self.stopping=True;self.pending=None;self.condition.notify_all()
        self.thread.join(timeout=2)


class ProgrammeView(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=4);self.app=app;self.photo=None;self.image=None;self.display_time=0.;self.rect=(0,0,1,1);self.drag=None;self.resize_id=None;self.wheel_id=None
        top=ttk.Frame(self);top.pack(fill='x');ttk.Label(top,text='PROGRAMME',style='Title.TLabel').pack(side='left')
        self.quality=tk.StringVar(value='640');box=ttk.Combobox(top,textvariable=self.quality,values=['360','640','960','Full'],width=5,state='readonly');box.pack(side='right');box.bind('<<ComboboxSelected>>',lambda e:self.request())
        self.bypass=tk.BooleanVar(value=False);ttk.Checkbutton(top,text='Preview FX off',variable=self.bypass,command=self.request).pack(side='right',padx=5)
        self.canvas=tk.Canvas(self,highlightthickness=0,bg=app.ui_chrome['preview_bg']);self.canvas.pack(fill='both',expand=True,pady=(5,3))
        self.info=tk.StringVar(value='The complete composition · selection only chooses editing controls')
        ttk.Label(self,textvariable=self.info,style='Muted.TLabel',wraplength=620).pack(fill='x')
        self.canvas.bind('<Configure>',self.resize);self.canvas.bind('<ButtonPress-1>',self.press);self.canvas.bind('<B1-Motion>',self.motion);self.canvas.bind('<ButtonRelease-1>',self.release)
        self.canvas.bind('<MouseWheel>',self.wheel);self.canvas.bind('<Button-4>',lambda e:self.wheel(e,1));self.canvas.bind('<Button-5>',lambda e:self.wheel(e,-1))
        self.canvas.bind('<Escape>',lambda e:self.app.cancel_gesture())
        self.result_epoch=0;self.result_stamp=None
        self.worker=ProgrammeWorker(app.events,app.live)
    def set_theme(self):self.canvas.configure(bg=self.app.ui_chrome['preview_bg']);self.paint()
    def size(self):
        p=self.app.project;limit=p.width if self.quality.get()=='Full' else int(self.quality.get());ratio=min(1,limit/p.width);return max(16,round(p.width*ratio/2)*2),max(16,round(p.height*ratio/2)*2)
    def invalidate(self):
        """A seek/new context invalidates images; a knob change must not starve presentation."""
        self.result_epoch+=1;self.result_stamp=None
    def request(self):
        self.result_stamp=(self.app.project.id,id(self.app.project),self.result_epoch,
                           bool(getattr(self.app,'reviewing',False)),self.size(),self.bypass.get())
        self.worker.submit(self.app.revision,self.app.snapshot(),self.app.playhead,self.size(),self.bypass.get(),self.result_stamp)
    def accepts_result(self,revision,t,image):
        stamp=image.info.get('neoscope_stamp')
        if stamp is None:return revision==self.app.revision
        return stamp==self.result_stamp and stamp[0]==self.app.project.id and stamp[1]==id(self.app.project)

    def resize(self,event=None):
        if self.resize_id:
            try:self.after_cancel(self.resize_id)
            except tk.TclError:pass
        self.resize_id=self.after(100,self.paint)
    def accept(self,t,image,elapsed):
        self.image=image;self.display_time=t;self.paint();self.info.set(f'Frame {self.app.format_time(t)} · {image.width} × {image.height} · {elapsed*1000:.0f} ms'+(' · FX bypassed (monitor only)' if self.bypass.get() else ''))
    def fail(self,message):
        self.canvas.delete('error');self.info.set('Programme error · '+message[:180]);self.canvas.create_text(12,14,text=message[:420],width=max(200,self.canvas.winfo_width()-24),fill=self.app.ui_chrome['failure_fg'],anchor='nw',tags='error')
    def paint(self):
        self.resize_id=None
        if not self.canvas.winfo_exists():return
        from queue_model import mode_at
        for tag in ('selection','error','recording','empty'):self.canvas.delete(tag)
        w=max(1,self.canvas.winfo_width());h=max(1,self.canvas.winfo_height())
        has_source=any(l.clips or mode_at(l,self.app.playhead)['mode']=='camera' for l in self.app.project.layers)
        if self.image is None or not has_source:
            if getattr(self,'picture_item',None):self.canvas.itemconfigure(self.picture_item,state='hidden')
            if not hasattr(self.app,'empty_preview'):
                self.canvas.create_text(w/2,h/2,text='Import media or start a camera.',fill=self.app.ui_chrome['muted_fg'],justify='center',width=max(120,w-40),tags='empty')
            return
        ratio=min(w/self.image.width,h/self.image.height);sz=(max(1,round(self.image.width*ratio)),max(1,round(self.image.height*ratio)));x=(w-sz[0])/2;y=(h-sz[1])/2;self.rect=(x,y,sz[0],sz[1])
        rendered=self.image.resize(sz,Image.Resampling.BILINEAR)
        if self.photo is not None and (self.photo.width(),self.photo.height())==sz:self.photo.paste(rendered)
        else:self.photo=ImageTk.PhotoImage(rendered)
        if not getattr(self,'picture_item',None):self.picture_item=self.canvas.create_image(x,y,image=self.photo,anchor='nw',tags='picture')
        else:self.canvas.coords(self.picture_item,x,y);self.canvas.itemconfigure(self.picture_item,image=self.photo,state='normal')
        self.canvas.tag_lower(self.picture_item)
        l,clip=self.app.get_edit_target()
        if clip and self.app.deck.scope.get()=='Clip':
            from queue_model import queue_position
            qt=queue_position(l,self.app.playhead) if l else self.app.playhead
            if clip.start<=qt<clip.end:
                c=self.app.ui_chrome;v=self.app.signal_evaluator();scale=v.value(clip.scale,qt,self.app.playhead);cx=x+sz[0]/2+v.value(clip.x,qt,self.app.playhead)*sz[0]/2;cy=y+sz[1]/2+v.value(clip.y,qt,self.app.playhead)*sz[1]/2
                self.canvas.create_rectangle(cx-sz[0]*scale/2,cy-sz[1]*scale/2,cx+sz[0]*scale/2,cy+sz[1]*scale/2,outline=c['accent'],dash=(3,3),tags='selection')
        if self.app.live.recording:self.canvas.create_text(12,12,text='● RETAINING LIVE INPUTS',fill=self.app.ui_chrome['failure_fg'],anchor='nw',tags='recording')
    def press(self,event):
        self.canvas.focus_set();layer,clip=self.app.get_edit_target()
        if not clip or not self.app.can_edit(clip):return
        
        if not self.app.live.recording:self.app.pause()
        self.app.begin_gesture('viewport');self.drag=(clip,event.x,event.y,clip.x.evaluate(self.app.playhead) if clip.x.mode=='animate' else clip.x.value,clip.y.evaluate(self.app.playhead) if clip.y.mode=='animate' else clip.y.value)
    def _write(self,param,value):
        value=max(param.minimum,min(param.maximum,value))
        if self.app.live.recording and self.app.record_automation.get():
            mode=param.mode
            if not param.keyframes:param.add_keyframe(0.,param.value);param.add_keyframe(self.app.live.recording['start'],param.value)
            param.add_keyframe(round(self.app.playhead*self.app.project.fps)/self.app.project.fps,value)
            if mode=='react':param.mode='react';param.combine_animation=True
        elif param.mode=='animate':param.add_keyframe(self.app.gesture_time,value)
        else:param.value=value
    def motion(self,event):
        if not self.drag:return
        clip,x,y,oldx,oldy=self.drag;self._write(clip.x,oldx+(event.x-x)*2/max(1,self.rect[2]));self._write(clip.y,oldy+(event.y-y)*2/max(1,self.rect[3]));clip.manual=True;self.app.changed(redraw=False)
    def release(self,event=None):
        if self.drag:self.drag=None;self.app.end_gesture()
    def wheel(self,event,direction=None):
        l,c=self.app.get_edit_target()
        if not c or not self.app.can_edit(c):return
        if self.wheel_id:
            self.after_cancel(self.wheel_id)
        else:self.app.begin_gesture('viewport scale')
        direction=direction if direction is not None else 1 if event.delta>0 else -1
        base=c.scale.evaluate(self.app.playhead) if c.scale.mode=='animate' else c.scale.value
        self._write(c.scale,base*(1.04 if direction>0 else 1/1.04));c.manual=True;self.app.changed(redraw=False)
        def finish():self.wheel_id=None;self.app.end_gesture()
        self.wheel_id=self.after(220,finish)
        return 'break'
