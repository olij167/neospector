"""Advanced queue views. Music never falls back to an unrelated volume mixer."""
import math
import tkinter as tk
from tkinter import ttk
from instrument_timeline import InstrumentTimeline
from live_parameter_controls import LiveGesture,should_debounce_key
import music_queue

class MusicTiming(ttk.Frame):
    def __init__(self,parent,app,*,shared=None):
        super().__init__(parent,padding=0 if shared else 5);self.shared=shared;self.app=app;self.selected=None;self.drag=None;self.hits=[];self.pps=45.;self.key=None;self.fields={};self.entries={};self.inline_entries={};self.jobs={};self.message=tk.StringVar();self.gesture_changed=False
        self.live_edit=LiveGesture(app,'music-timing',self._valid_identity,self.message.set)
        bar=ttk.Frame(self);bar.pack(fill='x')
        ttk.Label(bar,text='MUSIC · precise timing',style='Title.TLabel').pack(side='left')
        ttk.Button(bar,text='Fit',command=self.zoom_fit).pack(side='right')
        for text,mult in [('+',1.4),('−',1/1.4)]:ttk.Button(bar,text=text,width=3,command=lambda m=mult:self.zoom(m)).pack(side='right',padx=2)
        self.canvas=tk.Canvas(self,height=70,highlightthickness=0,takefocus=True);self.canvas.pack(fill='both',expand=True)
        self.scroll=ttk.Scrollbar(self,orient='horizontal',command=self.scrolling);self.scroll.pack(fill='x');self.canvas.configure(xscrollcommand=self.scroll.set)
        fields=ttk.Frame(self);fields.pack(fill='x',pady=3)
        for name,title in [('start','Start'),('duration','Duration'),('in_point','Source in'),('fade_in','Fade in'),('fade_out','Fade out')]:
            ttk.Label(fields,text=title,style='Muted.TLabel').pack(side='left',padx=(5,2));v=tk.StringVar();self.fields[name]=v;entry=ttk.Entry(fields,textvariable=v,width=6);entry.pack(side='left');self.inline_entries[name]=entry;self.entries[name]=entry;self._bind_entry(entry,name)
        ttk.Label(fields,textvariable=self.message,style='Muted.TLabel').pack(side='right',padx=3)
        self.field_frame=fields
        self.canvas.bind('<Configure>',lambda e:self.refresh(True));self.canvas.bind('<Button-1>',self.press);self.canvas.bind('<B1-Motion>',self.motion);self.canvas.bind('<ButtonRelease-1>',self.release)
        self.canvas.bind('<Double-Button-1>',lambda e:self.open_fields())
        if shared:
            bar.pack_forget();self.scroll.pack_forget();fields.pack_forget();self.canvas.pack_forget()
            self.columnconfigure(1,weight=1)
            self.header=ttk.Frame(self,width=shared.HEADER);self.header.grid(row=0,column=0,sticky='ns');self.header.pack_propagate(False)
            self.header.configure(height=68)
            ttk.Label(self.header,text='♪ MUSIC',style='Current.TLabel').pack(anchor='w',padx=7,pady=(4,1))
            ttk.Button(self.header,text='Track controls',command=self.open_fields,width=10).pack(anchor='w',padx=3)
            self.canvas.configure(height=68);self.canvas.grid(row=0,column=1,sticky='ew')
            spacer=ttk.Frame(self,width=shared.vbar.winfo_reqwidth());spacer.grid(row=0,column=2,sticky='ns')
    def open_fields(self):
        if not self.selected:
            events=music_queue.items(self.app.project)
            if not events:return self.app.update_status('Select audio in Library → Add to Music Queue.')
            self.selected=events[0]['id'];self.refresh(True)
        w=getattr(self,'fields_window',None)
        if w and w.winfo_exists():w.lift();return
        w=tk.Toplevel(self);self.fields_window=w;w.title('Music · track timing');w.transient(self.app)
        box=ttk.Frame(w,padding=14);box.pack(fill='both',expand=True)
        for i,(key,title) in enumerate([('start','Start'),('duration','Duration'),('in_point','Source in'),('fade_in','Fade in'),('fade_out','Fade out')]):
            ttk.Label(box,text=title+' (s)').grid(row=i,column=0,sticky='w',pady=4)
            entry=ttk.Entry(box,textvariable=self.fields[key],width=13);entry.grid(row=i,column=1,padx=7);self.entries[key]=entry;self._bind_entry(entry,key)
        ttk.Label(box,text='Changes are live while paused; Escape restores the current gesture.',style='Muted.TLabel').grid(row=5,column=0,columnspan=2,pady=(7,2))
        ttk.Label(box,textvariable=self.message,style='Muted.TLabel',wraplength=360).grid(row=6,column=0,columnspan=2,sticky='ew',pady=3)
        ttk.Button(box,text='Done',command=self.close_fields).grid(row=7,column=1,sticky='e')
        w.bind('<Escape>',self.escape);w.protocol('WM_DELETE_WINDOW',self.close_fields)

    def _bind_entry(self,entry,key):
        entry.bind('<KeyRelease>',lambda e,k=key:self.queue_field(k,e));entry.bind('<Return>',lambda e,k=key:self.finish_field(k));entry.bind('<KP_Enter>',lambda e,k=key:self.finish_field(k))
        entry.bind('<FocusOut>',lambda e,k=key:self.finish_field(k));entry.bind('<Escape>',self.escape)

    def _event(self,project,event_id):return next((e for e in music_queue.items(project) if e['id']==event_id),None)

    def _valid_identity(self,identity):
        project,event_id=identity
        if self.app.project is not project or self._event(project,event_id) is None:
            self.message.set('This Music item changed. Select it again.');return False
        if self.app.playing and not self.app.reviewing:
            self.message.set('Pause to edit Music timing; played output stays protected.');return False
        event=self._event(project,event_id)
        if event.get('locked') or event.get('timing_locked') or event.get('pinned'):
            self.message.set('Unpin or unlock this Music item before changing its timing.');return False
        return True

    def queue_field(self,key,event=None):
        if event is not None and not should_debounce_key(event):return
        job=self.jobs.pop(key,None)
        if job:
            try:self.after_cancel(job)
            except tk.TclError:pass
        self.jobs[key]=self.after(280,lambda k=key:self.flush_field(k))

    def flush_field(self,key,finish=False):
        job=self.jobs.pop(key,None)
        if job:
            try:self.after_cancel(job)
            except tk.TclError:pass
        try:
            value=float(self.fields[key].get())
            if not math.isfinite(value):raise ValueError
        except (ValueError,tk.TclError):
            self.message.set('Enter a finite, nonnegative number in seconds; incomplete text was not applied.')
            if finish:self.finish_gesture()
            return False
        identity=self.live_edit.identity if self.live_edit.active else (self.app.project,self.selected)
        if not identity[1]:
            self.message.set('Select a Music block first.')
            if finish:self.finish_gesture()
            return False
        if not self.live_edit.begin(identity):
            if finish:self.finish_gesture()
            return False
        if not self.live_edit.current():
            if finish:self.finish_gesture()
            return False
        try:music_queue.set_timing(self.app.project,identity[1],**{key:value})
        except ValueError as exc:
            self.message.set(str(exc));changed=False
        else:
            self.gesture_changed=True;self.app.changed(redraw=False);self.message.set('');self.refresh(True);changed=True
        if finish:self.finish_gesture()
        return changed

    def finish_field(self,key):self.flush_field(key,True);return 'break'

    def finish_gesture(self):
        changed=self.gesture_changed;self.gesture_changed=False;self.live_edit.finish()
        if changed:
            self.app.configure_sound_sources();self.app.prepare_sound_analysis();self.app.queue_deck.refresh(True);self.refresh(True)

    def cancel_gesture(self):
        self.gesture_changed=False;self.live_edit.cancel();self.refresh(True)

    def escape(self,event=None):
        for job in self.jobs.values():
            try:self.after_cancel(job)
            except tk.TclError:pass
        self.jobs.clear()
        if self.live_edit.active:self.cancel_gesture()
        elif getattr(self,'fields_window',None) and self.fields_window.winfo_exists():self.close_fields()
        return 'break'

    def close_fields(self):
        for job in self.jobs.values():
            try:self.after_cancel(job)
            except tk.TclError:pass
        self.jobs.clear()
        if self.live_edit.active:self.finish_gesture()
        w=getattr(self,'fields_window',None)
        if w and w.winfo_exists():w.destroy()
        self.entries=dict(self.inline_entries)
    def scrolling(self,*a):
        if self.shared:return self.shared.xview(*a)
        self.canvas.xview(*a);self.refresh(True)
    def zoom(self,m):
        if self.shared:return self.shared.zoom_by(m)
        self.pps=max(.02,min(1200,self.pps*m));self.refresh(True)
    def zoom_fit(self):
        if self.shared:return self.shared.zoom_fit()
        end=max((e['start']+e['duration'] for e in music_queue.items(self.app.project)),default=20)
        self.pps=max(2,(max(200,self.canvas.winfo_width())-25)/max(1,end));self.refresh(True)
    def refresh(self,force=False):
        if not self.winfo_ismapped() and not force:return
        if self.shared:self.pps=self.shared.pps
        key=(self.app.revision,self.pps,self.canvas.winfo_width(),int(self.canvas.canvasx(0)))
        if key==self.key and not force:self.draw_playhead();return
        self.key=key;cv=self.canvas;c=self.app.ui_chrome;cv.configure(bg=c['field_bg']);cv.delete('all');self.hits=[]
        events=music_queue.items(self.app.project);w=max(100,cv.winfo_width());left=cv.canvasx(0);right=left+w;end=max((e['start']+e['duration'] for e in events),default=20)
        if self.shared:
            total=float(self.shared.canvas.cget('scrollregion').split()[2]) if self.shared.canvas.cget('scrollregion') else max(w,self.app.project.max_end()*self.pps+30)
        else:total=max(w,end*self.pps+25)
        cv.configure(scrollregion=(0,0,total,68))
        if self.shared:
            cv.xview_moveto(self.shared.canvas.xview()[0]);left=cv.canvasx(0);right=left+w
        step=next((x for x in (.1,.25,.5,1,2,5,10,30,60,120,300) if x*self.pps>=55),300)
        for i in range(max(0,int(left/self.pps/step)),int(right/self.pps/step)+2):
            x=i*step*self.pps;cv.create_text(x+2,3,text=f'{i*step:g}s',anchor='nw',fill=c['muted_fg']);cv.create_line(x,20,x,62,fill=c['panel_edge'])
        for e in events:
            x1=e['start']*self.pps;x2=(e['start']+e['duration'])*self.pps
            if x2<left or x1>right:continue
            a=self.app.project.asset(e['asset_id']);y=26
            cv.create_rectangle(x1,y,x2,58,fill=c['selection_bg'] if e['id']==self.selected else c['panel_bg'],outline=c['accent'])
            if x2-x1>35:cv.create_text(x1+7,42,text=(a.name if a else 'Missing')[:max(3,int((x2-x1)/8))],anchor='w',fill=c['foreground'])
            cv.create_line(x1,58,x1+e.get('fade_in',0)*self.pps,y,fill=c['secondary_accent'],width=2)
            cv.create_line(x2-e.get('fade_out',0)*self.pps,y,x2,58,fill=c['secondary_accent'],width=2)
            self.hits.append((e['id'],x1,x2))
        if not events:cv.create_text(12,40,text='Add tracks from Library → Add to Music Queue',anchor='w',fill=c['muted_fg'])
        selected=next((e for e in events if e['id']==self.selected),None)
        focus=self.app.focus_get()
        if selected and focus not in set(self.entries.values())|set(self.inline_entries.values()):
            for key,var in self.fields.items():var.set(f'{selected.get(key,0):.3f}')
        self.draw_playhead()
    def draw_playhead(self):
        if not self.winfo_ismapped():return
        self.canvas.delete('playhead');x=self.app.playhead*self.pps;self.canvas.create_line(x,0,x,65,fill=self.app.ui_chrome['accent'],width=2,tags='playhead')
    def press(self,event):
        if self.live_edit.active:self.finish_gesture()
        self.canvas.focus_set();x=self.canvas.canvasx(event.x);hit=next((h for h in reversed(self.hits) if h[1]<=x<=h[2]),None)
        if not hit:
            if not self.app.playing or self.app.reviewing:self.app.set_playhead(x/self.pps)
            return
        self.selected=hit[0];e=next(e for e in music_queue.items(self.app.project) if e['id']==self.selected)
        op='left' if x-hit[1]<8 else 'right' if hit[2]-x<8 else 'move';self.drag=(op,x,dict(e));self.refresh(True)
    def motion(self,event):
        if not self.drag:return
        x=self.canvas.canvasx(event.x);self.canvas.delete('ghost');self.canvas.create_line(x,20,x,62,fill=self.app.ui_chrome['foreground'],width=3,tags='ghost')
    def release(self,event):
        self.canvas.delete('ghost');drag=self.drag;self.drag=None
        if not drag:return
        op,x,e=drag;delta=(self.canvas.canvasx(event.x)-x)/self.pps;delta=round(delta*self.app.project.fps)/self.app.project.fps
        if not delta:return
        if op=='move':changes={'start':max(0,e['start']+delta)}
        elif op=='right':changes={'duration':max(1/self.app.project.fps,e['duration']+delta)}
        else:
            rate=e.get('playback_rate',1);delta=max(-e['in_point']/rate,-e['start'],min(e['duration']-1/self.app.project.fps,delta));changes={'start':e['start']+delta,'duration':e['duration']-delta,'in_point':e['in_point']+delta*rate}
        self.app.music_edit('Music '+op,lambda p:music_queue.set_timing(p,e['id'],**changes));self.refresh(True)
    def apply_fields(self):
        """Compatibility entry point; visible fields already write live."""
        if not self.selected:return self.app.update_status('Select a Music block first.')
        try:changes={k:float(v.get()) for k,v in self.fields.items()}
        except ValueError:return self.app.update_status('Enter timing values in seconds.')
        self.app.music_edit('Music timing',lambda p:music_queue.set_timing(p,self.selected,**changes));self.refresh(True)

