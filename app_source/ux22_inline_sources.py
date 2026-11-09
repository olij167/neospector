"""UX22 explicit inline camera / screen source setup; no popup or auto-capture.

Screen descriptions use the same validated X11 capture descriptor as the old
window chooser. Cropping is displayed as a draggable normalized rectangle.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

class InlineSourceSettings(ttk.Frame):
    def __init__(self,parent,app,role):
        super().__init__(parent,padding=(6,5))
        self.app=app;self.role=role;self.mode=tk.StringVar(value='Queue')
        self.status=tk.StringVar(value='Select a source, then choose Use')
        self.sources=[];self.values={k:tk.DoubleVar(value=v) for k,v in zip('xywh',(0.,0.,100.,100.))}
        self.frame_open=False;self._drag_start=None
        bar=ttk.Frame(self);bar.pack(fill='x')
        self.title=ttk.Label(bar,text='SOURCE',style='PlayerName.TLabel');self.title.pack(side='left')
        ttk.Button(bar,text='×',width=3,command=lambda:app.queue_deck.pages[role].show_inline_source('queue')).pack(side='right')
        self.source_name=tk.StringVar(value='')
        self.source_picker=ttk.Combobox(self,textvariable=self.source_name,state='readonly',width=21)
        self.source_picker.pack(fill='x',pady=(5,3))
        self.source_picker.bind('<<ComboboxSelected>>',lambda _e:self.source_changed())
        self.crop_toggle=ttk.Button(self,text='▸ Frame / crop',command=self.toggle_crop)
        self.crop_canvas=tk.Canvas(self,height=92,bg='#101926',highlightthickness=1,highlightbackground='#536980')
        self.crop_canvas.bind('<Configure>',lambda e:self.paint_crop())
        self.crop_canvas.bind('<ButtonPress-1>',self.begin_crop)
        self.crop_canvas.bind('<B1-Motion>',self.move_crop)
        self.crop_canvas.bind('<ButtonRelease-1>',self.move_crop)
        self.crop_fields=ttk.Frame(self)
        for i,(key,label) in enumerate((('x','LEFT'),('y','TOP'),('w','WIDTH'),('h','HEIGHT'))):
            box=ttk.Frame(self.crop_fields);box.grid(row=0,column=i,sticky='ew',padx=1)
            ttk.Label(box,text=label,style='Muted.TLabel').pack()
            entry=ttk.Entry(box,textvariable=self.values[key],width=5,justify='center');entry.pack(fill='x')
            entry.bind('<Return>',lambda _e:self.paint_crop())
            self.crop_fields.columnconfigure(i,weight=1)
        self.fps=tk.StringVar(value='20');self.cursor=tk.BooleanVar(value=True)
        settings=ttk.Frame(self.crop_fields);settings.grid(row=1,column=0,columnspan=4,sticky='ew',pady=(4,0))
        ttk.Label(settings,text='FPS').pack(side='left')
        ttk.Combobox(settings,textvariable=self.fps,values=('10','15','20','30'),width=4,state='readonly').pack(side='left',padx=4)
        ttk.Checkbutton(settings,text='Pointer',variable=self.cursor).pack(side='left',padx=3)
        ttk.Button(settings,text='Full frame',command=self.reset_crop).pack(side='right')
        self.status_label=ttk.Label(self,textvariable=self.status,style='Muted.TLabel',wraplength=300)
        self.status_label.pack(fill='x',pady=(2,3))
        actions=ttk.Frame(self);actions.pack(fill='x',pady=(2,0))
        self.refresh_button=ttk.Button(actions,text='↻ Find sources',command=self.discover)
        self.refresh_button.pack(side='left')
        self.use_button=ttk.Button(actions,text=f'▶ Use on {role}',style='Accent.TButton',command=self.use)
        self.use_button.pack(side='right')
        self.source_picker.configure(values=())
    def show(self,mode):
        self.mode.set('Camera' if mode=='camera' else 'Screen / Window')
        self.title.configure(text=self.mode.get().upper()+' · CHANNEL '+self.role)
        self.crop_toggle.pack_forget();self.crop_fields.pack_forget();self.crop_canvas.pack_forget()
        if mode=='screen':self.crop_toggle.pack(fill='x',pady=(3,0),before=self.status_label)
        self.frame_open=False;self.reset_crop();self.discover()
    def discover(self):
        mode=self.mode.get()
        try:
            if mode=='Camera':
                from live_sources import enumerate_devices
                found=enumerate_devices().get('camera',[])
                # The camera API accepts identifiers including 'default'.
                self.sources=['default']+[d for d in found if d!='default']
                names=[str(d) for d in self.sources]
            else:
                from visual_capture import list_sources
                self.sources=list_sources();names=[('Screen · ' if d['kind']=='screen' else 'Window · ')+d['name'] for d in self.sources]
            self.source_picker.configure(values=names)
            if names:self.source_picker.current(0);self.status.set('Choose a source. Browsing does not start capture.')
            else:self.source_name.set('');self.status.set('No sources available · check devices or permissions')
        except Exception as exc:
            self.sources=[];self.source_picker.configure(values=());self.source_name.set('');self.status.set('Could not list sources: '+str(exc))
    def selected(self):
        index=self.source_picker.current()
        return self.sources[index] if 0<=index<len(self.sources) else None
    def source_changed(self):
        self.reset_crop()
        chosen=self.selected()
        if chosen is not None:self.status.set('Source selected · capture is not yet active')
    def toggle_crop(self):
        if self.mode.get()=='Camera':return
        self.frame_open=not self.frame_open
        self.crop_toggle.configure(text='▾ Frame / crop' if self.frame_open else '▸ Frame / crop')
        if self.frame_open:
            self.crop_canvas.pack(fill='x',pady=(3,0),before=self.status_label);self.crop_fields.pack(fill='x',pady=3,before=self.status_label);self.paint_crop()
        else:self.crop_canvas.pack_forget();self.crop_fields.pack_forget()
        if hasattr(self.app,'sidebar'):
            self.app.sidebar.request_fit();self.app.shell.schedule()
    def reset_crop(self):
        for k,v in zip('xywh',(0.,0.,100.,100.)):self.values[k].set(v)
        self.paint_crop()
    def paint_crop(self):
        cv=self.crop_canvas;cv.delete('all');w=max(100,cv.winfo_width());h=max(90,cv.winfo_height());pad=10
        cv.create_rectangle(pad,pad,w-pad,h-pad,outline='#718ba4',fill='#233447',width=1)
        try:
            x,y,cw,ch=[self.values[k].get()/100. for k in 'xywh']
            cv.create_rectangle(pad+x*(w-2*pad),pad+y*(h-2*pad),pad+(x+cw)*(w-2*pad),pad+(y+ch)*(h-2*pad),outline='#79b8fa',width=3)
        except (tk.TclError,ValueError):pass
    def begin_crop(self,event):self._drag_start=(event.x,event.y)
    def move_crop(self,event):
        if not self._drag_start:return
        w=max(100,self.crop_canvas.winfo_width());h=max(90,self.crop_canvas.winfo_height());pad=10
        def norm(xx,yy):return max(0,min(1,(xx-pad)/(w-2*pad))),max(0,min(1,(yy-pad)/(h-2*pad)))
        a,b=norm(*self._drag_start);c,d=norm(event.x,event.y)
        for k,v in zip('xywh',(100*min(a,c),100*min(b,d),100*abs(c-a),100*abs(d-b))):self.values[k].set(round(v,1))
        self.paint_crop()
        if event.type==tk.EventType.ButtonRelease:self._drag_start=None
    def use(self):
        source=self.selected()
        if source is None:return self.status.set('Choose an available source first')
        try:
            if self.mode.get()=='Camera':
                self.app.toggle_channel_camera(self.role,source)
            else:
                from visual_capture import describe
                box=tuple(self.values[k].get()/100 for k in 'xywh')
                descriptor=describe(source,box,int(self.fps.get()),self.cursor.get())
                self.app.toggle_channel_camera(self.role,descriptor)
            self.app.queue_deck.pages[self.role].close_inline_source()
        except (ValueError,KeyError,RuntimeError,tk.TclError) as exc:self.status.set(str(exc))
