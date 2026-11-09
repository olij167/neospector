"""Retained Conductor performance controls; detailed policy lives in Steering."""
from __future__ import annotations
from conductor_targets import DEFAULTS
import copy, tkinter as tk
from tkinter import ttk, simpledialog
import composition_queue as cues
from responsive_controls import FlowRow
from module_library import catalogue_rows


class CompositionQueueView(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;self._rows_key=None;self._editing=None;self._drag=None
        self.now_text=tk.StringVar(value='Now · Manual rack');self.next_text=tk.StringVar(value='Next · Add a composition')
        self.progress=tk.DoubleVar(value=0);self.status=tk.StringVar();self.hold=tk.StringVar(value='12');self.fade=tk.StringVar(value='2')
        self.loop=tk.BooleanVar(value=True);self.continuous=tk.BooleanVar(value=False);self.pool_label=tk.StringVar(value='All groups')
        self.reaction=tk.StringVar(value='full');self.count=tk.StringVar(value='2');self.source=tk.StringVar(value='reaction_mix')
        nowrow=ttk.Frame(self);nowrow.pack(fill='x',pady=(2,1))
        ttk.Label(nowrow,textvariable=self.now_text,style='PlayerName.TLabel',width=1).pack(side='left',fill='x',expand=True)
        ttk.Style(self).configure('Cue.Horizontal.TProgressbar',thickness=4)
        ttk.Progressbar(nowrow,variable=self.progress,maximum=1,length=40,style='Cue.Horizontal.TProgressbar').pack(side='right',padx=3)
        self.next_label=ttk.Label(self,textvariable=self.next_text,style='Muted.TLabel',wraplength=265)
        self.next_label.pack(fill='x',pady=(0,3))
        row=FlowRow(self,gap=4);row.pack(fill='x',pady=(0,5))
        self.next_button=ttk.Button(row,text='Next ›',style='Accent.TButton',width=7,command=self.take_next);row.add(self.next_button)
        self.capture_button=ttk.Button(row,text='Capture',width=8,command=self.capture);row.add(self.capture_button)
        self.generate_button=ttk.Button(row,text='Generate +',width=10,command=self.generate);row.add(self.generate_button)
        app.add_tip(self.next_button,'Transition to the next prepared composition. When playback is stopped, apply it immediately. Power OFF prevents automatic advances, not manual Next.')
        app.add_tip(self.capture_button,'Append a snapshot of the current master rack. Editing the live rack afterwards will not alter this saved cue.')
        app.add_tip(self.generate_button,'Append a new composition using the chosen module pool and reaction. Nothing changes on output until Next or timed progression.')
        box=ttk.Frame(self);box.pack(fill='both',expand=True);self.cue_list=box
        self.tree=ttk.Treeview(box,columns=('timing',),show='tree headings',selectmode='browse',height=3)
        self.tree.heading('#0',text='Compositions');self.tree.heading('timing',text='H / F (s)')
        self.tree.column('#0',width=170,minwidth=100);self.tree.column('timing',width=80,minwidth=70,stretch=False)
        self.tree.pack(side='left',fill='both',expand=True);scroll=ttk.Scrollbar(box,command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>',self.select);self.tree.bind('<Double-1>',lambda e:self.take_selected());self.tree.bind('<Return>',lambda e:self.take_selected())
        self.tree.bind('<Delete>',lambda e:self.delete());self.tree.bind('<Alt-Up>',lambda e:self.move(-1));self.tree.bind('<Alt-Down>',lambda e:self.move(1))
        self.tree.bind('<Button-3>',self.context);self.tree.bind('<ButtonPress-1>',self.drag_start,add='+');self.tree.bind('<ButtonRelease-1>',self.drag_end,add='+')
        tools=FlowRow(self,gap=3);tools.pack(fill='x',pady=4);self.cue_tools=tools
        for label,fn,width in [('↑',lambda:self.move(-1),3),('↓',lambda:self.move(1),3),('Delete',self.delete,6)]:tools.add(ttk.Button(tools,text=label,command=fn,width=width))
        timing=FlowRow(self,gap=3);timing.pack(fill='x',pady=(0,3));self.timing_title=tk.StringVar(value='New cues');self.timing_row=timing
        self.timing_entries=[]
        for label,var,lo,hi in [('Hold',self.hold,.25,3600),('Fade',self.fade,0,60)]:
            timing.add(ttk.Label(timing,text=label));entry=ttk.Spinbox(timing,from_=lo,to=hi,increment=.25,textvariable=var,width=4,command=self.apply_timing)
            entry.bind('<Return>',self.apply_timing);entry.bind('<FocusOut>',self.apply_timing);timing.add(entry);self.timing_entries.append(entry)
        timing.add(ttk.Label(timing,text='s',style='Muted.TLabel'))
        policy=FlowRow(self,gap=3);policy.pack(fill='x',pady=(0,2))
        policy.add(ttk.Checkbutton(policy,text='Loop',variable=self.loop,command=lambda:self.configure_queue({'loop':self.loop.get()})))
        policy.add(ttk.Checkbutton(policy,text='Auto-new',variable=self.continuous,command=lambda:self.configure_queue({'continuous':self.continuous.get()})))
        app.add_tip(policy,'Loop repeats prepared cues. Auto-new generates new cues after the prepared queue instead. Neither option starts playback or turns Conductor power on.')
        self.pool_button=ttk.Button(policy,text='Modules…',width=9,command=self.choose_modules);policy.add(self.pool_button)
        app.add_tip(self.pool_button,'Choose which modules and groups may be generated. The same Library supports Grid and List; checked choices form the Conductor pool.')
        self.more=ttk.Menubutton(tools,text='⋯',width=3);tools.add(self.more);menu=tk.Menu(self.more,tearoff=False);self.more.configure(menu=menu)
        menu.add_command(label='Take selected',command=self.take_selected)
        menu.add_command(label='Rename selected…',command=self.rename)
        menu.add_command(label='Use all factory groups',command=lambda:self.configure_queue({'pool_mode':'all'}))
        menu.add_command(label='Deselect cue / edit new-cue timing',command=self.deselect)
        menu.add_command(label='Replace selected snapshot with current rack',command=self.replace_snapshot)
        self.status_label=ttk.Label(self,textvariable=self.status,style='Muted.TLabel',wraplength=265);self.status_label.pack(fill='x',pady=(2,0))
        self.bind('<Configure>',self.resize);self.refresh()
    def resize(self,event):
        if event.widget is not self:return
        width=max(160,event.width-6)
        for label in (self.status_label,self.next_label):label.configure(wraplength=width)
    def selected(self):return next(iter(self.tree.selection()),None)
    def action(self,label,fn):
        if self.app.reviewing:return self.app.update_status('Return to Programme before changing the Conductor queue.')
        if self.app.mutating:return self.app.update_status('Preparation in progress; the composition queue is unchanged.')
        result=self.app.transaction(label,lambda:fn(self.app.project));self.refresh();return result
    def capture(self):
        def apply(p):
            item=cues.append_snapshot(p,name='Captured '+str(len(cues.state(p)['items'])+1));p.conductor.extra['evolve_treatment']=True;return item
        item=self.action('Capture rack composition',apply)
        if item:self.tree.selection_set(item['id'])
        return item
    def generate(self):
        rows=catalogue_rows(self.app)
        def apply(p):
            item=cues.append_generated(p,rows,seed=p.mutation_seed+1);p.mutation_seed+=1;p.conductor.extra['evolve_treatment']=True;return item
        item=self.action('Prepare module composition',apply)
        if item:self.tree.selection_set(item['id'])
        return item
    def take_next(self):return self._take(None)
    def take_selected(self):
        if self.selected():return self._take(self.selected())
    def _take(self,entry_id):
        now=self.app.programme_time()
        if cues.active_transition(self.app.project,now):return self.app.update_status('Transition in progress; the next composition remains prepared.')
        return self.action('Take module composition',lambda p:cues.take(p,entry_id,now=now,immediate=not self.app.playing))
    def move(self,offset):
        selected=self.selected()
        if selected:self.action('Reorder composition queue',lambda p:cues.move(p,selected,offset));self.tree.selection_set(selected)
        return 'break'
    def delete(self):
        selected=self.selected()
        if selected:self.action('Delete composition cue',lambda p:cues.remove(p,selected))
        return 'break'
    def rename(self):
        selected=self.selected();item=next((e for e in cues.state(self.app.project)['items'] if e['id']==selected),None)
        if not item:return
        name=simpledialog.askstring('Composition name','Name:',initialvalue=item['name'],parent=self.app)
        if name:self.action('Rename composition cue',lambda p:cues.update_entry(p,selected,name=name))
    def replace_snapshot(self):
        from sequencer_model import _encode
        selected=self.selected()
        def apply(p):
            s=copy.deepcopy(cues.state(p));item=next((e for e in s['items'] if e['id']==selected),None)
            if not item:raise ValueError('Select a composition cue first.')
            item['rack']=_encode(p.master_rack);item['generated']=False;p.conductor.extra['composition_queue']=s
        self.action('Replace cue snapshot',apply)
    def context(self,event):
        node=self.tree.identify_row(event.y)
        if node:self.tree.selection_set(node)
        menu=tk.Menu(self,tearoff=False)
        for label,fn in [('Take selected',self.take_selected),('Rename…',self.rename),('Move up',lambda:self.move(-1)),('Move down',lambda:self.move(1)),('Delete',self.delete),('Replace snapshot',self.replace_snapshot)]:menu.add_command(label=label,command=fn)
        self.app.popup_menu(menu,self.tree,event)
    def drag_start(self,event):self._drag=self.tree.identify_row(event.y)
    def drag_end(self,event):
        target=self.tree.identify_row(event.y);source=self._drag;self._drag=None
        order=list(self.tree.get_children())
        if source and target and source!=target and source in order and target in order:
            self.tree.selection_set(source);self.move(order.index(target)-order.index(source))
    def deselect(self):self.tree.selection_remove(*self.tree.selection());self.select()
    def select(self,event=None):
        p=self.app.project;s=cues.state(p);item=next((e for e in s['items'] if e['id']==self.selected()),None)
        self._editing=(p,item['id'] if item else None)
        self.timing_title.set('Cue' if item else 'New cues')
        data=item or s;self.hold.set(f"{data['hold']:g}");self.fade.set(f"{data['fade']:g}")
    def apply_timing(self,event=None):
        if not self._editing:self.select()
        p,entry=self._editing
        if p is not self.app.project:return
        try:hold=float(self.hold.get());fade=float(self.fade.get())
        except (ValueError,tk.TclError):return self.status.set('Use seconds for Hold and Fade.')
        current=next((e for e in cues.state(p)['items'] if e['id']==entry),None) if entry else cues.state(p)
        if current and current['hold']==hold and current['fade']==fade:return
        self.action('Composition timing',lambda p:cues.update_entry(p,entry,hold=hold,fade=fade) if entry else cues.configure(p,{'hold':hold,'fade':fade}))
        return 'break' if event is not None and getattr(event,'keysym','')=='Return' else None
    def configure_queue(self,changes):return self.action('Conductor composition policy',lambda p:cues.configure(p,changes))
    def choose_modules(self):
        self.app.show_module_library();self.app.module_library.begin_conductor_selection()
    def build_choices(self,parent):
        row=FlowRow(parent,gap=3);row.pack(fill='x',pady=(0,4));row.add(ttk.Label(row,text='Modules per cue'))
        count=ttk.Spinbox(row,from_=1,to=12,textvariable=self.count,width=4,command=self.apply_choices);row.add(count);count.bind('<Return>',self.apply_choices);count.bind('<FocusOut>',self.apply_choices)
        row=FlowRow(parent,gap=3);row.pack(fill='x',pady=2);row.add(ttk.Label(row,text='Reaction'))
        picker=ttk.Combobox(row,textvariable=self.reaction,values=cues.REACTIONS,state='readonly',width=9);row.add(picker);picker.bind('<<ComboboxSelected>>',self.apply_choices)
        row=FlowRow(parent,gap=3);row.pack(fill='x',pady=2);row.add(ttk.Label(row,text='Audio source'))
        picker=ttk.Combobox(row,textvariable=self.source,values=cues.SOURCES,state='readonly',width=13);row.add(picker);picker.bind('<<ComboboxSelected>>',self.apply_choices)
        self.app.add_tip(picker,'Reaction follows this signal; choosing it never enables a microphone or device. Power/routing remains in Audio. Full, bass, mid, high and onset are available; none makes new cues static.')
    def apply_choices(self,event=None):
        try:count=int(self.count.get())
        except ValueError:return self.status.set('Choose 1–12 modules.')
        changes={'count':count,'reaction':self.reaction.get(),'reaction_source':self.source.get()}
        if all(cues.state(self.app.project).get(k)==v for k,v in changes.items()):return
        self.configure_queue(changes)
    def refresh(self,now=None):
        p=self.app.project;s=cues.state(p);items=s.get('items',[]);key=(p.id,tuple((e['id'],e['name'],e['hold'],e['fade']) for e in items),s.get('active_id'),s.get('next_id'))
        if items:
            if not self.cue_list.winfo_manager():
                self.cue_list.pack(fill='both',expand=True,before=self.timing_row)
                self.cue_tools.pack(fill='x',pady=4,before=self.timing_row)
        else:
            self.cue_list.pack_forget();self.cue_tools.pack_forget()
        if key!=self._rows_key:
            self._rows_key=key;ids={e['id'] for e in items}
            for old in self.tree.get_children():
                if old not in ids:self.tree.delete(old)
            for index,item in enumerate(items):
                iid=item['id'];prefix='▶ ' if iid==s.get('active_id') else '› ' if iid==s.get('next_id') else ''
                data={'text':prefix+item['name'],'values':(f"{item['hold']:g} / {item['fade']:g}s",)}
                if self.tree.exists(iid):self.tree.item(iid,**data);self.tree.move(iid,'',index)
                else:self.tree.insert('','end',iid=iid,**data)
            if self.app.focus_get() not in self.timing_entries:self.select()
        now=self.app.programme_time() if now is None else now;transition=cues.active_transition(p,now);nxt=cues.next_entry(p)
        self.now_text.set('Now · '+s.get('active_name','Manual rack'))
        self.next_text.set('Next · '+nxt['name'] if nxt else 'Cues are optional: prepare a rack change below.')
        if transition:
            self.progress.set((now-transition['start'])/(transition.get('fade_end',transition['end'])-transition['start']));self.status.set('Transitioning · '+f"{max(0,transition['end']-now):.1f}s")
        else:
            self.progress.set(0);due=s.get('due_at')
            self.status.set(('Hold · '+f'{max(0,due-now):.1f}s') if due is not None and self.app.evolve.get() else ('' if items else 'Conductor ON evolves the current rack.'))
        if self.status.get():
            if not self.status_label.winfo_manager():self.status_label.pack(fill='x',pady=(2,0))
        elif self.status_label.winfo_manager():self.status_label.pack_forget()
        disabled=self.app.reviewing or self.app.mutating
        self.next_button.configure(state='disabled' if disabled or transition or not nxt else 'normal')
        self.generate_button.configure(state='disabled' if disabled or len(items)>=cues.MAX_ITEMS else 'normal')
        self.capture_button.configure(state='disabled' if disabled or len(items)>=cues.MAX_ITEMS else 'normal')
        self.loop.set(s.get('loop',True));self.continuous.set(s.get('continuous',False))
        self.pool_label.set('All groups' if s.get('pool_mode','all')=='all' else str(len(s.get('pool_ids',[])))+' selected')
        self.pool_button.configure(text='Modules…' if s.get('pool_mode','all')=='all' else f"Modules ({len(s.get('pool_ids',[]))})")
        self.reaction.set(s.get('reaction','full'));self.source.set(s.get('reaction_source','reaction_mix'))
        if not isinstance(self.app.focus_get(),ttk.Spinbox):self.count.set(str(s.get('count',2)))


class CompositionQueueActions:
    def _clock_tick(self):
        result=super()._clock_tick()
        now=self.programme_time();self.advance_composition_queue(now)
        if hasattr(self,'conductor') and now!=getattr(self,'_cue_paint_time',None) and abs(now-getattr(self,'_cue_paint_time',-1))>=.1:
            self._cue_paint_time=now;self.conductor.queue_view.refresh(now)
        return result
    def advance_composition_queue(self,now=None):
        if not self.playing or not self.evolve.get() or self.reviewing or self.gesture or self.mutating:return
        p=self.project
        if not p.conductor.extra.get('evolve_treatment',DEFAULTS['evolve_treatment']) or not p.conductor.extra.get('composition_queue'):return
        now=self.programme_time() if now is None else now;s=cues.state(p)
        if s.get('due_at') is not None and now<s['due_at']:return
        if cues.active_transition(p,now):return
        self.measure_history_budget()
        if not self.evolve.get():return
        explicit=next((e for e in s['items'] if e['id']==s.get('next_id')),None)
        if not explicit and not s.get('continuous') and not cues.next_entry(p):return
        rows=catalogue_rows(self) if s.get('continuous') else []
        def advance():
            if not explicit and s.get('continuous'):
                item=cues.replenish(p,rows,seed=p.mutation_seed+1);p.mutation_seed+=1
            else:item=explicit or cues.next_entry(p)
            result=cues.take(p,item['id'],now=now)
            current=cues.state(p)
            if not current.get('next_id') and current.get('continuous'):
                cues.replenish(p,rows,seed=p.mutation_seed+1);p.mutation_seed+=1
            return result
        result=self.transaction('Conductor · next composition',advance)
        if result is None:self.evolve.set(False);self.update_status('Conductor held. Check the selected module pool and composition queue; current playback continues.')
