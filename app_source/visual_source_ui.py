"""Explicit visual-source chooser, crop preview and channel commit."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from PIL import ImageTk
from visual_capture import list_sources,describe,VisualCapture


def show(app,role):
    old=getattr(app,'visual_source_window',None)
    if old and old.winfo_exists():old.lift();old.focus_set();return old
    win=tk.Toplevel(app);app.visual_source_window=win;win.title(f'Screen or Window → {role}');win.transient(app)
    win.geometry('760x650');win.minsize(620,510)
    project_id=app.project.id
    body=ttk.Frame(win,padding=12);body.pack(fill='both',expand=True);body.columnconfigure(0,weight=1);body.rowconfigure(2,weight=1)
    ttk.Label(body,text=f'Choose what channel {role} sees',style='Title.TLabel').grid(row=0,column=0,sticky='w')
    status=tk.StringVar(value='Select an X11 screen or window. Preview begins only when you press Preview.')
    ttk.Label(body,textvariable=status,wraplength=720,justify='left').grid(row=1,column=0,sticky='ew',pady=(4,8))
    pane=ttk.Panedwindow(body,orient='horizontal');pane.grid(row=2,column=0,sticky='nsew')
    left=ttk.Frame(pane);right=ttk.Frame(pane);pane.add(left,weight=1);pane.add(right,weight=2)
    left.columnconfigure(0,weight=1);left.rowconfigure(0,weight=1)
    sources=ttk.Treeview(left,columns=('size',),show='tree headings',selectmode='browse',height=12)
    sources.heading('#0',text='Available now');sources.heading('size',text='Size');sources.column('#0',width=205);sources.column('size',width=88,stretch=False)
    sources.grid(row=0,column=0,sticky='nsew')
    cv=tk.Canvas(right,width=450,height=285,bg='#11131a',highlightthickness=0,cursor='crosshair');cv.pack(fill='both',expand=True)
    ttk.Label(right,text='Drag on the preview to crop. Fine tune with the percentages below. Only the crop enters Neospector.',wraplength=430,justify='left').pack(fill='x',pady=5)
    values={key:tk.StringVar(value=value) for key,value in zip('xywh',('0','0','100','100'))}
    fields=ttk.Frame(right);fields.pack(fill='x')
    for col,(key,label) in enumerate((('x','Left %'),('y','Top %'),('w','Width %'),('h','Height %'))):
        ttk.Label(fields,text=label).grid(row=0,column=col,sticky='w',padx=(0,5))
        entry=ttk.Entry(fields,textvariable=values[key],width=8);entry.grid(row=1,column=col,sticky='ew',padx=(0,5));fields.columnconfigure(col,weight=1)
        entry.bind('<Return>',lambda _e:draw_crop())
    fps=tk.StringVar(value='20');cursor=tk.BooleanVar(value=True)
    opts=ttk.Frame(right);opts.pack(fill='x',pady=(10,0))
    ttk.Label(opts,text='Frames/s').pack(side='left')
    ttk.Combobox(opts,textvariable=fps,values=('10','15','20','30'),state='readonly',width=5).pack(side='left',padx=(5,15))
    ttk.Checkbutton(opts,text='Show pointer',variable=cursor).pack(side='left')
    ttk.Label(right,text='Audio remains separate. A crop limits saved frames, but X11 may deliver the full selected source to the capture process.',wraplength=430,justify='left',style='Muted.TLabel').pack(fill='x',pady=(9,0))
    selected=[];preview=[None];image=[None];draw_bounds=[(0,0,1,1)];drag=[None];poll_id=[None]
    def close():
        if poll_id[0]:
            try:win.after_cancel(poll_id[0])
            except tk.TclError:pass
            poll_id[0]=None
        if preview[0]:preview[0].close();preview[0]=None
        win.destroy();app.visual_source_window=None
    def choose(_=None):
        item=sources.focus()
        if not item:return
        selected[:]=[options[int(item)]]
        if preview[0]:preview[0].close();preview[0]=None
        cv.delete('all');image[0]=None
        for key,value in zip('xywh',('0','0','100','100')):values[key].set(value)
        label=selected[0]['name']
        status.set(('This may include Neospector and create visual feedback. ' if selected[0]['kind']=='screen' or 'neospector' in label.lower() else '')+'Press Preview, adjust Crop, then Use in channel.')
    sources.bind('<<TreeviewSelect>>',choose)
    def box():return tuple(float(values[k].get())/100 for k in 'xywh')
    def draw_crop():
        try:
            if not selected:return
            d=describe(selected[0],box(),int(fps.get()),cursor.get())
            x,y,w,h=d['crop'];left,top,pw,ph=draw_bounds[0]
            cv.delete('crop');cv.create_rectangle(left+x*pw,top+y*ph,left+(x+w)*pw,top+(y+h)*ph,
                      outline='#e8d46a',width=2,tags='crop')
            status.set(f"Crop {d['crop_px'][2]}×{d['crop_px'][3]} → {d['frame_size'][0]}×{d['frame_size'][1]} · {d['fps']} fps")
            return d
        except (ValueError,KeyError) as exc:status.set(str(exc));return None
    def pointer(event):
        left,top,w,h=draw_bounds[0]
        return (max(0,min(1,(event.x-left)/w)),max(0,min(1,(event.y-top)/h)))
    def press(event):
        if preview[0]:drag[0]=pointer(event)
    def move(event):
        if drag[0] is None:return
        ax,ay=drag[0];bx,by=pointer(event)
        cv.delete('crop');left,top,w,h=draw_bounds[0]
        cv.create_rectangle(left+min(ax,bx)*w,top+min(ay,by)*h,left+max(ax,bx)*w,top+max(ay,by)*h,
                            outline='#e8d46a',width=2,tags='crop')
    def release(event):
        if drag[0] is None:return
        ax,ay=drag[0];bx,by=pointer(event);drag[0]=None
        for key,value in zip('xywh',(min(ax,bx),min(ay,by),abs(bx-ax),abs(by-ay))):values[key].set(f'{100*value:.1f}')
        draw_crop()
    cv.bind('<ButtonPress-1>',press);cv.bind('<B1-Motion>',move);cv.bind('<ButtonRelease-1>',release)
    def refresh():
        try:rows=list_sources()
        except Exception as exc:status.set(str(exc));rows=[]
        nonlocal options
        options=rows;sources.delete(*sources.get_children())
        for index,source in enumerate(rows):sources.insert('','end',iid=str(index),text=('Screen · ' if source['kind']=='screen' else 'Window · ')+source['name'],values=(f"{source['width']}×{source['height']}",))
        if rows:sources.selection_set('0');sources.focus('0');choose()
    options=[]
    def repaint():
        poll_id[0]=None
        if not win.winfo_exists() or not preview[0]:return
        cap=preview[0]
        if cap.state=='error':status.set('Source stopped: '+cap.error);return
        if cap.latest is not None:
            w=max(1,cv.winfo_width());h=max(1,cv.winfo_height());frame=cap.latest
            scale=min(w/frame.width,h/frame.height);pw=max(1,int(frame.width*scale));ph=max(1,int(frame.height*scale))
            left=(w-pw)//2;top=(h-ph)//2;draw_bounds[0]=(left,top,pw,ph)
            image[0]=ImageTk.PhotoImage(frame.resize((pw,ph)))
            cv.delete('picture');cv.create_image(left,top,image=image[0],anchor='nw',tags='picture');cv.tag_lower('picture')
            draw_crop()
        poll_id[0]=win.after(180,repaint)
    def start_preview():
        if not selected:return status.set('Choose a source first.')
        if preview[0]:preview[0].close();preview[0]=None
        try:
            # Preview the full chosen source so a tighter crop can be drawn.
            d=describe(selected[0],(0,0,1,1),int(fps.get()),cursor.get())
            preview[0]=VisualCapture(d)
            repaint()
        except Exception as exc:status.set(str(exc))
    def use():
        if app.project.id!=project_id:return status.set('The project changed. Close and reopen the chooser for its intended channel.')
        d=draw_crop()
        if d is None:return
        close();app.toggle_channel_camera(role,d)
    actions=ttk.Frame(body);actions.grid(row=3,column=0,sticky='ew',pady=(10,0))
    ttk.Button(actions,text='Refresh choices',command=refresh).pack(side='left')
    ttk.Button(actions,text='Preview selected',command=start_preview).pack(side='left',padx=5)
    ttk.Button(actions,text='Reset crop',command=lambda:[values[k].set(v) for k,v in zip('xywh',('0','0','100','100'))] and draw_crop()).pack(side='left')
    ttk.Button(actions,text='Cancel',command=close).pack(side='right')
    ttk.Button(actions,text=f'Use in {role}',style='Accent.TButton',command=use).pack(side='right',padx=5)
    win.protocol('WM_DELETE_WINDOW',close);win.bind('<Escape>',lambda _e:close())
    refresh();return win
