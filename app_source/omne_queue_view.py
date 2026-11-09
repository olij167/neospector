"""MP3-player queue columns: current stays pinned, only upcoming cards scroll."""
from __future__ import annotations
import copy, tkinter as tk
from tkinter import ttk, font as tkfont
from PIL import Image, ImageTk
from flow_playback import QueueLane
from queue_model import ordered,current,queue_position,mode_at
from instrument_model import voice
from music_queue import items
from responsive_controls import FlowRow,PriorityToolbar,OverflowAdapter
from queue_gaps import gap_name
from ui_chrome import tk_scale_theme_options
from queue_transitions import boundary_labels


def clock_text(seconds):
    seconds=max(0,int(seconds));return f'{seconds//60}:{seconds%60:02d}'

class PlayerColumn(QueueLane):
    def __init__(self,parent,app,role,visibility=None):
        ttk.Frame.__init__(self,parent,padding=(3,2));self.app=app;self.role=role;self.editor_visibility=visibility;self.selected=None;self.items=[];self.hits=[];self.drag=None;self.key=None
        self.follow=tk.BooleanVar(value=True);self.last_active=None;self.now=tk.StringVar();self.next_text=tk.StringVar();self.source=tk.StringVar(value='queue');self.policy=tk.StringVar(value='finish');self.enabled=tk.BooleanVar(value=role=='A');self.selection_label=tk.StringVar(value='Select an item')
        title=ttk.Frame(self,padding=(3,2));title.pack(fill='x',pady=(0,3));self.channel_header=title;title.columnconfigure(3,weight=1)
        self.title_font=tkfont.Font(self,family='TkDefaultFont',size=9,weight='bold')
        self.header_state=tk.StringVar(value='QUEUE');self.count=tk.StringVar()
        if role=='Music':
            ttk.Label(title,text='Music',style='PlayerName.TLabel').grid(row=0,column=0,sticky='w')
        else:
            self.role_badge=tk.Label(title,text=role,width=2,anchor='center',bg=app.ui_chrome['accent'],fg=app.ui_chrome['preview_bg'],font=('TkFixedFont',10,'bold'),padx=3,pady=2)
            self.role_badge.grid(row=0,column=0,padx=(0,5))
            self.programme_enabled=tk.BooleanVar(value=True)
            self.programme_switch=ttk.Checkbutton(title,text='ON',variable=self.programme_enabled,command=lambda:app.set_role_enabled(role,self.programme_enabled.get()))
            self.programme_switch.grid(row=0,column=1,sticky='w',padx=(0,5))
            self.camera_device=tk.StringVar(value=voice(app.project,role).extra.get('camera_device',getattr(app,'last_camera_device','/dev/video0')))
            # One visible live-source toggle: Camera again returns to Queue.
            # Keep the explicit Queue command for saved integrations and menus.
            self.source_button=ttk.Button(title,text='Queue',width=0,command=self.resume_queue)
            camera=ttk.Frame(title);camera.grid(row=0,column=2,sticky='w',padx=(0,3))
            self.camera_button=ttk.Button(camera,text='Camera',width=0,command=lambda:app.toggle_channel_camera(role));self.camera_button.pack(side='left')
            for event in ('<Map>','<Unmap>'):
                self.camera_button.bind(event,lambda e:app.after_idle(app.refresh_primary_toolbar) if not app.closing else None,add='+')
            self.source_disclosure=ttk.Button(camera,text='▾',width=1,command=self.source_menu);self.source_disclosure.pack(side='left')
            from mixer_fader import InlineMixerFader
            self.level_fader=InlineMixerFader(title,app,'',self.begin_level,self.change_level,self.end_level,length=48,show_label=False,display_width=4)
            self.level_fader.grid(row=0,column=3,sticky='ew')
            if self.editor_visibility is None:self.editor_visibility=tk.BooleanVar(value=True)
            self.effects_button=ttk.Button(title,text='Effects',width=8,command=lambda:app.open_channel_effects(role))
            self.effects_button.grid_forget()  # rack disclosure is directly below its own queue
            self.editor_disclosure=ttk.Button(title,text='⌃',width=2,command=self.toggle_editor);self.editor_disclosure.grid(row=0,column=5,padx=(2,0))
            app.add_tip(self.programme_switch,'Enable channel '+role+' in Programme. The editor can be collapsed independently.')
            app.add_tip(self.editor_disclosure,'Expand or collapse the queue editor. Source, level and Programme power remain here.')
            self.role_badge.bind('<Button-1>',lambda e:app.queue_deck.show_role(role))
            app.add_tip(self.source_button,'Return to this channel’s retained queue and resume its clock.')
            app.add_tip(self.source_disclosure,'Choose a camera device or preview Screen / Window capture. Nothing starts by browsing.')
            app.add_tip(self.camera_button,'Take Camera live in this channel once ready; press again to resume its held queue.')
        # One retained editor can sit below all narrow channel strips or inside
        # its own wide column. The model, callbacks and widgets never re-create.
        self.editor_body=ttk.Frame(parent if role!='Music' else self);self.editor_body.pack(in_=self,fill='both',expand=True)
        if role!='Music':
            self.bind('<Destroy>',lambda event:self.editor_body.destroy() if event.widget is self and self.editor_body.winfo_exists() else None,add='+')
        transport=PriorityToolbar(self.editor_body,gap=2);transport.pack(fill='x',pady=(0,3));self.toolbar=transport
        transport.more_button.configure(text='⋯',width=3)
        actions=transport;self.action_toolbar=actions
        previous=ttk.Button(transport,text='⏮',width=2,command=self.previous);transport.add(previous,priority=30)
        next_button=ttk.Button(transport,text='Next ›',width=6,command=self.next);transport.add(next_button,priority=0,pinned=True)
        self.hold_button=ttk.Button(transport,text='Replay' if role=='Music' else 'Loop current',command=self.hold);transport.add(self.hold_button,priority=0,pinned=True)
        self.end_policy=tk.StringVar(value='Finish')
        self.loop_queue=tk.BooleanVar(value=True)
        self.loop_queue_button=ttk.Checkbutton(transport,text='Loop queue',variable=self.loop_queue,command=lambda:app.set_queue_policy(role,'repeat' if self.loop_queue.get() else 'finish'))
        transport.add(self.loop_queue_button,priority=5,pinned=True,overflow=OverflowAdapter.mirror())
        actions.add_action('Randomise',lambda:app.randomise_playable('queues',only_role=self.role,settings=app.settings()),priority=10,style='Accent.TButton',width=9)
        mutate_button=actions.add_action('Shuffle',self.shuffle,priority=25,width=6)
        actions.add_action('Queue…',self.player_menu,priority=30)
        app.add_tip(self.loop_queue_button,'Checked: repeat this queue. Unchecked: finish after its last item. Separate from Loop current.')
        app.add_tip(previous,'Play the previous '+role+' occurrence without rewinding the session clock.')
        app.add_tip(next_button,'Take the next '+role+' occurrence. Other queues continue.')
        if role=='Music':app.add_tip(self.hold_button,'Replay this track now.')
        tools=actions
        app.add_tip(mutate_button,'Shuffle reorders eligible future timing slots in this queue; pins and authored edges remain protected.')
        self.current_canvas=tk.Canvas(self.editor_body,height=58,highlightthickness=0,takefocus=True);self.current_canvas.pack(fill='x')
        direct=ttk.Frame(self.editor_body);direct.pack(fill='x',pady=(1,2));self.selection_actions=direct
        ttk.Label(direct,textvariable=self.selection_label,width=1,style='Muted.TLabel').pack(side='left',fill='x',expand=True)
        self.take_button=ttk.Button(direct,text='Take',width=4,command=self.play_selected);self.take_button.pack(side='left',padx=1)
        self.duration_button=ttk.Button(direct,text='Duration',width=7,command=self.duration);self.duration_button.pack(side='left',padx=1)
        self.remove_button=ttk.Button(direct,text='Remove',width=6,command=self.remove);self.remove_button.pack(side='left',padx=1)
        if role!='Music':
            self.item_effects_button=ttk.Button(direct,text='Item FX',width=6,command=lambda:app.open_channel_effects(role,clip_id=self.selected) if self.selected else None)
            self.item_effects_button.pack(side='left',padx=1)
        app.add_tip(self.hold_button,'Replay this track now.' if role=='Music' else 'Loop the current visual occurrence; Next resumes the sequence.')
        self.current_canvas.bind('<Button-1>',lambda e:self.select(self.current_id) if getattr(self,'current_id',None) else None)
        self.current_canvas.bind('<Button-3>',lambda e:self.options_current(e));self.current_canvas.bind('<Configure>',lambda e:self.refresh(True))
        progress_host=ttk.Frame(self.editor_body,height=6);progress_host.pack(fill='x',pady=(1,2));progress_host.pack_propagate(False)
        self.progress=ttk.Progressbar(progress_host,maximum=1);self.progress.pack(fill='both',expand=True)
        self.boundary_button=ttk.Button(self.editor_body,text='Transition to next',command=lambda:self.transition(self.current_id))
        # Boundary editing is in the channel overflow and on cards (T), not a full row.
        # Retained button is also the contextual boundary anchor; not packed.
        app.add_tip(self.boundary_button,'Edit the boundary between this occurrence and the next. Drag its overlap or choose a transition to change it live. T opens the selected card’s boundary.')
        body=ttk.Frame(self.editor_body);body.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(body,height=100,highlightthickness=0,takefocus=True);self.canvas.pack(side='left',fill='both',expand=True)
        self.queue_scrollbar=ttk.Scrollbar(body,command=self.scroll)
        def yscroll(first,last):
            self.queue_scrollbar.set(first,last)
            if float(first)<=0.0 and float(last)>=1.0:self.queue_scrollbar.pack_forget()
            elif not self.queue_scrollbar.winfo_manager():self.queue_scrollbar.pack(side='right',fill='y')
        self.canvas.configure(yscrollcommand=yscroll)
        self.canvas.bind('<Configure>',lambda e:self.refresh(True));self.canvas.bind('<Button-1>',self.press)
        self.canvas.bind('<Button-3>',self.options);self.canvas.bind('<Double-1>',lambda e:self.options(e))
        self.canvas.bind('<Return>',lambda e:self.options());self.canvas.bind('<Delete>',lambda e:self.remove())
        self.canvas.bind('<Up>',lambda e:self.step_selection(-1));self.canvas.bind('<Down>',lambda e:self.step_selection(1))
        self.canvas.bind('<t>',lambda e:self.transition());self.current_canvas.bind('<t>',lambda e:self.transition(self.current_id))
        self.canvas.bind('<MouseWheel>',lambda e:self.wheel(-1 if e.delta>0 else 1));self.canvas.bind('<Button-4>',lambda e:self.wheel(-1));self.canvas.bind('<Button-5>',lambda e:self.wheel(1))
        self.canvas.bind('<B1-Motion>',self.drag_card);self.canvas.bind('<ButtonRelease-1>',self.release_card)
        self.append_drop=ttk.Label(self.editor_body,text='＋ Drop to append',anchor='center',style='Muted.TLabel',padding=(0,4));self.append_drop.pack(side='bottom',fill='x',before=body)
        self.append_drop.bind('<Button-1>',lambda e:self.add());app.add_tip(self.append_drop,'Append Library selection; or drag here for a quick append. Hold over the upcoming cards for one second to insert at a precise position.')
        if role!='Music' and getattr(app,'inline_rack_mode',False):
            from inline_racks import RackSection
            self.rack_section=RackSection(self,app,role,expanded=getattr(app,'inline_rack_preferences',{}).get(role,True))
            self.rack_section.pack(side='bottom',fill='x',before=self.editor_body)
        self.photos={};self.current_key=None
    def toggle_editor(self):
        deck=getattr(self.app,'queue_deck',None)
        if not getattr(self.app,'inline_rack_mode',False) and deck and getattr(deck,'narrow',False) and deck.active_role!=self.role:
            deck.show_role(self.role);return
        self.editor_visibility.set(not self.editor_visibility.get())
        if hasattr(self.app,'queue_deck'):self.app.queue_deck.reflow()
    def set_expanded(self,value,*,narrow=False,editor_row=0):
        if self.role=='Music':return
        manager=self.editor_body.winfo_manager()
        if narrow:
            if manager=='pack':self.editor_body.pack_forget()
            if value:
                info=self.editor_body.grid_info()
                if manager!='grid' or int(info.get('row',-1))!=editor_row:self.editor_body.grid(row=editor_row,column=0,sticky='nsew')
            elif manager=='grid':self.editor_body.grid_remove()
        else:
            if manager=='grid':self.editor_body.grid_remove()
            if value:
                if manager!='pack':self.editor_body.pack(in_=self,fill='both',expand=True)
            elif manager=='pack':self.editor_body.pack_forget()
        self.editor_disclosure.configure(text='⌃' if value else '⌄')
    def source_menu(self):
        menu=tk.Menu(self,tearoff=False)
        menu.add_command(label='Return to retained queue',command=self.resume_queue)
        menu.add_separator()
        for value in self.camera_values():
            menu.add_command(label='Camera · '+('Test pattern' if value=='test' else value),command=lambda v=value:self.app.toggle_channel_camera(self.role,v))
        menu.add_command(label='Camera settings…',command=lambda:self.app.open_channel_camera(self.role))
        menu.add_command(label='Screen / Window…',command=lambda:self.app.open_visual_source(self.role))
        self.app.popup_menu(menu,self.source_disclosure)

    def resume_queue(self):
        now=self.app.programme_time() if self.app.playing else self.app.playhead
        mode=mode_at(voice(self.app.project,self.role),now)['mode']
        if mode=='camera' or self.role in getattr(self.app,'camera_tickets',{}):return self.app.toggle_channel_camera(self.role)
        if mode=='hold':return self.hold()

    def begin_level(self,event=None):
        if getattr(self,'level_active',False):return
        self.level_active=True;self.app.begin_gesture('program');self.level_time=self.app.programme_time() if self.app.playing else self.app.playhead
        from visual_channels import adopt_channel_mix
        adopt_channel_mix(self.app.project,self.level_time,self.app.signal_evaluator())
    def change_level(self,value):
        if not getattr(self,'level_active',False):return
        layer=voice(self.app.project,self.role);self.app.write_parameter(layer.opacity,value,layer.id)
    def end_level(self,event=None):
        if not getattr(self,'level_active',False):return
        self.level_active=False;self.app.end_gesture();self.refresh(True)

    def camera_values(self):
        if self.role=='Music':return []
        values=[]
        layer=voice(self.app.project,self.role)
        for value in (layer.extra.get('camera_device'),getattr(self.app,'last_camera_device',None),'test'):
            if value is not None and str(value) not in values:values.append(str(value))
        for asset in self.app.project.assets.values():
            if asset.kind=='camera':
                value=asset.metadata.get('device')
                if value is not None and str(value) not in values:values.append(str(value))
        return values
    def camera_selected(self,event=None):
        if self.role=='Music':return
        value=self.camera_device.get().strip()
        if not value:return
        layer=voice(self.app.project,self.role);layer.extra['camera_device']=value;self.app.last_camera_device=value
        if mode_at(layer,self.app.programme_time() if self.app.playing else self.app.playhead)['mode']=='camera':self.app.toggle_channel_camera(self.role,value)
        else:self.app.update_status('Camera '+value+' selected for channel '+self.role+' · press 📷 Camera to use it.')

    def edit_operation(self,label,operation,*args):
        from queue_gaps import edit_queue
        now=self.app.programme_time() if self.app.playing and not self.app.reviewing else None
        return self.app.transaction(label,lambda:edit_queue(self.app.project,self.role,operation,*args,now=now))

    def move_selected(self,index):
        if not self.selected:return
        if self.role=='Music':
            from music_queue import move
            self.edit_operation('Reorder Music',move,self.selected,index)
        else:
            from queue_model import reorder
            self.edit_operation('Reorder '+self.role,reorder,voice(self.app.project,self.role).id,self.selected,index)

    def remove(self):
        if not self.selected:return
        if self.role=='Music':
            from music_queue import remove
            self.edit_operation('Remove occurrence',remove,self.selected)
        else:
            from queue_model import remove
            from queue_gaps import edit_queue
            now=self.app.programme_time() if self.app.playing and not self.app.reviewing else self.app.playhead
            self.app.transaction('Remove occurrence',lambda:edit_queue(self.app.project,self.role,remove,self.selected,now=now))

    def duration(self):
        item=self.find()
        if item is None:return
        project=self.app.project;occurrence_id=self.selected;role=self.role
        from queue_gaps import edit_queue
        from music_queue import duration as music_duration
        from queue_model import set_duration
        operation=music_duration if role=='Music' else set_duration
        def build(parent):
            frame=ttk.Frame(parent,padding=6);frame.pack(fill='x')
            ttk.Label(frame,text='Duration · seconds').pack(anchor='w')
            value=tk.StringVar(value=f'{self.dur(item):.3f}');entry=ttk.Entry(frame,textvariable=value,width=12);entry.pack(fill='x')
            slider_value=tk.DoubleVar(value=self.dur(item));message=tk.StringVar();token=[None];last_text=[value.get()];analysis_dirty=[False]
            def begin(event=None):
                if self.app.project is not project:return False
                if token[0] is not None and getattr(self.app,'gesture',None) is token[0]:return True
                if getattr(self.app,'gesture',None):self.app.end_gesture()
                self.app.begin_gesture('queue-duration');token[0]=self.app.gesture;return True
            def finish(event=None):
                refresh=analysis_dirty[0] and self.app.project is project;analysis_dirty[0]=False
                if token[0] is not None and getattr(self.app,'gesture',None) is token[0]:self.app.end_gesture()
                token[0]=None
                if refresh and hasattr(self.app,'prepare_sound_analysis'):self.app.prepare_sound_analysis()
                return 'break' if event and getattr(event,'keysym','') in ('Return','KP_Enter') else None
            def cancel(event=None):
                analysis_dirty[0]=False
                if self.app.project is project and token[0] is not None and getattr(self.app,'gesture',None) is token[0]:self.app.cancel_gesture()
                token[0]=None;message.set('Gesture cancelled. Reopen duration to edit again.');return 'break'
            def change(event=None):
                text=value.get()
                if event is not None and (getattr(event,'keysym','') in ('Return','KP_Enter','Escape','Tab') or text==last_text[0]):return
                last_text[0]=text
                if not begin():message.set('The project changed. Reopen duration.');return
                try:
                    n=float(value.get());now=self.app.programme_time() if self.app.playing and not self.app.reviewing else None
                    edit_queue(project,role,operation,occurrence_id,n,now=now)
                except (ValueError,StopIteration) as exc:message.set(str(exc));return
                slider_value.set(n)
                analysis_dirty[0]=True
                self.app.changed(redraw=False);message.set('Next repeat duration.' if now is not None else 'Live duration.')
            def slide(v):value.set(f'{float(v):.3f}');change()
            scale=ttk.Scale(frame,from_=1/project.fps,to=max(30,self.dur(item)*2),variable=slider_value,command=slide);scale.pack(fill='x')
            for widget in (entry,scale):
                widget.bind('<FocusIn>',begin);widget.bind('<FocusOut>',finish);widget.bind('<Escape>',cancel)
            entry.bind('<KeyRelease>',change);entry.bind('<Return>',finish);entry.bind('<KP_Enter>',finish)
            scale.bind('<ButtonPress-1>',begin);scale.bind('<ButtonRelease-1>',finish)
            ttk.Label(frame,textvariable=message,wraplength=380).pack(fill='x')
            frame.bind('<Destroy>',lambda e:finish() if e.widget is frame else None,add='+')
            return frame
        self.app.open_context_tray(('queue-duration',role,occurrence_id),role+' · Duration',build)

    def add_gap(self):
        from queue_gaps import add_visual_gap,add_music_gap
        index=next((i+1 for i,e in enumerate(self.items) if self.ident(e)==self.selected),len(self.items))
        now=self.app.programme_time() if self.app.playing and not self.app.reviewing else None
        fn=(lambda:add_music_gap(self.app.project,1.,index=index,now=now)) if self.role=='Music' else (lambda:add_visual_gap(self.app.project,voice(self.app.project,self.role).id,1.,index=index,now=now))
        created=self.app.transaction('Add '+self.role+' gap',fn)
        if created:self.selected=self.ident(created);self.refresh(True)

    def options(self,event=None):
        if event:
            hit=self.hit(event.x,event.y)
            if hit:self.select(hit[0])
        item=self.find()
        if item is not None and gap_name(item):
            menu=tk.Menu(self,tearoff=False)
            menu.add_command(label='Duration…',command=self.duration)
            menu.add_command(label='Transition to next…',command=self.transition)
            menu.add_command(label='Add gap after',command=self.add_gap)
            menu.add_command(label='Move earlier',command=lambda:self.move_selected(self.items.index(item)-1))
            menu.add_command(label='Move later',command=lambda:self.move_selected(self.items.index(item)+1))
            menu.add_command(label='Remove gap',command=self.remove)
            if self.role!='Music':
                for mode,label in [('transparent','Transparent'),('hold','Hold frame'),('colour','Colour…')]:
                    menu.add_command(label=label,command=lambda mode=mode:self.gap_mode(mode))
            self.app.popup_menu(menu,self.toolbar);return
        return super().options(event)

    def gap_mode(self,mode):
        from tkinter import colorchooser
        from queue_policies import preserve_visual_history,next_visual_cycle
        from queue_model import append_switch
        colour='#000000'
        if mode=='colour':
            _,colour=colorchooser.askcolor(parent=self,title='Gap colour')
            if not colour:return
        def change():
            layer=voice(self.app.project,self.role);item=next(c for c in layer.clips if c.id==self.selected)
            if layer.locked or item.locked or item.extra.get('playable_pin'):raise ValueError('Unlock or unpin this gap first.')
            if self.app.playing and not self.app.reviewing:
                now=self.app.programme_time();q=queue_position(layer,now)
                at=max(now,max((r['end'] for r in layer.extra.get('queue_history',[]) if r['start']<=now<r['end']),default=now))
                if item.start<=q:
                    if layer.extra.get('queue_policy')!='repeat':raise ValueError('This gap has started. Edit a Draft or the next repeat.')
                    at=max(at,next_visual_cycle(layer,now))
                preserve_visual_history(layer,at);append_switch(layer,at,'queue',0. if at>now else q)
            item.extra['queue_gap']={'mode':mode,'colour':colour}
            return True
        self.app.transaction('Gap picture',change)

    def next(self):
        if self.role!='Music':return super().next()
        from queue_policies import music_position
        q=music_position(self.app.project,self.app.playhead)
        item=next((e for e in self.items if self.start(e)>q+.001),None)
        if item is None and self.items and self.app.project.extra.get('music_queue_policy')=='repeat':item=self.items[0]
        if item:self.app.music_take(self.ident(item))
        else:self.app.update_status('Music queue finished.')

    def previous(self):
        self.refresh();previous=[e for e in self.items if self.ident(e)!=self.current_id and self.start(e)<self.cursor]
        if previous:
            eid=self.ident(previous[-1]);self.app.music_take(eid) if self.role=='Music' else self.app.queue_next(self.role,eid)
        else:self.app.update_status('No earlier '+self.role+' occurrence.')
    def hold(self):
        if self.role=='Music':
            if self.current_id:self.app.music_take(self.current_id)
        else:self.app.hold_queue(self.role)
    def player_menu(self):
        m=tk.Menu(self,tearoff=False)
        m.add_command(label='Randomise…',command=lambda:self.app.open_randomise('queues',self.toolbar,role=self.role))
        m.add_command(label='Shuffle eligible upcoming',command=self.shuffle)
        m.add_command(label='Add Library selection',command=self.add)
        m.add_command(label='Transition to next…',command=lambda:self.transition(self.current_id))
        m.add_command(label='Add gap after selection',command=self.add_gap)
        m.add_command(label='Selected item options…',command=self.options)
        if self.role!='Music':
            m.add_separator()
            m.add_command(label='Hold / resume current item',command=self.hold)
            m.add_command(label='Resume queue',command=lambda:self.app.queue_source(self.role,'queue'))
            m.add_command(label='Loop queue',command=lambda:self.app.set_queue_policy(self.role,'repeat'))
            m.add_command(label='Finish at queue end',command=lambda:self.app.set_queue_policy(self.role,'finish'))
        self.app.popup_menu(m,self.toolbar)
    def options_current(self,e):
        if self.current_id:self.selected=self.current_id;self.options()
    def step_selection(self,delta):
        if not self.items:return 'break'
        ids=[self.ident(e) for e in self.items];i=ids.index(self.selected) if self.selected in ids else 0
        self.select(ids[max(0,min(len(ids)-1,i+delta))]);return 'break'
    def select(self,cid):
        self.selected=cid;self.refresh(True)
        # Selecting media must not open another rack or move its controls.
        self.app.update_status(self.role+' selected · Enter / right-click for duration, transition, pin and ordering. Selection does not play it.')
    def press(self,e):
        hit=self.hit(e.x,e.y)
        if hit and hit[3]=='transition':
            self.drag=None;self.select(hit[0]);self.transition(hit[0],hit[4]);return 'break'
        super().press(e);self.drag=(e.x_root,e.y_root,self.selected) if hit else None
    def transition(self,cid=None,to_id=None):
        from queue_transition_ui import open_queue_transition
        cid=cid or self.selected
        if cid:return open_queue_transition(self.app,self.role,cid,to_id)
        self.app.update_status('Select a queue item to edit its next boundary.')
    def drag_card(self,e):
        if not self.drag or abs(e.y_root-self.drag[1])<6:return
        hit=self.hit(e.x,e.y);self.canvas.delete('drop')
        if hit:self.canvas.create_line(4,hit[1],max(10,self.canvas.winfo_width()-4),hit[1],width=3,fill=self.app.ui_chrome['accent'],tags='drop')
    def release_card(self,e):
        drag=self.drag;self.drag=None;self.canvas.delete('drop')
        if not drag or abs(e.y_root-drag[1])<6:return
        hit=self.hit(e.x,e.y)
        if hit and hit[0]!=drag[2]:
            self.selected=drag[2];index=next((i for i,it in enumerate(self.items) if self.ident(it)==hit[0]),-1)
            if index>=0:self.move_selected(index)
    def fit_title(self,text,width):
        text=str(text).replace('\n',' ')
        if self.title_font.measure(text)<=width:return text
        while text and self.title_font.measure(text+'…')>width:text=text[:-1]
        return text+'…'
    def thumbnail(self,aid,size=(46,29)):
        photo=self.app.thumbnails.get(aid)
        if photo is None:
            a=self.app.project.asset(aid)
            if a and a.kind in ('video','image','audio'):self.app.request_thumbnail(a)
            return None
        key=(aid,id(photo),size)
        if key not in self.photos:
            try:
                im=ImageTk.getimage(photo);im.thumbnail(size,Image.Resampling.LANCZOS)
                self.photos[key]=ImageTk.PhotoImage(im,master=self)
            except (ValueError,tk.TclError):return None
            if len(self.photos)>80:self.photos={key:self.photos[key]}
        return self.photos[key]
    def refresh(self,force=False):
        p=self.app.project;t=self.app.programme_time() if self.app.playing and not self.app.reviewing else self.app.playhead;layer=None
        if self.role=='Music':
            from queue_policies import music_position
            self.items=items(p);self.cursor=music_position(p,t);active=[e for e in self.items if self.start(e)<=self.cursor<self.start(e)+self.dur(e)];on=active[-1] if active else None
            self.policy.set(p.extra.get('music_queue_policy','finish'))
        else:
            layer=next((l for l in p.layers if l.extra.get('voice')==self.role),None)
            if layer is None:self.items=[];return
            self.items=ordered(layer);self.cursor=queue_position(layer,t);on=current(layer,t)
            mode=mode_at(layer,t)['mode'];self.source.set(mode);self.enabled.set(layer.enabled);self.policy.set(layer.extra.get('queue_policy','finish'))
            self.hold_button.configure(text='Resume sequence' if mode=='hold' else 'Loop current')
            if hasattr(self,'source_button'):
                preparing=self.role in getattr(self.app,'camera_tickets',{})
                self.source_button.configure(style='Accent.TButton' if mode!='camera' else 'TButton')
                self.camera_button.configure(text='Wait…' if preparing else 'Cam ✓' if mode=='camera' else 'Camera',style='Accent.TButton' if mode=='camera' else 'TButton')
                device=layer.extra.get('camera_device',getattr(self.app,'last_camera_device',''))
                if device and self.camera_device.get()!=str(device):self.camera_device.set(str(device))
            if hasattr(self,'level_fader') and not getattr(self,'level_active',False):
                from visual_channels import strength_values
                self.level_fader.sync(strength_values(p,t,self.app.signal_evaluator()).get(self.role,0.))
            if hasattr(self,'programme_enabled') and self.programme_enabled.get()!=bool(layer.enabled):self.programme_enabled.set(bool(layer.enabled))
        self.end_policy.set('Loop queue' if self.policy.get()=='repeat' else 'Finish')
        self.loop_queue.set(self.policy.get()=='repeat')
        state=('MUSIC' if self.role=='Music' else ('CAM' if self.source.get()=='camera' else 'HOLD' if self.source.get()=='hold' else 'QUEUE'))
        if self.role!='Music' and not self.enabled.get():state='OFF'
        if self.header_state.get()!=state:self.header_state.set(state)
        self.current_id=self.ident(on) if on else None
        self.future=[e for e in self.items if self.start(e)>self.cursor+.001];self.next_id=self.ident(self.future[0]) if self.future else None
        boundaries=boundary_labels(self.items,self.role,layer,p)
        current_boundary=boundaries.get(self.current_id)
        boundary_text='⇄ '+current_boundary[1] if current_boundary else 'End of queue'
        if self.boundary_button.cget('text')!=boundary_text:
            self.boundary_button.configure(text=boundary_text,state='normal' if current_boundary else 'disabled')
        
        if self.count.get()!=str(len(self.future)):self.count.set(str(len(self.future)))
        if not self.winfo_ismapped() and not force:return
        c=self.app.ui_chrome;cv=self.current_canvas;w=max(120,cv.winfo_width())
        progress=max(0.,min(1.,(self.cursor-self.start(on))/max(.001,self.dur(on)))) if on else 0
        self.progress['value']=progress
        name=lambda e:(gap_name(e) or (p.asset(self.aid(e)).name if p.asset(self.aid(e)) else 'Missing source')) if e else 'No media'
        selected=next((item for item in self.items if self.ident(item)==self.selected),None)
        self.selection_label.set('Selected · '+name(selected) if selected else 'Select an item')
        for button in (self.take_button,self.duration_button,self.remove_button):button.configure(state='normal' if selected else 'disabled')
        
        if self.now.get()!=name(on):self.now.set(name(on))
        next_name=name(self.future[0]) if self.future else 'No upcoming media'
        if self.next_text.get()!=next_name:self.next_text.set(next_name)
        key=(self.current_id,int(self.cursor),w,self.selected,self.source.get(),self.enabled.get(),tuple(c.items()),id(self.app.thumbnails.get(self.aid(on) if on else '')))
        if force or key!=self.current_key:
            self.current_key=key;cv.delete('all');cv.configure(bg=c['field_bg'])
            cv.create_rectangle(1,1,w-1,56,fill=c['field_bg'],outline=c['accent'] if self.current_id and self.selected==self.current_id else c['panel_edge'])
            badge=('QUEUE · PLAYING' if self.app.playing else 'QUEUE · READY') if layer else 'NOW' if self.app.playing else 'READY'
            cancelled=(p.extra.get('music_pending_cancelled_at') if self.role=='Music' else layer.extra.get('queue_pending_cancelled_at') if layer else None)
            if cancelled is not None and cancelled<=t<cancelled+4:badge='MANUAL · NEXT CYCLE RESET'
            if layer and not layer.enabled:badge='SOURCE OFF'
            if layer and self.source.get()=='hold':badge='LOOP CURRENT'
            if layer and self.source.get()=='camera':badge='CAMERA · QUEUE HELD'
            cv.create_text(8,11,text=badge,anchor='w',fill=c['accent'],font=('TkFixedFont',8,'bold'))
            if layer and self.source.get()=='camera':
                asset=p.asset(mode_at(layer,t).get('camera_id',''))
                cv.create_text(28,35,text='▣',fill=c['accent'],font=('TkDefaultFont',20))
                cv.create_text(64,35,text=self.fit_title(asset.name if asset else 'Camera unavailable',w-76),anchor='w',fill=c['foreground'],font=('TkDefaultFont',9))
            elif on:
                photo=self.thumbnail(self.aid(on),(56,28))
                if photo:cv.create_image(8,23,image=photo,anchor='nw')
                else:cv.create_text(25,35,text='♫' if self.role=='Music' else '▶',fill=c['muted_fg'],font=('TkDefaultFont',18))
                cv.create_text(76,36,text=self.fit_title(' ↔ '.join(name(e) for e in active) if self.role=='Music' and len(active)>1 else name(on),w-88),anchor='w',fill=c['foreground'],font=('TkDefaultFont',9,'bold'))
                cv.create_text(w-7,11,text=clock_text(self.cursor-self.start(on))+' / '+clock_text(self.dur(on)),anchor='e',fill=c['muted_fg'],font=('TkFixedFont',8))
            else:cv.create_text(w/2,34,text='No source queued',width=w-14,fill=c['muted_fg'],justify='center',font=('TkDefaultFont',9))
        cv=self.canvas;width=max(120,cv.winfo_width());top=cv.canvasy(0)
        stride=78
        key=(width,int(top//stride),tuple((self.ident(e),self.aid(e),self.start(e),self.dur(e),name(e)) for e in self.future),tuple(boundaries.items()),self.selected,tuple(c.items()),len(self.app.thumbnails))
        if key==self.key and not force:return
        self.key=key;self.hits=[];cv.delete('all');cv.configure(bg=c['preview_bg'])
        first=max(0,int(top//stride)-1);last=min(len(self.future),first+max(4,int(cv.winfo_height()/stride)+3))
        for n in range(first,last):
            e=self.future[n];eid=self.ident(e);y=2+n*stride;selected=eid==self.selected
            cv.create_rectangle(2,y,width-2,y+52,fill=c['selection_bg'] if selected else c['field_bg'],outline=c['accent'] if selected else c['panel_edge'])
            photo=self.thumbnail(self.aid(e)) if self.aid(e) else None;tx=58 if photo and width>=150 else 9
            if photo and width>=150:cv.create_image(7,y+10,image=photo,anchor='nw')
            cv.create_text(tx,y+14,text=self.fit_title(name(e),width-tx-5),anchor='w',fill=c['foreground'],font=('TkDefaultFont',9,'bold'))
            pinned=e.get('pinned',False) if self.role=='Music' else e.extra.get('playable_pin') or e.locked
            cv.create_text(tx,y+38,text=('NEXT  ' if n==0 else '')+clock_text(self.dur(e))+('  PIN' if pinned else ''),anchor='w',fill=c['accent'] if n==0 else c['muted_fg'],font=('TkFixedFont',8))
            self.hits.append((eid,y,y+52,'clip'))
            if eid in boundaries:
                to_id,label=boundaries[eid]
                cv.create_line(width/2,y+52,width/2,y+57,fill=c['muted_fg'])
                cv.create_rectangle(12,y+56,width-12,y+75,fill=c['field_bg'],outline=c['panel_edge'])
                cv.create_text(width/2,y+65,text=self.fit_title('⇄ '+label,width-30),fill=c['accent'],font=('TkDefaultFont',8))
                self.hits.append((eid,y+53,y+77,'transition',to_id))
        if not self.future:cv.create_text(width/2,26,text='Up next is empty',fill=c['muted_fg'],font=('TkDefaultFont',9))
        cv.configure(scrollregion=(0,0,width,max(cv.winfo_height(),len(self.future)*stride+4)))

class QueueColumns(ttk.Frame):
    def __init__(self,parent,app,prefs):
        super().__init__(parent,padding=(5,3));self.app=app;self.pages={};self.sequence=tk.BooleanVar(value=True);self.mix_active=False;self.active_role='A';self.narrow=False
        self.visibility={r:tk.BooleanVar(value=prefs.get('queue_columns',{}).get(r,r in ('A','B'))) for r in ('A','B','C','D','Music')}
        bar=ttk.Frame(self);bar.pack(fill='x',pady=(0,2));self.panel_bar=bar
        app.shell.mount_panel_controls('panel.queues',bar)
        head=PriorityToolbar(bar,gap=3);head.pack(side='left',fill='x',expand=True);self.header=head
        randomise=ttk.Button(head,text='Options…',command=lambda:app.open_randomise('queues',randomise));head.add(randomise,priority=20)
        self.add_button=ttk.Button(head,text='+ Channel',command=self.add_channel);head.add(self.add_button,priority=25)
        self.channel_faders={};self.channel_enabled={}
        viewport=ttk.Frame(self);viewport.pack(fill='both',expand=True);viewport.rowconfigure(0,weight=1);viewport.columnconfigure(0,weight=1)
        self.hcanvas=tk.Canvas(viewport,highlightthickness=0,height=170);self.hcanvas.grid(row=0,column=0,sticky='nsew')
        self.vscroll=ttk.Scrollbar(viewport,orient='vertical',command=self.hcanvas.yview);self.hcanvas.configure(yscrollcommand=self.vscroll.set)
        self.columns=ttk.Frame(self.hcanvas);self.window=self.hcanvas.create_window(0,0,anchor='nw',window=self.columns)
        self.hscroll=ttk.Scrollbar(self,orient='horizontal',command=self.hcanvas.xview);self.hcanvas.configure(xscrollcommand=self.hscroll.set)
        self.sound=PlayerColumn(app.source_strip.music_host,app,'Music',self.visibility['Music']);self.sound.pack(fill='both',expand=True);self.pages['Music']=self.sound
        self.mix=tk.DoubleVar(value=.5);self.sync_channels();self.hcanvas.bind('<Configure>',lambda e:self.reflow(save=False));self.reflow(save=False)
    def sync_channels(self):
        from visual_channels import channels,MAX_CHANNELS
        roles=[l.extra['voice'] for l in channels(self.app.project)]
        if tuple(roles)==getattr(self,'_channel_roles',None):return
        self._channel_roles=tuple(roles);self.channel_faders={};self.channel_enabled={}
        for r in list(self.pages):
            if r not in roles and r!='Music':self.pages.pop(r).destroy()
        for r in roles:
            if r not in self.pages:self.pages[r]=PlayerColumn(self.columns,self.app,r,self.visibility[r])
            page=self.pages[r];self.channel_faders[r]=page.level_fader;self.channel_enabled[r]=page.programme_enabled
        self.add_button.configure(state='disabled' if len(roles)>=MAX_CHANNELS else 'normal')
        from instrument_density import compact_tree
        compact_tree(self);compact_tree(self.sound)
        self._visible_roles=None;self._layout_key=None
    def add_channel(self):
        from visual_channels import add_channel,adopt_channel_mix
        def add():
            adopt_channel_mix(self.app.project,self.app.playhead,self.app.signal_evaluator());return add_channel(self.app.project)
        layer=self.app.transaction('Add visual channel',add)
        if layer:
            self.visibility[layer.extra['voice']].set(True);self.sync_channels();self.reflow()
            self.app.update_status('Channel '+layer.extra['voice']+' added · enabled and shown. Drop media or select Camera.')
    def show_role(self,role):
        if role=='Music':
            if hasattr(self.app,'source_strip'):
                self.app.shell.show('Audio');self.app.source_strip.show_queue();self.app.source_strip.music_host.focus_set()
            return
        self.sync_channels()
        if role in self.visibility:self.active_role=role;self.visibility[role].set(True);self.reflow()
    def reflow(self,save=True):
        self.sync_channels()
        visible=list(self._channel_roles)
        w=max(180,self.hcanvas.winfo_width());h=max(100,self.hcanvas.winfo_height());self.narrow=w<380*len(visible)
        if self.active_role not in visible or not self.visibility[self.active_role].get():
            self.active_role=next((role for role in visible if self.visibility[role].get()),visible[0] if visible else 'A')
        expanded={role:bool(self.visibility[role].get()) for role in visible}
        for role in visible:self.pages[role].set_expanded(expanded[role],narrow=False)
        width=w
        mins={role:(225 if expanded[role] else 45)+(245 if self.pages[role].rack_section.expanded else 38) for role in visible}
        minimum=sum(mins.values()) if self.narrow else max(mins.values(),default=200)
        height=max(h,minimum)
        layout=(tuple(visible),w,h,height,self.narrow,tuple(expanded.items()),tuple(mins.items()));structural=layout!=getattr(self,'_layout_key',None)
        if structural:
            self._layout_key=layout
            for i in range(6):
                self.columns.columnconfigure(i,weight=0,minsize=0,uniform='');self.columns.rowconfigure(i,weight=0,minsize=0)
            for i,role in enumerate(visible):
                row,col=(i,0) if self.narrow else (0,i)
                page=self.pages[role];page.pack_propagate(False)
                page.grid(row=row,column=col,sticky='nsew')
                self.columns.columnconfigure(col,weight=1,uniform='' if self.narrow else 'players')
                self.columns.rowconfigure(row,weight=1,minsize=mins[role] if self.narrow else minimum)
            self._visible_roles=tuple(visible)
            self.hcanvas.itemconfigure(self.window,width=width,height=height);self.hcanvas.configure(scrollregion=(0,0,width,height))
            if height>h:self.vscroll.grid(row=0,column=1,sticky='ns')
            else:self.vscroll.grid_remove()
            self.hscroll.pack_forget()
        if structural:self.refresh(True)
        if save:self.app.save_preferences()
    def refresh(self,force=False):
        self.sync_channels();p=self.app.project;t=self.app.playhead
        events=items(p);active=[e for e in events if e['start']<=t<e['start']+e['duration']];nxt=next((e for e in events if e['start']>t),None)
        def name(e):
            a=p.asset(e['asset_id']) if e else None;return a.name if a else ('Missing' if e else '—')
        caption='Music: '+(' ↔ '.join(name(e) for e in active) or '—')+' → '+name(nxt)
        if self.app.music_transport_caption.get()!=caption:self.app.music_transport_caption.set(caption)
        for page in self.pages.values():page.refresh(force)
        # Each PlayerColumn refreshes its owned level/power state. Master is
        # deliberately Level-1 and synced by the global toolbar.
        if hasattr(self.app,'refresh_primary_toolbar'):self.app.refresh_primary_toolbar()
        if hasattr(self.app,'overview'):self.app.overview.schedule()
        if hasattr(self.app,'source_strip'):self.app.source_strip.refresh()
        if hasattr(self.app,'conductor'):self.app.conductor.refresh()
        if hasattr(self.app,'empty_preview'):self.app.refresh_empty_preview()
