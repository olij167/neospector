"""Read-only temporal projection; clicking an event reveals its real owner."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from music_queue import items

class TimelineOverview(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(4,2));self.app=app;self.layer=tk.StringVar(value='Clips');self.job=None;self.key=None;self.hits=[]
        bar=ttk.Frame(self);bar.pack(fill='x')
        self.compact=False
        self.reveal=ttk.Button(bar,text='Overview ▾',command=lambda:self.set_compact(not self.compact));self.reveal.pack(side='left',padx=(0,5))
        for mode in ('Clips','Effects','Waveform'):ttk.Radiobutton(bar,text=mode,variable=self.layer,value=mode,command=self.show_overview).pack(side='left')
        ttk.Button(bar,text='Timing…',command=app.toggle_precision).pack(side='right')
        self.canvas=tk.Canvas(self,height=64,highlightthickness=0,takefocus=True);self.canvas.pack(fill='x')
        self.canvas.bind('<Configure>',self.invalidate);self.canvas.bind('<Button-1>',self.press)
        self.canvas.bind('<Return>',lambda e:self.focus_first());self.canvas.bind('<Left>',lambda e:self.cycle(-1));self.canvas.bind('<Right>',lambda e:self.cycle(1));self.selected=0
        app.add_tip(self.canvas,'Click an event to reveal its queue or treatment, without seeking. Arrow keys choose an event; Return focuses its owner. Timing opens precise editing.')
        self.bind('<Destroy>',self.cleanup,add='+')
    def set_compact(self,compact):
        self.compact=bool(compact);self.reveal.configure(text='Overview '+('▸' if self.compact else '▾'))
        if self.compact:self.canvas.pack_forget()
        else:self.canvas.pack(fill='x');self.invalidate()
    def show_overview(self):self.set_compact(False)
    def cleanup(self,e):
        if e.widget is self and self.job:
            try:self.after_cancel(self.job)
            except tk.TclError:pass
    def invalidate(self,event=None):self.key=None;self.schedule()
    def schedule(self,event=None):
        if self.job is None:self.job=self.after(32,self.draw)
    def draw(self):
        self.job=None
        if self.app.closing:return
        p=self.app.project;t=self.app.playhead;w=max(100,self.canvas.winfo_width());c=self.app.ui_chrome
        key=(self.app.revision,self.layer.get(),w,int(t//15),tuple(c.items()))
        if key==self.key:return self.playhead(t)
        self.key=key;cv=self.canvas;cv.configure(bg=c['field_bg']);cv.delete('all');self.hits=[]
        self.start=max(0,int((t-20)/15)*15);self.end=max(self.start+60,min(self.start+90,p.max_end()+3));self.span=self.end-self.start
        self.width=w
        def x(v):return 42+(v-self.start)/self.span*(w-48)
        self.x=x
        for sec in range(int(self.start),int(self.end)+1,15):
            xx=x(sec);cv.create_text(xx+2,6,text=f'{sec//60}:{sec%60:02d}',anchor='w',fill=c['muted_fg'],font=('TkFixedFont',8));cv.create_line(xx,14,xx,63,fill=c['panel_edge'])
        mode=self.layer.get()
        if mode=='Clips':
            roles=[l.extra['voice'] for l in __import__('visual_channels').channels(p) if l.extra.get('voice') in ('A','B','C','D')]+['Music']
            stride=max(10,45//len(roles))
            cv.configure(height=max(64,18+len(roles)*stride))
            for n,role in enumerate(roles):
                y=18+n*stride
                cv.create_text(4,y+5,text={'Music':'♫'}.get(role,role),anchor='w',fill=c['muted_fg'],font=('TkFixedFont',8))
                layer=next((l for l in p.layers if l.extra.get('voice')==role),None)
                events=items(p) if role=='Music' else layer.clips if layer else []
                for e in events:
                    start=e['start'] if isinstance(e,dict) else e.start;dur=e['duration'] if isinstance(e,dict) else e.duration
                    if start+dur<self.start or start>self.end:continue
                    eid=e['id'] if isinstance(e,dict) else e.id;aid=e['asset_id'] if isinstance(e,dict) else e.asset_id;a=p.asset(aid)
                    x1=max(42,x(start));x2=min(w-3,x(start+dur))
                    cv.create_rectangle(x1,y,x2,y+11,fill=c['selection_bg'] if start<=t<start+dur else c['panel_bg'],outline=c['accent'])
                    if x2-x1>40:cv.create_text(x1+3,y+5,text=(a.name if a else 'Missing')[:max(1,int((x2-x1)/7))],anchor='w',fill=c['foreground'],font=('TkDefaultFont',8))
                    self.hits.append((x1,y,x2,y+11,('clip',role,eid)))
        elif mode=='Effects':
            from omne_timeline_model import treatment_spans
            spans=treatment_spans(p,self.start,self.end);self.effect_spans={s['id']:s for s in spans}
            roles=['Master']+[role for role in ('A','B','C','D','Camera') if any(s['role']==role and (s['rack'] or s['historical']) for s in spans)]
            rowheight=max(9,36//len(roles))
            for n,role in enumerate(roles):
                y=18+n*rowheight
                cv.create_text(3,y+5,text={'Master':'FX','Camera':'Cam'}.get(role,role),anchor='w',fill=c['muted_fg'],font=('TkFixedFont',8))
                for span in (s for s in spans if s['role']==role):
                    x1=max(42,x(span['start']));x2=min(w-3,x(span['end']))
                    if x2<=x1:continue
                    names=[fx.get('extra',{}).get('name',fx.get('kind','Module')) for fx in span['rack']]
                    title=' + '.join(names) or 'No modules'
                    cv.create_rectangle(x1,y,x2,y+rowheight-2,fill=c['panel_bg'],outline=c['accent'])
                    if x2-x1>40:cv.create_text(x1+3,y+(rowheight-2)/2,text=title[:max(1,int((x2-x1)/6))],anchor='w',fill=c['foreground'],font=('TkDefaultFont',8))
                    # Dashed future means continuation, not an already generated decision.
                    if not span['historical'] and span['end']>t:
                        cv.create_line(max(x1,x(t)),y+rowheight-2,x2,y+rowheight-2,fill=c['foreground'],dash=(3,3))
                    self.hits.append((x1,y,x2,y+rowheight-2,('treatment',role,span['id'])))
            self.decisions={e['id']:e for e in p.extra.get('conductor_decisions',[]) if self.start<=e['time']<=self.end}
            for eid,event in self.decisions.items():
                xx=x(event['time']);cv.create_polygon(xx-4,58,xx,54,xx+4,58,xx,62,fill=c['accent'])
                self.hits.append((xx-5,53,xx+5,63,('decision','Conductor',eid)))
        else:
            wave=p.analysis.get('waveform',[]) or p.waveform
            if wave:
                duration=float(p.analysis.get('duration',p.max_end())) or 1
                for px in range(42,w-3,2):
                    sec=self.start+(px-42)/max(1,w-48)*self.span;i=int(sec/duration*len(wave))
                    if i<len(wave):
                        amplitude=min(1,abs(float(wave[i])))*19;cv.create_line(px,38-amplitude,px,38+amplitude,fill=c['accent'])
                for e in items(p):
                    if e['start']+e['duration']>=self.start and e['start']<=self.end:self.hits.append((max(42,x(e['start'])),16,min(w-3,x(e['start']+e['duration'])),60,('clip','Music',e['id'])))
            else:cv.create_text(w/2,35,text='No cached waveform · Music analysis appears here',fill=c['muted_fg'])
        self.playhead(t)
    def playhead(self,t):
        if not hasattr(self,'x'):return
        self.canvas.delete('playhead');x=self.x(t)
        if 42<=x<=self.width:self.canvas.create_line(x,13,x,63,fill=self.app.ui_chrome['foreground'],width=2,tags='playhead')
    def press(self,e):
        self.canvas.focus_set()
        for n,(x1,y1,x2,y2,target) in enumerate(self.hits):
            if x1<=e.x<=x2 and y1<=e.y<=y2:self.selected=n;self.activate(target);return
    def cycle(self,n):
        if self.hits:self.selected=(self.selected+n)%len(self.hits);self.app.update_status('Overview selected · '+str(self.hits[self.selected][-1])+' · Return to focus')
        return 'break'
    def focus_first(self):
        if self.hits:self.activate(self.hits[self.selected%len(self.hits)][-1])
        return 'break'
    def activate(self,target):
        kind,role,eid=target;a=self.app
        if a.gesture:return a.update_status('Finish the current gesture before navigating to another owner.')
        if kind=='clip':return self.focus_occurrence(role,eid)
        if kind=='decision':
            event=self.decisions.get(eid)
            if event:
                a.conductor.power.focus_set()
                self.inspect_history('Conductor decision · recorded policy',event)
            return
        span=self.effect_spans.get(eid)
        if not span:return
        if span['historical']:
            return self.inspect_history(f"{role} treatment · {span['start']:.2f}–{span['end']:.2f} s",span['style'])
        if not a.panel_states['Rack']:a.toggle_panel('Rack')
        if role=='Master':a.deck.scope.set('Master');a.deck.refresh(True)
        else:a.focus_voice(role)
        rack,owner=a.deck.target()
        if rack:a.deck.select_card(rack[0].id)
        a.deck.randomise_button.focus_set()
        a.update_status(role+' current treatment focused · playback position unchanged')
    def inspect_history(self,title,data):
        import json
        old=getattr(self,'inspector',None)
        if old and old.winfo_exists():old.destroy()
        w=tk.Toplevel(self.app);self.inspector=w;w.title(title);w.geometry('600x390');w.transient(self.app)
        body=ttk.Frame(w,padding=10);body.pack(fill='both',expand=True)
        ttk.Label(body,text=title,style='Title.TLabel',wraplength=560).pack(anchor='w')
        ttk.Label(body,text='Recorded context · read-only · current Programme is unchanged',style='Muted.TLabel').pack(anchor='w',pady=6)
        text=tk.Text(body,wrap='word',bg=self.app.ui_chrome['field_bg'],fg=self.app.ui_chrome['foreground'],borderwidth=0)
        text.pack(fill='both',expand=True);text.insert('1.0',json.dumps(data,indent=2,ensure_ascii=False));text.configure(state='disabled')
        ttk.Button(body,text='Close',command=w.destroy).pack(anchor='e',pady=(6,0));w.bind('<Escape>',lambda e:w.destroy())
    def focus_occurrence(self,role,eid):
        a=self.app
        if a.gesture:return a.update_status('Finish the current gesture before navigating to another owner.')
        if not a.panel_states['Queues']:a.toggle_panel('Queues')
        a.queue_deck.show_role(role);page=a.queue_deck.pages[role];page.selected=eid;page.refresh(True);page.canvas.focus_set()
        a.update_status(role+' queue occurrence focused · playback position unchanged')
        occurrence=next((e for e in page.items if page.ident(e)==eid),None)
        if occurrence is not None and eid!=page.current_id and page.start(occurrence)<=page.cursor:
            from sequencer_model import _encode
            self.inspect_history(role+' · earlier queue occurrence',_encode(occurrence))
