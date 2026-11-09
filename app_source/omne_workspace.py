"""Stable docked performance workspace over the accepted Neospector runtime."""
from __future__ import annotations
import copy,json,math,queue,random,sys,time
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
from instrument_app import (MultiLiveInputs,CreativeLibrary,ProjectHistory,new_instrument,
                            InstrumentProgrammeView,ProgrammeWorker,base)
from responsive_controls import FlowRow, PriorityToolbar, OverflowAdapter
from omne_library import OmneLibrary
from omne_conductor import ConductorPanel
from omne_sources import SourceStrip
from omne_queue_view import QueueColumns
from omne_overview import TimelineOverview
from omne_rack import CompactRack
from omne_randomise import normalise_settings,make_rack,vary_rack,vary_conductor
from flow_timing import TimingWorkbench
from sequencer_model import project_to_dict
from playable_intent import load_intent
from command_registry import CommandRegistry,CommandDefinition
from panel_registry import PanelRegistry,PanelDefinition
from workspace_system import WorkspaceController,WorkspaceState,DEFAULT_WORKSPACES,migrate_preferences,PANEL_NAMES,panel_id
from module_library import ModuleLibraryPanel

WORKSPACE_PANELS=tuple(PANEL_NAMES.values())

from channel_camera_ui import ChannelCameraActions
from multi_live import ChannelLiveInputs

from media_placement import MediaPlacementActions

from composition_queue_view import CompositionQueueActions

