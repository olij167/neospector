"""Queue-first playback lanes. Music and pictures share the same visible grammar."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk,simpledialog
from queue_model import ordered,current,mode_at,queue_position
from instrument_model import voice
import music_queue
from effects_engine import BLEND_MODES
from responsive_controls import FlowRow

class QueueLane(ttk.Frame):
    def __init__(self,parent,app,role):
        super().__init__(parent,padding=(4,3));self.app=app;self.role=role;self.selected=None;self.items=[];self.hits=[];self.drag=None;self.key=None
        self.follow=tk.BooleanVar(value=True);self.last_active=None
        self.now=tk.StringVar();self.next_text=tk.StringVar();self.source=tk.StringVar(value='queue');self.policy=tk.StringVar(value='finish')
        row=FlowRow(self,gap=3);row.pack(fill='x');self.toolbar=row
        source=ttk.Frame(row)
        if role!='Music':
            for label,mode in [('Queue','queue'),('Live…','camera')]:ttk.Radiobutton(source,text=label,variable=self.source,value=mode,command=lambda m=mode:app.queue_source(role,m)).pack(side='left')
            ttk.Button(source,text='Hold',width=5,command=lambda:app.hold_queue(role)).pack(side='left',padx=2)
            b=ttk.Combobox(source,textvariable=self.policy,values=['finish','repeat'],width=6,state='readonly');b.pack(side='left');b.bind('<<ComboboxSelected>>',lambda e:app.set_queue_policy(role,self.policy.get()))
        else:ttk.Label(source,text='MUSIC QUEUE',style='Title.TLabel').pack(side='left',padx=3)
        row.add(source)
        if role!='Music':
            self.enabled=tk.BooleanVar(value=role=='A')
            row.add(ttk.Checkbutton(row,text='Enabled',variable=self.enabled,command=lambda:app.set_role_enabled(role,self.enabled.get())))
        row.add(ttk.Button(row,text='Add from Library',command=self.add))
        row.add(ttk.Button(row,text='Next ▶',width=7,command=self.next))
        row.add(ttk.Button(row,text='Shuffle',command=self.shuffle))
        row.add(ttk.Button(row,text='Randomise Queue',command=lambda:app.randomise_playable('queues',only_role=role)))
        row.add(ttk.Button(row,text='Item options…',command=self.options))
        row.add(ttk.Checkbutton(row,text='Follow',variable=self.follow,command=lambda:self.refresh(True)))
        summary=ttk.Frame(self);summary.pack(fill='x',pady=3)
        self.current_label=ttk.Label(summary,textvariable=self.now,style='Current.TLabel',anchor='w',wraplength=290);self.current_label.pack(fill='x',pady=(2,3))
        self.next_label=ttk.Label(summary,textvariable=self.next_text,style='Muted.TLabel',anchor='w',wraplength=290);self.next_label.pack(fill='x',pady=(0,3))
        self.current_label.bind('<Button-1>',lambda e:self.select(self.current_id) if getattr(self,'current_id',None) else None)
        self.next_label.bind('<Button-1>',lambda e:self.select(self.next_id) if getattr(self,'next_id',None) else None)
        summary.bind('<Configure>',lambda e:(self.current_label.configure(wraplength=max(120,e.width-8)),self.next_label.configure(wraplength=max(120,e.width-8))))
        ttk.Label(self,text='UPCOMING · select to inspect',style='Muted.TLabel').pack(anchor='w')
        body=ttk.Frame(self);body.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(body,height=120,highlightthickness=0,takefocus=True);self.canvas.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(body,orient='vertical',command=self.scroll);scroll.pack(side='right',fill='y');self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.bind('<Configure>',lambda e:self.refresh(True));self.canvas.bind('<Button-1>',self.press);self.canvas.bind('<Double-1>',lambda e:self.duration());self.canvas.bind('<Button-3>',self.options);self.canvas.bind('<Return>',lambda e:self.duration());self.canvas.bind('<Delete>',lambda e:self.remove())
        self.canvas.bind('<MouseWheel>',lambda e:self.wheel(-1 if e.delta>0 else 1));self.canvas.bind('<Button-4>',lambda e:self.wheel(-1));self.canvas.bind('<Button-5>',lambda e:self.wheel(1))
    def shuffle(self):
        from playable_queues import shuffle_future
        count=self.app.transaction('Shuffle eligible future',lambda:shuffle_future(self.app.project,self.role,now=self.app.playhead,seed=self.app.project.mutation_seed+1))
        self.app.update_status(f'Shuffled {count or 0} compatible future slots · current, pinned and manual items preserved. Unequal timings stay fixed.')
    def pin(self):
        from playable_queues import pin_occurrence
        item=self.find()
        if item is None:return
        pinned=item.get('pinned',False) if self.role=='Music' else item.extra.get('playable_pin',False)
        self.app.transaction('Pin occurrence',lambda:pin_occurrence(self.app.project,self.role,self.selected,not pinned))
    def ident(self,e):return e['id'] if self.role=='Music' else e.id
    def aid(self,e):return e['asset_id'] if self.role=='Music' else e.asset_id
    def dur(self,e):return e['duration'] if self.role=='Music' else e.duration
    def start(self,e):return e['start'] if self.role=='Music' else e.start
    def scroll(self,*args):self.follow.set(False);self.canvas.yview(*args);self.refresh(True)
    def wheel(self,n):self.follow.set(False);self.canvas.yview_scroll(n,'units');self.refresh(True);return 'break'
    def add(self):
        if self.role=='Music':self.app.queue_sound_selected()
        else:self.app.queue_selected(self.role)
    def next(self):
        if self.role=='Music':
            t=self.app.playhead;e=next((e for e in self.items if self.start(e)>t+.01),None)
            if e:self.app.music_take(self.ident(e))
            else:self.app.update_status('Music queue is at its end. Add a track from the Library.')
        else:self.app.queue_next(self.role)
    def play_selected(self):
        if self.selected:
            if self.role=='Music':self.app.music_take(self.selected)
            else:self.app.queue_next(self.role,self.selected)
    def find(self):return next((e for e in self.items if self.ident(e)==self.selected),None)
    def remove(self):
        if not self.selected:return
        if self.role=='Music':self.app.music_edit('Remove track',music_queue.remove,self.selected)
        else:self.app.queue_remove(self.role,self.selected)
    def duration(self):
        e=self.find()
        if e is None:return
        value=simpledialog.askfloat('Duration','Seconds for this occurrence',initialvalue=self.dur(e),minvalue=1/self.app.project.fps,parent=self.app)
        if value is not None:
            if self.role=='Music':self.app.music_edit('Track duration',music_queue.duration,self.selected,value)
            else:self.app.queue_duration(self.selected,value)
    def move_selected(self,index):
        if not self.selected:return
        if self.role=='Music':self.app.music_edit('Reorder music',music_queue.move,self.selected,index)
        else:self.app.queue_move(self.role,self.selected,index)
    def transition(self,cid=None):
        cid=cid or self.selected
        if not cid:return
        if self.role=='Music':
            value=simpledialog.askfloat('Audio transition','Crossfade into the next track (seconds). Zero is a cut.',initialvalue=1,minvalue=0,parent=self.app)
            if value is not None:self.app.music_edit('Music crossfade',music_queue.transition,cid,value)
        else:self.app.queue_transition(self.role,cid);self.app.deck.refresh(True)
    def options(self,event=None):
        if event:
            hit=self.hit(event.x,event.y)
            if hit:self.select(hit[0])
        e=self.find()
        if e is None:return self.app.update_status('Select a queue card first. Double-click its duration to fine-tune.')
        index=self.items.index(e);m=tk.Menu(self,tearoff=False)
        for text,fn in [('Play this now',self.play_selected),('Duration…',self.duration),('Transition to next…',self.transition),('Move earlier',lambda:self.move_selected(index-1)),('Move later',lambda:self.move_selected(index+1)),('Pin / unpin',self.pin),('Remove occurrence',self.remove)]:m.add_command(label=text,command=fn)
        if self.role!='Music':
            m.add_separator()
            for text,fn in [('Replace with Library selection',lambda:self.app.replace_queue_clip(self.role,self.selected)),('Insert Library selection before',lambda:self.app.queue_selected(self.role,before=self.selected)),('Insert Library selection after',lambda:self.app.queue_selected(self.role,after=self.selected)),('Clip effects / exact parameters…',self.details)]:m.add_command(label=text,command=fn)
        else:m.add_command(label='Detailed soundtrack events…',command=self.app.soundtrack_dialog)
        from contextual_surface import post_native_menu
        post_native_menu(self.app,m,self.canvas if event else self,event)
    def details(self):
        if self.role=='Music':return self.app.soundtrack_dialog()
        e=self.find()
        if e:self.app.selected_layer_id=voice(self.app.project,self.role).id;self.app.selected_clip_id=e.id;self.app.follow_playhead.set(False);self.app.deck.scope.set('Clip');self.app.deck.refresh(True)
    def hit(self,x,y=0):
        y=self.canvas.canvasy(y)
        return next((h for h in self.hits if h[1]<=y<h[2]),None)
    def select(self,cid):
        self.selected=cid
        # Inspection never redirects the rack or takes an occurrence live.
        self.refresh(True)
    def press(self,e):
        self.canvas.focus_set();hit=self.hit(e.x,e.y)
        if hit:self.select(hit[0])
    def refresh(self,force=False):
        p=self.app.project;t=self.app.playhead;l=None;active=[]
        if self.role=='Music':
            self.items=music_queue.items(p);cursor=t;active=[e for e in self.items if e['start']<=t<e['start']+e['duration']];on=active[-1] if active else None
        else:
            l=next((l for l in p.layers if l.extra.get('voice')==self.role),None)
            if not l:self.now.set('Legacy composition · use Timing');self.items=[];return
            self.enabled.set(l.enabled and self.role in __import__('playable_intent').load_intent(p)['enabled_roles']);self.items=ordered(l);cursor=queue_position(l,t);on=current(l,t);active=[e for e in self.items if e.start<=cursor<e.end]
            mode=mode_at(l,t);self.source.set('camera' if mode['mode']=='camera' else 'queue');self.policy.set(l.extra.get('queue_policy','finish'))
        def title(e):
            a=p.asset(self.aid(e)) if e else None
            return a.name if a else ('Source unavailable' if e else '—')
        future=[e for e in self.items if self.start(e)>cursor+.001];nxt=future[0] if future else None
        self.current_id=self.ident(on) if on else None;self.next_id=self.ident(nxt) if nxt else None
        live_asset=p.asset(mode_at(l,t).get('camera_id','')) if l and self.source.get()=='camera' else None
        self.now.set('CURRENT  '+((live_asset.name if live_asset else 'Live source')+' · queue retained' if l and self.source.get()=='camera' else ' ↔ '.join(title(e) for e in active) or '—'))
        self.next_text.set('NEXT  '+title(nxt))
        if not self.winfo_ismapped() and not force:return
        cv=self.canvas;width=max(160,cv.winfo_width());top=cv.canvasy(0)
        key=(self.app.revision,width,int(top//46),tuple(self.ident(e) for e in future),self.selected,tuple(self.app.ui_chrome.items()))
        if key==self.key and not force:return
        self.key=key;self.hits=[];cv.delete('all');c=self.app.ui_chrome;cv.configure(bg=c['preview_bg'])
        if not future:cv.create_text(9,20,text='No upcoming items · Add or Randomise Queue',anchor='w',width=width-18,fill=c['muted_fg'])
        first=max(0,int(top//46)-1);last=min(len(future),first+max(8,int(cv.winfo_height()/46)+3))
        for n in range(first,last):
            e=future[n];cid=self.ident(e);y=3+n*46;selected=cid==self.selected
            cv.create_rectangle(4,y,width-4,y+41,fill=c['field_bg'],outline=c['accent'] if selected else c['panel_edge'],width=2 if selected else 1)
            pinned=e.get('pinned',False) if self.role=='Music' else e.locked or e.extra.get('playable_pin')
            cv.create_text(12,y+12,text=('PIN · ' if pinned else '')+title(e),width=width-24,anchor='w',fill=c['foreground'],font=('TkDefaultFont',9,'bold'))
            cv.create_text(12,y+30,text=f'{self.start(e):.1f}s · {self.dur(e):.1f}s'+(' · NEXT' if n==0 else ''),anchor='w',fill=c['muted_fg'],font=('TkDefaultFont',9))
            self.hits.append((cid,y,y+41,'clip'))
        cv.configure(scrollregion=(0,0,width,max(60,len(future)*46+6)))

class PlaybackQueues(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;self.tabs=ttk.Notebook(self,style='Queue.TNotebook');self.tabs.pack(fill='both',expand=True);self.pages={}
        self.sound=QueueLane(self.tabs,app,'Music');self.pages['Music']=self.sound;self.tabs.add(self.sound,text='Music')
        self.visuals=ttk.Frame(self.tabs);self.tabs.add(self.visuals,text='Visuals')
        front=FlowRow(self.visuals);front.pack(fill='x');self.sequence=tk.BooleanVar(value=True)
        front.add(ttk.Checkbutton(front,text='Sequence ON',variable=self.sequence,command=lambda:app.set_sequence_enabled(self.sequence.get())))
        front.add(ttk.Button(front,text='Reveal Camera',command=app.reveal_camera))
        self.roles=ttk.Notebook(self.visuals,style='Queue.TNotebook');self.roles.pack(fill='both',expand=True)
        background=ttk.Frame(self.roles);self.roles.add(background,text='Background')
        
        for role in ('C','D'):
            lane=QueueLane(self.roles,app,role);self.pages[role]=lane;self.roles.add(lane,text=role)
        self.background_tabs=ttk.Notebook(background,style='Queue.TNotebook');self.background_tabs.pack(fill='both',expand=True)
        for role in ('A','B'):
            lane=QueueLane(self.background_tabs,app,role);self.pages[role]=lane;self.background_tabs.add(lane,text='Channel '+role)
        for book in (self.tabs,self.roles,self.background_tabs):book.bind('<<NotebookTabChanged>>',lambda e:self.refresh(True))
    def refresh(self,force=False):
        p=self.app.project;t=self.app.playhead
        self.sequence.set(any(l.enabled and l.extra.get('voice') in ('A','B','C','D') for l in p.layers))
        try:
            events=music_queue.items(p);active=[e for e in events if e['start']<=t<e['start']+e['duration']];nxt=next((e for e in events if e['start']>t),None)
            def name(e):
                a=p.asset(e['asset_id']) if e else None
                return a.name if a else ('Missing' if e else '—')
            music='Music: '+(' ↔ '.join(name(e) for e in active) or '—')+' → '+name(nxt)
        except ValueError:music='Music: missing source · Locate to repair'
        if hasattr(self.app,'music_transport_caption'):self.app.music_transport_caption.set(music)
        visual=[]
        for role in ('A','B'):
            l=next((l for l in p.layers if l.extra.get('voice')==role),None)
            e=current(l,t) if l and l.enabled else None;a=p.asset(e.asset_id) if e else None
            visual.append(role+': '+(a.name if a else '—'))
        if hasattr(self.app,'transport_queue_caption'):self.app.transport_queue_caption.set('Background · '+' + '.join(visual))
        for page in self.pages.values():
            try:page.refresh(force)
            except ValueError:page.now.set('Missing source · Locate to repair')
