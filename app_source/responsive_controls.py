"""Bounded, wrapping layouts. Reflow existing widgets; never rebuild or hide them.

Dimensions are Tk logical pixels after user scaling. Controls retain their normal
font/hit targets. Space contracts before a row wraps; larger panes stop enlarging
individual controls at their declared maxima.
"""
from __future__ import annotations
import math
import tkinter as tk
from tkinter import ttk


class OverflowAdapter:
    """Explicit contract for one toolbar item's temporary overflow view.

    ``mirror`` shares Tk variables and commands, and forwards only the event
    bindings named by the consumer.  Editors therefore declare their commit and
    guard lifecycle instead of relying on a partial widget-type guess.
    """
    def __init__(self,builder,sync=None):self.builder=builder;self.sync=sync

    @classmethod
    def mirror(cls,*events):
        events=tuple(dict.fromkeys(events))
        return cls(lambda toolbar,parent,original:toolbar._mirror_widget(original,parent,events))


class PriorityToolbar(ttk.Frame):
    """A single-row toolbar which overflows whole, live control groups.

    Widgets remain owned by the toolbar.  The overflow popover creates only a
    temporary view onto their commands and Tk variables, so an action has one
    source of truth even while it is in ``More…``.
    """
    def __init__(self,parent,*,gap=4,**kw):
        super().__init__(parent,**kw)
        self.gap=gap;self.items=[];self._order=0;self.job=None;self.last=None
        self._pending_width=None;self._pointer_active=0;self._popover=None;self._flush_job=None;self._popover_focus_job=None;self._sync_job=None
        self.overflow_widgets=[];self.overflow_controls=[];self._proxy_pairs=[];self._outside_button_bind=None;self._outside_focus_bind=None
        self.pin_policy=None
        self.more_button=ttk.Button(self,text='More…',command=self.open_overflow)
        self.bind('<Configure>',self.schedule,add='+')

    def add(self,widget,*,priority=50,pinned=False,overflow=None,available=True):
        """Add one semantic group.  Lower priorities stay in the row first."""
        if widget.master is not self:
            raise ValueError('PriorityToolbar widgets must be children of the toolbar')
        adapter=overflow or self._default_adapter(widget)
        if adapter is None and not pinned:
            raise ValueError('Editable/grouped toolbar items need OverflowAdapter.mirror(...)')
        self.items.append({'widget':widget,'priority':int(priority),
                           'pinned':bool(pinned),'order':self._order,'overflow':adapter,'available':bool(available)})
        self._order+=1
        self._watch(widget);self.schedule();return widget

    def add_action(self,text,command,*,priority=50,pinned=False,**button_options):
        button=ttk.Button(self,text=text,command=command,**button_options)
        return self.add(button,priority=priority,pinned=pinned)

    def remove(self,widget,*,destroy=False):
        """Remove a semantic group without rebuilding the toolbar.

        Dynamic contextual actions (for example Return to Programme) can come and
        go without leaving an empty place or destroying the reusable widget.
        """
        self.items=[item for item in self.items if item['widget'] is not widget]
        self.overflow_widgets=[item for item in self.overflow_widgets if item is not widget]
        try:widget.place_forget()
        except tk.TclError:pass
        if destroy:
            try:widget.destroy()
            except tk.TclError:pass
        self.last=None;self.close_overflow(schedule=False);self.schedule();return widget

    def contains(self,widget):
        return any(item['widget'] is widget for item in self.items)

    def set_available(self,widget,available):
        """Retain a contextual command without stacking new widget bindings."""
        item=next((item for item in self.items if item['widget'] is widget),None)
        if item is None or item.get('available',True)==bool(available):return
        item['available']=bool(available)
        if not available:widget.place_forget()
        self.last=None;self.close_overflow(schedule=False);self.schedule()

    def _watch(self,widget):
        widget.bind('<ButtonPress-1>',self._press,add='+')
        widget.bind('<ButtonRelease-1>',self._release,add='+')
        widget.bind('<FocusOut>',lambda event:self._defer_flush(),add='+')
        for child in widget.winfo_children():self._watch(child)

    def _press(self,event=None):self._pointer_active+=1
    def _release(self,event=None):
        self._pointer_active=max(0,self._pointer_active-1);self._defer_flush()

    def _defer_flush(self):
        if self._flush_job is None:self._flush_job=self.after_idle(self._run_flush)

    def _run_flush(self):
        self._flush_job=None;self._flush_pending()

    def _editing(self):
        if self._pointer_active or self._popover is not None:return True
        try:focus=self.focus_get()
        except tk.TclError:return False
        if focus is None:return False
        editing=(ttk.Entry,ttk.Combobox,ttk.Spinbox,ttk.Scale,tk.Entry,tk.Scale)
        if not isinstance(focus,editing):return False
        while focus is not None:
            if focus is self:return True
            focus=getattr(focus,'master',None)
        return False

    def schedule(self,event=None):
        if event is not None and event.widget is not self:return
        if self.job is None:self.job=self.after_idle(self._layout)

    def _layout(self):
        self.job=None
        if self.winfo_exists():self.arrange(self.winfo_width())

    def arrange(self,width=None,*,force=False):
        width=max(1,int(width if width is not None else self.winfo_width()))
        if not force and self._editing():
            self._pending_width=width;return
        self._pending_width=None
        items=[item for item in self.items if item.get('available',True)]
        dims={item['widget']:(max(1,item['widget'].winfo_reqwidth()),
                              max(1,item['widget'].winfo_reqheight())) for item in items}
        if self.pin_policy:self.pin_policy(self,width,dims)
        all_width=sum(dims[item['widget']][0] for item in items)+self.gap*max(0,len(items)-1)
        hidden=[]
        if all_width<=width:
            visible={item['widget'] for item in items}
        else:
            more_width=max(1,self.more_button.winfo_reqwidth())
            pinned=[item for item in items if item['pinned']]
            optional=sorted((item for item in items if not item['pinned']),
                            key=lambda item:(item['priority'],item['order']))
            visible={item['widget'] for item in pinned}
            used=sum(dims[item['widget']][0] for item in pinned)
            used+=self.gap*max(0,len(pinned)-1)
            # More is part of the bounded row whenever anything overflows.
            budget=max(0,width-more_width-self.gap)
            overflowing=False
            for item in optional:
                ww=dims[item['widget']][0]+(self.gap if visible else 0)
                if not overflowing and used+ww<=budget:
                    visible.add(item['widget']);used+=ww
                else:
                    overflowing=True;hidden.append(item)
        self.overflow_widgets=[item['widget'] for item in sorted(hidden,key=lambda x:x['order'])]
        key=(width,tuple(str(w) for w in visible),tuple(str(w) for w in self.overflow_widgets),
             tuple(dims.values()))
        if key==self.last:return
        self.last=key;x=0;row_h=1
        for item in self.items:
            widget=item['widget']
            if widget in visible:
                ww,hh=dims[widget]
                widget.place(x=x,y=0,width=ww,height=hh);x+=ww+self.gap;row_h=max(row_h,hh)
            else:widget.place_forget()
        if self.overflow_widgets:
            ww=max(1,self.more_button.winfo_reqwidth());hh=max(1,self.more_button.winfo_reqheight())
            self.more_button.place(x=x,y=0,width=ww,height=hh);row_h=max(row_h,hh)
        else:self.more_button.place_forget()
        self.configure(height=row_h)

    def _flush_pending(self):
        if not self.winfo_exists() or self._editing():return
        width=self._pending_width
        if width is not None:self.arrange(width,force=True)
        else:self.schedule()

    @staticmethod
    def _option(widget,name,default=None):
        try:
            value=widget.cget(name)
            return default if value in ('',None) else value
        except tk.TclError:return default

    @staticmethod
    def _default_adapter(widget):
        if isinstance(widget,(ttk.Button,ttk.Checkbutton,ttk.Radiobutton,ttk.Label,ttk.Separator)):
            return OverflowAdapter.mirror()
        return None

    def _forward(self,original,sequence,event):
        try:
            if sequence.startswith('<<'):original.event_generate(sequence)
            elif sequence in ('<FocusOut>','<FocusIn>','<Unmap>','<Map>'):original.event_generate(sequence)
            elif sequence in ('<Return>','<Escape>'):original.event_generate(sequence)
            elif sequence.startswith('<Key'):
                original.event_generate(sequence,keysym=getattr(event,'keysym',''),state=getattr(event,'state',0))
            else:
                original.event_generate(sequence,x=getattr(event,'x',0),y=getattr(event,'y',0),state=getattr(event,'state',0))
        except tk.TclError:
            try:original.event_generate(sequence)
            except tk.TclError:pass

    def _bind_forwarded(self,proxy,original,events):
        for sequence in events:
            if original.bind(sequence):
                proxy.bind(sequence,lambda event,w=original,s=sequence:self._forward(w,s,event),add='+')

    def _mirror_widget(self,widget,parent,events):
        """Build the view requested by an explicit OverflowAdapter."""
        proxy=None
        common={'text':self._option(widget,'text','')}
        textvariable=self._option(widget,'textvariable')
        if textvariable:common={'textvariable':textvariable}
        style=self._option(widget,'style')
        if style:common['style']=style
        if isinstance(widget,ttk.Checkbutton):
            proxy=ttk.Checkbutton(parent,**common,variable=self._option(widget,'variable'),
                onvalue=self._option(widget,'onvalue','1'),offvalue=self._option(widget,'offvalue','0'),
                command=self._option(widget,'command'))
        elif isinstance(widget,ttk.Radiobutton):
            proxy=ttk.Radiobutton(parent,**common,variable=self._option(widget,'variable'),
                value=self._option(widget,'value'),command=self._option(widget,'command'))
        elif isinstance(widget,ttk.Button):proxy=ttk.Button(parent,**common,command=widget.invoke)
        elif isinstance(widget,ttk.Combobox):
            proxy=ttk.Combobox(parent,textvariable=textvariable,values=widget.cget('values'),
                               state=str(widget.cget('state')),width=max(6,int(self._option(widget,'width',12))),
                               style=style or 'TCombobox')
        elif isinstance(widget,ttk.Scale):
            options={'variable':self._option(widget,'variable'),
                'from_':self._option(widget,'from',0),'to':self._option(widget,'to',100),
                'orient':self._option(widget,'orient','horizontal'),
                'length':max(40,int(self._option(widget,'length',100))),
                'command':self._option(widget,'command')}
            if style:options['style']=style
            proxy=ttk.Scale(parent,**options)
        elif isinstance(widget,ttk.Spinbox):
            proxy=ttk.Spinbox(parent,textvariable=textvariable,from_=self._option(widget,'from',0),
                to=self._option(widget,'to',100),increment=self._option(widget,'increment',1),
                width=max(5,int(self._option(widget,'width',8))),command=self._option(widget,'command'),
                style=style or 'TSpinbox')
        elif isinstance(widget,ttk.Entry):
            options={'textvariable':textvariable,'width':max(6,int(self._option(widget,'width',12))),
                     'style':style or 'TEntry'}
            for name in ('justify','show','validate','validatecommand','invalidcommand'):
                value=self._option(widget,name)
                if value is not None:options[name]=value
            proxy=ttk.Entry(parent,**options)
        elif isinstance(widget,ttk.Label):proxy=ttk.Label(parent,**common)
        elif isinstance(widget,ttk.Separator):proxy=ttk.Separator(parent,orient=self._option(widget,'orient','horizontal'))
        elif isinstance(widget,(ttk.Frame,ttk.LabelFrame)):
            options={}
            if isinstance(widget,ttk.LabelFrame):options['text']=self._option(widget,'text','')
            proxy=type(widget)(parent,**options)
            children=widget.winfo_children()
            for child in children:
                child_proxy=self._mirror_widget(child,proxy,events)
                if child_proxy is not None:child_proxy.pack(side='left',padx=(0,self.gap))
        if proxy is not None:
            self._bind_forwarded(proxy,widget,events)
            try:
                if widget.instate(['disabled']):proxy.state(['disabled'])
            except (AttributeError,tk.TclError):pass
            self._proxy_pairs.append((widget,proxy));self.overflow_controls.append(proxy)
        return proxy

    def _popover_contains(self,widget):
        popup=self._popover
        if popup is None:return False
        path=str(widget or '')
        try:
            current=widget
            while current is not None:
                if current is popup or current is self.more_button:return True
                current=getattr(current,'master',None)
        except (tk.TclError,AttributeError):pass
        # ttk Combobox popdowns are Tcl windows rather than Python children. Their
        # path is nevertheless rooted at the originating combobox widget.
        prefixes=[str(popup),str(self.more_button),*[str(w) for w in self.overflow_controls]]
        return bool(path and any(path==prefix or path.startswith(prefix+'.') for prefix in prefixes))

    def _overflow_outside(self,event=None):
        if self._popover is None:return
        if event is not None and self._popover_contains(getattr(event,'widget',None)):return
        if self._popover_focus_job is not None:
            try:self.after_cancel(self._popover_focus_job)
            except tk.TclError:pass
        self._popover_focus_job=self.after(80,self._check_popover_focus)

    def _bind_overflow_outside(self):
        if self._outside_button_bind is None:self._outside_button_bind=self.bind_all('<ButtonPress>',self._overflow_outside,add='+')
        if self._outside_focus_bind is None:self._outside_focus_bind=self.bind_all('<FocusIn>',self._overflow_outside,add='+')

    def _unbind_overflow_outside(self):
        for seq,name in (('<ButtonPress>','_outside_button_bind'),('<FocusIn>','_outside_focus_bind')):
            bid=getattr(self,name,None)
            if bid:
                try:self._root()._unbind(('bind','all',seq),bid)
                except tk.TclError:pass
                setattr(self,name,None)

    def open_overflow(self):
        if not self.overflow_widgets:return None
        if self._popover is not None:
            self._popover.lift();return self._popover
        popup=tk.Toplevel(self);self._popover=popup;popup.overrideredirect(True);popup.transient(self.winfo_toplevel())
        body=ttk.Frame(popup,padding=6,relief='raised');body.pack(fill='both',expand=True)
        self.overflow_controls=[];self._proxy_pairs=[]
        for widget in self.overflow_widgets:
            item=next(item for item in self.items if item['widget'] is widget)
            adapter=item['overflow'];proxy=adapter.builder(self,body,widget)
            if proxy is not None:
                # Mirror adapters register every descendant while they build.
                # A consumer-owned builder returns only its semantic root, so
                # register that root here unless the builder already did.
                if not any(source is widget for source,_ in self._proxy_pairs):
                    self._proxy_pairs.append((widget,proxy));self.overflow_controls.append(proxy)
                proxy.pack(fill='x',anchor='w',pady=2)
        popup.update_idletasks()
        x=self.more_button.winfo_rootx()+self.more_button.winfo_width()-popup.winfo_reqwidth()
        y=self.more_button.winfo_rooty()+self.more_button.winfo_height()
        popup.geometry(f'+{max(0,x)}+{max(0,y)}')
        popup.bind('<Escape>',lambda event:self.close_overflow())
        popup.bind('<FocusOut>',self._popover_focus_out,add='+');popup.focus_force();self._bind_overflow_outside()
        self.sync_overflow();return popup

    def overflow_proxy(self,original):
        return next((proxy for source,proxy in self._proxy_pairs if source is original),None)

    def sync_overflow(self):
        if self._popover is None or not self._popover.winfo_exists():return
        for original,proxy in self._proxy_pairs:
            try:
                proxy.state(['disabled'] if original.instate(['disabled']) else ['!disabled'])
                if not self._option(original,'textvariable'):proxy.configure(text=self._option(original,'text',''))
                style=self._option(original,'style')
                if style:proxy.configure(style=style)
                if isinstance(original,ttk.Combobox):
                    proxy.configure(values=original.cget('values'),state=str(original.cget('state')))
                    if original.instate(['disabled']):proxy.state(['disabled'])
            except (AttributeError,tk.TclError):pass
        for item in self.items:
            if item['widget'] in self.overflow_widgets and item['overflow'] and item['overflow'].sync:
                proxy=self.overflow_proxy(item['widget'])
                if proxy is not None:item['overflow'].sync(self,item['widget'],proxy)
        if self._sync_job is None:self._sync_job=self._popover.after(100,self._sync_tick)

    def _sync_tick(self):
        self._sync_job=None;self.sync_overflow()

    def _popover_focus_out(self,event=None):
        if self._popover_focus_job is None:self._popover_focus_job=self.after_idle(self._check_popover_focus)

    def _check_popover_focus(self):
        self._popover_focus_job=None
        popup=self._popover
        if popup is None:return
        try:
            focus=self.focus_get();focus_path=str(self.tk.call('focus') or '')
        except tk.TclError:return
        if focus is not None and self._popover_contains(focus):return
        if focus_path:
            prefixes=[str(popup),*[str(w) for w in self.overflow_controls]]
            if any(focus_path==prefix or focus_path.startswith(prefix+'.') for prefix in prefixes):return
        self.close_overflow()

    def close_overflow(self,*,schedule=True):
        popup=self._popover;self._popover=None;self._unbind_overflow_outside()
        if self._sync_job is not None and popup is not None:
            try:popup.after_cancel(self._sync_job)
            except tk.TclError:pass
            self._sync_job=None
        if popup is not None and popup.winfo_exists():popup.destroy()
        if schedule:self._defer_flush()

    def destroy(self):
        if self.job:
            try:self.after_cancel(self.job)
            except tk.TclError:pass
        if self._flush_job:
            try:self.after_cancel(self._flush_job)
            except tk.TclError:pass
        if self._popover_focus_job:
            try:self.after_cancel(self._popover_focus_job)
            except tk.TclError:pass
        self.close_overflow(schedule=False);super().destroy()

