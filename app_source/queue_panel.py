"""Current / Next / Upcoming over the same editable occurrences as the timeline."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk,simpledialog
from queue_model import ordered,current,mode_at,queue_position
from instrument_model import voice
from sound_panel import SourceMixer
from contextual_surface import post_native_menu

class VoiceQueue(ttk.Frame):
    def __init__(self,parent,app,role):
        super().__init__(parent,padding=5);self.app=app;self.role=role;self.key=None;self.drag=None;self.items=[];self.selected=None;self.positions=[];self.source=tk.StringVar(value='queue');self.policy=tk.StringVar(value='finish')
        row=ttk.Frame(self);row.pack(fill='x',pady=(1,5));ttk.Radiobutton(row,text='Queue',value='queue',variable=self.source,command=lambda:app.queue_source(role,'queue')).pack(side='left');ttk.Radiobutton(row,text='Camera',value='camera',variable=self.source,command=lambda:app.quick_camera(role)).pack(side='left',padx=4)
        ttk.Button(row,text='Device…',width=8,command=self.camera_device).pack(side='right')
        row=ttk.Frame(self);row.pack(fill='x');ttk.Button(row,text='Add',width=6,command=lambda:app.queue_selected(role)).pack(side='left');ttk.Button(row,text='Generate',width=9,command=lambda:app.generate_queue(role)).pack(side='left',padx=2);self.hold=ttk.Button(row,text='Loop current',command=lambda:app.hold_queue(role));self.hold.pack(side='left',padx=2);ttk.Button(row,text='Next ▶',width=7,command=lambda:app.queue_next(role)).pack(side='right')
        self.now=tk.StringVar(value='Choose media or turn on Camera');ttk.Label(self,textvariable=self.now,wraplength=285,style='Muted.TLabel',justify='left').pack(fill='x',pady=6)
        body=ttk.Frame(self);body.columnconfigure(0,weight=1);body.rowconfigure(0,weight=1)
        self.canvas=tk.Canvas(body,highlightthickness=0,takefocus=True);self.canvas.grid(row=0,column=0,sticky='nsew');bar=ttk.Scrollbar(body,command=self.scroll_to);bar.grid(row=0,column=1,sticky='ns');self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.bind('<Configure>',lambda e:self.refresh(True));self.canvas.bind('<ButtonPress-1>',self.press);self.canvas.bind('<B1-Motion>',self.motion);self.canvas.bind('<ButtonRelease-1>',self.release);self.canvas.bind('<Button-3>',self.menu);self.canvas.bind('<Double-1>',self.details);self.canvas.bind('<Delete>',lambda e:app.queue_remove(role,self.selected));self.canvas.bind('<Return>',lambda e:self.edit_duration());self.canvas.bind('<MouseWheel>',lambda e:self.scroll(-int(e.delta/120) or (-1 if e.delta>0 else 1)));self.canvas.bind('<Button-4>',lambda e:self.scroll(-2));self.canvas.bind('<Button-5>',lambda e:self.scroll(2))
        row=ttk.Frame(self);row.pack(fill='x',pady=4);ttk.Button(row,text='Play now',command=lambda:app.queue_next(role,self.selected)).pack(side='left');self.remove_button=ttk.Button(row,text='Remove',command=lambda:app.queue_remove(role,self.selected));self.remove_button.pack(side='left',padx=2);ttk.Button(row,text='Duration',command=self.edit_duration).pack(side='left',padx=2);ttk.Button(row,text='⋯',width=3,command=self.menu).pack(side='right')
        policy=ttk.Frame(self);policy.pack(fill='x');ttk.Label(policy,text='Queue end',style='Muted.TLabel').pack(side='left');box=ttk.Combobox(policy,textvariable=self.policy,values=['Finish','Loop queue'],width=12,state='readonly');box.pack(side='left',padx=4);box.bind('<<ComboboxSelected>>',lambda e:app.set_queue_policy(role,'repeat' if self.policy.get()=='Loop queue' else 'finish'));ttk.Button(policy,text='Timing view',command=app.toggle_precision).pack(side='right')
        body.pack(fill='both',expand=True,before=row)
        # Reserve the action strips before offering remaining space to the canvas.
        row.pack_forget();policy.pack_forget();body.pack_forget()
        policy.pack(side='bottom',fill='x');row.pack(side='bottom',fill='x',pady=4);body.pack(fill='both',expand=True)
        self.refresh(True)
    def layer(self):return next((l for l in self.app.project.layers if l.extra.get('voice')==self.role),None)
    def camera_device(self):
        v=simpledialog.askstring('Camera device','Device path / name / index. This is shared by the visual voices.',initialvalue=getattr(self.app,'last_camera_device','/dev/video0'),parent=self.app)
        if v:self.app.quick_camera(self.role,v)
    def scroll_to(self,*args):self.canvas.yview(*args);self.refresh(True)
    def scroll(self,n):self.canvas.yview_scroll(n,'units');self.refresh(True);return 'break'
    def row_at(self,y):
        y=self.canvas.canvasy(y)
        return next((c for top,bottom,c in self.positions if top<=y<bottom),None)
    def select(self,c):
        if not c:return
        self.selected=c.id;self.app.selected_layer_id=self.layer().id;self.app.selected_clip_id=c.id;self.app.follow_playhead.set(False);self.app.deck.scope.set('Clip');self.app.deck.refresh(True);self.canvas.focus_set();self.refresh(True)
    def press(self,event):
        c=self.row_at(event.y)
        if not c:return
        self.select(c);self.drag=(c.id,event.x,event.y)
    def motion(self,event):
        if not self.drag or abs(event.y-self.drag[2])<8:return
        self.canvas.delete('insertion');y=self.canvas.canvasy(event.y);self.canvas.create_line(0,y,self.canvas.winfo_width(),y,fill=self.app.ui_chrome['accent'],width=3,tags='insertion')
    def release(self,event):
        drag=self.drag;self.drag=None;self.canvas.delete('insertion')
        if drag and abs(event.y-drag[2])>8:
            c=self.row_at(event.y)
            if c:self.app.queue_move(self.role,drag[0],next(i for i,x in enumerate(self.items) if x.id==c.id))
    def details(self,event):
        c=self.row_at(event.y)
        if c:self.select(c);self.edit_duration()
    def edit_duration(self):
        l=self.layer();c=next((c for c in l.clips if c.id==self.selected),None) if l else None
        if c:
            value=simpledialog.askfloat('Occurrence duration','Seconds in this queue. Source trim remains separate.',initialvalue=c.duration,minvalue=1/self.app.project.fps,parent=self.app)
            if value is not None:self.app.queue_duration(c.id,value)
    def menu(self,event=None):
        if event:
            c=self.row_at(event.y)
            if c:self.select(c)
        l=self.layer();c=next((c for c in l.clips if c.id==self.selected),None) if l else None
        if not c:return
        m=tk.Menu(self,tearoff=False)
        actions=[('Replace media, keep treatment',lambda:self.app.replace_queue_clip(self.role,c.id)),('Add selected media before',lambda:self.app.queue_selected(self.role,before=c.id)),('Add selected media after',lambda:self.app.queue_selected(self.role,after=c.id)),('Earlier',lambda:self.app.queue_move(self.role,c.id,self.items.index(c)-1)),('Later',lambda:self.app.queue_move(self.role,c.id,self.items.index(c)+1)),('Transition to next…',lambda:self.app.queue_transition(self.role,c.id)),('Unpin' if c.locked else 'Pin against changes',lambda:self.app.transaction('Queue pin',lambda:setattr(c,'locked',not c.locked))),('Remove occurrence',lambda:self.app.queue_remove(self.role,c.id))]
        for title,command in actions:m.add_command(label=title,command=command)
        post_native_menu(self.app,m,self.canvas if event else self,event)
    def refresh(self,force=False):
        l=self.layer()
        if not l:self.now.set('Legacy composition · use Timing view');return
        t=self.app.programme_time() if self.app.playing and not self.app.reviewing else self.app.playhead;s=mode_at(l,t);self.source.set('camera' if s['mode']=='camera' else 'queue');self.policy.set('Loop queue' if l.extra.get('queue_policy')=='repeat' else 'Finish');self.hold.configure(text='Resume sequence' if s['mode']=='hold' else 'Loop current');active=current(l,t);qtime=queue_position(l,t)
        self.remove_button.configure(state='normal' if self.selected and any(c.id==self.selected for c in l.clips) else 'disabled')
        asset=self.app.project.asset(active.asset_id) if active else None
        if s['mode']=='camera':self.now.set('CAMERA LIVE  ·  queue held at '+f'{qtime:.1f}s')
        elif asset:self.now.set(('LOOP CURRENT  ·  ' if s['mode']=='hold' else 'QUEUE CURRENT  ·  ')+asset.name+'\n'+f'{max(0,qtime-active.start):.1f} / {active.duration:.1f}s')
        else:self.now.set('Choose media from the Library, or Camera above.')
        items=ordered(l);width=max(150,self.canvas.winfo_width());viewport_row=max(0,int(self.canvas.canvasy(0)//86));key=(id(l),width,viewport_row,tuple((c.id,c.asset_id,c.duration,c.start,c.locked) for c in items),tuple((tr.id,tr.kind,tr.duration) for tr in l.transitions),self.selected,tuple((c.asset_id,id(self.app.thumbnails.get(c.asset_id))) for c in items[:80]),active.id if active else None,s['mode'],tuple(sorted(self.app.ui_chrome.items())))
        if not force and key==self.key:
            if active:self.canvas.coords('progress',3,3,width*max(0,min(1,(qtime-active.start)/active.duration)),3)
            return
        self.key=key;self.items=items;self.canvas.delete('all');self.positions=[];chrome=self.app.ui_chrome;self.canvas.configure(bg=chrome['preview_bg']);y=10
        # Lists page naturally through a canvas. Only near-visible thumbnails decode.
        top=self.canvas.canvasy(0);bottom=top+max(200,self.canvas.winfo_height())
        first=max(0,int((top-10)//86)-1);last=min(len(items),int((bottom-10)//86)+3)
        active_index=next((i for i,c in enumerate(items) if active and c.id==active.id),-2)
        transition_map={(tr.from_clip,tr.to_clip):tr for tr in l.transitions}
        for i in range(first,last):
            c=items[i];y=10+i*86;h=60;a=self.app.project.asset(c.asset_id);picked=c.id==self.selected;on=active is not None and c.id==active.id and s['mode']!='camera'
            fill=chrome.get('field_bg',chrome['preview_bg']);border=chrome['accent'] if picked or on else chrome.get('border',chrome['muted_fg'])
            self.canvas.create_rectangle(2,y,width-4,y+h,fill=fill,outline=border,width=2 if picked else 1)
            if a:
                photo=getattr(self.app,'small_thumbnails',{}).get(a.id)
                if photo:self.canvas.create_image(9,y+12,anchor='nw',image=photo)
                elif top-120<y<bottom+120:self.app.request_thumbnail(a)
            self.canvas.create_text(55,y+12,anchor='nw',text=(a.name if a else 'Missing source')[:48],width=max(70,width-80),fill=chrome.get('fg',chrome.get('text_fg','#fff')),font=('TkDefaultFont',10,'bold'))
            hint=('LOOP CURRENT · ' if on and s['mode']=='hold' else 'CURRENT · ' if on else 'NEXT · ' if active and i==active_index+1 else '')+f'{c.duration:.2g}s'+(' · PINNED' if c.locked else '')
            self.canvas.create_text(55,y+40,anchor='w',text=hint,fill=chrome['muted_fg'],font=('TkDefaultFont',9));self.positions.append((y,y+h,c));y+=h
            if i<len(items)-1:
                tr=transition_map.get((c.id,items[i+1].id))
                tag='tr-'+c.id;self.canvas.create_rectangle(45,y+2,width-45,y+22,fill=chrome.get('field_bg',chrome['preview_bg']),outline=chrome['muted_fg'],tags=tag)
                self.canvas.create_text(width/2,y+12,text=(tr.kind.replace('_',' ')+' · '+f'{tr.duration:.2g}s') if tr else '+ Transition',fill=chrome['accent'],font=('TkDefaultFont',9),tags=tag);self.canvas.tag_bind(tag,'<Button-1>',lambda e,cid=c.id:self.app.queue_transition(self.role,cid));y+=26
        if not items:self.canvas.create_text(width/2,45,text='Your queue is empty.\n\nAdd selected Library media\nor Generate a sequence.',width=width-28,fill=chrome['muted_fg'],justify='center')
        self.canvas.create_line(3,3,3,3,fill=chrome['accent'],width=3,tags='progress');self.canvas.configure(scrollregion=(0,0,width,max(150,20+86*len(items))))

class QueueDeck(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;ttk.Label(self,text='SOURCES  /  QUEUES',style='Title.TLabel',padding=(4,3)).pack(anchor='w')
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True);self.voices={}
        for role in ('A','B','C','D'):
            q=VoiceQueue(self.tabs,app,role);self.tabs.add(q,text=role);self.voices[role]=q
        self.sound=SourceMixer(self.tabs,app);self.tabs.add(self.sound,text='Sound');self.tabs.bind('<<NotebookTabChanged>>',self.select)
    def select(self,event=None):
        selected=self.tabs.select()
        for role,q in self.voices.items():
            if str(q)==selected and hasattr(self.app,'deck'):self.app.focus_voice(role)
    def refresh(self,force=False):
        selected=self.tabs.select()
        for q in self.voices.values():
            if selected==str(q):q.refresh(force)
