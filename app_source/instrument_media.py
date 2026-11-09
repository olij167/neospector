"""Instrument media desk: retained playback engines in stable queue tabs."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from omne_queue_view import PlayerColumn, QueueColumns, clock_text
from queue_gaps import gap_name


class InstrumentPlayer(PlayerColumn):
    """Compact presentation with explicit selection and playback actions."""
    ROW_HEIGHT = 42

    def __init__(self, parent, app, role, visibility=None):
        super().__init__(parent, app, role, visibility)
        self.toolbar.pack_forget()
        self.current_canvas.bind('<Button-3>',lambda e:self.select(self.current_id) if getattr(self,'current_id',None) else 'break')
        self.current_canvas.bind('<Button-1>',self.current_click)
        self.canvas.bind('<Button-3>',lambda e: 'break')
        # UX21: clip-level effects are no longer an editing destination.
        if hasattr(self,"item_effects_button"):self.item_effects_button.pack_forget()
        self.selection_label.set('')
        # The current card and row-end glyphs already expose selection/removal.
        # Do not duplicate a text-heavy selected-item action row below them.
        self.selection_actions.pack_forget()
        self.canvas.configure(height=62)
        self.current_canvas.configure(height=41 if role=='Music' else 51)
        self.take_button.configure(text='▶ Take',width=6)
        self.remove_button.configure(text='×',width=2)
        self.duration_button.configure(text='Time',width=4)
        if role!='Music':
            # One global crossfader, never a second per-source mix control.
            self.level_fader.grid_remove()
            self.programme_switch.grid_remove()
            self.editor_disclosure.grid_remove()
            self.source_disclosure.pack_forget()  # UX13: live choices are visible buttons
            # Keep identity readable when the queue is detached from its toggle.
            self.role_badge.grid(row=0,column=0,sticky='w',padx=(0,5))
            from instrument_icons import icon
            # Capture commands are icons at the source itself; none live in the global menu.
            self.visual_source_bar=self.camera_button.master
            self.camera_button.configure(image=icon(app,'camera-flash'),text=' Cam',compound='left',width=0)
            screen_button=ttk.Button(self.visual_source_bar,image=icon(app,'screen'),text=' Screen',compound='left',width=0,
                command=lambda:self.show_inline_source('screen'))
            screen_button.pack(side='left',padx=(3,0))
            files_button=ttk.Button(self.visual_source_bar,image=icon(app,'files'),text=' Queue',compound='left',width=0,
                command=lambda:self.show_inline_source('queue'))
            files_button.pack(side='left',padx=(3,0))
            self.camera_button.configure(command=lambda:self.show_inline_source('camera'))
            self.source_actions={'camera':self.camera_button,'screen':screen_button,'files':files_button}
            app.add_tip(screen_button,'Choose desktop or application window capture for channel '+role+'. Selection does not start sharing.')
            app.add_tip(files_button,'Return to the retained media queue for '+role)
        else:
            from instrument_icons import icon
            for child in self.channel_header.grid_slaves(row=0,column=0):child.grid_remove()
            self.sound_badge=tk.Label(self.channel_header,text='♫ AUDIO',bg='#1d4554',fg='#f0f5f5',
                padx=6,pady=3,font=('TkDefaultFont',9,'bold'))
            self.sound_badge.grid(row=0,column=0,sticky='w')
            mic=ttk.Frame(self.channel_header)
            mic.grid_remove()  # Input selector is now a single toggle; other inputs live in Sources.
            self.mic_button=ttk.Button(mic,image=icon(app,'mic'),text=' Mic',compound='left',width=0,command=app.quick_microphone)
            self.mic_button.pack(side='left')
            self.mic_choices=ttk.Button(mic,text='▾',width=2,command=self.music_source_menu)
            self.mic_choices.pack_forget()  # UX13: Mic / PC / App are direct actions
            self.pc_button=ttk.Button(mic,image=icon(app,'audio'),text=' PC',compound='left',width=0,
                command=lambda:self.open_audio_capture(False));self.pc_button.pack(side='left',padx=(4,0))
            self.app_button=ttk.Button(mic,image=icon(app,'app'),text=' App',compound='left',width=0,
                command=lambda:self.open_audio_capture(True));self.app_button.pack(side='left',padx=(2,0))
            app.add_tip(self.pc_button,'Choose PC/system audio for reactions; does not alter soundtrack playback.')
            app.add_tip(self.app_button,'Choose application audio for reactions; permission remains explicit.')
            self.reaction_meter=ttk.Progressbar(mic,length=25,maximum=100,mode='determinate')
            self.reaction_meter.pack(side='left',padx=(5,0))
            app.add_tip(self.reaction_meter,'Live audio reaction level. Meter does not alter the soundtrack or input routing.')
            app.add_tip(self.mic_button,'Explicitly toggle live audio input. Source routing and monitoring are configured separately.')
        transport=ttk.Frame(self.editor_body)
        transport.pack(fill='x',before=self.current_canvas,pady=(0,4))
        self.compact_toolbar=transport
        controls=[('⏮','Previous item',self.previous),('↺','Restart current',self.restart_current),
                  ('⏯','Pause or resume channel',self.toggle_channel_play),('⏭','Next queued item',self.next),
                  ('■','Stop this queue (also disables repeat)',self.stop_queue),
                  ('↻','Toggle repeat queue',self.toggle_repeat),('×','Remove playing item',self.remove_current)]
        for i,(glyph,tip,callback) in enumerate(controls):
            b=ttk.Button(transport,text=glyph,width=3,command=callback)
            col=i
            b.grid(row=0,column=col,sticky='ew',padx=1,pady=1)
            transport.columnconfigure(col,weight=1)
            if callback is None:b.configure(state='disabled')
            if i==2:self.transport_play=b
            if i==5:self.repeat_button=b
            if i==6:self.remove_current_button=b
            app.add_tip(b,tip)
        # Always identify the on-air source directly under its transport,
        # including explicit camera takeover and an otherwise empty queue.
        if role in ('A','B'):
            self.active_source_name=tk.StringVar(value='NOW · No source queued')
            self.active_source_label=ttk.Label(self.editor_body,textvariable=self.active_source_name,
                style='PlayerName.TLabel',anchor='w')
            self.active_source_label.pack_forget()  # current card owns NOW title
        # Compact live switch in the same queue header as Add/disclosure.
        # It deliberately calls the same live action as the top source pair.
        self.quick_live_button=ttk.Button(self.channel_header,
            text='◉ CAM' if role!='Music' else '◉ MIC',width=6,
            style='UX28.LiveMini.TButton' if role!='Music' else 'UX28.MicMini.TButton',
            command=(lambda:self.toggle_camera()) if role!='Music' else (lambda:app.quick_microphone()))
        self.quick_live_button.grid(row=0,column=2,sticky='e',padx=(1,4))
        self.upcoming_visible=True
        self.future_body=self.canvas.master
        self.queue_fold=ttk.Button(self.editor_body,text='UP NEXT ▴',command=self.toggle_future)
        self.queue_fold.pack_forget()  # replaced by header disclosure below
        self.queue_count=tk.StringVar(value='0 upcoming')
        if role!='Music':
            self.queue_count_label=ttk.Label(self.channel_header,textvariable=self.queue_count,style='Muted.TLabel')
            self.queue_count_label.grid(row=0,column=3,sticky='e',padx=3)
            self.queue_toggle=ttk.Button(self.channel_header,text='⌄',width=3,style='UX28.Disclose.TButton',command=self.toggle_future)
            self.queue_toggle.grid(row=0,column=5,sticky='e',padx=2)
        from ux16_media_browser import SourceMediaBrowser
        # Retain the old browser adapter for legacy tests, but the *visible*
        # project shelf is mounted once by RightSourceStack and shared by A/B/AUDIO.
        self.source_browser=SourceMediaBrowser(self.editor_body,app,role)
        self.browser_open=False
        self.inline_source_mode='queue'
        if role!='Music':
            from ux22_inline_sources import InlineSourceSettings
            self.inline_source=InlineSourceSettings(self.editor_body,app,role)
        self.browse_button=ttk.Button(self.channel_header if role!='Music' else self.editor_body,
                                      text='＋ Add' if role!='Music' else '＋ Add to queue',width=7,
                                      style='UX28.Insert.TButton',command=self.add_from_sources)
        if role!='Music':
            self.channel_header.columnconfigure(3,weight=1)
            self.browse_button.grid(row=0,column=4,sticky='e',padx=2)
            app.add_tip(self.browse_button,'Add files, cameras or application sources to queue '+role)
        else:
            self.browse_button.pack(fill='x',before=self.future_body,pady=(2,0))
        # One source-browser entry per queue; types are selected in that browser.
        self.source_shortcuts=ttk.Frame(self.editor_body)  # legacy adapter, unmounted
        self.shortcut_buttons={}

        self.source_browser.refresh(True)
        if role!='Music':
            # UX23: the queue is the channel. Live sources and files are chosen
            # from the same shared shelf, not three competing source tabs.
            self.visual_source_bar.pack_forget() if self.visual_source_bar.winfo_manager()=='pack' else self.visual_source_bar.grid_remove() if self.visual_source_bar.winfo_manager()=='grid' else None
        if role=='Music':
            self.editor_body.configure(style='MusicDeck.TFrame')
            ttk.Style(app).configure('MusicDeck.TFrame',background='#16313e')
        if role!='Music':
            self.edit_button=ttk.Button(self.channel_header,text='Edit FX',width=7,
                command=lambda:app.queue_deck.show_role(role))
            self.edit_button.grid_remove()  # channel badge already selects the same rack
        # FX belongs at each source. The badge exposes ownership and current
        # processing count without requiring an always-open bottom rack.
        if role!='Music':
            # FX is attached to the current source card, not squeezed into its
            # capture toolbar. Its visible count identifies the owner.
            self.fx_button=ttk.Button(self.current_canvas,text='FX · 0',width=7,
                command=lambda r=role:app.toggle_effects_context(r))
            self.fx_button.place_forget()  # one global Effects entry in the toolbar
            app.add_tip(self.fx_button,"Open this source\'s FX · count shows active module stack.")
        else:
            self.music_files_button=ttk.Button(mic,text='Files ▸',command=self.toggle_music_files)
            self.music_files_button.pack(side='left',padx=1)
            self.audio_files_active=False
        self.append_drop.pack_forget()  # Canvas itself remains a file drop target.
        self.set_future(False)
        if role=='Music':
            self._music_surface(False)
            # A radio's identity is the current sound and play action, not an
            # A/B queue transport clone. Keep current art/card visible.
            self.radio_transport=ttk.Frame(self.editor_body,style='MusicDeck.TFrame',padding=(4,4))
            self.radio_transport.pack(fill='x',before=self.progress.master)
            self.radio_play=ttk.Button(self.radio_transport,text='▶ / ❚❚',width=8,command=self.toggle_channel_play)
            self.radio_play.pack(side='left',padx=(0,5))
            self.radio_now=tk.StringVar(value='No track · Microphone ready to connect')
            ttk.Label(self.radio_transport,textvariable=self.radio_now,style='PlayerName.TLabel').pack(side='left',fill='x',expand=True)
            self.radio_next=ttk.Button(self.radio_transport,text='⏭',width=3,command=self.next)
            self.radio_next.pack(side='right')
            self.radio_stop=ttk.Button(self.radio_transport,text='■',width=3,command=self.stop_queue)
            self.radio_stop.pack(side='right',padx=(0,2))
            self.radio_repeat=ttk.Button(self.radio_transport,text='↻',width=3,command=self.toggle_repeat)
            self.radio_repeat.pack(side='right',padx=(0,2))
            self.radio_remove=ttk.Button(self.radio_transport,text='×',width=3,command=self.remove_current)
            self.radio_remove.pack(side='right',padx=(0,2))
            self.radio_level=ttk.Progressbar(self.radio_transport,length=28,maximum=100,mode='determinate')
            self.radio_level.pack(side='right',padx=(0,4))
            # Radio transport owns the current track; a second current canvas
            # repeats the same name and steals height from the music tray.
            self.current_canvas.pack_forget()
            self.compact_toolbar.pack_forget()
            # UX29: One Audio tray, two complementary views sharing the same
            # source and routing state. The mixer is an existing SourceMixer,
            # not an alternate implementation of the sound engine.
            self.audio_view='queue'
            self.audio_mode_bar=ttk.Frame(self.channel_header)
            self.audio_mode_bar.grid(row=0,column=1,sticky='w',padx=(2,3))
            self.audio_mode_buttons={}
            for key,label in (('queue','QUEUE'),('mixer','MIX')):
                button=ttk.Button(self.audio_mode_bar,text=label,width=6 if key=='queue' else 5,
                    style='UX28.QueueOpen.TButton' if key=='queue' else 'UX28.QueueIdle.TButton',
                    command=lambda k=key:self.show_audio_view(k))
                button.pack(side='left',padx=1)
                self.audio_mode_buttons[key]=button
            from sound_panel import DeskFaderMixer
            self.audio_mixer=DeskFaderMixer(self.editor_body,app,expanded=False)
            self.audio_mixer.pack_forget()
            # The audio queue already presents current and upcoming material.
            # The mixer needs only independently routed live/record faders.
            self.audio_mixer.info.set('ON = Sound + React + recording · ⋯ = routing exceptions')
            # UX31: the mixer is not a catalogue. Inputs are discovered on opening it.
        else:
            # Queue transports appear only when the queue contains material.
            # Capture and source selection never inherit six irrelevant buttons.
            self.compact_toolbar.pack_forget()
        self.bind('<Alt-Up>',lambda e:(self.move_selected(max(0,self._selected_index()-1)),'break')[1])
        self.bind('<Alt-Down>',lambda e:(self.move_selected(self._selected_index()+1),'break')[1])

    def show_audio_view(self,view):
        if self.role!='Music' or view not in ('queue','mixer'):
            raise ValueError('Audio view must be Queue or Mixer')
        previous=self.audio_view
        self.audio_view=view
        if view=='mixer' and previous!='mixer' and not self.audio_mixer.all.get():
            # Discover actual per-app stream IDs only on explicit mixer open.
            # Device enumeration runs in the existing worker, never Tk's loop.
            self.audio_mixer.all.set(True)
            if not self.audio_mixer.sources:self.audio_mixer.discover()
        for key,button in self.audio_mode_buttons.items():
            button.configure(style='UX28.QueueOpen.TButton' if key==view else 'UX28.QueueIdle.TButton')
        # When the view changes, open the tray automatically, even if the user
        # had previously collapsed it. Camera and queues are unaffected.
        if view=='mixer':
            for widget in (self.radio_transport,self.browse_button,self.progress.master,
                           self.future_body,self.compact_toolbar,self.current_canvas):
                widget.pack_forget()
            if not self.audio_mixer.winfo_manager():
                self.audio_mixer.pack(fill='both',expand=True,pady=(1,0))
            self.audio_mixer.refresh(True)
        else:
            self.audio_mixer.pack_forget()
            if not self.radio_transport.winfo_manager():
                self.radio_transport.pack(fill='x')
            if not self.progress.master.winfo_manager():
                self.progress.master.pack(fill='x',pady=(1,2),after=self.radio_transport)
            self.set_future(True)
            if not self.browse_button.winfo_manager():
                self.browse_button.pack(fill='x',before=self.future_body,pady=(2,0))
        if hasattr(self.app,'sidebar'):
            self.app.sidebar.set_open('Music',True)
            self.app.sidebar.request_fit()
        self.app.shell.schedule()

    def set_future(self,visible):
        self.upcoming_visible=bool(visible)
        if not self.upcoming_visible or (self.role=='Music' and getattr(self,'audio_view','queue')=='mixer'):
            self.future_body.pack_forget();self.append_drop.pack_forget();self.selection_actions.pack_forget()
        else:
            self.future_body.pack(fill='both',expand=True)
            self.append_drop.pack_forget();self.selection_actions.pack_forget()
        self.queue_fold.configure(text=('▾ UP NEXT' if self.upcoming_visible else '▸ UP NEXT')+
                                  (' · '+str(len(self.future)) if hasattr(self,'future') else ''))
        if hasattr(self,'queue_toggle'):self.queue_toggle.configure(text='⌃' if self.upcoming_visible else '⌄')
        deck=getattr(self.app,'queue_deck',None)
        if deck is not None and self.role in ('A','Music'):deck.update_left_heights()
        if self.role=='Music' and hasattr(self.app,'refresh_audio_tray'):self.app.refresh_audio_tray()
        sidebar=getattr(self.app,'sidebar',None)
        if sidebar is not None:sidebar.request_fit()

    def toggle_future(self):self.set_future(not self.upcoming_visible)

    def add_from_sources(self):
        self.app.sidebar.open_browser(self.role,'files')
        self.app.sidebar.signal(self.role)

    def stop_queue(self):
        from ux26_queue_actions import stop_queue
        now=self.app.programme_time() if self.app.playing and not self.app.reviewing else self.app.playhead
        self.app.transaction('Stop '+self.role+' queue',lambda:stop_queue(self.app.project,self.role,now))
        if self.role=='Music':
            self.app.configure_sound_sources()
            self.app.prepare_sound_analysis()
        else:self.app.release_unassigned_cameras()
        self.refresh(True)

    def remove_current(self):
        cid=getattr(self,'current_id',None)
        if not cid:return
        from ux26_queue_actions import remove_playing
        now=self.app.programme_time() if self.app.playing and not self.app.reviewing else self.app.playhead
        self.app.transaction('Remove playing '+self.role+' item',lambda:remove_playing(self.app.project,self.role,cid,now))
        if self.role=='Music':
            self.app.configure_sound_sources();self.app.prepare_sound_analysis()
        else:self.app.release_unassigned_cameras()
        self.selected=None
        self.refresh(True)

    def current_click(self,event):
        if getattr(self,'current_id',None):
            if event.x>=self.current_canvas.winfo_width()-35:self.remove_current()
            else:self.select(self.current_id)
        return 'break'

    def press(self,event):
        # Canvas hit-testing is spatial: the main item row and its glyphs
        # occupy the same Y coordinate, so check the X range as well.
        hit=next((h for h in self.hits if len(h)>=6 and h[1]<=self.canvas.canvasy(event.y)<h[2]
                  and h[4]<=event.x<h[5]),None)
        if hit and hit[3] in ('take','move_up','move_down','remove'):
            self.selected=hit[0]
            if hit[3]=='take':
                if self.role=='Music':self.app.music_take(self.selected)
                else:self.app.queue_next(self.role,self.selected)
            elif hit[3]=='remove':self.remove()
            else:
                idx=next((i for i,item in enumerate(self.items) if self.ident(item)==hit[0]),-1)
                if idx>=0:self.move_selected(max(0,idx+(-1 if hit[3]=='move_up' else 1)))
            return 'break'
        return super().press(event)

    def toggle_browser(self):
        self.app.sidebar.toggle_browser(self.role)
        self.browser_open=self.app.sidebar._browser_open and self.app.sidebar._browser_request==self.role
        if self.role!='Music':
            self.browse_button.configure(text='▾ Media & Sources' if self.browser_open else '＋ Media & Sources')
        self.app.sidebar.request_fit()

    def close_inline_source(self):
        if self.role=='Music':return
        self.inline_source.pack_forget();self.inline_source_mode='queue'
        if not self.current_canvas.winfo_manager():self.current_canvas.pack(fill='x',before=self.browse_button)
        if self.role!='Music':self.browse_button.grid_remove()
        else:self.browse_button.pack_forget()
        self.refresh(force=True)
        self.app.sidebar.request_fit();self.app.shell.schedule()

    def show_inline_source(self,mode):
        if self.role=='Music':return
        if mode=='queue':
            self.close_inline_source()
            self.resume_queue()
            return
        if mode not in ('camera','screen'):raise ValueError('Choose camera, screen or queue')
        if self.inline_source_mode==mode and self.inline_source.winfo_manager():
            return self.close_inline_source()
        self.inline_source_mode=mode
        for widget in (self.compact_toolbar,self.current_canvas,self.queue_fold,self.future_body,self.append_drop,self.selection_actions):
            if widget.winfo_manager():widget.pack_forget()
        self.browse_button.grid_remove()
        self.inline_source.show(mode)
        self.inline_source.pack(fill='x',pady=(4,0))
        self.app.sidebar.request_fit();self.app.shell.schedule()

    def _music_surface(self,files):
        if self.role!='Music':return
        if hasattr(self,'radio_transport'):
            self.radio_transport.pack(fill='x',before=self.progress.master)
            self.compact_toolbar.pack_forget()
        self.audio_files_active=bool(files)
        for widget in (self.current_canvas,self.browse_button):widget.pack_forget()
        if not files:
            self.future_body.pack_forget();self.append_drop.pack_forget();self.selection_actions.pack_forget()
            self.source_browser.pack_forget();self.browser_open=False
        self.music_files_button.configure(text='Files ▾' if files else 'Files ▸')
        if hasattr(self,'radio_files_button'):
            self.radio_files_button.configure(text='＋ Add to queue')
            self.compact_toolbar.pack(fill='x',before=self.progress.master)
            self.current_canvas.pack(fill='x',after=self.compact_toolbar)

    def toggle_music_files(self):
        if self.role!='Music':return
        self.app.sidebar.open_browser('Music','files') if not self.app.sidebar._browser_open else self.app.sidebar.close_browser()
        self.audio_files_active=self.app.sidebar._browser_open and self.app.sidebar._browser_request=='Music'
        self.music_files_button.configure(text='＋ Sources')
        self.app.sidebar.request_fit()

    def fx_badge(self):
        count=self.app.effects_count(self.role)
        active=self.app.shell.rack_open and self.app.deck.scope.get()!='Master' and (
            getattr(self.app.deck.selected_cell().adapter.owner,'extra',{}).get('voice')==self.role
            if self.app.deck.selected_cell() else False)
        return f'FX · {count}' + (' ▲' if active else ' ▾')

    def _selected_index(self):
        return next((i for i,c in enumerate(self.items) if self.ident(c)==self.selected),0)

    def open_audio_capture(self,application=False):
        bar=getattr(self.app,'input_bar',None)
        if bar is not None and hasattr(bar,'discover'):
            return bar.discover(bool(application))
        return self.app.open_live()

    def music_source_menu(self):
        # Legacy callback: open the visible audio input surface, never a menu.
        return self.open_audio_capture(False)

    def toggle_repeat(self):
        self.loop_queue.set(not self.loop_queue.get())
        self.app.set_queue_policy(self.role,'repeat' if self.loop_queue.get() else 'finish')

    def toggle_channel_play(self):
        if self.role=='Music':return self.app.toggle_play()
        if self.live_device_kind():return self.app.update_status('Live input is not a seekable queue; use Camera to return to files.')
        from queue_model import toggle_pause
        from instrument_model import voice
        now=self.app.programme_time() if self.app.playing else self.app.playhead
        return self.app.transaction('Pause/resume '+self.role,lambda:toggle_pause(voice(self.app.project,self.role),now))

    def restart_current(self):
        if self.role=='Music':
            item=next((c for c in self.items if self.ident(c)==self.current_id),None)
            if item:return self.app.music_take(self.ident(item))
        elif self.current_id:return self.app.queue_next(self.role,self.current_id)
        self.app.update_status('Nothing is playing in '+self.role+' yet.')

    def scan_backward(self):
        now=self.app.programme_time() if self.app.playing else self.app.playhead
        if self.role=='Music':
            from queue_policies import music_position,preserve_music_history,set_music_origin
            def rewind():
                position=max(0.,music_position(self.app.project,now)-5.)
                preserve_music_history(self.app.project,now)
                set_music_origin(self.app.project,now,position)
            return self.app.transaction('Rewind music',rewind)
        from queue_model import queue_position,append_switch,mode_at
        from queue_policies import activate_visual_state,preserve_visual_history
        from instrument_model import voice
        layer=voice(self.app.project,self.role)
        if self.live_device_kind():return self.app.update_status('Live input cannot be rewound.')
        def rewind():
            position=max(0.,queue_position(layer,now)-5.)
            activate_visual_state(layer,now);preserve_visual_history(layer,now)
            append_switch(layer,now,'queue',position)
        return self.app.transaction('Rewind '+self.role,rewind)

    def scan_ahead(self):
        now=self.app.programme_time() if self.app.playing else self.app.playhead
        if self.role=='Music':
            from queue_policies import music_position,preserve_music_history,set_music_origin
            position=music_position(self.app.project,now)+5.
            def seek():
                preserve_music_history(self.app.project,now)
                set_music_origin(self.app.project,now,position)
            self.app.transaction('Seek music ahead',seek)
            return
        from queue_model import queue_position,append_switch,mode_at
        from queue_policies import activate_visual_state,preserve_visual_history
        from instrument_model import voice
        layer=voice(self.app.project,self.role)
        if self.live_device_kind():return self.app.update_status('Live input is not seekable.')
        def seek():
            position=queue_position(layer,now)+5.
            activate_visual_state(layer,now);preserve_visual_history(layer,now)
            append_switch(layer,now,'queue',position)
        self.app.transaction('Seek '+self.role+' ahead',seek)

    def live_device_kind(self):
        from instrument_model import voice
        from queue_model import mode_at
        state=mode_at(voice(self.app.project,self.role),self.app.programme_time() if self.app.playing else self.app.playhead)
        from ux25_source_state import active_source
        asset,kind=active_source(self.app.project,voice(self.app.project,self.role),
            self.app.programme_time() if self.app.playing else self.app.playhead)
        if not asset or asset.kind not in ('camera','screen','window'):return ''
        device=asset.metadata.get('device')
        return device.get('kind','camera') if isinstance(device,dict) else 'camera'
    def toggle_camera(self):
        if self.live_device_kind() in ('screen','window'):return self.app.toggle_channel_camera(self.role,device=self.app.last_camera_device)
        return self.app.toggle_channel_camera(self.role)

    def select(self,cid):
        self.selected=cid
        self.refresh(True)
        self.app.update_status('Selected queued item · Take plays it; channel FX are in Effects')

    def refresh(self,force=False):
        super().refresh(force)
        if hasattr(self,'queue_fold'):
            inline=self.role!='Music' and self.inline_source_mode!='queue'
            self.queue_fold.configure(text=('▾ UP NEXT' if self.upcoming_visible else '▸ UP NEXT')+' · '+str(len(self.future)))
            if self.role!='Music':
                # A completely empty optional queue is a browser, not a transport deck.
                empty=not bool(getattr(self,'items',None) or getattr(self,'future',None))
                if inline:
                    self.queue_fold.pack_forget();self.browse_button.pack_forget()
                elif empty:
                    # An empty optional queue is a single Add/Browse invitation.
                    # No redundant 'Queue Ready / Add from Files' card is needed.
                    if not self.current_canvas.winfo_manager():self.current_canvas.pack(fill='x',before=self.source_shortcuts)
                    self.queue_fold.pack_forget()
                    self.browse_button.configure(text='＋ Add',style='UX28.Insert.TButton')
                    if not self.browse_button.winfo_manager():self.browse_button.grid(row=0,column=4,sticky='e',padx=2)
                else:
                    if not self.current_canvas.winfo_manager():self.current_canvas.pack(fill='x',before=self.source_shortcuts)
                    self.browse_button.configure(text='＋ Add',style='UX28.Insert.TButton')
                    if not self.browse_button.winfo_manager():self.browse_button.grid(row=0,column=4,sticky='e',padx=2)
                    self.queue_fold.pack_forget()
            if hasattr(self,'source_browser') and self.browser_open:self.source_browser.refresh()
        if hasattr(self,'edit_button'):
            selected=getattr(getattr(self.app,'queue_deck',None),'active_role','')==self.role
            self.edit_button.configure(style='Accent.TButton' if selected else 'TButton',text='EDITING' if selected else 'Edit FX')
        if self.role in ('A','B') and hasattr(self,'active_source_name'):
            from ux25_source_state import active_source
            from instrument_model import voice
            now=self.app.programme_time() if self.app.playing else self.app.playhead
            asset,source=active_source(self.app.project,voice(self.app.project,self.role),now)
            label='NOW · '+(asset.name if asset else 'No source queued')
            if source=='override' and asset:label+=' · LIVE OVERRIDE'
            if self.active_source_name.get()!=label:self.active_source_name.set(label)
        if not hasattr(self,'compact_toolbar'):return
        if self.role!='Music':
            # A source controls its capture until there is an actual media
            # queue. Do not show seek, restart and repeat for empty sources.
            queued=bool(getattr(self,'items',None) or getattr(self,'future',None))
            from queue_model import current as current_clip
            from instrument_model import voice
            live_clip=current_clip(voice(self.app.project,self.role),
                self.app.programme_time() if self.app.playing else self.app.playhead)
            live_asset=self.app.project.asset(live_clip.asset_id) if live_clip else None
            live_queued=bool(live_asset and live_asset.kind in ('camera','screen','window'))
            visible=queued and self.inline_source_mode=='queue'
            if visible and not self.compact_toolbar.winfo_manager():
                self.compact_toolbar.pack(fill='x',before=self.current_canvas,pady=(0,2))
            if not visible and self.compact_toolbar.winfo_manager():self.compact_toolbar.pack_forget()
            # All queues retain Next/Stop/Repeat. Unseekable live sources
            # disable only time-seeking/restart/pause, not the queue itself.
            for i,button in enumerate(self.compact_toolbar.winfo_children()):
                if isinstance(button,ttk.Button) and i in (0,1,2):
                    button.configure(state='disabled' if live_queued or bool(self.live_device_kind()) else 'normal')
        if self.role=='Music':
            if hasattr(self,'radio_now'):
                now=getattr(self,'now',None)
                label=now.get().strip() if now is not None else ''
                cues=getattr(getattr(getattr(self.app,'sidebar',None),'source_shelf',None),'audio_cues',None)
                cue_count=len(cues.items()) if cues else 0
                self.radio_now.set(label if getattr(self,'current_id',None) else
                    f'{cue_count} live input cue(s) scheduled' if cue_count else 'No track · Mic ready')
                # The on-air card is a stable part of the player, including
                # empty/silent state; it must not disappear during playback.
                if self.current_canvas.winfo_manager():self.current_canvas.pack_forget()
                if hasattr(self,'radio_level'):
                    self.radio_level['value']=float(self.reaction_meter['value'])
            from live_parameter_controls import source_status
            from sound_routes import source_id
            try:
                status,level=source_status(self.app,'reaction_mix')
                self.reaction_meter['value']=min(100.,max(0.,level*100.))
                states=self.app.live.source_states()
                mic=states.get(source_id(getattr(self.app,'last_microphone_device','default')),{}).get('state')=='live'
                self.mic_button.configure(text=' Mic',style='Accent.TButton' if mic else 'TButton')
                if hasattr(self,'quick_live_button'):
                    self.quick_live_button.configure(style='UX28.MicMiniActive.TButton' if mic else 'UX28.MicMini.TButton',text='● MIC' if mic else '◉ MIC')
            except (AttributeError,ValueError,RuntimeError):
                self.reaction_meter['value']=0
        if self.role!='Music':
            from ux25_source_state import queued_camera_active
            from instrument_model import voice
            now=self.app.programme_time() if self.app.playing and not self.app.reviewing else self.app.playhead
            active=queued_camera_active(self.app.project,voice(self.app.project,self.role),now)
            if hasattr(self,'quick_live_button'):
                self.quick_live_button.configure(style='UX28.LiveMiniActive.TButton' if active else 'UX28.LiveMini.TButton',text='● CAM' if active else '◉ CAM')
            if hasattr(self,'fx_button'):self.fx_button.configure(text=self.fx_badge())
            from queue_model import mode_at
            from instrument_model import voice
            now=self.app.programme_time() if self.app.playing else self.app.playhead
            paused=mode_at(voice(self.app.project,self.role),now)['mode']=='pause'
            # Same transport slot, explicit pause state, without changing rack scope.
            if hasattr(self,'transport_play'):
                self.transport_play.configure(text='▶' if paused else '⏯')
        if self.role!='Music' and hasattr(self,'source_actions'):
            kind=self.live_device_kind();live=bool(kind);camera=kind=='camera';screen=kind in ('screen','window')
            self.source_actions['camera'].configure(style='Accent.TButton' if camera else 'TButton',text=' Cam')
            self.source_actions['screen'].configure(style='Accent.TButton' if screen else 'TButton',text=' Screen')
            self.source_actions['files'].configure(style='TButton' if live else 'Accent.TButton')
        if hasattr(self.app,'sidebar'):self.app.sidebar.request_fit()
        if hasattr(self,'queue_count'):
            self.queue_count.set(f'{len(self.future)} next')
        if hasattr(self,'repeat_button'):
            self.repeat_button.configure(style='Accent.TButton' if self.policy.get()=='repeat' else 'TButton')
        if hasattr(self,'radio_repeat'):
            self.radio_repeat.configure(style='Accent.TButton' if self.policy.get()=='repeat' else 'TButton')
        if hasattr(self,'remove_current_button'):
            self.remove_current_button.configure(state='normal' if self.current_id else 'disabled')
        if hasattr(self,'radio_remove'):
            self.radio_remove.configure(state='normal' if self.current_id else 'disabled')
        if self.role=='Music' and hasattr(self.app,'refresh_audio_tray'):self.app.refresh_audio_tray()
        if not self.winfo_ismapped() and not force:return
        # Keep the engine's current card, progress, policies and source state.
        # Draw a fixed-height list while retaining the engine's hit/drop contract.
        self.current_canvas.delete('ux26-current-remove')
        if self.current_id:
            w=max(80,self.current_canvas.winfo_width())
            self.current_canvas.create_text(w-14,34,text='×',anchor='center',fill=self.app.ui_chrome['accent'],
                font=('TkDefaultFont',14,'bold'),tags='ux26-current-remove')
        cv=self.canvas;chrome=self.app.ui_chrome;width=max(120,cv.winfo_width())
        top=cv.canvasy(0);stride=self.ROW_HEIGHT
        first=max(0,int(top//stride)-1)
        last=min(len(self.future),first+max(4,int(cv.winfo_height()/stride)+3))
        cv.delete('all');self.hits=[]
        for index in range(first,last):
            item=self.future[index];cid=self.ident(item);y=index*stride+1
            asset=self.app.project.asset(self.aid(item))
            name=gap_name(item) or (asset.name if asset else 'Missing source')
            selected=cid==self.selected
            cv.create_rectangle(2,y,width-2,y+stride-3,fill=chrome['selection_bg'] if selected else chrome['field_bg'],outline=chrome['accent'] if selected else chrome['panel_edge'])
            cv.create_text(9,y+12,anchor='w',text=self.fit_title(name,width-120),fill=chrome['foreground'],font=('TkDefaultFont',9,'bold'))
            pinned=item.get('pinned',False) if self.role=='Music' else bool(item.extra.get('playable_pin') or item.locked)
            cv.create_text(9,y+28,anchor='w',text=('NEXT · ' if index==0 else '')+clock_text(self.dur(item))+(' · PINNED' if pinned else ''),fill=chrome['muted_fg'],font=('TkFixedFont',8))
            # Inline ending-edge controls are action targets, not extra rows.
            for offset,glyph,action in ((101,'▶','take'),(76,'↑','move_up'),(51,'↓','move_down'),(24,'×','remove')):
                x=width-offset
                cv.create_text(x,y+stride/2,text=glyph,fill=chrome['accent'] if action=='remove' else chrome['muted_fg'],
                    font=('TkDefaultFont',11,'bold'))
                self.hits.append((cid,y,y+stride-3,action,x-11,x+12))
            self.hits.append((cid,y,y+stride-3,'clip'))
        if not self.future:cv.create_text(width/2,23,text='Drop a source here',fill=chrome['muted_fg'],width=width-12)
        cv.configure(scrollregion=(0,0,width,max(cv.winfo_height(),len(self.future)*stride+2)))


class InstrumentQueues(ttk.Frame):
    """UX11: A over MUSIC on the left; B appears in the opposing right column."""
    def __init__(self,parent,app,prefs,right_host=None,audio_host=None,left_host=None):
        super().__init__(parent,padding=(4,3))
        self.app=app;app.inline_rack_mode=False
        self.pages={};self.tab_hosts={};self.active_role='Master';self.narrow=False
        self.sequence=tk.BooleanVar(self,value=True);self.mix_active=False
        self.mix=tk.DoubleVar(self,value=.5)
        self.visibility={r:tk.BooleanVar(self,value=True) for r in ('Music','A','B')}
        self.channel_faders={};self.channel_enabled={}
        self.panel_bar=ttk.Frame(self);self.panel_bar.grid(row=0,column=0,sticky='ew')
        app.shell.mount_panel_controls('panel.queues',self.panel_bar)
        ttk.Label(self.panel_bar,text='CHANNEL A',style='PlayerName.TLabel').pack(side='left',padx=3)
        self.columnconfigure(0,weight=1)
        self.rowconfigure(1,weight=3,minsize=130)
        self.rowconfigure(2,weight=2 if audio_host is None else 0,minsize=95 if audio_host is None else 0)
        host_a=ttk.Frame(left_host if left_host is not None else self)
        if left_host is None:host_a.grid(row=1,column=0,sticky='nsew',pady=(2,4))
        else:host_a.pack(fill='both',expand=True)
        self.tab_hosts['A']=host_a
        self.pages['A']=InstrumentPlayer(host_a,app,'A',self.visibility['A'])
        self.pages['A'].pack(fill='both',expand=True)
        if right_host is None:
            right_host=ttk.Frame(self)
            right_host.grid(row=3,column=0,sticky='nsew')
            self.rowconfigure(3,weight=1)
        self.tab_hosts['B']=right_host
        self.pages['B']=InstrumentPlayer(right_host,app,'B',self.visibility['B'])
        self.pages['B'].pack(fill='both',expand=True)
        self.sound_host=ttk.Frame(audio_host if audio_host is not None else self)
        if audio_host is None:self.sound_host.grid(row=2,column=0,sticky='nsew',pady=(4,0))
        else:self.sound_host.pack(fill='both',expand=True)
        self.tab_hosts['Music']=self.sound_host
        self.sound=self.pages['Music']=InstrumentPlayer(self.sound_host,app,'Music',self.visibility['Music'])
        self.sound.pack(fill='both',expand=True)
        if left_host is not None:
            # Radio-style transport is always available; the music queue and
            # browser remain optional even while microphone is the live source.
            music=self.sound
            music.mic_button.master.grid_remove()  # mic lives in preview header
            music.sound_badge.configure(text='♫ RADIO')
            music.radio_files_button=ttk.Button(music.channel_header,text='＋ Add',width=7,
                style='UX28.Insert.TButton',command=music.add_from_sources)
            music.radio_files_button.grid(row=0,column=4,sticky='e',padx=2)
            music.quick_live_button.grid(row=0,column=2,sticky='e',padx=(1,4))
            # UX18: RADIO retains its own concise transport, never A/B's six-key deck.
            music.compact_toolbar.pack_forget()
            music.radio_transport.pack(fill='x',before=music.progress.master)
            music.current_canvas.pack_forget()
            # Align the Music disclosure with A/B: right end of the header,
            # never an independent full-width row at the bottom of the card.
            music.sound_badge.configure(text='♫ AUDIO')
            music.queue_fold.pack_forget()
            music.queue_count_label=ttk.Label(music.channel_header,textvariable=music.queue_count,style='Muted.TLabel')
            music.queue_count_label.grid(row=0,column=3,sticky='e',padx=(2,2))
            music.channel_header.columnconfigure(3,weight=1)
            music.queue_toggle=ttk.Button(music.channel_header,text='⌄',width=3,style='UX28.Disclose.TButton',command=music.toggle_future)
            music.queue_toggle.grid(row=0,column=5,sticky='e',padx=2)
            music.browse_button.pack_forget()
            music.music_files_button.pack_forget()
            # Keep every requested playback action, but let the soundtrack
            # title breathe. The input meter is already available in the
            # reaction surface and needn't occupy the queue transport.
            music.radio_play.configure(text='⏯',width=3)
            music.radio_level.pack_forget()

        if getattr(app,'dnd_available',False):
            for role,page in self.pages.items():
                for widget in (page,page.canvas,page.current_canvas):app.register_media_drop(widget,role)
        self.audio_now=tk.StringVar(value='Music · No track')
        self.notebook=None
        self._channel_roles=('A','B')
        self.channel_faders={r:self.pages[r].level_fader for r in ('A','B')}
        self.channel_enabled={r:self.pages[r].programme_enabled for r in ('A','B')}

    def update_left_heights(self):
        """Give collapsed A's unused list height back to MUSIC."""
        a_expanded=self.pages['A'].upcoming_visible
        music_expanded=self.pages['Music'].upcoming_visible
        self.rowconfigure(1,weight=3 if a_expanded else 0,minsize=145 if a_expanded else 0)
        if self.sound_host.master is self:
            self.rowconfigure(2,weight=2 if music_expanded else 0,minsize=115 if music_expanded else 0)

    def sync_channels(self):return
    def fit_sources(self,event=None):return
    def _tab_changed(self,event=None):return
    def show_role(self,role):
        if role in ('A','B'):
            self.active_role=role
            self.app.open_channel_effects(role)
            for r in ('A','B'):self.pages[r].refresh(False)
    def reflow(self,save=True):
        if save:self.app.save_preferences()
    def refresh(self,force=False):
        for page in self.pages.values():page.refresh(force)
        shelf=getattr(getattr(self.app,'sidebar',None),'source_shelf',None)
        if shelf is not None:shelf.audio_cues.step()
        active=[item for item in self.sound.items if self.sound.start(item)<=self.sound.cursor<self.sound.start(item)+self.sound.dur(item)]
        def title(item):
            asset=self.app.project.asset(self.sound.aid(item))
            return gap_name(item) or (asset.name if asset else 'Missing source')
        name=' ↔ '.join(dict.fromkeys(title(item) for item in active)) or 'No music'
        upcoming=self.sound.future[0] if self.sound.future else None
        self.audio_now.set('Music · '+name)
        if hasattr(self.app,'music_transport_caption'):self.app.music_transport_caption.set('Music: '+name+' → '+(title(upcoming) if upcoming else '—'))
        if hasattr(self.app,'refresh_primary_toolbar'):self.app.refresh_primary_toolbar()
        if hasattr(self.app,'overview'):self.app.overview.schedule()
        if hasattr(self.app,'source_strip'):self.app.source_strip.refresh()
        if hasattr(self.app,'conductor'):self.app.conductor.refresh()
        if hasattr(self.app,'empty_preview'):self.app.refresh_empty_preview()