class TimingWorkbench(ttk.Frame):
    """One common ruler/scroll position, Music permanently above the visual rows."""
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;self.visual=InstrumentTimeline(self,app);self.visual.pack(fill='both',expand=True);self.music_mode=False
        # Insert the Music row within the existing timing surface instead of
        # switching between two timelines that conceal one another.
        for widget in (self.visual.headers,self.visual.canvas,self.visual.vbar):widget.grid_configure(row=3)
        self.visual.hbar.grid_configure(row=4);self.visual.rowconfigure(2,weight=0);self.visual.rowconfigure(3,weight=1,minsize=75)
        self.music=MusicTiming(self.visual,app,shared=self.visual);self.music.grid(row=2,column=0,columnspan=3,sticky='ew')
        self.visual.canvas.configure(xscrollcommand=self._scroll_changed)
        self.visual.canvas.bind('<Configure>',lambda e:self.music.refresh(True),add='+')
    def __getattr__(self,key):
        visual=self.__dict__.get('visual')
        if visual is not None:return getattr(visual,key)
        raise AttributeError(key)
    def _scroll_changed(self,first,last):
        self.visual.hbar.set(first,last)
        if hasattr(self,'music'):self.music.refresh(True)
    def choose_music(self,value):
        # Selection is a focus hint, never a visibility switch.
        self.music_mode=bool(value)
        self.redraw()
    def redraw(self):
        self.visual.redraw();self.music.refresh(True)
    def schedule(self,*a):
        self.visual.schedule();self.music.refresh()
    def draw_playhead(self):
        if self.winfo_ismapped():self.visual.draw_playhead();self.music.refresh()
    def zoom_fit(self):self.visual.zoom_fit();self.music.refresh(True)
    def zoom_by(self,factor):self.visual.zoom_by(factor);self.music.refresh(True)
    def xview(self,*args):self.visual.xview(*args);self.music.refresh(True)
