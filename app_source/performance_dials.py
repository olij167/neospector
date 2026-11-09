"""Compact rotary controls over the existing Conductor values and gestures.

Relative drag avoids jumps; precise entry and keyboard operation remain first
class. Canvas items persist and only changed values cause pointer updates.
"""
import math
import tkinter as tk
from tkinter import ttk
from input_gestures import claim_input, release_input


def clamp(value):return min(1.,max(0.,float(value)))

def drag_value(value,dx,dy,*,fine=False):
    return clamp(value+(dx-dy)/(1800. if fine else 180.))

def key_value(value,key,*,fine=False):
    if key=='Home':return 0.
    if key=='End':return 1.
    step=.001 if fine else .01
    return clamp(value+step*(1 if key in ('Up','Right') else -1)) if key in ('Up','Right','Down','Left') else value

def parse_percent(text):
    value=float(text.strip().removesuffix('%').strip())
    if not math.isfinite(value) or not 0<=value<=100:raise ValueError('Enter a percentage from 0 to 100.')
    return value/100.


class PerformanceDial(ttk.Frame):
    def __init__(self,parent,app,title,variable,begin,change,end,help_text,*,units='percent'):
        super().__init__(parent,padding=(5,2));self.app=app;self.variable=variable;self.begin_callback=begin;self.change_callback=change;self.end_callback=end
        self.active=False;self.custom=False;self._last_draw=None;self._point=None
        self.columnconfigure(0,weight=1)
        self.title=ttk.Label(self,text=title,style='Muted.TLabel');self.title.grid(row=0,column=0,columnspan=2,sticky='w')
        self.canvas=tk.Canvas(self,width=64,height=60,highlightthickness=1,borderwidth=0,takefocus=True)
        self.canvas.grid(row=1,column=0,sticky='w');self.scale=self.canvas
        self.text=tk.StringVar();self.entry=ttk.Entry(self,textvariable=self.text,width=6,justify='right');self.entry.grid(row=1,column=1,sticky='e',padx=(2,0))
        # A 270-degree physical dial: fixed end stops, marked sweep and pointer.
        for n in range(9):
            angle=math.radians(225-270*n/8);x,y=32+26*math.cos(angle),29-26*math.sin(angle)
            self.canvas.create_line(x,y,32+29*math.cos(angle),29-29*math.sin(angle),tags='tick')
        self.ring=self.canvas.create_arc(8,5,56,53,start=225,extent=-270,style='arc',width=3,tags='ring')
        self.sweep=self.canvas.create_arc(8,5,56,53,start=225,extent=-135,style='arc',width=3,tags='sweep')
        self.canvas.create_oval(13,10,51,48,width=2,tags='body')
        self.canvas.create_oval(18,15,46,43,width=1,tags='inner')
        self.pointer=self.canvas.create_line(32,29,32,12,width=3,capstyle='round',tags='pointer')
        self.custom_mark=self.canvas.create_text(32,29,text='—',font=('TkDefaultFont',11,'bold'),tags='custom')
        self.canvas.bind('<ButtonPress-1>',self.press);self.canvas.bind('<B1-Motion>',self.drag);self.canvas.bind('<ButtonRelease-1>',self.release)
        self.canvas.bind('<FocusOut>',self.release);self.canvas.bind('<Unmap>',self.release);self.canvas.bind('<Double-Button-1>',self.precise)
        self.canvas.bind('<KeyPress>',self.key)
        for event in ('<MouseWheel>','<Button-4>','<Button-5>'):self.canvas.bind(event,lambda e:'break')
        self.entry.bind('<Return>',self.enter);self.entry.bind('<Escape>',self.cancel_entry);self.entry.bind('<FocusOut>',lambda e:self.show_value(force=True))
        tip=help_text+' Drag up/right to increase; Shift-drag for fine control. Arrow keys adjust; Home/End reach the limits. Enter a precise value. Scrolling never changes this control.'
        app.add_tip(self.canvas,tip);app.add_tip(self.entry,('Enter 0–100%' if units=='percent' else 'Enter a value in the parameter’s displayed range')+' and press Return. Escape cancels typing. '+help_text)
        self.trace=variable.trace_add('write',self.show_value);self.retheme();self.show_value(force=True)
    def retheme(self):
        c=self.app.ui_chrome;self.canvas.configure(bg=c['panel_bg'],highlightbackground=c['panel_bg'],highlightcolor=c['accent'])
        for tag,colour in (('tick',c['muted_fg']),('ring',c['field_bg']),('sweep',c['accent']),('pointer',c['foreground'])):self.canvas.itemconfigure(tag,fill=colour) if tag in ('tick','pointer') else self.canvas.itemconfigure(tag,outline=colour)
        self.canvas.itemconfigure('body',fill=c['button_bg'],outline=c['muted_fg']);self.canvas.itemconfigure('inner',fill=c['button_bg'],outline=c['field_bg']);self.canvas.itemconfigure('custom',fill=c['muted_fg']);self._last_draw=None;self.show_value()
    def set_custom(self,value):
        if self.custom!=bool(value):self.custom=bool(value);self._last_draw=None;self.show_value()
    def show_value(self,*_,force=False):
        try:value=clamp(self.variable.get())
        except (ValueError,tk.TclError):return
        if force or self.app.focus_get() is not self.entry:
            label='—' if self.custom else f'{value*100:.1f}'.rstrip('0').rstrip('.')+'%'
            if self.text.get()!=label:self.text.set(label)
        key=(round(value,5),self.custom)
        if key==self._last_draw:return
        self._last_draw=key;angle=math.radians(225-270*value)
        self.canvas.coords(self.pointer,32+5*math.cos(angle),29-5*math.sin(angle),32+17*math.cos(angle),29-17*math.sin(angle))
        self.canvas.itemconfigure(self.sweep,extent=-max(.001,270*value),state='hidden' if self.custom or value==0 else 'normal')
        self.canvas.itemconfigure(self.pointer,state='hidden' if self.custom else 'normal');self.canvas.itemconfigure(self.custom_mark,state='normal' if self.custom else 'hidden')
    def begin(self):
        if not self.active:
            claim_input(self.app,self)
            self._before_value=self.variable.get();self._before_custom=self.custom
            self.active=True;self.begin_callback()
    def apply(self,value):
        value=clamp(value)
        if value==self.variable.get() and not self.custom:return
        self.begin();self.set_custom(False);self.variable.set(value);self.change_callback(self.variable.get())
    def press(self,event):
        claim_input(self.app,self)
        self.canvas.focus_set();self._point=(event.x_root,event.y_root);return 'break'
    def drag(self,event):
        if self._point is None:return 'break'
        x,y=self._point;self.apply(drag_value(self.variable.get(),event.x_root-x,event.y_root-y,fine=bool(event.state&1)));self._point=(event.x_root,event.y_root);return 'break'
    def release(self,event=None):
        self._point=None
        release_input(self.app,self)
        if self.active:self.active=False;self.end_callback()
        return 'break'
    def finish_input(self,*,cancel=False):
        if not cancel:return self.release()
        self._point=None;release_input(self.app,self)
        if self.active:
            self.active=False
            self.variable.set(self._before_value);self.set_custom(self._before_custom)
            self.app.cancel_gesture()
            self.end_callback()
        return 'break'
    def precise(self,event=None):
        self.release();self.entry.focus_set();self.entry.selection_range(0,'end');return 'break'
    def key(self,event):
        if event.keysym=='Escape':return self.finish_input(cancel=True)
        if event.keysym in ('Return','KP_Enter'):return self.precise()
        if event.keysym not in ('Up','Right','Down','Left','Home','End'):return None
        self.apply(key_value(self.variable.get(),event.keysym,fine=bool(event.state&1)));self.release();return 'break'
    def enter(self,event=None):
        try:
            value=parse_percent(self.text.get());self.apply(value);self.release();self.canvas.focus_set();self.show_value(force=True)
        except ValueError as exc:self.app.update_status(str(exc));self.entry.selection_range(0,'end')
        return 'break'
    def cancel_entry(self,event=None):
        self.show_value(force=True);self.canvas.focus_set();return 'break'
    def destroy(self):
        try:self.variable.trace_remove('write',self.trace)
        except tk.TclError:pass
        super().destroy()