class AdaptiveGrid(ttk.Frame):
    def __init__(self,parent,*,minimum=170,maximum=310,max_columns=3,gap=8,**kw):
        super().__init__(parent,**kw)
        self.minimum=minimum;self.maximum=maximum;self.max_columns=max_columns;self.gap=gap
        self.items=[];self.columns=1;self.job=None;self._arrangement=None
        self.bind('<Configure>',self.schedule)
    def add(self,widget):
        self.items.append(widget);self.schedule();return widget
    def schedule(self,event=None):
        if self.job is None:self.job=self.after_idle(self._layout)
    def _layout(self):
        self.job=None
        if self.winfo_exists():self.arrange(self.winfo_width())
    def arrange(self,width=None):
        width=max(1,int(width if width is not None else self.winfo_width()))
        if not self.items:return
        gap=self.gap if width>=450 else max(3,self.gap//2)
        columns=max(1,min(self.max_columns,len(self.items),(width+gap)//(self.minimum+gap)))
        cell_width=min(self.maximum,max(1,(width-gap*(columns-1))//columns))
        heights=[max(1,w.winfo_reqheight()) for w in self.items]
        key=(width,columns,cell_width,tuple(heights),gap)
        self.columns=columns
        if key==self._arrangement:return
        self._arrangement=key;y=0
        for start in range(0,len(self.items),columns):
            row=self.items[start:start+columns];height=max(heights[start:start+columns])
            for col,w in enumerate(row):w.place(x=col*(cell_width+gap),y=y,width=cell_width,height=height)
            y+=height+gap
        self.configure(height=max(1,y-gap))
    def destroy(self):
        if self.job:
            try:self.after_cancel(self.job)
            except tk.TclError:pass
        super().destroy()

class FlowRow(ttk.Frame):
    """Wrap semantic control groups without truncating their primary actions."""
    def __init__(self,parent,gap=5,**kw):
        super().__init__(parent,**kw);self.items=[];self.gap=gap;self.job=None;self.last=None
        self.bind('<Configure>',self.schedule)
    def add(self,widget):self.items.append(widget);self.schedule();return widget
    def schedule(self,event=None):
        if self.job is None:self.job=self.after_idle(self.arrange)
    def arrange(self):
        self.job=None
        width=max(1,self.winfo_width());dims=tuple((w.winfo_reqwidth(),w.winfo_reqheight()) for w in self.items)
        key=(width,dims)
        if key==self.last:return
        self.last=key;x=y=row_h=0
        for w,(ww,hh) in zip(self.items,dims):
            ww=min(width,ww)
            if x and x+ww>width:y+=row_h+self.gap;x=row_h=0
            w.place(x=x,y=y,width=ww,height=hh);x+=ww+self.gap;row_h=max(row_h,hh)
        self.configure(height=max(1,y+row_h))
    def destroy(self):
        if self.job:
            try:self.after_cancel(self.job)
            except tk.TclError:pass
        super().destroy()
