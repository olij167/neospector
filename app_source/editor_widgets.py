"""Small contextual controls. A control edits the named object, never hidden state."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from ui_chrome import tk_scale_theme_options
from live_parameter_controls import (ParameterGesture, available_reaction_sources,
    initial_reaction_changes, should_debounce_key)
from rack_editing import PARAMETER_CHOICES, PARAMETER_NUMBERS, update_parameter


class ScrollFrame(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app
        self.canvas=tk.Canvas(self,highlightthickness=0,bg=app.ui_chrome['panel_bg']);self.canvas.pack(side='left',fill='both',expand=True)
        self.bar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview);self.bar.pack(side='right',fill='y');self.canvas.configure(yscrollcommand=self.bar.set)
        self.body=ttk.Frame(self.canvas,padding=6);self.window=self.canvas.create_window(0,0,window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.window,width=e.width))
        self.canvas.bind('<Button-4>',lambda e:self.canvas.yview_scroll(-3,'units'));self.canvas.bind('<Button-5>',lambda e:self.canvas.yview_scroll(3,'units'))
        self.wheel_binding=self.bind_all('<MouseWheel>',self._wheel,add='+');self.bind('<Destroy>',self._cleanup,add='+')
    def _cleanup(self,event):
        if event.widget is self and self.wheel_binding:
            try:self._root()._unbind(('bind','all','<MouseWheel>'),self.wheel_binding)
            except tk.TclError:pass
            self.wheel_binding=None
    def _wheel(self,event):
        try:
            w=self.winfo_containing(event.x_root,event.y_root)
            if w and str(w).startswith(str(self)) and w.winfo_class() not in {'Scale','TScale'}:self.canvas.yview_scroll(-int(event.delta/120) or (-1 if event.delta>0 else 1),'units')
        except tk.TclError:pass
    def set_theme(self):self.canvas.configure(bg=self.app.ui_chrome['panel_bg'])


def small_button(parent,text,command,**kwargs):
    return ttk.Button(parent,text=text,command=command,**kwargs)


class ParameterRow(ttk.Frame):
    def __init__(self,parent,app,label,param,owner=None):
        super().__init__(parent);self.app=app;self.param=param;self.owner=owner;self.label=label;self.active=False;self.loading=False
        self.columnconfigure(1,weight=1)
        ttk.Label(self,text=label,width=11).grid(row=0,column=0,sticky='w')
        self.value=tk.DoubleVar(value=param.value);self.text=tk.StringVar(value=f'{param.value:.3g}')
        self.scale=tk.Scale(self,variable=self.value,from_=param.minimum,to=param.maximum,resolution=(param.maximum-param.minimum)/500,orient='horizontal',showvalue=False,command=self.changed,**tk_scale_theme_options(app.ui_chrome))
        self.scale.grid(row=0,column=1,sticky='ew',padx=3)
        self.entry=ttk.Entry(self,textvariable=self.text,width=7);self.entry.grid(row=0,column=2,padx=(2,1));self.entry.bind('<Return>',self.enter)
        self.mode=ttk.Button(self,text={'static':'●','animate':'◆','react':'≈'}.get(param.mode,'●'),width=3,command=self.program);self.mode.grid(row=0,column=3)
        app.add_tip(self.mode,'Static / Animate / React · edit keyframes, audio source, frequency band and response range.')
        self.scale.bind('<ButtonPress-1>',self.begin);self.scale.bind('<ButtonRelease-1>',self.end)
        self.scale.bind('<KeyPress>',self.begin,add='+');self.scale.bind('<KeyRelease>',self.end,add='+')
        self.evaluated=ttk.Label(self,text='',style='Muted.TLabel');self.evaluated.grid(row=1,column=1,columnspan=3,sticky='e')
    def begin(self,event=None):
        if self.active:return
        if not self.app.can_edit(self.owner):return 'break'
        self.active=True;self.app.begin_gesture('parameter')
    def changed(self,value):
        if not self.active or self.loading:return
        self.write(float(value));self.text.set(f'{float(value):.3g}')
    def write(self,value):
        value=max(self.param.minimum,min(self.param.maximum,value))
        if hasattr(self.app,'write_parameter'):
            self.app.write_parameter(self.param,value,self.owner);return
        if self.app.live.recording and self.app.record_automation.get():
            mode=self.param.mode
            if not self.param.keyframes:self.param.add_keyframe(0.,self.param.value);self.param.add_keyframe(self.app.live.recording['start'],self.param.value)
            self.param.add_keyframe(round(self.app.playhead*self.app.project.fps)/self.app.project.fps,value)
            if mode=='react':self.param.mode='react';self.param.combine_animation=True
        elif self.param.mode=='animate':self.param.add_keyframe(self.app.gesture_time,value)
        else:self.param.value=value
        if hasattr(self.owner,'manual'):self.owner.manual=True
        self.app.changed(redraw=False)
    def end(self,event=None):
        if not self.active:return
        self.write(self.value.get());self.active=False;self.app.end_gesture()
    def enter(self,event=None):
        try:
            value=float(self.text.get())
            if not __import__('math').isfinite(value):raise ValueError('Non-finite value')
        except ValueError:self.app.update_status('Enter a numerical value');return 'break'
        if self.app.can_edit(self.owner):
            self.app.begin_gesture('parameter');self.write(value);self.app.end_gesture();self.refresh()
        return 'break'
    def refresh(self):
        if self.active:return
        self.loading=True
        p=self.param
        try:
            value=self.app.signal_evaluator().value(p,self.app.playhead)
            if self.app.focus_get() is not self.entry:
                self.value.set(value if p.mode=='animate' else p.value);self.text.set(f'{self.value.get():.3g}')
            self.mode.configure(text={'static':'●','animate':'◆','react':'≈'}.get(p.mode,'●'))
            self.evaluated.configure(text=f'{p.mode.title()} · now {value:.3g}' if p.mode!='static' else '')
            if p.mode=='static':self.evaluated.grid_remove()
            else:self.evaluated.grid()
        finally:self.loading=False
    def program(self):
        if self.app.can_edit(self.owner):ParameterDialog(self.app,self.label,self.param,self.owner)


class ParameterDialog(tk.Toplevel):
    def __init__(self,app,label,param,owner=None):
        super().__init__(app);self.app=app;self.param=param;self.owner=owner;self.title(label+' · Static / Animate / React');self.transient(app)
        self.vars={};self.boxes={};self.entries={};self.jobs={};self.message=tk.StringVar();self.geometry('660x590');self.minsize(550,480)
        self.gesture=ParameterGesture(app,self.resolve,self.message.set)
        body=ttk.Frame(self,padding=14);body.pack(fill='both',expand=True)
        ttk.Label(body,text=label,style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,text='Values change Programme as you edit. Keyframes use project seconds.',style='Muted.TLabel').pack(anchor='w',pady=(2,10))
        top=ttk.Frame(body);top.pack(fill='x')
        for key,values in PARAMETER_CHOICES.items():
            row=ttk.Frame(top);row.pack(fill='x',pady=2);ttk.Label(row,text=key.replace('_',' ').title(),width=18).pack(side='left')
            v=tk.StringVar(value=getattr(param,key));self.vars[key]=v;box=ttk.Combobox(row,textvariable=v,values=values,state='readonly');box.pack(side='left',fill='x',expand=True);box.bind('<<ComboboxSelected>>',lambda e,k=key:self.choice(k));self.boxes[key]=box
        nums=ttk.Frame(body);nums.pack(fill='x',pady=8)
        for i,(key,labeltext) in enumerate([('value','Base'),('minimum','Minimum'),('maximum','Maximum'),('react_amount','Reaction amount'),('attack','Attack (s)'),('release','Release (s)'),('threshold','Threshold')]):
            r=i//2;c=(i%2)*2;ttk.Label(nums,text=labeltext).grid(row=r,column=c,sticky='w',padx=(0,5),pady=2)
            v=tk.StringVar(value=f'{getattr(param,key):g}');self.vars[key]=v;entry=ttk.Entry(nums,textvariable=v,width=12);entry.grid(row=r,column=c+1,sticky='ew',padx=(0,14));self.entries[key]=entry
            entry.bind('<KeyRelease>',lambda e,k=key:self.queue_number(k,e));entry.bind('<Return>',lambda e,k=key:self.finish_number(k));entry.bind('<KP_Enter>',lambda e,k=key:self.finish_number(k));entry.bind('<FocusOut>',lambda e,k=key:self.finish_number(k));entry.bind('<Escape>',self.escape)
        nums.columnconfigure(1,weight=1);nums.columnconfigure(3,weight=1)
        self.combine=tk.BooleanVar(value=param.combine_animation);ttk.Checkbutton(body,text='React on top of the authored animation',variable=self.combine,command=lambda:self.flag('combine_animation',self.combine.get())).pack(anchor='w')
        if hasattr(app,'programme_project'):
            self.conductor_locked=tk.BooleanVar(value=bool(param.extra.get('conductor_locked',False)))
            ttk.Checkbutton(body,text='Protect this parameter from Conductor evolution',variable=self.conductor_locked,command=lambda:self.flag('conductor_locked',self.conductor_locked.get())).pack(anchor='w',pady=3)
        ttk.Label(body,textvariable=self.message,style='Muted.TLabel').pack(fill='x',pady=2)
        keys=ttk.LabelFrame(body,text='Keyframes',padding=6);keys.pack(fill='both',expand=True,pady=8)
        self.tree=ttk.Treeview(keys,columns=('time','value'),show='headings',height=5);self.tree.heading('time',text='Project time (seconds)');self.tree.heading('value',text='Value');self.tree.pack(fill='both',expand=True)
        row=ttk.Frame(keys);row.pack(fill='x',pady=5);self.kt=tk.StringVar(value=f'{app.playhead:.4f}');self.kv=tk.StringVar(value=f'{param.evaluate(app.playhead):.4f}')
        for v in (self.kt,self.kv):ttk.Entry(row,textvariable=v,width=12).pack(side='left',padx=2)
        ttk.Button(row,text='Add / replace',command=self.add_key).pack(side='left',padx=3);ttk.Button(row,text='Delete selected',command=self.delete_key).pack(side='left')
        self.tree.bind('<<TreeviewSelect>>',self.choose_key)
        foot=ttk.Frame(body);foot.pack(side='bottom',before=body.winfo_children()[0],fill='x');ttk.Button(foot,text='Done',command=self.done).pack(side='right',padx=6)
        self.keys();self.protocol('WM_DELETE_WINDOW',self.done);self.bind('<Escape>',self.escape);self.grab_set()

    def resolve(self):
        try:
            from instrument_model import walk_parameters
            if not any(candidate is self.param for candidate in walk_parameters(self.app.project)):return None
        except Exception:return None
        return self.param,self.owner

    def choice(self,key):
        changes=initial_reaction_changes(self.param,available=available_reaction_sources(self.app)) if key=='mode' and self.vars[key].get()=='react' else {key:self.vars[key].get()}
        try:
            if self.gesture.begin():self.gesture.write_fields(changes);self.gesture.finish();self.sync()
        except ValueError as exc:self.message.set(str(exc));self.gesture.cancel()

    def flag(self,key,value):
        try:
            if self.gesture.begin():
                if key=='conductor_locked':update_parameter(self.param,{key:value});self.app.changed(redraw=False)
                else:self.gesture.write_field(key,value)
                self.gesture.finish();self.sync()
        except ValueError as exc:self.message.set(str(exc));self.gesture.cancel()

    def queue_number(self,key,event=None):
        if event is not None and not should_debounce_key(event):return
        job=self.jobs.pop(key,None)
        if job:
            try:self.after_cancel(job)
            except tk.TclError:pass
        self.jobs[key]=self.after(280,lambda:self.write_number(key))

    def write_number(self,key,finish=False):
        job=self.jobs.pop(key,None)
        if job:
            try:self.after_cancel(job)
            except tk.TclError:pass
        try:
            value=float(self.vars[key].get())
            if not __import__('math').isfinite(value):raise ValueError
            if key=='value':
                if not self.param.minimum<=value<=self.param.maximum:raise ValueError
                changed=self.gesture.write_base(value)
            else:changed=self.gesture.write_field(key,value)
            if changed:self.message.set('')
        except ValueError:self.message.set('Enter a finite value inside the parameter range.');changed=False
        if finish:self.gesture.finish()
        return changed

    def finish_number(self,key):self.write_number(key,True);return 'break'

    def sync(self):
        for key,var in self.vars.items():
            if self.focus_get() is not self.entries.get(key):var.set(f'{getattr(self.param,key):g}' if key in PARAMETER_NUMBERS else getattr(self.param,key))
        self.combine.set(self.param.combine_animation)
        if hasattr(self,'conductor_locked'):self.conductor_locked.set(bool(self.param.extra.get('conductor_locked',False)))

    def keys(self):
        self.tree.delete(*self.tree.get_children())
        for i,k in enumerate(self.param.keyframes):self.tree.insert('', 'end',iid=str(i),values=(f'{k.time:.4f}',f'{k.value:.4f}'))
    def choose_key(self,event):
        selected=self.tree.selection()
        if selected:k=self.param.keyframes[int(selected[0])];self.kt.set(str(k.time));self.kv.set(str(k.value))
    def add_key(self):
        try:
            t=float(self.kt.get());v=float(self.kv.get())
            if not self.gesture.begin():return
            self.param.add_keyframe(t,v);self.param.extra['conductor_locked']=True
            if hasattr(self.owner,'manual'):self.owner.manual=True
            self.app.changed(redraw=False);self.gesture.finish();self.vars['mode'].set(self.param.mode);self.keys()
        except Exception as exc:self.message.set(str(exc));self.gesture.cancel()
    def delete_key(self):
        selected=self.tree.selection()
        if selected and self.gesture.begin():
            self.param.keyframes.pop(int(selected[0]));self.param.extra['conductor_locked']=True
            if hasattr(self.owner,'manual'):self.owner.manual=True
            self.app.changed(redraw=False);self.gesture.finish();self.keys()
    def done(self):
        for job in self.jobs.values():
            try:self.after_cancel(job)
            except tk.TclError:pass
        self.jobs.clear()
        if self.gesture.active:self.gesture.finish()
        try:self.grab_release()
        except tk.TclError:pass
        self.destroy()
    def escape(self,event=None):
        for job in self.jobs.values():
            try:self.after_cancel(job)
            except tk.TclError:pass
        self.jobs.clear()
        if self.gesture.active:
            self.gesture.cancel();self.done()
        else:self.sync()
        return 'break'
