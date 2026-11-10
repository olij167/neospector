"""UX20: one compact A/B mixer surface with transition and audio reaction.

The original project.voice_mix and ux16_transition remain the sole authorities.
No second properties panel and no source is activated while editing the mix.
"""
import tkinter as tk
from tkinter import ttk
from ui_chrome import tk_scale_theme_options
from ux16_transitions import STYLES,configure_transition
from timed_mix import configure_pingpong,pingpong_at,validate as validate_pingpong

BANDS=(('full','Level'),('bass','Bass'),('mid','Mid'),('high','High'),('onset','Hits'))

class VisualMixStrip(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(8,4),style='UX20.Mixer.TFrame')
        self.app=app;self.active=False;self._compact=None;self._depth_dragging=False;self._depth_controls_visible=False
        self._pingpong_state=None
        self.value=tk.DoubleVar(value=0);self.caption=tk.StringVar(value='50 : 50')
        self.transition_style=tk.StringVar(value=app.project.extra.get('ux16_transition',{}).get('kind','dissolve'))
        self.react_active=tk.BooleanVar(value=app.project.voice_mix.mode=='react')
        self.band=tk.StringVar(value=app.project.voice_mix.react_band)
        self.react_depth=tk.DoubleVar(value=abs(app.project.voice_mix.react_amount))
        fader_row=ttk.Frame(self)
        fader_row.columnconfigure(1,weight=1)
        ttk.Label(fader_row,text='A',style='UX20.MixEdge.TLabel').grid(row=0,column=0,padx=(0,8))
        self.fader=tk.Scale(fader_row,variable=self.value,from_=0,to=1,resolution=.001,
            orient='horizontal',showvalue=False,command=self.write,length=125,
            **{**tk_scale_theme_options(app.ui_chrome),'width':10,'sliderlength':18,'bd':0,'highlightthickness':0})
        self.fader.grid(row=0,column=1,sticky='ew')
        ttk.Label(fader_row,text='B',style='UX20.MixEdge.TLabel').grid(row=0,column=2,padx=(8,7))
        ttk.Label(fader_row,textvariable=self.caption,style='UX20.MixRatio.TLabel',width=8).grid(row=0,column=3)
        self.tools=ttk.Frame(self);self.tools.pack(fill='x')
        self.mix_controls=ttk.Frame(self.tools)
        self.transition_group=ttk.Frame(self.mix_controls)
        self.transition_label=ttk.Label(self.transition_group,text='TRANSITION',style='UX20.ToolLabel.TLabel')
        self.transition_label.pack(side='left',padx=(1,5))
        self.previous_transition=ttk.Button(self.transition_group,text='‹',width=2,style='UX20.Small.TButton',command=lambda:self.step_transition(-1))
        # Preset arrows removed: animation is authored in Transition FX rack.
        self.transition_display=ttk.Button(self.transition_group,text='✧ Edit motion',width=14,style='UX20.Transition.TButton',command=self.open_transition_menu)
        self.transition_display.pack(side='left',padx=1)
        self.pingpong_button=ttk.Button(self.transition_group,text='↔ Auto OFF',width=11,
            style='UX20.Small.TButton',command=self.toggle_pingpong)
        self.pingpong_button.pack(side='left',padx=(3,0))
        self.next_transition=ttk.Button(self.transition_group,text='›',width=2,style='UX20.Small.TButton',command=lambda:self.step_transition(1))
        # Authoring, grouping and timing now live in the Transition rack.
        self.audio_group=ttk.Frame(self.mix_controls)
        self.react_button=ttk.Button(self.audio_group,text='∿ React OFF',width=12,style='UX20.ReactionOff.TButton',command=self.toggle_reactive)
        self.react_button.pack(side='left',padx=(1,3))
        # Legacy compatibility handles are not packed: microphone and the
        # soundtrack queue both have explicit upper-right channel controls.
        self.mic_button=ttk.Button(self.audio_group,text='MIC',width=5,
            style='UX19.MicIdle.TButton',command=app.quick_microphone)
        # UX28: source MIC lives with CAM A/B in top channel pair strip.
        self.audio_queue_button=ttk.Button(self.audio_group,text='♫ Audio ▾',width=9,
            style='UX20.Small.TButton',command=app.toggle_audio_tray)
        # The audio queue now has its own persistent corner toggle. Preserve
        # the callback handle for compatibility but do not show two controls.
        app.add_tip(self.mic_button,'Toggle microphone reaction input; it does not change soundtrack queue playback.')
        app.add_tip(self.audio_queue_button,'Open the soundtrack queue in the bottom-right dock.')
        self.previous_band=ttk.Button(self.audio_group,text='‹',width=2,style='UX20.Small.TButton',command=lambda:self.step_band(-1))
        self.previous_band.pack(side='left')
        self.band_button=ttk.Button(self.audio_group,text='Level',width=6,style='UX20.Small.TButton',command=self.open_band_menu)
        self.band_button.pack(side='left')
        self.next_band=ttk.Button(self.audio_group,text='›',width=2,style='UX20.Small.TButton',command=lambda:self.step_band(1))
        self.next_band.pack(side='left',padx=(0,3))
        self.depth_label=ttk.Label(self.audio_group,text='Depth',style='UX20.ToolLabel.TLabel')
        self.depth_slider=ttk.Scale(self.audio_group,variable=self.react_depth,from_=0,to=1,length=64)
        self.depth_value=ttk.Label(self.audio_group,text='100%',width=5,style='UX20.ToolLabel.TLabel')
        self.depth_slider.configure(command=lambda value:self.depth_value.configure(text=f'{round(float(value)*100)}%'))
        self.depth_slider.bind('<ButtonPress-1>',lambda e:setattr(self,'_depth_dragging',True))
        self.depth_slider.bind('<ButtonRelease-1>',self.finish_depth_drag)
        self.depth_slider.bind('<Escape>',self.cancel_depth_drag)
        self.direction_button=ttk.Button(self.audio_group,text='A→B',width=5,style='UX20.Small.TButton',command=self.reverse_reaction)
        self.tools.columnconfigure(1,weight=1)
        # Preview actions occupy the left edge; transition and reaction
        # are a single responsive group at the right edge.
        self.preview_actions=ttk.Frame(self.tools)
        app.record_button=app.command_button(self.preview_actions,'record.toggle',text='● Record',width=8,style='UX28.Record.TButton')
        app.record_button.pack(side='left',padx=(2,3))
        app.record_disclosure=app.record_button
        app.output_viewer_button=app.command_button(self.preview_actions,'output.viewer',text='↗ Output',width=9,style='UX28.Output.TButton')
        app.output_viewer_button.pack(side='left',padx=(0,3))
        self.focus_button=ttk.Button(self.preview_actions,text='⛶ Focus',width=8,style='UX28.Action.TButton',command=app.toggle_focus_output)
        self.focus_button.pack(side='left')
        self.preview_actions.grid(row=0,column=0,sticky='w',padx=(0,7))
        app.add_tip(app.record_button,'Start or stop programme recording.')
        app.add_tip(app.output_viewer_button,'Open a clean separate output viewer.')
        self._choice_popup=None

        fader_row.pack(fill='x',pady=(4,0))
        # Only reveal timing controls when the performer opts into an automatic
        # A/B cycle. Values commit on Enter/focus-out, never each keypress.
        defaults=validate_pingpong(app.project.extra.get('ux41_pingpong'))
        self.hold_var=tk.StringVar(value=f"{defaults['hold']:g}")
        self.fade_var=tk.StringVar(value=f"{defaults['fade']:g}")
        self.tempo_row=ttk.Frame(self,padding=(8,1));self._timing_visible=False
        ttk.Label(self.tempo_row,text='PING-PONG',style='UX20.ToolLabel.TLabel').pack(side='left',padx=(0,7))
        ttk.Label(self.tempo_row,text='Hold each (s)',style='UX20.ToolLabel.TLabel').pack(side='left')
        self.hold_entry=ttk.Entry(self.tempo_row,textvariable=self.hold_var,width=5)
        self.hold_entry.pack(side='left',padx=(4,11))
        ttk.Label(self.tempo_row,text='Fade (s)',style='UX20.ToolLabel.TLabel').pack(side='left')
        self.fade_entry=ttk.Entry(self.tempo_row,textvariable=self.fade_var,width=5)
        self.fade_entry.pack(side='left',padx=(4,0))
        for editor in (self.hold_entry,self.fade_entry):
            editor.bind('<Return>',self.commit_pingpong_timing)
            editor.bind('<KP_Enter>',self.commit_pingpong_timing)
            editor.bind('<FocusOut>',self.commit_pingpong_timing)
            editor.bind('<Escape>',self.cancel_pingpong_timing)
        self.tools.bind('<Configure>',self._reflow,add='+')
        self.transition_group.pack(side='left',padx=(0,7))
        self.audio_group.pack(side='left')
        self.mix_controls.grid(row=0,column=1,sticky='e')
        self.fader.bind('<ButtonPress-1>',self.begin)
        self.fader.bind('<ButtonRelease-1>',self.finish)
        self.fader.bind('<KeyPress>',self.begin,add='+')
        self.fader.bind('<KeyRelease>',self.finish,add='+')
        self.fader.bind('<Escape>',lambda e:(self.finish_input(cancel=True),'break')[1])
        app.add_tip(self.fader,'A/B crossfade. Transition and audio modulation operate this same mix.')
        app.add_tip(self.transition_display,'Author transition geometry, timing, motion and visual FX in the Transition module rack.')
        app.add_tip(self.pingpong_button,'Automatically alternate A and B: hold one channel, fade to the other using the authored Transition rack, then repeat in reverse. Turn off to resume manual/audio mixing.')
        app.add_tip(self.react_button,'Let the selected audio band drive the A/B crossfade.')
        app.add_tip(self.band_button,'Choose an audio reaction band directly, or use the arrows.')
        self.refresh()
    def _reflow(self,event=None):
        width=event.width if event else self.tools.winfo_width()
        # Action area on the left, one cohesive mix-control cluster on the
        # right. The right cluster wraps intact instead of overflowing when
        # an effects or sources workbench narrows the preview.
        # The label costs ~85px yet carries no action. Eliminate it *before*
        # any actual control is compressed; keep transition buttons accessible.
        if width<950 and self.transition_label.winfo_manager():
            self.transition_label.pack_forget()
        elif width>=950 and not self.transition_label.winfo_manager():
            self.transition_label.pack(side='left',before=self.transition_display,padx=(1,5))
        mode=2 if width<470 else 1 if width<850 else 0
        if mode==self._compact:return
        self._compact=mode
        self.transition_group.pack_forget();self.audio_group.pack_forget()
        if mode==2:
            self.transition_group.pack(side='top',anchor='e',pady=(0,2))
            self.audio_group.pack(side='top',anchor='e')
        else:
            self.transition_group.pack(side='left',padx=(0,7))
            self.audio_group.pack(side='left')
        self.preview_actions.grid_configure(row=0,column=0,sticky='w',padx=(0,5),pady=(0,0))
        self.mix_controls.grid_configure(row=1 if mode else 0,column=0 if mode else 1,
                                         columnspan=2 if mode else 1,sticky='e',
                                         padx=(0,0),pady=(3 if mode else 0,0))

    def _menu(self,anchor,items,selected,change):
        """One non-grabbing transient selector. No native tk_popup lifetime race.

        Clicking outside, Escape, focus change, and clicking the launcher again
        dismiss through one shared controller. Browsing options never commits.
        """
        key=('ux24-mixer-choice',id(self))
        if self._choice_popup is not None:
            self.app.contextual_surfaces.dismiss(key)
            return None
        popup=tk.Toplevel(self.app)
        popup.withdraw();popup.overrideredirect(True)
        popup.configure(background='#35465e',padx=1,pady=1)
        self._choice_popup=popup
        body=ttk.Frame(popup,padding=4)
        body.pack(fill='both',expand=True)
        def close():
            if self._choice_popup is popup:self._choice_popup=None
            self.app.contextual_surfaces.forget(key)
            if popup.winfo_exists():popup.destroy()
        for value,label in items:
            current=selected.get()==value
            b=ttk.Button(body,text=('✓  ' if current else '    ')+label,
                         style='UX20.Transition.TButton' if current else 'TButton',
                         command=lambda v=value:(self.app.contextual_surfaces.dismiss(key),change(v)))
            b.pack(fill='x',pady=1)
        popup.update_idletasks()
        from contextual_surface import popup_coordinates
        x,y=popup_coordinates(anchor,popup.winfo_reqwidth(),popup.winfo_reqheight())
        popup.geometry(f'+{max(0,x)}+{max(0,y)}')
        self.app.contextual_surfaces.show(key,popup,close,anchors=(anchor,))
        popup.deiconify();popup.lift()
        return popup

    def open_transition_menu(self):
        return self.app.open_effects_context('Transition')
    def open_band_menu(self):
        if self.app.project.voice_mix.mode!='react':return
        return self._menu(self.band_button,BANDS,self.band,self.set_reaction_band)
    def finish_depth_drag(self,event=None):
        if not self._depth_dragging:return
        depth=self.react_depth.get()
        self._depth_dragging=False
        self.set_reaction_depth(depth)
    def cancel_depth_drag(self,event=None):
        self._depth_dragging=False
        self.refresh()
        return 'break'
    def step_transition(self,direction):
        kinds=list(STYLES)
        current=self.transition_style.get()
        i=kinds.index(current) if current in kinds else 0
        self.set_transition(kinds[(i+int(direction))%len(kinds)])
    def set_transition(self,kind):
        if kind not in STYLES:raise ValueError('Unknown transition')
        self.app.transaction('A/B transition · '+STYLES[kind],lambda:configure_transition(self.app.project,kind))
        self.transition_style.set(kind)
        self.refresh()
    def toggle_pingpong(self):
        was=bool(self.app.project.extra.get('ux41_pingpong',{}).get('enabled'))
        now=self.app.programme_time() if self.app.playing else self.app.playhead
        current=self.app.signal_evaluator().value(self.app.project.voice_mix,now)
        try:
            settings=validate_pingpong(self.app.project.extra.get('ux41_pingpong'))
            hold=float(self.hold_var.get());fade=float(self.fade_var.get())
            settings=validate_pingpong({**settings,'hold':hold,'fade':fade})
        except (ValueError,TypeError) as exc:
            self.app.update_status('Ping-pong timing: '+str(exc));self.cancel_pingpong_timing();return
        self.app.transaction('A/B ping-pong '+('off' if was else 'on'),
            lambda:configure_pingpong(self.app.project,not was,start=max(0.,now),
                                      hold=settings['hold'],fade=settings['fade'],
                                      first='B' if current>.5 else 'A'))
        self.refresh()

    def commit_pingpong_timing(self,event=None):
        config=validate_pingpong(self.app.project.extra.get('ux41_pingpong'))
        try:
            data=validate_pingpong({**config,'hold':float(self.hold_var.get()),
                                   'fade':float(self.fade_var.get())})
        except (ValueError,TypeError) as exc:
            self.app.update_status('Hold/Fade: '+str(exc));self.cancel_pingpong_timing();return 'break'
        if abs(data['hold']-config['hold'])>1e-8 or abs(data['fade']-config['fade'])>1e-8:
            # The edit reanchors a playing cycle at its current dominant
            # channel. There is no redundant transition polling timer.
            now=self.app.programme_time() if self.app.playing else self.app.playhead
            mix=self.app.signal_evaluator().value(self.app.project.voice_mix,now)
            self.app.transaction('A/B ping-pong timing',
                lambda:configure_pingpong(self.app.project,config['enabled'],
                    start=max(0.,now),hold=data['hold'],fade=data['fade'],
                    first='B' if mix>.5 else 'A'))
        self.refresh();return 'break'

    def cancel_pingpong_timing(self,event=None):
        settings=validate_pingpong(self.app.project.extra.get('ux41_pingpong'))
        self.hold_var.set(f"{settings['hold']:g}")
        self.fade_var.set(f"{settings['fade']:g}")
        return 'break'

    def toggle_reactive(self):self.set_reactive(self.app.project.voice_mix.mode!='react' or bool(self.app.project.extra.get('ux41_pingpong',{}).get('enabled')))
    def set_reactive(self,enabled):
        def edit():
            p=self.app.project.voice_mix
            if enabled and self.app.project.extra.get('ux41_pingpong',{}).get('enabled'):
                configure_pingpong(self.app.project,False)
            if enabled:
                p.mode='react';p.source='reaction_mix';p.react_band=self.band.get()
                p.react_amount=1 if p.value<=.5 else -1
                p.extra['react_full_range']=True;p.attack=.018;p.release=.17
            else:p.mode='static'
        self.app.transaction('A/B audio reaction '+('on' if enabled else 'off'),edit)
        self.refresh()
    def step_band(self,direction):
        names=[x for x,_ in BANDS];index=names.index(self.band.get()) if self.band.get() in names else 0
        self.set_reaction_band(names[(index+int(direction))%len(names)])
    def set_reaction_band(self,band):
        if band not in dict(BANDS):raise ValueError('Unsupported audio band')
        self.app.transaction('A/B reaction · '+band,lambda:setattr(self.app.project.voice_mix,'react_band',band))
        self.band.set(band);self.refresh()
    def set_reaction_depth(self,depth):
        value=max(0,min(1,float(depth)))
        def edit():
            p=self.app.project.voice_mix;p.react_amount=value*(1 if p.value<=.5 else -1)
        self.app.transaction('A/B reaction depth',edit)
        self.refresh()
    def reverse_reaction(self):
        def edit():
            p=self.app.project.voice_mix;p.value=1.-round(p.value)
            p.react_amount=abs(p.react_amount)*(1 if p.value<=.5 else -1)
        self.app.transaction('Reverse A/B reaction',edit);self.refresh()
    def begin(self,event=None):
        if self.active:return
        if self.app.project.extra.get('ux41_pingpong',{}).get('enabled'):
            self.app.update_status('Turn Ping-pong off to move the A/B fader manually.');return 'break'
        from input_gestures import claim_input
        claim_input(self.app,self);self.fader.focus_set();self.active=True;self.app.begin_gesture('program')
    def write(self,value):
        if not self.active:return
        v=max(0.,min(1.,float(value)))
        self.app.write_parameter(self.app.project.voice_mix,v,self.app.project)
        self.caption.set(f'{round((1-v)*100)} : {round(v*100)}')
    def finish_input(self,*,cancel=False):
        if not self.active:return
        from input_gestures import release_input
        self.active=False;release_input(self.app,self)
        if cancel:self.app.cancel_gesture()
        else:self.app.end_gesture()
        if self.winfo_exists():self.refresh()
    def finish(self,event=None):self.finish_input()
    def refresh(self):
        if self.active:return
        now=self.app.programme_time() if self.app.playing else self.app.playhead
        b=max(0.,min(1.,self.app.signal_evaluator().value(self.app.project.voice_mix,now)))
        if abs(float(self.value.get())-b)>.0005:self.value.set(b)
        caption=f'{round((1-b)*100)} : {round(b*100)}'
        if self.caption.get()!=caption:self.caption.set(caption)
        automatic=bool(self.app.project.extra.get('ux41_pingpong',{}).get('enabled'))
        label='↔ Auto ON' if automatic else '↔ Auto OFF'
        if self.pingpong_button.cget('text')!=label:self.pingpong_button.configure(text=label)
        if automatic!=self._pingpong_state:
            self._pingpong_state=automatic
            self.pingpong_button.configure(style='UX20.ReactionOn.TButton' if automatic else 'UX20.Small.TButton')
            self.fader.configure(state='disabled' if automatic else 'normal')
        if automatic!=self._timing_visible:
            self._timing_visible=automatic
            if automatic:self.tempo_row.pack(fill='x',pady=(0,1))
            else:self.tempo_row.pack_forget()
        if self.app.focus_get() not in (self.hold_entry,self.fade_entry):
            config=validate_pingpong(self.app.project.extra.get('ux41_pingpong'))
            if self.hold_var.get()!=f"{config['hold']:g}":self.hold_var.set(f"{config['hold']:g}")
            if self.fade_var.get()!=f"{config['fade']:g}":self.fade_var.set(f"{config['fade']:g}")
        p=self.app.project.voice_mix
        reacting=p.mode=='react' and not automatic
        self.react_active.set(reacting);self.band.set(p.react_band)
        # The transport clock refreshes every frame. Never overwrite a user's
        # live fader position until the drag has committed on release.
        if not self._depth_dragging:
            self.react_depth.set(abs(p.react_amount))
            self.depth_value.configure(text=f'{round(abs(p.react_amount)*100)}%')
        spec=self.app.project.extra.get('ux16_transition',{})
        kind=spec.get('kind','dissolve');self.transition_style.set(kind)
        self.transition_display.configure(text='✧ Edit motion')
        self.react_button.configure(text='∿ React ON' if reacting else '∿ React OFF',
                                    style='UX20.ReactionOn.TButton' if reacting else 'UX20.ReactionOff.TButton')
        self.band_button.configure(text=dict(BANDS).get(p.react_band,'Level'),state='normal' if reacting else 'disabled')
        for b in (self.previous_band,self.next_band):b.configure(state='normal' if reacting else 'disabled')
        # Never unmap a slider during the periodic render refresh: Tk loses
        # pointer capture and the thumb appears to snap back repeatedly.
        if reacting!=self._depth_controls_visible:
            self._depth_controls_visible=reacting
            if self._depth_controls_visible:
                self.depth_label.pack(side='left',padx=(3,2))
                self.depth_slider.pack(side='left')
                self.depth_value.pack(side='left',padx=(1,2))
                self.direction_button.pack(side='left',padx=(4,0))
            else:
                for item in (self.depth_label,self.depth_slider,self.depth_value,self.direction_button):item.pack_forget()
        if reacting:
            self.direction_button.configure(text='A→B' if p.react_amount>=0 else 'B→A')