class OmneWorkspace(CompositionQueueActions,MediaPlacementActions,ChannelCameraActions,OmneLibrary):
    def build_ui(self):
        self.minsize(1024,768)
        self.live=ChannelLiveInputs();self.audio_bus.live_inputs=self.live
        prefs=migrate_preferences(self.read_preferences())
        self.recent_projects=list(prefs.get('recent_projects',[]))[:8]
        self.last_camera_device=prefs.get('camera_device','/dev/video0' if sys.platform.startswith('linux') else '0')
        self.last_microphone_device=prefs.get('microphone_device','default' if sys.platform.startswith('linux') else '0')
        self.last_import_folder=prefs.get('import_folder',str(Path.home()));self.recent_import_folders=prefs.get('recent_import_folders',[])
        self.auto_import_media=bool(prefs.get('auto_import_media',False));self.preferences_window=None
        from signed_updates import DEFAULT_FEED
        self.auto_check_updates=bool(prefs.get('auto_check_updates',True))
        self.update_feed_url=str(prefs.get('update_feed_url',DEFAULT_FEED))
        self.import_window=None;self.precision_visible=tk.BooleanVar(value=False)
        self.project=new_instrument();self.project.extra['playable_intent']=load_intent(self.project)
        for layer in self.project.layers:layer.enabled=True
        self.project.extra['playable_intent']['enabled_roles']=['A','B']
        self.history=ProjectHistory(self.project);self.selected_layer_id=self.project.layers[0].id
        self.evolve=tk.BooleanVar(value=False);self.retention_enabled=False;self.retain_armed=tk.BooleanVar(value=False)
        self.retain_armed.trace_add('write',lambda *_:setattr(self,'retention_enabled',bool(self.retain_armed.get())))
        self.capture_seconds=tk.StringVar(value='30')
        record_pref=dict(prefs.get('recording',{}))
        default_record_dir=str(Path.home()/'Videos'/'Neospector')
        self.recording_settings={
            'name':str(record_pref.get('name','Neospector Recording')),
            'directory':str(record_pref.get('directory',default_record_dir)),
            'profile':str(record_pref.get('profile','web')) if str(record_pref.get('profile','web')) in ('web','small','master') else 'web',
            'resolution':str(record_pref.get('resolution','Programme')),
            'fps':int(record_pref.get('fps',20)) if str(record_pref.get('fps',20)).isdigit() else 20,
        }
        self.record_settings_window=None;self._recording_kind=None;self._recording_sequence_label='';self._duration_record=None
        self.album=tk.StringVar(value='all');self.album_label=tk.StringVar(value='This project');self.mode_label=tk.StringVar(value='OUTPUT')
        self.voice_labels={};self.catalog=CreativeLibrary(self.cfg/'creative-library.sqlite3');self.takes=[];self._catalog_futures=[]
        self.cache=base.cache_dir()/'neospector-omne-r5';self.cache.mkdir(parents=True,exist_ok=True)
        self.log_path=self.cache/'session.log';self.preferences_path=self.cfg/'preferences-neospector-omne-r5.json'
        self.autosave_path=self.cfg/'recovery/neospector-omne-r5-autosave.omne-sequence.json'
        self.source_labels={};self.randomise_label=tk.StringVar(value='Randomise')
        self.performance_status=tk.StringVar();self.transport_queue_caption=tk.StringVar();self.music_transport_caption=tk.StringVar()
        self.retention_info=tk.StringVar(value='Live history off');self.audio_info=tk.StringVar(value='No soundtrack')
        self.panel_states={n:False for n in WORKSPACE_PANELS};self.panel_buttons={}
        self.panel_floats={};self.panel_tab_groups={};self._maximized_panel=''
        self._browser_key=None;self._drag_media=None;self.randomise_popup=None
        self.install_ux2_substrate()
        self.workspace_controller=WorkspaceController(self,prefs)
        self.workspace_locked=tk.BooleanVar(value=self.workspace_controller.state.locked)
        self.workspace_name=tk.StringVar(value=self.workspace_controller.state.name)
        from contextual_surface import ContextualSurfaceController
        self.contextual_surfaces=ContextualSurfaceController(self)
        root=ttk.Frame(self,padding=3);self.console_root=root;root.pack(fill='both',expand=True)
        root.columnconfigure(0,weight=1);root.rowconfigure(1,weight=1)
        self.console_styles();style=ttk.Style(self)
        style.configure('PlayerName.TLabel',font=('TkDefaultFont',9,'bold'))
        style.configure('Instrument.TNotebook',tabmargins=0);style.layout('Instrument.TNotebook.Tab',[])
        self.build_menu();self.build_performance_bar(root)
        from instrument_shell import InstrumentShell as WorkspaceShell
        self.shell=WorkspaceShell(root,self,self.workspace_controller.state);self.shell.grid(row=1,column=0,sticky='nsew')
        self.library_frame=self.shell.frames['panel.library'];self.queues_frame=self.shell.frames['panel.queues']
        self.viewport_frame=self.shell.frames['panel.programme'];self.rack_frame=self.shell.frames['panel.rack']
        self.conductor_shell=self.shell.frames['panel.conductor'];self.audio_shell=self.shell.frames['panel.audio']
        self.panel_views={PANEL_NAMES[pid]:frame for pid,frame in self.shell.frames.items()}
        self.queue_content=self.shell.bodies['panel.queues'];self.playback_frame=self.queue_content
        # UX17: A/B/RADIO have independent tabs on one resizable right edge.
        # Their players retain the exact same queue/source model as UX16.
        from ux17_sidebar import RightSourceStack
        self.sidebar=RightSourceStack(self.shell.bodies['panel.library'],self)
        self.sidebar.pack(fill='both',expand=True)
        self.right_a_content=self.sidebar.sections['A']['frame']
        self.right_b_content=self.sidebar.sections['B']['frame']
        self.media_tab=self.sidebar.sections['Music']['frame']  # stage-anchored bottom-right soundtrack queue
        self.shell.headers['panel.library'].pack_forget()
        programme=self.shell.bodies['panel.programme'];header=self.shell.headers['panel.programme']
        self.shell.titles['panel.programme'].configure(textvariable=self.mode_label)
        self.programme_toolbar=header
        # UX21: the preview has no toolbar of its own. Its source controls
        # belong in a right-aligned group on the persistent application bar.
        # Retain this dormant widget for older integrations, never as an FX entry.
        self.output_fx_button=ttk.Button(header,text='OUTPUT FX',command=lambda:self.toggle_effects_context('Master'))
        self.source_switches=ttk.Frame(self.top_source_host,style='UX20.SourceGroup.TFrame',padding=(4,2))
        self.source_switches.pack(side='right')
        self.sources_heading=ttk.Label(self.source_switches,text='SOURCES',style='UX20.SourceHeading.TLabel')
        self.sources_heading.pack_forget()  # Three individually named channels replace redundant group label
        # Three channel columns: direct live toggle above its own queue tray.
        # Same spatial grammar, different semantic shapes and active states.
        self.source_tab_buttons=self.sidebar.dock_buttons
        self.source_capture_buttons={};self.source_pair_hosts={}
        from instrument_icons import icon
        for role in ('A','B','Music'):
            pair=ttk.Frame(self.source_switches,style='UX28.Group.TFrame',padding=(1,1))
            pair.pack(side='left',padx=2)
            if role=='Music':
                live=ttk.Button(pair,image=icon(self,'mic'),text=' MIC',compound='left',width=10,
                    style='UX28.MicIdle.TButton',command=lambda:self.quick_microphone())
                self.preview_microphone=live
            else:
                live=ttk.Button(pair,image=icon(self,'camera-flash'),text=' CAM '+role,
                    compound='left',width=10,style='UX28.LiveIdle.TButton',
                    command=lambda r=role:self.queue_deck.pages[r].toggle_camera())
                if role=='A':self.preview_camera=live
                else:self.preview_camera_b=live
            live.pack(side='top',fill='x',pady=(0,2))
            queue_toggle_button=ttk.Button(pair,text='QUEUE '+role if role!='Music' else '♫ AUDIO',width=10,
                style='UX28.QueueIdle.TButton',command=lambda r=role:self.sidebar.toggle(r))
            queue_toggle_button.pack(side='top',fill='x')
            self.sidebar.sections[role]['button']=queue_toggle_button
            self.sidebar.dock_buttons[role]=queue_toggle_button
            self.source_pair_hosts[role]=pair
            self.source_capture_buttons[role]=live
            self.add_tip(live,'Toggle '+('microphone input' if role=='Music' else 'camera takeover for channel '+role)+'. Press again to return.')
            self.add_tip(queue_toggle_button,'Show or hide '+('audio' if role=='Music' else role)+' queue at bottom-right.')
        self.sidebar.music_button=self.sidebar.sections['Music']['button']
        self.refresh_source_tabs()
        self.preview_screen=ttk.Button(header,text='Screen',command=lambda:self.open_visual_source('A'))
        self.refresh_source_tabs()
        self.programme_toolbar.pack_forget()
        self.return_programme_button=ttk.Button(header,text='Return to Programme',command=self.go_live)
        self.missing_notice=ttk.Button(programme,text='',command=self.locate_missing,style='Missing.TButton')
        from instrument_mix import VisualMixStrip
        self.visual_mix=VisualMixStrip(self.top_row,self)
        self.visual_mix.grid(row=0,column=1,sticky='ew',padx=(4,5))
        # UX28: Audio joins A/B in the right floating queue stack.
        self.audio_tray_host=self.sidebar.sections['Music']['frame']
        self.audio_tray_open=False
        self.media_tab=self.audio_tray_host
        self.viewport=InstrumentProgrammeView(programme,self);self.viewport.quality.set(prefs.get('preview_quality','360'));self.viewport.pack(fill='both',expand=True)
        self.preview_options_row=self.viewport.winfo_children()[0];self.preview_options_row.pack_forget()
        self.preview_diagnostics_row=self.viewport.winfo_children()[-1]
        if self.preview_diagnostics_row is not self.viewport.canvas:self.preview_diagnostics_row.pack_forget()
        self.empty_preview=ttk.Frame(self.viewport.canvas,padding=14)
        ttk.Label(self.empty_preview,text='DROP MEDIA HERE',style='PlayerName.TLabel').pack(pady=(0,6))
        ttk.Button(self.empty_preview,text='Import media',style='UX19.Import.TButton',command=self.add_media).pack(fill='x',pady=3)
        # Retain the legacy action widget for ImmediateActions wiring, but
        # never duplicate it in the preview; Camera A is in the header.
        self.empty_preview_camera=ttk.Button(self.empty_preview,text='Start camera',command=self.toggle_camera_layer)
        self.drop_role=tk.StringVar(value='A');self.drop_feedback=tk.StringVar(value='Audio → Music')
        # UX8: one primary rack, independent of queue playback and disclosure.
        from instrument_rack import InstrumentRack
        self.inline_rack_mode=False
        self.channel_queues_host=ttk.Frame(self.queue_content)
        # Packed *after* project media, so the folder reserves visible height.
        # A/B and MUSIC share the remaining media-desk height.
        self.channel_effects_host=self.shell.bodies['panel.rack']
        self.overview=TimelineOverview(self.channel_effects_host,self)
        self.tools_notebook=ttk.Notebook(self.channel_effects_host,style='Instrument.TNotebook')
        self.modules_tab=self.channel_effects_host
        # The module catalogue is part of the rack; project files never replace it.
        self.rack_split=ttk.PanedWindow(self.modules_tab,orient='horizontal')
        self.rack_split.pack(fill='both',expand=True)
        self.rack_split.bind('<Configure>',self._ux13_rack_size,add='+')
        self.rack_primary=ttk.Frame(self.rack_split)
        self.rack_split.add(self.rack_primary,weight=3)
        # UX20: a fixed orientation/owner bar directly above the rack.
        # It stays visible while modules scroll, and switches target in one click.
        self.rack_owner_strip=tk.Frame(self.rack_primary,bg='#1b2c3a',bd=0,
                                       highlightthickness=2,highlightbackground='#77b4e5')
        self.rack_owner_strip.pack(fill='x',pady=(0,3))
        self.rack_owner_title=tk.StringVar(value='EDITING OUTPUT · AFTER MIX')
        self.rack_owner_header=ttk.Frame(self.rack_owner_strip,style='UX20.OwnerFrame.TFrame')
        self.rack_owner_header.pack(fill='x',padx=5,pady=(3,1))
        self.rack_owner_heading=ttk.Label(self.rack_owner_header,textvariable=self.rack_owner_title,style='UX20.OwnerTitle.TLabel')
        self.rack_owner_heading.pack(side='left',fill='x',expand=True,padx=(4,2))
        self.rack_close_control=ttk.Button(self.rack_owner_header,text='×',width=3,style='UX20.Small.TButton',
             command=lambda:self.shell.collapse('Rack'))
        self.rack_close_control.pack(side='right',padx=(4,0))
        self.rack_flip_control=ttk.Button(self.rack_owner_header,text='↔',width=3,style='UX20.Small.TButton',
             command=self.shell.flip_rack_overlay)
        self.rack_flip_control.pack_forget()  # UX22: rack stays on its docked side
        self.rack_power_control=ttk.Button(self.rack_owner_header,text='FX ON',width=7,
             style='UX20.PowerOn.TButton',command=self.toggle_rack_power_ux20)
        self.rack_power_control.pack(side='right',padx=(2,0))
        destinations=ttk.Frame(self.rack_owner_strip,style='UX20.OwnerFrame.TFrame')
        destinations.pack(fill='x',padx=6,pady=(0,5))
        self.rack_target_buttons={}
        for role,label in (('A','A'),('B','B'),('Transition','TRANSITION'),('Master','OUTPUT')):
            button=ttk.Button(destinations,text=label,style='UX20.TargetIdle.TButton',width=12 if role=='Transition' else 8 if role=='Master' else 4,
                              command=lambda r=role:self.open_effects_context(r))
            button.pack(side='left',padx=(0,3))
            self.rack_target_buttons[role]=button
        self.rack_count_label=ttk.Label(destinations,text='0 effects',style='UX20.OwnerCount.TLabel')
        self.rack_count_label.pack(side='right',padx=(6,2))
        self.transition_shape_row=ttk.Frame(self.rack_owner_strip,padding=(5,1))
        # Authored animation belongs in the modules below, not a parallel row
        # of shape and easing presets. Legacy project values remain readable.
        self.transition_shape_text=tk.StringVar(value='AUTHORED MOTION')
        self.transition_curve_text=tk.StringVar(value='')
        self.transition_softness=tk.DoubleVar(value=.09)
        ttk.Label(self.transition_shape_row,text='MOTION  ·  Edit timing, reveal, pixel, iris and slide modules below.',
                  style='Muted.TLabel').pack(side='left',padx=(0,5))
        ttk.Button(self.transition_shape_row,text='+ Animations',width=12,
                   command=self.show_module_library).pack(side='right')

        self.deck=InstrumentRack(self.rack_primary,self)
        # The original breadcrumb repeats this persistent owner heading and
        # makes a second identical toolbar. Keep the old widget as a service
        # compatibility object, but do not spend space on its duplicate row.
        self.deck.path_label.master.pack_forget()
        self.deck.pack(fill='both',expand=True)
        self.module_library_host=ttk.Frame(self.rack_split)
        self.module_tab=self.module_library_host
        self.legacy_library_host=ttk.Frame(self.module_library_host)
        self.build_library(self.legacy_library_host)
        self.module_library=ModuleLibraryPanel(self.module_library_host,self)
        for widget in (self.module_library.filter_button,):
            flow=widget.master
            if widget in flow.items:flow.items.remove(widget)
            widget.place_forget();flow.last=None;flow.schedule()
        self.module_library.view.set('List')
        self.module_library.pack(fill='both',expand=True)
        self.module_builder_host=ttk.Frame(self.module_library_host)
        self.module_builder=None
        self.library_open=False
        self.deck.library_button=ttk.Button(self.deck.action_toolbar,text='+ Modules',width=10,style='Accent.TButton',command=self.toggle_module_library)
        self.deck.library_button.pack(side='left',padx=1)
        self.add_tip(self.deck.library_button,'Browse modules beside this rack. Project Media stays in the right sidebar.')
        self.module_library.refresh(force=True)
        self.shell.headers['panel.rack'].pack_forget()
        self.precision_window=tk.Toplevel(self);self.precision_window.withdraw();self.precision_window.title('Precise timing · Neospector')
        self.precision_window.geometry('1000x590');self.precision_window.protocol('WM_DELETE_WINDOW',self.hide_precision)
        self.timeline=TimingWorkbench(self.precision_window,self);self.timeline.pack(fill='both',expand=True)
        from editor_widgets import ScrollFrame
        conductor_scroll=ScrollFrame(self.shell.bodies['panel.conductor'],self);self.conductor_tab=conductor_scroll;conductor_scroll.pack(fill='both',expand=True)
        self.conductor=ConductorPanel(conductor_scroll.body,self);self.conductor.pack(fill='x')
        audio_scroll=ScrollFrame(self.shell.bodies['panel.audio'],self);audio_scroll.pack(fill='both',expand=True);self.audio_scroll=audio_scroll
        self.source_strip=SourceStrip(audio_scroll.body,self);self.source_strip.pack(fill='both',expand=True)
        from instrument_media import InstrumentQueues
        self.queue_deck=InstrumentQueues(self.channel_queues_host,self,prefs,
            left_host=self.right_a_content,right_host=self.right_b_content,audio_host=self.media_tab)
        self.queue_deck.pack(fill='both',expand=True)
        # Source panels own project browsing; retained project folder remains an
        # unmounted service adapter for legacy library commands.
        # Audio is available without permanently exposing its soundtrack queue.
        from ux10_project_media import ProjectMediaFolder
        self._legacy_media_service=ttk.Frame(self)  # never packed; retained library adapter
        self.project_media_folder=ProjectMediaFolder(self._legacy_media_service,self)
        self.channel_queues_host.pack(fill='both',expand=True)
        self.build_fx_navigator(root)
        self.library=self.project_media_folder.browser
        self.search=self.library.query
        self.project_media_folder.refresh_assets()
        self.queue_conductor_visible=tk.BooleanVar(value=True);self.conductor_mini_visible=tk.BooleanVar(value=True)
        self.queue_conductor=self.conductor;self.queue_conductor.controller=self.conductor
        self.conductor_mini=self.conductor;self.performance_panel=self.shell.bodies['panel.conductor']
        from lesson_ui import LessonCoach
        self.guides=LessonCoach(self)
        self.ux7_lesson_progress=self.guides.progress
        for pid,header in self.shell.headers.items():
            if pid in ('panel.programme','panel.queues','panel.rack'):
                continue
            help_button=ttk.Button(header,text='?',width=2,command=lambda p=pid:self.open_panel_help(p))
            help_button.pack(side='right',padx=(0,3))
            self.add_tip(help_button,'Find actions and short guided tasks for '+self.panels.get(pid).title+'. F1 searches all Help.')
        self.precision_button=ttk.Button(self.precision_window,text='Close timing',command=self.hide_precision);self.precision_button.pack(side='bottom')
        status=ttk.Frame(root);self.status_row=status;status.columnconfigure(0,weight=1)
        ttk.Label(status,textvariable=self.status,style='Muted.TLabel').grid(row=0,column=0,sticky='ew')
        self.progress=ttk.Progressbar(status,length=70,maximum=100)
        self.cancel_button=ttk.Button(status,text='Cancel export',command=lambda:self.render_cancel.set(),state='disabled')
        self.range_label=ttk.Label(status,text='',style='Muted.TLabel')
        self._status_hide=None;self.status.trace_add('write',self.refresh_status_line)
        self.background_events=queue.Queue();self.background_worker=ProgrammeWorker(self.background_events,self.live)
        self.after(300,self.init_drop_support);self.after(700,self.check_media_health)
        self.after_idle(self.refresh_empty_preview)
        self.apply_workspace_state(self.workspace_controller.state)

        self.after_idle(lambda:(self.deck.refresh(True),self.refresh_effects_badges()))
        from dialog_policy import install
        install(self)
    def _ux19_fit_preview_header(self,event=None):
        # UX21: the old preview toolbar is permanently removed.
        return None

    def refresh_source_tabs(self):
        if not hasattr(self,'source_tab_buttons'):return
        for role,button in self.source_tab_buttons.items():
            opened=bool(self.sidebar.sections[role]['open'])
            count=self.effects_count(role) if role!='Music' and hasattr(self,'project') else 0
            base={'A':'QUEUE A','B':'QUEUE B','Music':'♫ AUDIO'}[role]
            button.configure(text=base+(' ▴' if opened else ' ▾'),
                style='UX28.QueueFlash.TButton' if role==getattr(self.sidebar,'_flash_role',None) else
                      'UX28.QueueOpen.TButton' if opened else 'UX28.QueueIdle.TButton')

    def build_fx_navigator(self,root):
        """One global effect map: locate owners and bypass without entering a rack."""
        self.master_fx_tray=tk.Frame(root,bg='#1d2432',highlightthickness=2,highlightbackground='#779adb',bd=0)
        title=ttk.Frame(self.master_fx_tray,padding=(9,7));title.pack(fill='x')
        ttk.Label(title,text='FX · SIGNAL MAP',style='PlayerName.TLabel').pack(side='left')
        ttk.Button(title,text='×',width=3,command=self.hide_master_fx).pack(side='right')
        ttk.Label(self.master_fx_tray,text='Choose a source to edit, or bypass its whole rack.',
                  style='Muted.TLabel',wraplength=295).pack(anchor='w',padx=8,pady=(0,5))
        self.fx_nav_rows={}
        for role,title in [('A','CHANNEL A'),('B','CHANNEL B'),('Master','OUTPUT · AFTER MIX')]:
            row=ttk.Frame(self.master_fx_tray,padding=(7,2));row.pack(fill='x')
            label=ttk.Label(row,text=title,width=21);label.pack(side='left')
            go=ttk.Button(row,text='Open',width=6,command=lambda r=role:self.fx_nav_target(r));go.pack(side='right',padx=2)
            bypass=ttk.Button(row,text='ON',width=5,command=lambda r=role:self.fx_nav_toggle(r))
            bypass.pack(side='right',padx=2)
            self.fx_nav_rows[role]=(label,bypass)
        self.fx_nav_clip_rows={}
        self.fx_nav_clip_controls={}
        for role in ('A','B'):
            row=ttk.Frame(self.master_fx_tray,padding=(7,2))
            label=ttk.Label(row,text=role+' · CLIP',width=21);label.pack(side='left')
            go=ttk.Button(row,text='Open',width=6)
            go.pack(side='right',padx=2)
            bypass=ttk.Button(row,text='ON',width=5)
            bypass.pack(side='right',padx=2)
            self.fx_nav_clip_rows[role+' · CLIP']=row
            self.fx_nav_clip_controls[role]=(label,go,bypass)
        self.master_fx_tray.place_forget()

    def _fx_active_clip(self,role):
        from instrument_model import voice
        layer=voice(self.project,role)
        if layer is None:return None
        page=getattr(getattr(self,'queue_deck',None),'pages',{}).get(role)
        clip_id=getattr(page,'current_id',None)
        if not clip_id:return None
        return next((clip for clip in layer.clips if clip.id==clip_id),None)

    def _fx_toggle_clip(self,role):
        clip=self._fx_active_clip(role)
        if clip is None:return
        self.transaction('Bypass clip effects · '+role,
            lambda:setattr(clip,'extra',{**clip.extra,'rack_bypassed':not bool(clip.extra.get('rack_bypassed',False))}))
        self.refresh_fx_map()

    def _fx_open_clip(self,role):
        clip=self._fx_active_clip(role)
        if clip is None:return
        self.hide_master_fx()
        self.open_effects_context(role,clip.id)

    def _fx_owner(self,role):
        if role=='Master':return self.project
        from instrument_model import voice
        return voice(self.project,role)

    def refresh_fx_map(self):
        if not hasattr(self,'fx_nav_rows'):return
        for role,(label,button) in self.fx_nav_rows.items():
            owner=self._fx_owner(role)
            count=self.effects_count(role)
            bypass=bool(owner.extra.get('rack_bypassed',False)) if owner is not None else False
            label.configure(text=f'{"OUTPUT" if role=="Master" else "CHANNEL "+role}  ·  {count} FX')
            button.configure(text='OFF' if bypass else 'ON',style='TButton' if bypass else 'Accent.TButton')
        for role,(label,go,bypass_button) in self.fx_nav_clip_controls.items():
            clip=self._fx_active_clip(role)
            row=self.fx_nav_clip_rows[role+' · CLIP']
            if clip is None or not clip.rack:
                row.pack_forget();continue
            label.configure(text=f'{role} · CLIP  ·  {len(clip.rack)} FX')
            bypassed=bool(clip.extra.get('rack_bypassed',False))
            bypass_button.configure(text='OFF' if bypassed else 'ON',
                                    style='TButton' if bypassed else 'Accent.TButton',
                                    command=lambda r=role:self._fx_toggle_clip(r))
            go.configure(command=lambda r=role:self._fx_open_clip(r))
            if not row.winfo_manager():row.pack(fill='x')

    def show_master_fx(self):
        tray=self.master_fx_tray
        if tray.winfo_manager():self.hide_master_fx();return
        self.refresh_fx_map()
        tray.place(x=8,y=40,width=338,height=305)
        tray.lift()

    def hide_master_fx(self):self.master_fx_tray.place_forget()

    def fx_nav_target(self,role):
        self.hide_master_fx();self.open_effects_context(role)
        self.update_status('Editing '+('Output' if role=='Master' else 'Channel '+role)+' effects')

    def fx_nav_toggle(self,role):
        owner=self._fx_owner(role)
        if owner is None:return
        def change():owner.extra['rack_bypassed']=not bool(owner.extra.get('rack_bypassed',False))
        self.transaction('Bypass effects · '+role,change)
        self.refresh_fx_map();self.refresh_effects_badges()

    def effects_count(self,role,clip_id=None):
        """Visible processing count for each owner; never infer from the UI."""
        if role=='Transition':rack=self.project.transition_rack
        elif role=='Master':rack=self.project.master_rack
        else:
            from instrument_model import voice
            layer=voice(self.project,role)
            if not layer:return 0
            clip=next((c for c in layer.clips if c.id==clip_id),None) if clip_id else None
            rack=clip.rack if clip else layer.rack
        return len(rack)

    def open_effects_context(self,role='Master',clip_id=None):
        """One canvas for A, B and Output; never selects a clip-level rack."""
        clip_id=None
        self.open_channel_effects(role,clip_id=None,show=False)
        self.shell.show('Rack')
        self.deck.refresh(True)
        self.refresh_effects_badges()
        return self.deck.selected_cell()

    def toggle_main_effects(self):
        """The sole application-level FX disclosure; preserve the selected owner."""
        if self.shell.rack_open:
            self.shell.collapse('Rack')
        else:
            self.open_effects_context(getattr(self,'rack_context_role','Master'))
        self.refresh_effects_badges()
        self.refresh_main_effects_button()

    def refresh_main_effects_button(self):
        if hasattr(self,'master_fx_button'):
            self.master_fx_button.configure(style='UX21.EffectsActive.TButton' if self.shell.rack_open else 'UX21.Effects.TButton',
                 text='Effects')
        if hasattr(self,'media_sources_button'):
            self.media_sources_button.configure(style='UX21.EffectsActive.TButton' if self.sidebar._browser_open else 'UX21.Effects.TButton')

    def toggle_effects_context(self,role='Master',clip_id=None):
        cell=self.deck.selected_cell()
        selected=(cell.adapter.scope=='Master' and role=='Master') if cell else False
        if cell and role!='Master':
            selected=(cell.adapter.scope in ('Layer','Clip') and
                      cell.adapter.parent.extra.get('voice')==role if cell.adapter.scope=='Clip' else
                      cell.adapter.owner.extra.get('voice')==role if cell.adapter.scope=='Layer' else False)
            if clip_id and selected:selected=cell.adapter.scope=='Clip' and cell.adapter.owner.id==clip_id
        if self.shell.rack_open and selected:
            self.shell.collapse('Rack');self.refresh_effects_badges()
            if hasattr(self,'sidebar'):self.sidebar.highlight(None)
            if hasattr(self,'viewport_frame'):self.viewport_frame.configure(highlightbackground=self.ui_chrome.get('sash_color','#44414e'))
            return False
        self.open_effects_context(role,clip_id);return True

    def refresh_effects_badges(self):
        if hasattr(self,'rack_owner_title'):self.refresh_rack_ownership()
        self.refresh_main_effects_button()
        if hasattr(self,'output_fx_button'):
            self.output_fx_button.configure(text=f'OUTPUT FX · {self.effects_count("Master")}' + (' ▲' if self.shell.rack_open and self.deck.scope.get()=='Master' else ' ▾'))
        if hasattr(self,'queue_deck'):
            for role in ('A','B'):
                page=self.queue_deck.pages[role]
                if hasattr(page,'fx_button'):page.fx_button.configure(text=page.fx_badge())
        if hasattr(self,'sidebar'):self.sidebar.refresh_rail()
        if hasattr(self,'master_fx_tray') and self.master_fx_tray.winfo_manager():self.refresh_fx_map()

    def toggle_rack_power_ux20(self):
        self.deck.direct_toggle_fx()
        self.refresh_rack_ownership()
        self.refresh_fx_map()

    def cycle_transition_property(self,key):
        from ux16_transitions import STYLES,EASING,configure_transition,validated_spec
        names=STYLES if key=='kind' else EASING
        current=validated_spec(self.project.extra.get('ux16_transition',{}))[key]
        keys=list(names);value=keys[(keys.index(current)+1)%len(keys)]
        kind=value if key=='kind' else validated_spec(self.project.extra.get('ux16_transition',{}))['kind']
        updates={} if key=='kind' else {key:value}
        self.transaction('Transition '+key,lambda:configure_transition(self.project,kind,**updates))
        self.refresh_rack_ownership();self.visual_mix.refresh()

    def commit_transition_softness(self):
        from ux16_transitions import configure_transition,validated_spec
        current=validated_spec(self.project.extra.get('ux16_transition',{}))
        value=float(self.transition_softness.get())
        if abs(current['softness']-value)<.00001:return
        self.transaction('Transition edge softness',lambda:configure_transition(self.project,current['kind'],softness=value))
        self._transition_drag_start=None
        self.visual_mix.refresh()

    def refresh_rack_ownership(self):
        if not hasattr(self,'rack_owner_title'):return
        role=getattr(self,'rack_context_role','Master')
        from ux16_transitions import STYLES,EASING,validated_spec
        shape=validated_spec(self.project.extra.get('ux16_transition',{}))
        self.transition_shape_text.set(STYLES[shape['kind']])
        self.transition_curve_text.set(EASING[shape['easing']])
        if not getattr(self,'_transition_drag_start',None):self.transition_softness.set(shape['softness'])
        if role=='Transition' and not self.transition_shape_row.winfo_manager():self.transition_shape_row.pack(fill='x',padx=5,pady=(0,4))
        elif role!='Transition' and self.transition_shape_row.winfo_manager():self.transition_shape_row.pack_forget()
        clip_id=getattr(self,'rack_context_clip_id',None)
        name=('A/B TRANSITION · DURING MIX' if role=='Transition' else 'OUTPUT · AFTER MIX' if role=='Master' else
              'CLIP '+role if clip_id else 'CHANNEL '+role)
        self.rack_owner_title.set('EDITING '+name)
        accents={'A':'#5eacc5','B':'#e9a16c','Master':'#8d9df4','Transition':'#c3a2db'}
        self.rack_owner_strip.configure(highlightbackground=accents.get(role,'#8d9df4'))
        count=self.effects_count(role,clip_id)
        self.rack_count_label.configure(text=f'{count} effect'+('' if count==1 else 's'))
        if hasattr(self,'deck'):
            active=self.deck.fx_enabled()
            self.rack_power_control.configure(text='FX ON' if active else 'FX OFF',
                                              style='UX20.PowerOn.TButton' if active else 'UX20.PowerOff.TButton')
        for r,button in self.rack_target_buttons.items():
            button.configure(style='UX20.TargetActive.TButton' if r==role else 'UX20.TargetIdle.TButton')
        if hasattr(self,'sidebar') and role in ('A','B'):
            self.sidebar.highlight(role)

    def open_channel_effects(self,role,*,clip_id=None,show=True):
        if role in ('A','B'):clip_id=None
        if role in ('A','B','Master','Transition'):
            self.rack_context_role=role;self.rack_context_clip_id=clip_id
            self.edit_target_role=role
            if hasattr(self,'queue_deck'):self.queue_deck.active_role=role
        if self.gesture:self.end_gesture()
        self.deck.group_path=();self.deck.group_context=None
        if role=='Mix':
            from instrument_widgets import EffectsDeck
            def build(body):
                editor=EffectsDeck(body,self);editor.scope.set(role);editor.pack(fill='both',expand=True);editor.refresh(True)
            return self.open_context_tray(('routing',role),'Mixer controls' if role=='Mix' else 'Transition controls',build)
        if role in ('Master','Transition'):self.deck.scope.set(role)
        else:
            from instrument_model import voice
            layer=voice(self.project,role)
            if layer is None:return
            self.selected_layer_id=layer.id
            if clip_id:
                found=self.deck.find_clip(role,clip_id)
                if not found or found[0].id!=layer.id:return
                self.selected_clip_id=clip_id;self.deck.scope.set('Clip')
            else:
                self.selected_clip_id=None;self.deck.scope.set('Layer')
        self.follow_playhead.set(False)
        self.deck.refresh(True)
        if hasattr(self,'queue_deck'):
            for r in ('A','B'):self.queue_deck.pages[r].refresh(False)
        if show:self.shell.show('Rack')
        self.refresh_effects_badges()
        self.refresh_library_destination()
        if hasattr(self,'module_library') and self.library_open:self.module_library.refresh(force=True)
        if hasattr(self,'sidebar'):self.sidebar.highlight(role if role in ('A','B') else None)
        if hasattr(self,'viewport_frame'):
            self.viewport_frame.configure(highlightbackground=('#84b3f7' if role=='Master' else self.ui_chrome.get('sash_color','#44414e')))
        return self.deck.selected_cell()

    def install_ux2_substrate(self):
        """Install the complete UX2 command/panel/task-window substrate."""
        self.commands=CommandRegistry();self.panels=PanelRegistry()
        for definition in (
            PanelDefinition('panel.programme','Programme','Programme','programme',min_width=350,min_height=180,preferred_width=820,preferred_height=520,dock_zones=('centre',)),
            PanelDefinition('panel.queues','Queues','Queues','queue',min_width=316,min_height=360,preferred_width=360,preferred_height=450,dock_zones=('left','right','bottom','centre')),
            PanelDefinition('panel.library','Library','Library','library',min_width=316,min_height=250,preferred_width=360,preferred_height=300,dock_zones=('left','right','bottom','centre')),
            PanelDefinition('panel.rack','Module Rack','Rack','rack',min_width=350,min_height=260,preferred_width=850,preferred_height=430,dock_zones=('bottom','centre')),
            PanelDefinition('panel.conductor','Conductor','Conductor','conductor',min_width=278,min_height=220,preferred_width=310,preferred_height=420,dock_zones=('left','right','bottom','centre')),
            PanelDefinition('panel.audio','Audio','Audio','audio',min_width=278,min_height=190,preferred_width=310,preferred_height=260,dock_zones=('left','right','bottom','centre')),
            PanelDefinition('task.timing','Precise timing','precision','timing',lifetime='task',min_width=720,min_height=420,state_owner='project'),
            PanelDefinition('task.record-settings','Record Settings','record_settings','record',lifetime='task',min_width=520,min_height=0,state_owner='preferences'),
        ):self.panels.register(definition)
        def add(cid,label,handler,**meta):self.commands.register(CommandDefinition(cid,label,handler,**meta))
        # File/project commands
        add('project.new','New instrument',self.new_project,icon='new',shortcut='Ctrl+N',scope='project')
        add('project.open','Open…',self.open_project,icon='open',shortcut='Ctrl+O',scope='project')
        add('project.example','Open example',self.open_example,icon='example',scope='project')
        add('project.save','Save',self.save_project,icon='save',help='Save the current project.',shortcut='Ctrl+S',scope='project')
        add('project.save-as','Save as…',lambda:self.save_project(as_new=True),icon='save-as',shortcut='Ctrl+Shift+S',scope='project')
        add('project.import-media','Import Media…',self.add_media,scope='project')
        add('project.import-folder','Import Folder…',self.import_folder,scope='project')
        add('project.inspect-imports','Inspect Imports…',self.open_import_browser,scope='project')
        add('project.locate-missing','Locate Missing Media…',self.locate_missing,scope='project')
        add('project.drafts','Drafts…',self.show_drafts,scope='project')
        add('project.export','Export…',self.export_video,scope='project')
        add('project.diagnostics','Diagnostics…',self.export_diagnostics,scope='application')
        add('project.exit','Exit',self.close,scope='application')
        # Transport/edit
        add('transport.play','Play / Pause',self.toggle_play,icon='play',help='Play or pause Programme.',shortcut='Space',scope='programme')
        add('transport.stop','Stop',self.stop_session,icon='stop',help='Stop Programme.',scope='programme')
        add('edit.undo','Undo',self.undo,icon='undo',shortcut='Ctrl+Z',scope='project')
        add('edit.redo','Redo',self.redo,icon='redo',shortcut='Ctrl+Y',scope='project')
        add('edit.split','Split',self.split_current,shortcut='S',scope='selection')
        add('edit.replace','Replace media',self.replace_current,scope='selection')
        add('edit.insert-before','Insert before',lambda:self.insert_near(False),scope='selection')
        add('edit.insert-after','Insert after',lambda:self.insert_near(True),scope='selection')
        add('edit.duplicate','Duplicate',self.duplicate_current,scope='selection')
        add('edit.delete','Delete',self.delete_current,shortcut='Delete',scope='selection')
        add('edit.add-text','Add Text',self.add_text,scope='project');add('edit.add-shape','Add Shape',self.add_shape,scope='project')
        # Sources/rack/capture
        add('rack.randomise','Randomise',lambda:self.randomise_playable(settings=self.settings()),icon='randomise',help='Build a new composition in the selected scope, respecting explicit composition locks. Open options to choose its pool and variation.',scope='rack')
        add('rack.add-module','Add Module',self.show_module_library,icon='plus',help='Open Library directly to Modules and focus search.',scope='rack')
        add('rack.group','Group',lambda:self.deck.group_selected() if hasattr(self,'deck') else False,icon='group',help='Group adjacent selected rack modules in one undoable action.',scope='rack')
        add('rack.mutate','Mutate',self.mutate,icon='mutate',help='Vary the current treatment while retaining its module chain. Use variation controls to tune how far it moves.',shortcut='M',scope='rack')
        add('input.camera.toggle','Camera',self.toggle_selected_camera,icon='camera',help='Explicitly start/stop the selected live camera.',scope='input')
        add('input.microphone.toggle','Microphone',self.quick_microphone,icon='microphone',help='Explicitly start/stop the microphone. ON means Sound + React + recording.',scope='input')
        add('output.viewer','Output Viewer',self.open_output,icon='output',scope='programme')
        add('record.toggle','Record',self.record_programme,icon='record',scope='programme')
        add('record.settings','Record Settings',lambda:self.open_preferences('recording'),icon='settings',scope='programme')
        add('record.sequence','Record Sequence',self.record_sequence_action,icon='record-sequence',scope='programme')
        add('programme.settings','Canvas / output settings…',lambda:self.open_preferences('output'),scope='programme')
        add('theme.studio','Theme Studio',self.open_theme_studio,scope='application')
        add('application.preferences','Preferences…',lambda:self.open_preferences('general'),scope='application')
        add('theme.import','Import theme',self.open_theme_import,scope='application')
        add('help.startup','Welcome',lambda:self.show_startup_window(True),help='Choose a starting task, continue this project or open an example. Opening Welcome does not start a source.',scope='application')
        add('help.quick-guide','Help and actions',self.quick_guide,help='Search actions by name or purpose. Selecting a result explains it without activating it.',shortcut='F1',scope='application')
        add('input.visual.choose','Screen / Window…',self.open_visual_source,help='Choose an X11 screen or window, preview and crop it before explicitly using it in a channel. Audio is separate.',scope='input')
        add('programme.focus','Focus output',self.toggle_focus_output,icon='focus',scope='workspace')
        add('timing.precision','Precise timing',self.toggle_precision,icon='timing',scope='workspace')
        # Workspace/panel commands
        add('workspace.switch','Switch Workspace',lambda:self.switch_workspace(self.workspace_name.get()),icon='workspace',scope='workspace')
        add('workspace.next','Next Workspace',self.next_workspace,icon='workspace',shortcut='Ctrl+Tab',scope='workspace')
        add('workspace.lock','Lock Workspace',self.toggle_workspace_lock,icon='lock',checked=lambda:bool(getattr(self,'workspace_locked',None) and self.workspace_locked.get()),scope='workspace')
        add('workspace.save-as','Save Workspace As…',self.save_workspace_as,scope='workspace')
        add('workspace.rename','Rename Custom Workspace…',self.rename_workspace,scope='workspace')
        add('workspace.delete','Delete Custom Workspace',self.delete_workspace,scope='workspace')
        add('workspace.reset','Reset Workspace',self.reset_workspace,scope='workspace')
        add('workspace.restore','Restore Panel Layout',self.restore_maximized_panel,shortcut='Escape',scope='workspace')
        for name in WORKSPACE_PANELS:
            slug=name.lower();pid='panel.'+slug;add(pid+'.toggle',name,lambda n=name:self.toggle_panel(n),icon=slug,checked=lambda n=name:bool(self.panel_states.get(n)),scope='workspace',target=pid)
            add(pid+'.float','Float '+name,lambda n=name:self.float_panel(n),scope='workspace',target=pid)
            add(pid+'.redock','Redock '+name,lambda n=name:self.redock_panel(n),scope='workspace',target=pid)
            add(pid+'.maximize','Maximize '+name,lambda n=name:self.toggle_panel_maximize(n),scope='workspace',target=pid)

    def _global_camera_selected(self,event=None):
        value=self.quick_camera_device.get().strip()
        if value:self.last_camera_device=value
        self.refresh_primary_toolbar()

    def begin_visual_master(self):
        if getattr(self,'_visual_master_active',False):return
        self._visual_master_active=True;self.begin_gesture('program');self._visual_master_time=self.programme_time() if self.playing else self.playhead
    def change_visual_master(self,value):
        if not getattr(self,'_visual_master_active',False):return
        from visual_channels import set_master
        set_master(self.project,'visual',value,self._visual_master_time);self.changed()
    def end_visual_master(self):
        if not getattr(self,'_visual_master_active',False):return
        self._visual_master_active=False;self.end_gesture();self.refresh_primary_toolbar()

    def refresh_primary_toolbar(self):
        if not hasattr(self,'global_toolbar'):return
        if hasattr(self,'queue_deck'):
            local_camera=any(page.camera_button.winfo_viewable() for role,page in self.queue_deck.pages.items() if role!='Music')
            self.global_toolbar.set_available(self.global_camera_button.master,False)
        if hasattr(self,'source_strip'):
            self.global_toolbar.set_available(self.global_mic_button.master,False)
        from visual_channels import master_at,channels
        from queue_model import mode_at
        from sound_routes import source_id,default_route
        t=self.programme_time() if self.playing and not self.reviewing else self.playhead
        if hasattr(self,'visual_master_fader') and not getattr(self,'_visual_master_active',False):self.visual_master_fader.sync(master_at(self.project,'visual',t))
        # Keep selected camera and the global action adjacent, with stable width.
        if hasattr(self,'quick_camera_device') and self.quick_camera_device.get()!=str(self.last_camera_device):self.quick_camera_device.set(str(self.last_camera_device))
        camera_live=any(l.enabled and mode_at(l,t).get('mode')=='camera' for l in channels(self.project))
        from instrument_model import voice
        channel_a=voice(self.project,'A')
        from ux25_source_state import queued_camera_active
        camera_a_active=bool(channel_a and queued_camera_active(self.project,channel_a,t))
        if hasattr(self,'preview_camera'):
            self.preview_camera.configure(style='UX28.LiveActive.TButton' if camera_a_active else 'UX28.LiveIdle.TButton',
                text=' CAM A ●' if camera_a_active else ' CAM A')
        channel_b=voice(self.project,'B')
        camera_b_active=bool(channel_b and queued_camera_active(self.project,channel_b,t))
        if hasattr(self,'preview_camera_b'):
            self.preview_camera_b.configure(style='UX28.LiveActive.TButton' if camera_b_active else 'UX28.LiveIdle.TButton',
                text=' CAM B ●' if camera_b_active else ' CAM B')
        sharing=False
        for layer in channels(self.project):
            source=mode_at(layer,t)
            asset=self.project.asset(source.get('camera_id','')) if source.get('mode')=='camera' else None
            if asset and asset.kind in ('screen','window'):
                device=asset.metadata.get('device');entry=self.live.camera_sources.get(self.live.camera_key(device)) if device else None
                if entry and entry.camera and entry.camera.state in ('starting','live'):sharing=True;break
        if hasattr(self,'stop_sharing_button'):
            if sharing and not self.global_toolbar.contains(self.stop_sharing_button):self.global_toolbar.add(self.stop_sharing_button,priority=0,pinned=True)
            elif not sharing and self.global_toolbar.contains(self.stop_sharing_button):self.global_toolbar.remove(self.stop_sharing_button)
        camera_starting=bool(getattr(self,'camera_tickets',{}))
        if hasattr(self,'global_camera_button'):
            label='Camera…' if camera_starting else ('Camera ON' if camera_live else 'Camera')
            if self.global_camera_button.cget('text')!=label:self.global_camera_button.configure(text=label)
        rid=source_id(self.last_microphone_device);route=self.project.extra.get('sound_routes',{}).get(rid,default_route(rid,'Microphone'))
        state=self.live.source_states().get(rid,{}).get('state') if hasattr(self,'live') else None
        mic_on=bool(route.get('enabled',False) and state in ('starting','live'))
        if hasattr(self,'preview_microphone'):
            self.preview_microphone.configure(style='UX28.MicActive.TButton' if mic_on else 'UX28.MicIdle.TButton',
                text=' MIC ●' if mic_on else ' MIC')
        if hasattr(self,'global_mic_button'):
            label='Mic…' if state=='starting' else ('Mic ON' if mic_on else 'Mic')
            if self.global_mic_button.cget('text')!=label:self.global_mic_button.configure(text=label)
        if hasattr(self,'undo_button'):
            self.undo_button.configure(state='normal' if self.history.undo_stack else 'disabled')
            self.redo_button.configure(state='normal' if self.history.redo_stack else 'disabled')
        if not self.mutating:
            scope=load_intent(self.project).get('global_randomise_scope','all')
            self.randomise_label.set('Randomise '+scope)
        if hasattr(self,'visual_mix'):self.visual_mix.refresh()
        if hasattr(self,'audio_now') and hasattr(self,'queue_deck'):self.audio_now.set(self.queue_deck.audio_now.get())
        self.refresh_record_controls()

    def command_button(self,parent,command_id,**kwargs):
        """Create one Tk projection of a registry command."""
        definition=self.commands.get(command_id)
        kwargs.setdefault('text',definition.label)
        button=ttk.Button(parent,command=lambda cid=command_id:self.commands.invoke(cid),**kwargs)
        button.command_id=command_id
        if definition.help:self.add_tip(button,definition.help)
        return button

    def _menu_command(self,menu,command_id,label=None):
        d=self.commands.get(command_id);menu.add_command(label=label or d.label,accelerator=d.shortcut,command=lambda cid=command_id:self.commands.invoke(cid))
    def open_panel_help(self,panel_id):
        from help_browser import show
        return show(self,'panel.'+panel_id.split('.')[-1]+'.toggle')
    def build_menu(self):
        # Project and file operations live here; the performance bar stays playable.
        menu=tk.Menu(self,tearoff=False);self.application_menu=menu;self.configure(menu='')
        self._menu_command(menu,'project.new','New Project')
        self._menu_command(menu,'project.open','Open Project…')
        self._menu_command(menu,'project.example','Open Example…')
        menu.add_separator()
        self._menu_command(menu,'project.save','Save Project')
        self._menu_command(menu,'project.save-as','Save Project As…')
        menu.add_command(label='Save Current FX Rack to Library…',command=lambda:self.deck.save_rack())
        menu.add_separator()
        imp=tk.Menu(menu,tearoff=False)
        menu.add_cascade(label='Import',menu=imp)
        for cid in ('project.import-media','project.import-folder','project.inspect-imports','project.locate-missing'):
            self._menu_command(imp,cid)
        self._menu_command(menu,'project.export','Export Video…')
        self._menu_command(menu,'project.drafts','Project Drafts / Recovery…')
        menu.add_separator()
        menu.add_command(label='Media & Sources…',command=lambda:self.sidebar.open_browser('A','files'))
        menu.add_command(label='Visual Queues…',command=lambda:(self.sidebar.set_open('A',True),self.sidebar.signal('A')))
        menu.add_command(label='Effects…',command=lambda:self.open_effects_context('Master'))
        menu.add_separator()
        menu.add_command(label='Preferences…',command=lambda:self.open_preferences('general'))
        menu.add_command(label='Output Settings…',command=lambda:self.open_preferences('output'))
        menu.add_command(label='Recording Settings…',command=lambda:self.open_preferences('recording'))
        menu.add_command(label='Input & Media Defaults…',command=lambda:self.open_preferences('devices'))
        menu.add_command(label='Appearance…',command=lambda:self.open_preferences('appearance'))
        menu.add_command(label='Theme Studio…',command=self.open_theme_studio)
        menu.add_command(label='Welcome…',command=lambda:self.show_startup_window(True))
        menu.add_command(label='Check for Updates…',command=self.check_for_updates)
        menu.add_command(label='Check for Updates…',command=self.check_for_updates)
        menu.add_command(label='Support Neospector…',command=self.open_support_site)
        self._menu_command(menu,'project.diagnostics','Diagnostics…')
        self._menu_command(menu,'project.exit','Exit')
        return
        edit=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Edit',menu=edit)
        for cid in ('edit.undo','edit.redo','edit.split','edit.replace','edit.insert-before','edit.insert-after','edit.duplicate','edit.delete'):self._menu_command(edit,cid)
        add_menu=tk.Menu(edit,tearoff=False);edit.add_cascade(label='Add',menu=add_menu);self._menu_command(add_menu,'edit.add-text');self._menu_command(add_menu,'edit.add-shape')
        view=tk.Menu(menu,tearoff=False);menu.add_cascade(label='View',menu=view)
        view.add_command(label='Show / hide Media desk',command=lambda:self.shell.toggle_media())
        self._menu_command(view,'programme.focus','Focus Output / Restore')
        view.add_command(label='Focus Rack / Restore',command=lambda:self.shell.maximize('Rack'))
        self._menu_command(view,'timing.precision')
        view.add_command(label='Reset proportions',command=self.reset_workspace)
        self.workspace_menu=tk.Menu(view,tearoff=False) # retained integration handle
        inputs=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Inputs',menu=inputs)
        inputs.add_command(label='Camera / screen → Visual A…',command=lambda:self.open_channel_camera('A'))
        inputs.add_command(label='Screen / application window…',command=self.open_visual_source)
        inputs.add_command(label='Microphone and audio routing…',command=lambda:self.shell.show('Audio'))
        output=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Output',menu=output)
        for cid in ('record.toggle','record.settings','record.sequence','project.export','output.viewer','programme.settings'):self._menu_command(output,cid)
        output.add_command(label='Conductor…',command=lambda:self.shell.show('Conductor'))
        appearance=tk.Menu(view,tearoff=False);view.add_cascade(label='Appearance',menu=appearance)
        for cid in ('theme.studio','theme.import','help.startup'):self._menu_command(appearance,cid)
        view.add_separator();self._menu_command(view,'help.quick-guide')
        help_menu=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Help',menu=help_menu)
        self._menu_command(help_menu,'help.quick-guide');self._menu_command(help_menu,'help.startup')
        help_menu.add_separator()
        from guided_lessons import LESSONS,RECIPES,BY_ID
        for area in dict.fromkeys(item.area for item in LESSONS):
            family=tk.Menu(help_menu,tearoff=False);help_menu.add_cascade(label=area,menu=family)
            for item in LESSONS:
                if item.area==area:family.add_command(label=item.title,command=lambda lid=item.id:self.guides.open(lid))
        recipes=tk.Menu(help_menu,tearoff=False);help_menu.add_cascade(label='Quick recipes',menu=recipes)
        for name,ids in RECIPES.items():
            sub=tk.Menu(recipes,tearoff=False);recipes.add_cascade(label=name,menu=sub)
            for lid in ids:sub.add_command(label=BY_ID[lid].title,command=lambda i=lid:self.guides.open(i))

    def open_preferences(self,page='general'):
        from preferences_ui import show
        return show(self,page)

    def open_support_site(self):
        from family_chrome import SUPPORT_URL
        import webbrowser
        return webbrowser.open(SUPPORT_URL)

    def check_for_updates(self):
        controller=getattr(self,'update_controller',None)
        if controller is None:return self.update_status('Update checks are not available during initialisation')
        return controller.check(silent=False)

    def auto_import_folder_if_enabled(self):
        """Opt-in, bounded flat scan for an otherwise empty project.

        Never scans subfolders or symlinks, never starts capture and never
        imports over an existing project or an in-progress import.
        """
        if not self.auto_import_media or self.importing or any(layer.clips for layer in self.project.layers):return False
        folder=Path(self.last_import_folder).expanduser()
        if not folder.is_dir():return False
        suffixes={'.mp4','.mov','.mkv','.webm','.avi','.png','.jpg','.jpeg','.gif','.webp','.tif','.wav','.mp3','.flac','.m4a','.ogg'}
        try:
            paths=[str(p) for p in sorted(folder.iterdir()) if p.is_file() and not p.is_symlink() and p.suffix.lower() in suffixes]
        except OSError:return False
        if len(paths)>200:
            self.update_status('Default media folder has more than 200 supported files. Import manually to choose a subset.');return False
        if paths:self.import_files(paths);return True
        return False

    def _record_profile_labels(self):
        return {'Web · H.264 / AAC':'web','Small file · H.264 / AAC':'small','Lossless master · FFV1 / PCM':'master'}
    def _record_resolution(self):
        value=str(self.recording_settings.get('resolution','Programme'))
        if value=='Programme':return self.programme_size()
        import re
        match=re.search(r'(\d+)\D+(\d+)',value)
        if not match:return self.programme_size()
        w,h=(int(match.group(1)),int(match.group(2)))
        return (max(64,w),max(64,h))
    def prepare_output_recording(self):
        from media_engine import EXPORT_PROFILES
        import re
        profile=self.recording_settings.get('profile','web')
        if profile not in ('web','small','master'):profile='web'
        folder=Path(self.recording_settings.get('directory') or (Path.home()/'Videos'/'Neospector')).expanduser()
        try:folder.mkdir(parents=True,exist_ok=True)
        except OSError as exc:
            self.update_status('Recording destination: '+str(exc));return None
        raw=(self.recording_settings.get('name') or self.project.name or 'Neospector Recording').strip()
        stem=re.sub(r'[\/:*?"<>|\x00-\x1f]+','-',raw).strip(' .-') or 'Neospector Recording'
        ext=EXPORT_PROFILES[profile]['extension'];candidate=folder/(stem+ext);n=2
        while candidate.exists():candidate=folder/f'{stem} {n}{ext}';n+=1
        fps=max(1,min(60,int(self.recording_settings.get('fps',20))))
        return {'path':candidate,'profile':profile,'size':self._record_resolution(),'fps':fps}
    def open_record_settings(self):
        return self.open_preferences('recording')

    def refresh_record_controls(self):
        if not hasattr(self,'record_button'):return
        recording=bool(getattr(self,'output_recording',None));busy=bool(getattr(self,'output_busy',False))
        self.record_button.configure(text='Finalising…' if busy else '■ Stop Recording' if recording else '● Record',state='disabled' if busy else 'normal')
        self.record_disclosure.configure(state='disabled' if busy else 'normal')
    def record_programme(self):
        if self.output_busy:return self.update_status('Finishing recording; Programme continues…')
        if self.output_recording:return self.toggle_output_record()
        if self.reviewing:return self.update_status('Return to Programme before recording new output.')
        self._recording_kind='manual';self._recording_sequence_label='';return self.toggle_output_record()
    def _visual_queue_duration(self,role):
        from instrument_model import voice
        layer=voice(self.project,role);return max((c.end for c in layer.clips),default=0.)
    def _current_visual_duration(self,role):
        from instrument_model import voice
        from queue_model import current,queue_position
        layer=voice(self.project,role);clip=current(layer,self.programme_time())
        return max(0.,clip.end-queue_position(layer,self.programme_time())) if clip else 0.
    def _music_queue_duration(self):
        from music_queue import items
        return max((e['start']+e['duration'] for e in items(self.project)),default=0.)
    def _current_music_duration(self):
        from music_queue import items
        from queue_policies import music_position
        q=music_position(self.project,self.programme_time());event=next((e for e in items(self.project) if e['start']<=q<e['start']+e['duration']),None)
        return max(0.,event['start']+event['duration']-q) if event else 0.
    def _start_sequence_recording(self,seconds,label):
        try:seconds=float(seconds)
        except (TypeError,ValueError):return self.update_status('Choose a valid recording duration.')
        if seconds<=0:return self.update_status(label+' has no playable duration.')
        self._recording_kind='sequence';self._recording_sequence_label=label
        self.record_next_duration(seconds)
        if self.output_recording:
            self.refresh_record_controls();self.update_status(f'Recording sequence · {label} · up to {seconds:.1f}s. Press Record Sequence again to end early.')
        else:
            self._recording_kind=None;self._recording_sequence_label='';self.refresh_record_controls()
    def record_sequence_action(self,event=None):
        if self.output_busy:return self.update_status('Finishing recording; Programme continues…')
        if self.output_recording:
            if self._recording_kind=='sequence':return self.toggle_output_record()
            return self.update_status('Stop the current recording before starting a Record Sequence capture.')
        if self.reviewing:return self.update_status('Return to Programme before recording a sequence.')
        menu=tk.Menu(self,tearoff=False)
        from visual_channels import channels
        for layer in channels(self.project):
            role=layer.extra.get('voice');duration=self._visual_queue_duration(role)
            if duration>0:menu.add_command(label=f'Queue {role} · one cycle ({duration:.1f}s)',command=lambda r=role,d=duration:self._start_sequence_recording(d,f'Queue {r}'))
        music=self._music_queue_duration()
        if music>0:menu.add_command(label=f'Music queue · one cycle ({music:.1f}s)',command=lambda d=music:self._start_sequence_recording(d,'Music queue'))
        current_added=False
        for layer in channels(self.project):
            role=layer.extra.get('voice');duration=self._current_visual_duration(role)
            if duration>0:
                if not current_added:menu.add_separator();current_added=True
                menu.add_command(label=f'Current {role} media · remaining ({duration:.1f}s)',command=lambda r=role,d=duration:self._start_sequence_recording(d,f'Current {r} media'))
        current_music=self._current_music_duration()
        if current_music>0:
            if not current_added:menu.add_separator();current_added=True
            menu.add_command(label=f'Current Music item · remaining ({current_music:.1f}s)',command=lambda d=current_music:self._start_sequence_recording(d,'Current Music item'))
        menu.add_separator()
        def manual():
            value=simpledialog.askfloat('Record Sequence','Duration in seconds',parent=self,minvalue=.1,maxvalue=86400)
            if value:self._start_sequence_recording(value,'Manual duration')
        menu.add_command(label='Manual duration…',command=manual)
        self.popup_menu(menu,self.record_disclosure,event)
    def refresh_programme_toolbar(self):
        if not hasattr(self,'return_programme_button'):return
        if self.reviewing and not self.return_programme_button.winfo_manager():self.return_programme_button.pack(side='left',padx=8)
        elif not self.reviewing:self.return_programme_button.pack_forget()
        self.refresh_record_controls()

    def refresh_all(self):
        super().refresh_all()
        library=getattr(self,'module_library',None)
        if library is not None and library.conductor_selection:library.refresh()

    def refresh_library(self):
        super().refresh_library()
        if hasattr(self,'project_media_folder'):
            self.project_media_folder.refresh_assets()
            # Update the actual visible shared shelf on the same transaction,
            # not only when a tab change happens to cause a fresh mount.
            if hasattr(self,'sidebar'):self.sidebar.source_shelf.media.refresh(force=True)
            self.library=self.project_media_folder.browser
            self.search=self.library.query

    def refresh_module_library(self):
        if hasattr(self,'module_library'):self.module_library.refresh(force=True)
    def toggle_right_lower(self):
        """Compatibility action for the new independent Radio edge section."""
        return self.sidebar.toggle('Music')

    def _ux13_rack_size(self,event=None):
        """At narrow widths, catalogue and rack occupy the same space in turn."""
        if not getattr(self,'library_open',False):return
        narrow=self.rack_split.winfo_width()<560
        panes=tuple(str(p) for p in self.rack_split.panes())
        primary=str(self.rack_primary)
        if narrow and primary in panes:
            self.rack_split.forget(self.rack_primary)
        elif not narrow and primary not in panes:
            if self.rack_split.panes():self.rack_split.insert(0,self.rack_primary,weight=3)
            else:self.rack_split.add(self.rack_primary,weight=3)
        # No output/media mutation; this is solely the presentation of ingredients.

    def toggle_module_library(self,open_=None):
        """Direct rack-owned catalogue; at narrow sizes swap views, not pinch pedals."""
        wanted=not self.library_open if open_ is None else bool(open_)
        if wanted==self.library_open:return wanted
        self.library_open=wanted
        if wanted:
            self.rack_split.add(self.module_library_host,weight=2)
            self._ux13_rack_size()
            self.module_library.refresh(force=True)
        else:
            self.rack_split.forget(self.module_library_host)
            if str(self.rack_primary) not in tuple(str(p) for p in self.rack_split.panes()):
                if self.rack_split.panes():self.rack_split.insert(0,self.rack_primary,weight=3)
                else:self.rack_split.add(self.rack_primary,weight=3)
        self.deck.library_button.configure(text='▥ Modules ◂' if wanted else '▥ Modules ▸')
        self.after_idle(lambda:self.deck.relayout() if self.deck.winfo_exists() else None)
        return wanted

    def select_right_tray(self,name):
        """Compatibility entry point for older actions; no shared tabs exist."""
        if name=='Modules':
            self.toggle_module_library(True)
            return self.module_library_host
        if name in ('Media','Project Media'):
            self.shell.show('Queues')
            page=self.queue_deck.pages['A']
            if not page.browser_open:page.toggle_browser()
            return page.source_browser
        raise ValueError('Unknown workspace collection')

    def close_module_builder(self):
        if not hasattr(self,'module_builder_host'):return
        builder=self.module_builder
        self.module_builder=None
        if builder is not None and builder.winfo_exists():builder.destroy()
        self.module_builder_host.pack_forget()
        if self.module_library.winfo_exists():
            self.module_library.pack(fill='both',expand=True)
            self.module_library.refresh(force=True)

    def open_module_builder(self,deck,rack,group_fx=None):
        from playable_rack import ModuleBuilder
        self.select_right_tray('Modules')
        self.close_module_builder()
        self.module_library.pack_forget()
        self.module_builder_host.pack(fill='both',expand=True)
        bar=ttk.Frame(self.module_builder_host,padding=5);bar.pack(fill='x')
        ttk.Button(bar,text='← Modules',command=self.close_module_builder).pack(side='left')
        ttk.Label(bar,text='GROUP BUILDER',style='PlayerName.TLabel').pack(side='right')
        self.module_builder=ModuleBuilder(self,deck,rack,group_fx=group_fx,parent=self.module_builder_host,on_close=self.close_module_builder)
        self.after_idle(self.module_builder.focus_set)
        return self.module_builder

    def show_module_library(self):
        if getattr(self,'module_builder',None) is not None:self.close_module_builder()
        if hasattr(self,'module_library'):self.module_library.finish_conductor_selection()
        if not hasattr(self,'module_library'):return False
        self.select_right_tray('Modules')
        def focus():
            frame=self.shell.frames['panel.library']
            self.module_library.focus_library()
        self.after_idle(focus);return True
    def module_library_drop_index(self,x_root,y_root):
        cell=self.deck.selected_cell() if hasattr(self,'deck') else None
        return cell.insertion_index_at(x_root,y_root) if cell else None
    def insert_module_from_library(self,fx,name,index=None,entry_type='Base'):
        cell=self.deck.selected_cell() if hasattr(self,'deck') else None
        if cell is None:return self.update_status('Choose a rack target before adding a module.')
        rack,owner=cell.target()
        if rack is None or not self.can_edit(owner):return False
        if cell.adapter.scope!='Transition':
            from module_engine import compile_rack
            if any(e.kind.startswith('transition_') for e in compile_rack([fx])):
                return self.update_status('Transition animation modules belong only to the Transition rack')
        if cell.adapter.scope=='Transition':
            from ux16_transitions import validate_transition_rack
            try:validate_transition_rack([*rack,fx])
            except ValueError as exc:return self.update_status(str(exc))
        # Preserve saved/factory authoring; only a lone base effect needs a useful first-play value.
        if entry_type=='Base':
            from module_engine import randomise_rack
            seed=int(self.project.extra.get('rack_seed',0))+1;randomise_rack([fx],seed,source='reaction_mix',rebuild=False);self.project.extra['rack_seed']=seed
        from module_engine import expose_group_front
        if fx.kind=='module':expose_group_front(fx)
        pos=len(rack) if index is None else max(0,min(len(rack),int(index)));context=__import__('rack_editing').RackContext.capture(cell)
        def apply(r,module,o):
            trial=r[:];trial.insert(pos,fx);compile_rack(trial)
            if cell.adapter.scope=='Transition':
                from ux16_transitions import validate_transition_rack
                validate_transition_rack(trial)
            r[:]=trial
        from module_engine import compile_rack
        if cell.run_edit(context,'Add '+str(name),apply):
            cell.selected_fx.clear();cell.selected_fx.add(fx.id);cell.refresh(True);self.deck._sync_selected(cell);self.deck.refresh_toolbar_state();self.update_status('Added '+str(name)+(' at rack position '+str(pos+1) if index is not None else '.'))
            from attention_feedback import pulse
            shell=cell.card_parts.get(fx.id,(None,))[0]
            if shell is not None:pulse(shell,color=shell.face[2])
            if self.library_open and self.rack_split.winfo_width()<560:self.toggle_module_library(False)
            self.refresh_effects_badges()
            return True
        return False

    def _panel_frame(self,name):return self.shell.frames[self.shell.resolve(name)]
    def toggle_panel(self,name,force=None):
        pid=self.shell.resolve(name)
        if force is False:return self.shell.collapse(pid)
        if force is True:return self.shell.show(pid)
        return self.shell.show(pid) if self.shell.state.panels[pid]['presentation']=='collapsed' else self.shell.collapse(pid)
    def move_panel(self,name,zone):return self.shell.dock(name,zone)
    def float_panel(self,name):return self.shell.float_panel(name)
    def redock_panel(self,name):return self.shell.dock(name)
    def _floating_close(self,name):return self.shell.collapse(name)
    def toggle_panel_maximize(self,name,force=None):return self.shell.maximize(name)
    def restore_maximized_panel(self):
        if not self.shell.state.maximized:return False
        self.shell.state.maximized='';self.shell.changed();return True
    def select_workspace_tab(self,region,name):return self.shell.select_tab(region,name)
    def toggle_tab_group(self,region):
        if region in self.shell.state.tabs:return self.shell.ungroup(region)
        names={'left':('Library','Queues'),'right':('Conductor','Audio'),'bottom':('Queues','Rack'),'centre':('Programme','Rack')}.get(region)
        if not names:return False
        self.shell.dock(names[0],region);return self.shell.tab_with(names[1],names[0])
    def capture_workspace_state(self,name='Custom'):return self.shell.snapshot(name)
    def apply_workspace_state(self,state):
        self.shell.apply(state);self.workspace_name.set(state.name);self.workspace_locked.set(state.locked)
        if hasattr(self,'library_modes'):self.select_library_mode(state.library_mode)
        self.save_preferences()

    def switch_workspace(self,name):
        try:self.workspace_controller.switch(name)
        except KeyError:return False
        self.workspace_name.set(name);self.update_status('Workspace · '+name);return True
    def next_workspace(self):
        names=self.workspace_controller.names();cur=self.workspace_name.get();i=names.index(cur) if cur in names else -1;return self.switch_workspace(names[(i+1)%len(names)])
    def toggle_workspace_lock(self):
        value=not self.workspace_locked.get();self.workspace_locked.set(value);self.workspace_controller.set_locked(value);self.workspace_lock_changed();self.save_preferences();return value
    def workspace_lock_changed(self):
        locked=bool(self.workspace_locked.get())
        if hasattr(self,'workspace_lock_button'):self.workspace_lock_button.configure(text='🔒' if locked else '⌑')
        self.update_status('Workspace locked.' if locked else 'Workspace unlocked.')
    def save_workspace_as(self):
        name=simpledialog.askstring('Save Workspace As','Workspace name',parent=self)
        if not name:return False
        try:clean=self.workspace_controller.save_as(name)
        except ValueError as exc:return self.update_status(str(exc))
        self.workspace_name.set(clean);self.workspace_combo.configure(values=self.workspace_controller.names());self.save_preferences();self.update_status('Workspace saved · '+clean);return True
    def rename_workspace(self):
        current=self.workspace_name.get()
        if current in DEFAULT_WORKSPACES:return self.update_status('Built-in workspaces cannot be renamed. Use Save Workspace As… to duplicate one.')
        name=simpledialog.askstring('Rename Workspace','New workspace name',initialvalue=current,parent=self)
        if not name:return False
        try:clean=self.workspace_controller.rename(name)
        except ValueError as exc:return self.update_status(str(exc))
        self.workspace_name.set(clean);self.workspace_combo.configure(values=self.workspace_controller.names());self.save_preferences();self.update_status('Workspace renamed · '+clean);return True
    def delete_workspace(self):
        current=self.workspace_name.get()
        if current in DEFAULT_WORKSPACES:return self.update_status('Built-in workspaces cannot be deleted.')
        if not messagebox.askyesno('Delete Workspace',f'Delete custom workspace “{current}”?',parent=self):return False
        self.workspace_controller.delete_custom();self.workspace_name.set(self.workspace_controller.state.name);self.workspace_combo.configure(values=self.workspace_controller.names());self.save_preferences();self.update_status('Custom workspace deleted.');return True
    def reset_workspace(self):
        state=self.workspace_controller.reset();self.workspace_name.set(state.name);self.workspace_combo.configure(values=self.workspace_controller.names());self.save_preferences();self.update_status('Workspace reset · '+state.name);return True
    def toggle_focus_output(self):return self.shell.maximize('panel.programme')

    def toggle_precision(self):
        if self.precision_visible.get():return self.hide_precision()
        self.precision_visible.set(True);self.precision_window.deiconify();self.precision_window.lift();self.timeline.schedule();self.timeline.zoom_fit()
    def hide_precision(self):self.precision_visible.set(False);self.precision_window.withdraw()
    def toggle_queue_conductor(self):self.conductor.toggle_details()
    def toggle_conductor_mini(self):self.conductor.toggle_details()
    def show_conductor_mini(self):self.conductor.refresh()
    def layout_preferences(self):return self.shell.snapshot().to_dict()
    def load_layout(self,pref):
        if not hasattr(self,'shell'):return
        migrated=migrate_preferences(pref)
        self.workspace_controller=WorkspaceController(self,migrated)
        self.apply_workspace_state(self.workspace_controller.state)
        if not pref.get('inline_racks'):
            self.shell.state.sizes['bottom']=max(560,self.shell.state.sizes['bottom']);self.shell.schedule()
    def save_preferences(self):
        if self.test_mode or not hasattr(self,'queue_deck'):return
        try:
            # Preserve unrelated preference extensions instead of rebuilding a lossy document.
            data=migrate_preferences(self.read_preferences())
            data.update(auto_check_updates=bool(getattr(self,'auto_check_updates',True)),
                        update_feed_url=str(getattr(self,'update_feed_url','')),
                        theme_name=self.theme_name.get(),tooltips=self.tooltips_enabled.get(),show_startup=self.show_startup.get(),geometry=self.geometry(),
                        preview_quality=self.viewport.quality.get(),camera_device=self.last_camera_device,microphone_device=self.last_microphone_device,
                        import_folder=self.last_import_folder,recent_import_folders=self.recent_import_folders,recording=dict(self.recording_settings),
                        recent_projects=self.recent_projects,auto_import_media=self.auto_import_media,
                        ux7_lesson_progress=getattr(self,'ux7_lesson_progress',{}),
                        module_library_view=self.module_library.view.get(),
                        inline_racks={},
                        rack_layout=self.deck.serialize_layout(),queue_columns={r:v.get() for r,v in self.queue_deck.visibility.items()})
            data.update(self.workspace_controller.serialize())
            path=self.cfg/'preferences-neospector-omne-r5.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(path)
        except (OSError,ValueError,tk.TclError) as exc:self.log('Preference save: '+str(exc))
    def bind_shortcuts(self):
        """Keyboard is another Command Registry projection; text fields retain typing."""
        mapping={
            '<Control-s>':'project.save','<Control-Shift-S>':'project.save-as','<Control-o>':'project.open','<Control-n>':'project.new',
            '<Control-z>':'edit.undo','<Control-y>':'edit.redo','<Control-Shift-Z>':'edit.redo','<space>':'transport.play','<Key-m>':'rack.mutate',
            '<Key-s>':'edit.split','<Delete>':'edit.delete','<Control-Tab>':'workspace.next','<Control-Shift-m>':'panel.rack.maximize',
        }
        for key,cid in mapping.items():self.bind_all(key,lambda e,c=cid:self.shortcut(e,lambda:self.commands.invoke(c)))
        self.bind_all('<Key-i>',lambda e:self.shortcut(e,lambda:self.set_range('in')));self.bind_all('<Key-o>',lambda e:self.shortcut(e,lambda:self.set_range('out')))
        self.bind_all('<Left>',lambda e:self.shortcut(e,lambda:self.set_playhead(self.playhead-1/self.project.fps)));self.bind_all('<Right>',lambda e:self.shortcut(e,lambda:self.set_playhead(self.playhead+1/self.project.fps)))
        self.bind_all('<Escape>',self.workspace_escape)
        self.bind_all('<F1>',lambda _e:(self.quick_guide(),'break')[1])

    def refresh_source_choices(self,periodic=False):
        if hasattr(self,'conductor'):self.conductor.refresh(refresh_pools=not periodic)
        if hasattr(self,'programme_toolbar'):self.refresh_programme_toolbar()
        if hasattr(self,'source_strip'):self.source_strip.refresh()
        if hasattr(self,'overview'):self.overview.schedule()
        if hasattr(self,'empty_preview'):self.refresh_empty_preview()
    def refresh_empty_preview(self):
        active=any(l.enabled and l.clips for l in self.project.layers) or getattr(self.live.camera,'state','stopped')=='live'
        if not active and not self.reviewing:self.empty_preview.place(relx=.5,rely=.5,anchor='center')
        else:self.empty_preview.place_forget()
    def end_gesture(self):
        from input_gestures import finish_active_input
        if finish_active_input(self):return
        if self.gesture and self.gesture.get('kind')=='conductor-policy':return self.conductor.end()
        return super().end_gesture()
    def cancel_gesture(self):
        if self._drag_media:self.clear_media_drag();return
        from input_gestures import finish_active_input
        if finish_active_input(self,cancel=True):return
        if self.gesture and self.gesture.get('kind')=='conductor-policy':return self.conductor.cancel()
        return super().cancel_gesture()
    def queue_transition(self,role,cid):
        from queue_transition_ui import open_queue_transition
        return open_queue_transition(self,role,cid)
    def policy_changed(self):
        self.dirty=True;self.revision+=1;self.update_title()
        if self._autosave_after:
            try:self.after_cancel(self._autosave_after)
            except tk.TclError:pass
        self._autosave_after=self.after(2000,self.write_recovery)
        self.update_status('Conductor policy saved · applies to the next permitted choices')
    def evolve_next(self):
        if self.gesture:return
        # Explicit composition cues own Rack when present. Otherwise the existing
        # interval-based rack evolution remains the default effects instrument.
        options=self.programme_project().conductor.extra;present='evolve_treatment' in options;value=options.get('evolve_treatment')
        try:
            composition=options.get('composition_queue')
            if isinstance(composition,dict) and composition.get('items'):options['evolve_treatment']=False
            return super().evolve_next()
        finally:
            if present:options['evolve_treatment']=value
            else:options.pop('evolve_treatment',None)
    def source_intent(self,project=None):
        p=project if project is not None else self.project;intent=load_intent(p)
        for key in ('music','visuals'):
            choice=intent[key];album=choice.get('album_id')
            if album and album!='all':
                local=p.extra.get('library_albums',{}).get(album)
                choice['pool_ids']=list(local['ids']) if local else sorted(self.catalog.member_ids(album)&set(p.assets))
        return intent
    def popup_menu(self,menu,anchor,event=None):
        from contextual_surface import post_native_menu
        return post_native_menu(self,menu,anchor,event)
    def init_drop_support(self):
        super().init_drop_support()
        for browser in self.media_browsers.values():self.register_drop(browser.canvas,lambda:self.album.get())
    def place_media(self,ids,role,action='queue'):
        ids=self.ensure_project_media(ids)
        if not ids:return self.update_status('Choose material in the Library first.')
        if action=='now' and all(self.project.asset(i).kind=='audio' for i in ids):role='Music'
        if role=='auto':
            from visual_channels import strongest_channel
            try:role=strongest_channel(self.project,self.playhead,self.signal_evaluator())
            except ValueError as exc:return self.update_status(str(exc))
        eligible=[i for i in ids if (self.project.asset(i).kind=='audio' or self.project.asset(i).metadata.get('has_audio'))] if role=='Music' else [i for i in ids if self.project.asset(i).kind!='audio']
        if len(eligible)!=len(ids):return self.update_status('Incompatible drop · choose Music for audio or a visual channel for pictures.')
        if action=='queue':
            self.queue_sound_selected(ids) if role=='Music' else self.queue_selected(role,asset_ids=ids)
            self.queue_deck.show_role(role)
            if hasattr(self,'sidebar'):self.sidebar.signal(role)
            return
        from instrument_model import voice
        from queue_model import append_assets,current,ordered,take_next,queue_position
        from music_queue import items,take,store,layout
        from audio_bus import add_sound
        now=self.programme_time() if self.playing and not self.reviewing else self.playhead
        def apply():
            if role=='Music':
                existing=items(self.project)
                future=[e for e in existing if e['start']>now]
                if action=='next' and any(e.get('locked') or e.get('timing_locked') or e.get('pinned') for e in future):
                    raise ValueError('A future Music item is pinned or timing-locked. Unpin it before inserting a new next choice.')
                boundary=max([now]+[e['start']+e['duration'] for e in existing if e['start']<=now])
                if action=='now':boundary=max([now]+[e['start']+e['duration'] for e in existing])
                created=[]
                for aid in ids:
                    event=add_sound(self.project,aid,start=boundary)
                    event['pinned']=True;event['manual']=True;created.append(event)
                    boundary+=event['duration']
                if action=='now':
                    store(self.project,existing+created);take(self.project,created[0]['id'],now)
                else:
                    # The current/history events are byte-for-byte retained. Only
                    # the explicitly edited upcoming order is laid out again.
                    prefix=[e for e in existing if e['start']<=now]
                    boundary=max([now]+[e['start']+e['duration'] for e in prefix])
                    store(self.project,prefix+layout(created+future,boundary))
            else:
                layer=voice(self.project,role)
                on=current(layer,now)
                # Insertion respects locked transitions and cannot move a protected boundary.
                created=append_assets(self.project,layer.id,ids,after=on.id if action=='next' and on else None)
                for c in created:c.manual=True;c.extra['playable_pin']=True
                if action=='now':
                    take_next(layer,now,created[0].id)
                    intent=load_intent(self.project);intent['enabled_roles']=list(dict.fromkeys(intent['enabled_roles']+[role]));self.project.extra['playable_intent']=intent;layer.enabled=True
            return created
        created=self.transaction(('Play now' if action=='now' else 'Reserve next eligible choice')+' · '+role,apply)
        if created is None:return
        self.queue_deck.show_role(role);self.queue_deck.refresh(True)
        if hasattr(self,'sidebar'):self.sidebar.signal(role)
        if action=='now' and not self.playing and not self.reviewing:self.play_assigned_media()
        if role=='Music':self.configure_sound_sources();self.prepare_sound_analysis()
        if action=='next':
            name=self.project.asset(ids[0]).name;self.conductor.next_text.set(name+' · reserved in '+role+' queue')
            self.update_status('Reserved '+name+' · '+role+' · current playback and Conductor power unchanged')
    def play_assigned_media(self):
        # A direct placement is not a request to fill any other empty queue.
        if not self.playing:
            from instrument_app import InstrumentApp
            InstrumentApp.toggle_play(self);self.play_button.configure(text='Ⅱ PAUSE')
    def settings(self):
        try:return normalise_settings(self.project.extra.get('randomise_settings',{}))
        except ValueError:return normalise_settings()
    def open_randomise(self,scope='all',anchor=None,role=None):
        if scope in ('rack','mutate'):
            self.shell.show('Rack')
            return self.deck.toggle_variation_options(True)
        old=self.randomise_popup
        if old and old.winfo_exists():
            self.contextual_surfaces.dismiss(('randomise',id(old)))
            if old.winfo_exists():old.destroy()
            self.randomise_popup=None;return
        w=tk.Toplevel(self);self.randomise_popup=w;w.title('Randomise · '+scope.title());w.transient(self);w.resizable(False,False)
        popup_key=('randomise',id(w))
        def close_popup():
            self.contextual_surfaces.forget(popup_key)
            if self.randomise_popup is w:self.randomise_popup=None
            try:
                if w.winfo_exists():w.destroy()
            except tk.TclError:pass
        w.protocol('WM_DELETE_WINDOW',close_popup)
        box=ttk.Frame(w,padding=12);box.pack(fill='both',expand=True)
        ttk.Label(box,text='RANDOMISE '+({'rack':'MODULES','queues':'QUEUES','conductor':'CONDUCTOR','mutate':'MUTATION'}.get(scope,'PERFORMANCE')),style='Title.TLabel').pack(anchor='w',pady=(0,6))
        values=self.settings();fields={};field_rows={};target=tk.StringVar(value=role or 'Enabled visual queues')
        def field(key,title,choices=None):
            row=ttk.Frame(box);row.pack(fill='x',pady=4);ttk.Label(row,text=title).pack(side='left',padx=(0,14));v=tk.StringVar(value=str(values[key]));fields[key]=v;field_rows[key]=row
            if key in ('variation','mutation_variation','conductor_variation'):v.set(f'{values[key]*100:g}')
            control=ttk.Combobox(row,textvariable=v,values=choices,state='readonly',width=13) if choices else ttk.Entry(row,textvariable=v,width=10,justify='right')
            control.pack(side='right');return control
        scope_choice=tk.StringVar(value=self.source_intent().get('global_randomise_scope','all'))
        if scope=='all':
            scope_row=ttk.Frame(box);scope_row.pack(fill='x',pady=4);ttk.Label(scope_row,text='Scope').pack(side='left')
            ttk.Combobox(scope_row,textvariable=scope_choice,values=('all','queues','effects'),state='readonly',width=13).pack(side='right')
        if scope in ('queues','all'):
            if scope=='queues':
                row=ttk.Frame(box);row.pack(fill='x',pady=4);ttk.Label(row,text='Target').pack(side='left')
                ttk.Combobox(row,textvariable=target,values=['Enabled visual queues',*[l.extra['voice'] for l in __import__('visual_channels').channels(self.project)],'Music'],state='readonly',width=22).pack(side='right')
            mode_control=field('queue_mode','Length by',['items','seconds','song'])
            field('queue_count','New items per queue')
            field('queue_seconds','Look-ahead seconds')
            def display_length(event=None):
                for key in ('queue_count','queue_seconds'):field_rows[key].pack_forget()
                chosen=fields['queue_mode'].get()
                if chosen in ('items','seconds'):field_rows['queue_count' if chosen=='items' else 'queue_seconds'].pack(fill='x',pady=4,after=field_rows['queue_mode'])
            mode_control.bind('<<ComboboxSelected>>',display_length);display_length()
            ttk.Label(box,text='Current, manual and pinned items stay.\nSeconds measure ahead from now.\nMusic keeps whole tracks and may overshoot.',style='Muted.TLabel').pack(anchor='w',pady=5)
        if scope in ('rack','all'):
            field('module_count','Total modules (1–12)')
            field('variation','Parameter variation (%)')
            ttk.Label(box,text='New: vary from factory settings. Mutate: from current.\n0% = no parameter variation · 100% = full range.\nOnly explicitly locked modules keep their identity.',style='Muted.TLabel').pack(anchor='w',pady=5)
        if scope in ('mutate','rack'):field('mutation_variation','Mutate strength (%)')
        if scope=='conductor':
            field('conductor_variation','Policy variation (%)')
            ttk.Label(box,text='Vary the policy, not power, source targets or devices.\nExisting treatment continues unchanged.',style='Muted.TLabel').pack(anchor='w',pady=5)
        error=tk.StringVar();ttk.Label(box,textvariable=error,wraplength=330,style='Muted.TLabel').pack(fill='x')
        actions=ttk.Frame(box);actions.pack(fill='x',pady=(8,0))
        def apply(mutate=False,save_only=False):
            try:
                raw={k:(float(v.get())/100 if k in ('variation','mutation_variation','conductor_variation') else v.get()) for k,v in fields.items()}
                setting=normalise_settings({**values,**raw})
            except ValueError as exc:error.set(str(exc));return
            close_popup()
            def save_options():
                self.project.extra['randomise_settings']=setting
                if scope=='all':self.project.extra['playable_intent']=dict(self.source_intent(),global_randomise_scope=scope_choice.get())
            if save_only:
                self.transaction('Randomise options',save_options)
                self.deck.random_count.set(str(setting['module_count']));self.deck.random_variation.set(str(setting['variation']*100));self.deck.mutation_variation.set(setting['mutation_variation']*100)
                return
            if scope in ('rack','mutate'):self.apply_rack_randomise(setting,mutate=mutate or scope=='mutate')
            elif scope=='conductor':
                def change():
                    seed=self.project.mutation_seed+1;vary_conductor(self.project.conductor,seed=seed,variation=setting['conductor_variation']);self.project.mutation_seed=seed;self.project.extra['randomise_settings']=setting
                self.transaction('Vary Conductor policy',change)
            else:
                requested=target.get() if scope=='queues' else None
                save_options()
                self.randomise_playable(scope_choice.get() if scope=='all' else 'queues',only_role=requested if requested in ('A','B','C','D','Music') else 'Visuals' if scope=='queues' else None,settings=setting)
        ttk.Button(actions,text='Cancel',command=close_popup).pack(side='left')
        ttk.Button(actions,text='Save options',command=lambda:apply(save_only=True)).pack(side='left',padx=4)
        ttk.Button(actions,text='Mutate' if scope=='mutate' else 'Randomise',style='Accent.TButton',command=apply).pack(side='right')
        w.bind('<Escape>',lambda e:(close_popup(),'break')[1]);w.update_idletasks()
        anchor=anchor or self.randomise_button
        if not anchor.winfo_viewable():anchor=self.global_toolbar.more_button
        x=min(self.winfo_screenwidth()-w.winfo_reqwidth()-10,anchor.winfo_rootx());y=min(self.winfo_screenheight()-w.winfo_reqheight()-30,anchor.winfo_rooty()+anchor.winfo_height()+3)
        w.geometry(f'+{max(0,x)}+{max(0,y)}');w.focus_set()
        self.contextual_surfaces.show(popup_key,w,close_popup,anchors=(anchor,))
    def apply_rack_randomise(self,settings=None,mutate=False,selected=None,seed=None):
        setting=normalise_settings(settings or self.settings());rack,owner=self.deck.target()
        if rack is None:return self.update_status('Choose an output, voice or clip rack first.')
        if not self.can_edit(owner):return
        seed=int(seed if seed is not None else self.project.extra.get('rack_seed',730)+1)
        def apply():
            if mutate:vary_rack(rack,seed=seed,variation=setting['mutation_variation'],selected=selected)
            elif self.deck.scope.get()=='Transition':
                from ux16_transitions import random_transition_rack
                rack[:]=random_transition_rack(rack,seed,setting['module_count'],setting['variation'])
            else:rack[:]=make_rack(rack,seed=seed,count=setting['module_count'],variation=setting['variation'])
            self.project.extra['randomise_settings']=setting;self.project.extra['rack_seed']=seed
        self.transaction('Mutate treatment' if mutate else 'Randomise module rack',apply)
    def new_treatment(self,seed=None):return self.apply_rack_randomise(seed=seed)
    def mutate_treatment(self,selected=None,seed=None):return self.apply_rack_randomise(mutate=True,selected=selected,seed=seed)
    def queue_sound_selected(self,asset_ids=None):
        super().queue_sound_selected(asset_ids)
        if hasattr(self,'queue_deck'):self.queue_deck.show_role('Music')

    def set_audio_tray_open(self,opened):
        if not hasattr(self,'audio_tray_host'):return
        opened=bool(opened)
        if self.audio_tray_open==opened:return
        self.audio_tray_open=opened
        self.sidebar.sections['Music']['open']=opened
        self.sidebar._sync()
        self.sidebar.request_fit()
        self.shell.schedule()

    def toggle_audio_tray(self):
        self.set_audio_tray_open(not self.audio_tray_open)

    def refresh_audio_tray(self):
        if getattr(self,'audio_tray_open',False) and hasattr(self,'sidebar'):
            self.sidebar.request_fit()

    def build_performance_bar(self,root):
        # Two distinct horizontal areas: performance on left, source pairs at
        # the right edge directly above their collapsible right-hand dock.
        row=ttk.Frame(root);row.grid(row=0,column=0,sticky='ew',pady=(0,3))
        row.columnconfigure(0,weight=1)
        self.top_row=row
        top=PriorityToolbar(row,gap=4);self.global_toolbar=top
        top.grid(row=0,column=0,sticky='ew')
        self.top_source_host=ttk.Frame(row)
        self.top_source_host.grid(row=0,column=2,sticky='e',padx=(5,1))
        row.columnconfigure(1,weight=1)
        self.application_button=ttk.Menubutton(top,text='☰ File',width=7,menu=self.application_menu)
        top.add(self.application_button,priority=0,pinned=True)
        self.play_button=self.command_button(top,'transport.play',text='▶ Play',width=8,style='UX21.Play.TButton')
        top.add(self.play_button,priority=0,pinned=True)
        self.record_button=self.command_button(top,'record.toggle',text='● Record',width=9,style='UX21.Record.TButton')
        # Compatibility command target; the visible control belongs to the preview.
        # A real Record button is created in VisualMixStrip.
        self.record_disclosure=self.record_button  # compatibility anchor
        self.master_fx_button=ttk.Button(top,text='Effects',width=9,style='UX21.Effects.TButton',command=self.toggle_main_effects)
        top.add(self.master_fx_button,priority=0,pinned=True)
        self.media_sources_button=ttk.Button(top,text='Media & Sources',width=17,
            style='UX21.Effects.TButton',command=lambda:self.sidebar.close_browser() if self.sidebar._browser_open else self.sidebar.open_browser(getattr(self.sidebar,'_browser_request','A'),self.sidebar.source_shelf.mode))
        top.add(self.media_sources_button,priority=0,pinned=True)
        self.output_viewer_button=self.command_button(top,'output.viewer',text='Output Window ↗',width=17,style='UX21.Output.TButton')
        # Output Viewer is also projected next to Focus in the preview.
        self.undo_button=self.command_button(top,'edit.undo',text='↶',width=3)
        top.add(self.undo_button,priority=10)
        self.redo_button=self.command_button(top,'edit.redo',text='↷',width=3)
        top.add(self.redo_button,priority=12)
        # Retained command/service adapters are intentionally not displayed.
        self.workspace_combo=ttk.Combobox(top,textvariable=self.workspace_name,values=self.workspace_controller.names(),state='readonly',width=9)
        self.workspace_combo.bind('<<ComboboxSelected>>',lambda e:self.commands.invoke('workspace.switch'))
        self.randomise_button=self.command_button(top,'rack.randomise',text='Randomise')
        self.randomise_disclosure=self.randomise_button
        self.global_camera_button=self.command_button(top,'input.camera.toggle',text='Camera')
        self.camera_disclosure=self.global_camera_button
        self.global_mic_button=self.command_button(top,'input.microphone.toggle',text='Mic')
        self.mic_disclosure=self.global_mic_button
        self.quick_camera_device=tk.StringVar(value=str(self.last_camera_device))
        self.stop_sharing_button=ttk.Button(top,text='Stop sharing',command=self.stop_visual_sharing)
        from mixer_fader import InlineMixerFader
        self.visual_master_fader=InlineMixerFader(top,self,'MASTER',self.begin_visual_master,self.change_visual_master,self.end_visual_master,length=60,accent=True)
        self.media_button=ttk.Button(top,text='Media',command=lambda:self.shell.toggle_media())
        self.save_project_button=self.command_button(top,'project.save',text='Save')
        self.export_project_button=self.command_button(top,'project.export',text='Export')
        self.audio_now=tk.StringVar(value='Audio · No track')
        self.audio_now_label=ttk.Label(top,textvariable=self.audio_now)
        for widget,tip in ((self.master_fx_button,'Open the A/B/Output effects rack. Select the owner inside the rack.'),
                           (self.output_viewer_button,'Open a separate output viewer window.'),
                           (self.application_button,'Project, import, save, export and settings.'),
                           (self.media_sources_button,'Browse files, cameras, screen capture and audio sources directly.')):
            self.add_tip(widget,tip)

    def source_disclosure(self,kind):
        menu=tk.Menu(self,tearoff=False)
        if kind=='camera':
            from visual_channels import channels
            values=[]
            try:values=list(self.live.camera_devices())
            except Exception:pass
            values=list(dict.fromkeys([self.last_camera_device,*values,'test']))
            def choose(value):self.last_camera_device=str(value);self.quick_camera_device.set(str(value));self.save_preferences()
            for value in values:menu.add_command(label=('✓ ' if str(value)==str(self.last_camera_device) else '')+('Test pattern' if value=='test' else str(value)),command=lambda v=value:choose(v))
            def custom():
                value=simpledialog.askstring('Camera device','Device path or index',initialvalue=str(self.last_camera_device),parent=self)
                if value:choose(value)
            menu.add_command(label='Other device…',command=custom);anchor=self.camera_disclosure
            menu.add_separator()
            for role in (layer.extra['voice'] for layer in channels(self.project)):
                menu.add_command(label='Screen or Window → '+role,command=lambda r=role:self.open_visual_source(r))
            menu.add_command(label='Stop screen/window sharing',command=self.stop_visual_sharing)
        else:
            menu.add_command(label='Microphone and routing…',command=lambda:self.shell.show('panel.audio'))
            def device():
                value=simpledialog.askstring('Microphone device','Device name',initialvalue=str(self.last_microphone_device),parent=self)
                if value:self.last_microphone_device=value;self.refresh_source_choices();self.save_preferences()
            menu.add_command(label='Select device…',command=device);anchor=self.mic_disclosure
        self.popup_menu(menu,anchor if anchor.winfo_viewable() else self.global_toolbar.more_button)

    def record_options(self):
        menu=tk.Menu(self,tearoff=False)
        for cid in ('record.sequence','record.settings','project.drafts','project.export'):self._menu_command(menu,cid)
        menu.add_separator();menu.add_checkbutton(label='Retain live inputs',variable=self.retain_armed,command=self.toggle_retention)
        menu.add_checkbutton(label='Record control motion',variable=self.record_automation)
        menu.add_command(label='History limits and coverage…',command=self.history_settings)
        for seconds in (10,30,60,120):menu.add_command(label=f'Keep recent {seconds} seconds',command=lambda n=seconds:(self.capture_seconds.set(str(n)),self.capture_recent()))
        self.popup_menu(menu,self.record_disclosure if self.record_disclosure.winfo_viewable() else self.global_toolbar.more_button)

    def populate_programme_menu(self,menu):
        for cid in ('output.viewer','programme.settings','timing.precision'):self._menu_command(menu,cid)
        quality=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Preview quality',menu=quality)
        for value in ('240','360','540','720','1080'):quality.add_radiobutton(label=value,value=value,variable=self.viewport.quality,command=lambda:(self.request_preview(),self.save_preferences()))
        menu.add_checkbutton(label='Preview bypass (not recording)',variable=self.viewport.bypass,command=lambda:self.request_preview())
        menu.add_command(label='Preview diagnostics',command=self.toggle_preview_diagnostics)

    def toggle_preview_diagnostics(self):
        row=self.preview_diagnostics_row
        if row.winfo_manager():row.pack_forget()
        else:row.pack(side='bottom',fill='x')

    def workspace_escape(self,event=None):
        if self.contextual_surfaces.active():self.contextual_surfaces.dismiss();return 'break'
        if self.shell.escape():return 'break'
        if getattr(self,'_context_tray',None):self.close_context_tray();return 'break'
        self.cancel_gesture()

    def apply_theme(self,name,save=True,chrome_override=None):
        from ui_chrome import configure_theme,retheme_native_tk_scales
        self.ui_chrome=dict(chrome_override if chrome_override is not None else self.theme_library.get(name,self.ui_chrome))
        configure_theme(self,self.ui_chrome);self.refine_widget_theme();self.clean_tips()
        if chrome_override is None:self.theme_name.set(name)
        for tip in self.tip_instances:tip.chrome=self.ui_chrome
        retheme_native_tk_scales(self,self.ui_chrome)
        if hasattr(self,'shell'):
            self.shell.stage.configure(bg=self.ui_chrome.get('background','#15151c'))
            for tab in self.shell.edge_tabs.values():tab.chrome=self.ui_chrome;tab.paint(tab.active)
            for frame in self.shell.frames.values():frame.configure(bg=self.ui_chrome.get('background','#15151c'),highlightbackground=self.ui_chrome.get('sash_color','#44414e'))
            for grip in self.shell.grips.values():grip.configure(bg=self.ui_chrome.get('sash_color','#44414e'))
        if hasattr(self,'viewport'):self.viewport.set_theme()
        if hasattr(self,'deck'):self.deck.scroll.set_theme()
        if hasattr(self,'timeline'):self.timeline.redraw()
        welcome=getattr(self,'startup_window',None)
        if welcome is not None and welcome.winfo_exists() and hasattr(welcome,'retheme'):
            welcome.retheme()
        if save and chrome_override is None:self.save_preferences()

    def refresh_status_line(self,*_):
        if not hasattr(self,'status_row') or self.closing:return
        text=self.status.get()
        if self._status_hide:
            try:self.after_cancel(self._status_hide)
            except tk.TclError:pass
            self._status_hide=None
        if not text or text.startswith('Ready'):
            self.status_row.grid_remove();return
        self.status_row.grid(row=2,column=0,sticky='ew')
        exporting=bool(getattr(self,'render_thread',None) and self.render_thread.is_alive())
        if exporting:self.progress.grid(row=0,column=1,padx=3);self.cancel_button.grid(row=0,column=2)
        else:self.progress.grid_remove();self.cancel_button.grid_remove()
        persistent=any(word in text.lower() for word in ('error','failed','missing','not found','needs attention','cannot','finishing','finalising'))
        if not persistent and not exporting:self._status_hide=self.after(4500,self.status_row.grid_remove)

    def toggle_selected_camera(self):
        from visual_channels import strongest_channel
        from queue_model import mode_at
        from instrument_model import voice
        now=self.programme_time() if self.playing else self.playhead
        try:role=strongest_channel(self.project,now,self.signal_evaluator())
        except ValueError as exc:return self.update_status(str(exc))
        layer=voice(self.project,role)
        device=None if mode_at(layer,now)['mode']=='camera' or role in getattr(self,'camera_tickets',{}) else self.quick_camera_device.get().strip() or None
        return self.toggle_channel_camera(role,device)
