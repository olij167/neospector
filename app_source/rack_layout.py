"""Shared layout policy and bounded, nested scrolling for owner and module cells."""
from dataclasses import dataclass
import math
import tkinter as tk
from tkinter import ttk

@dataclass(frozen=True)
class LayoutPolicy:
    presentation: str = 'Grid'
    flow: str = 'Wrap'
    detail: str = 'Principal controls'
    rows: str = 'Auto'

CHOICES={'presentation':('Grid','List'),'flow':('Wrap','Single strip'),'detail':('Principal controls','Expand focused','Expand all','Collapsed'),'rows':('Auto','1','2','3','4')}

def positions(width,keys,policy,minimum=220):
    width=max(100,int(width));count=max(1,len(keys));gap=6
    cols=count if policy.flow=='Single strip' else 1 if policy.presentation=='List' else max(1,min(count,width//minimum))
    cell=max(minimum,width//cols-gap) if policy.flow=='Single strip' else max(80,width//cols-gap)
    return cols,cell,[(key,i//cols,i%cols) for i,key in enumerate(keys)]

class RackArea(ttk.Frame):
    """One viewport; only the innermost scrollable area consumes the wheel."""
    def __init__(self,parent,app,height=250):
        super().__init__(parent);self.app=app;self.policy=LayoutPolicy();self.canvas=tk.Canvas(self,highlightthickness=0,height=height,bg=app.ui_chrome['panel_bg'])
        self.canvas.grid(row=0,column=0,sticky='nsew');self.columnconfigure(0,weight=1);self.rowconfigure(0,weight=1)
        self.bar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview);self.bar.grid(row=0,column=1,sticky='ns')
        self.hbar=ttk.Scrollbar(self,orient='horizontal',command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.bar.set,xscrollcommand=self.hbar.set)
        self.body=ttk.Frame(self.canvas);self.window=self.canvas.create_window(0,0,anchor='nw',window=self.body)
        self._region_job=None;self._hbar_visible=False;self._vbar_visible=False;self._last_window_width=None
        self.body.bind('<Configure>',self.region);self.canvas.bind('<Configure>',self.region)
        self.wheel_binding=self.bind_all('<MouseWheel>',self.wheel,add='+')
        self.up_binding=self.bind_all('<Button-4>',self.wheel,add='+');self.down_binding=self.bind_all('<Button-5>',self.wheel,add='+')
        self.bind('<Destroy>',self.cleanup,add='+')
    def cleanup(self,event):
        if event.widget is not self:return
        if self._region_job is not None:
            try:self.after_cancel(self._region_job)
            except tk.TclError:pass
            self._region_job=None
        for name,key in (('<MouseWheel>',self.wheel_binding),('<Button-4>',self.up_binding),('<Button-5>',self.down_binding)):
            try:self._root()._unbind(('bind','all',name),key)
            except tk.TclError:pass
    def wheel(self,event):
        widget=self.winfo_containing(event.x_root,event.y_root)
        if widget is None or not str(widget).startswith(str(self)):return
        areas=[];w=widget
        while w is not None:
            if isinstance(w,RackArea):areas.append(w)
            w=getattr(w,'master',None)
        direction=-1 if getattr(event,'num',None)==4 or getattr(event,'delta',0)>0 else 1
        for area in areas:
            horizontal=area.policy.flow=='Single strip' and not (getattr(event,'state',0)&1)
            if horizontal and area.canvas.xview()==(0.0,1.0) and getattr(area,'allow_vertical',False):horizontal=False
            view=area.canvas.xview if horizontal else area.canvas.yview
            first,last=view()
            if (direction<0 and first>0) or (direction>0 and last<1):
                (area.canvas.xview_scroll if horizontal else area.canvas.yview_scroll)(direction*2,'units');return 'break'
        return 'break'
    def region(self,event=None):
        # Configure events arrive in bursts while nested racks settle.  Coalesce them
        # rather than forcing synchronous geometry passes; repeated update_idletasks()
        # here caused the owner rack to oscillate and visibly blank on Linux/Tk.
        if event is not None and event.widget not in (self.body,self.canvas):return
        if self._region_job is None:self._region_job=self.after_idle(self._region_now)
    def _region_now(self):
        self._region_job=None
        if not self.winfo_exists():return
        strip=self.policy.flow=='Single strip';width=max(1,self.canvas.winfo_width())
        target_width=max(width,self.body.winfo_reqwidth()) if strip else width
        if target_width!=self._last_window_width:
            self.canvas.itemconfigure(self.window,width=target_width);self._last_window_width=target_width
        bounds=self.canvas.bbox('all') or (0,0,target_width,1)
        self.canvas.configure(scrollregion=bounds)
        reqw=max(1,self.body.winfo_reqwidth());reqh=max(1,self.body.winfo_reqheight());viewh=max(1,self.canvas.winfo_height())
        show_h=bool(strip and reqw>width+2);show_v=bool((not strip or getattr(self,'allow_vertical',False)) and reqh>viewh+3)
        if show_h!=self._hbar_visible:
            (self.hbar.grid if show_h else self.hbar.grid_remove)(row=1,column=0,sticky='ew') if show_h else self.hbar.grid_remove()
            self._hbar_visible=show_h
        if show_v!=self._vbar_visible:
            (self.bar.grid if show_v else self.bar.grid_remove)(row=0,column=1,sticky='ns') if show_v else self.bar.grid_remove()
            self._vbar_visible=show_v
    def reveal(self,widget):
        self.update_idletasks();bounds=self.canvas.bbox('all')
        if not bounds:return
        top=widget.winfo_rooty()-self.body.winfo_rooty();left=widget.winfo_rootx()-self.body.winfo_rootx()
        if self.policy.flow=='Single strip':self.canvas.xview_moveto(max(0,left)/max(1,bounds[2]))
        else:self.canvas.yview_moveto(max(0,top)/max(1,bounds[3]))
    def set_theme(self):
        # ScrollFrame compatibility, including retained native rack controls.
        from performance_dials import PerformanceDial
        chrome=self.app.ui_chrome
        self.canvas.configure(bg=chrome['panel_bg'])
        def repaint(widget):
            if isinstance(widget,RackArea):widget.canvas.configure(bg=chrome['panel_bg'])
            elif isinstance(widget,PerformanceDial):widget.retheme()
            elif isinstance(widget,tk.Frame) and hasattr(widget,'fx_id'):
                widget.accent=chrome['accent'];widget.configure(bg=chrome['panel_bg'],highlightbackground=chrome['accent'])
            for child in widget.winfo_children():repaint(child)
        repaint(self.body)

    def set_policy(self,policy,height=None):
        changed=policy!=self.policy;self.policy=policy
        if height is not None:
            target=max(48,int(height))
            try:current=int(float(self.canvas.cget('height')))
            except (ValueError,tk.TclError):current=-1
            if abs(current-target)>1:self.canvas.configure(height=target);changed=True
        if changed:self.region()

def policy_menu(parent,policy,changed):
    from dataclasses import replace
    menu=tk.Menu(parent,tearoff=False)
    for field,choices in CHOICES.items():
        child=tk.Menu(menu,tearoff=False);menu.add_cascade(label={'presentation':'Presentation','flow':'Flow','detail':'Detail','rows':'Visible rows'}[field],menu=child)
        for choice in choices:child.add_command(label=('✓ ' if getattr(policy,field)==choice else '')+choice,command=lambda f=field,v=choice:changed(replace(policy,**{f:v})))
    return menu
