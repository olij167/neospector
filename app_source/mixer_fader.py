"""Shared visual/audio fader: explicit gesture, readable value and stable identity."""
import tkinter as tk
from tkinter import ttk
from ui_chrome import tk_scale_theme_options
from input_gestures import claim_input, release_input

class MixerFader(ttk.Frame):
    def __init__(self,parent,app,label,begin,change,end,maximum=1.,length=70,horizontal=False,show_label=True,accent=False):
        super().__init__(parent,padding=(1,0));self.app=app;self.active=False;self.change=change;self.begin_callback=begin;self.end_callback=end
        self.value=tk.DoubleVar(value=1.);self.horizontal=horizontal
        head=ttk.Frame(self);head.pack(fill='x')
        if show_label:ttk.Label(head,text=label,anchor='center',style='Title.TLabel' if accent else 'Muted.TLabel').pack(side='left' if horizontal else 'top',fill='x')
        self.display=ttk.Label(head if horizontal else self,text='100%',anchor='center',style='Title.TLabel' if accent else 'Muted.TLabel')
        if horizontal:self.display.pack(side='right')
        self.scale=tk.Scale(self,from_=0 if horizontal else maximum,to=maximum if horizontal else 0,orient='horizontal' if horizontal else 'vertical',resolution=.01,showvalue=False,variable=self.value,
            command=self.changed,length=length,width=11,sliderlength=20,**tk_scale_theme_options(app.ui_chrome))
        self.scale.pack(fill='x' if horizontal else None)
        if not horizontal:self.display.pack(fill='x')
        self.scale.bind('<ButtonPress-1>',self.begin);self.scale.bind('<ButtonRelease-1>',self.end)
        self.scale.bind('<B1-Motion>',lambda e:None if self.active else 'break')
        self.scale.bind('<KeyPress>',self.begin);self.scale.bind('<KeyRelease>',self.end)
        self.scale.bind('<Escape>',lambda e:self.finish_input(cancel=True))
        self.scale.bind('<FocusOut>',self.end);self.scale.bind('<Unmap>',self.end)
        for event in ('<MouseWheel>','<Button-4>','<Button-5>'):self.scale.bind(event,lambda e:'break')
    def begin(self,event=None):
        key=getattr(event,'keysym','??')
        if key not in ('??','Up','Down','Left','Right','Home','End','Prior','Next'):return
        if not self.active:
            claim_input(self.app,self)
            if key=='??':self.scale.focus_set()
            self._before_value=self.value.get();self.begin_callback();self.active=True
    def changed(self,value):
        if self.active:self.change(float(value));self.display.configure(text=f'{float(value):.0%}')
    def end(self,event=None):
        if not self.active:return
        self.changed(self.value.get());self.active=False;release_input(self.app,self);self.end_callback()
    def finish_input(self,*,cancel=False):
        if not cancel:return self.end()
        release_input(self.app,self)
        if self.active:
            self.active=False
            # End Tk's native trough-repeat/slider drag before restoring the
            # value, so later motion cannot move a cancelled control's thumb.
            self.scale.event_generate('<ButtonRelease-1>',x=-1,y=-1)
            self.value.set(self._before_value)
            self.app.cancel_gesture();self.end_callback()
        return 'break'
    def sync(self,value):
        if self.active:return
        if abs(self.value.get()-value)>1e-6:self.value.set(value)
        text=f'{value:.0%}'
        if self.display.cget('text')!=text:self.display.configure(text=text)
    def retheme(self):self.scale.configure(**tk_scale_theme_options(self.app.ui_chrome))


class InlineMixerFader(ttk.Frame):
    """Single-row mixer control for hierarchy-critical toolbars.

    Uses the same explicit gesture lifecycle as MixerFader but keeps label,
    slider and percentage on one row so a Level-1 master can remain visible
    without increasing toolbar height.
    """
    def __init__(self,parent,app,label,begin,change,end,maximum=1.,length=82,accent=False,show_label=True,display_width=4):
        super().__init__(parent,padding=(2,0));self.app=app;self.active=False;self.change=change;self.begin_callback=begin;self.end_callback=end
        self.value=tk.DoubleVar(value=1.)
        if show_label:ttk.Label(self,text=label,style='Title.TLabel' if accent else 'Muted.TLabel').pack(side='left',padx=(0,3))
        self.scale=tk.Scale(self,from_=0,to=maximum,orient='horizontal',resolution=.01,showvalue=False,variable=self.value,command=self.changed,length=length,width=9,sliderlength=18,**tk_scale_theme_options(app.ui_chrome))
        self.scale.pack(side='left')
        self.display=ttk.Label(self,text='100%',width=display_width,anchor='e',style='Title.TLabel' if accent else 'Muted.TLabel');self.display.pack(side='left',padx=(2,0))
        self.scale.bind('<ButtonPress-1>',self.begin);self.scale.bind('<ButtonRelease-1>',self.end)
        self.scale.bind('<B1-Motion>',lambda e:None if self.active else 'break')
        self.scale.bind('<KeyPress>',self.begin);self.scale.bind('<KeyRelease>',self.end)
        self.scale.bind('<Escape>',lambda e:self.finish_input(cancel=True));self.scale.bind('<FocusOut>',self.end);self.scale.bind('<Unmap>',self.end)
        for event in ('<MouseWheel>','<Button-4>','<Button-5>'):self.scale.bind(event,lambda e:'break')
    def begin(self,event=None):
        key=getattr(event,'keysym','??')
        if key not in ('??','Up','Down','Left','Right','Home','End','Prior','Next'):return
        if not self.active:
            claim_input(self.app,self)
            if key=='??':self.scale.focus_set()
            self._before_value=self.value.get();self.begin_callback();self.active=True
    def changed(self,value):
        if self.active:self.change(float(value))
        self.display.configure(text=f'{float(value):.0%}')
    def end(self,event=None):
        if not self.active:return
        self.changed(self.value.get());self.active=False;release_input(self.app,self);self.end_callback()
    def finish_input(self,*,cancel=False):
        if not cancel:return self.end()
        release_input(self.app,self)
        if self.active:
            self.active=False;self.scale.event_generate('<ButtonRelease-1>',x=-1,y=-1);self.value.set(self._before_value);self.app.cancel_gesture();self.end_callback()
        return 'break'
    def sync(self,value):
        if self.active:return
        if abs(self.value.get()-value)>1e-6:self.value.set(value)
        text=f'{value:.0%}'
        if self.display.cget('text')!=text:self.display.configure(text=text)
    def retheme(self):self.scale.configure(**tk_scale_theme_options(self.app.ui_chrome))
