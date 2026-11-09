"""Neospector OmN-e R5: docked instrument over the preserved R4 runtime.

Queue, Library, Conductor, overview and rack have stable responsibilities.
Capture, export, processing and advanced editors retain their existing services.
"""
from __future__ import annotations
from release_identity import VERSION, RELEASE
from instrument_app import *
from neospector_pedals import PedalDeck
from neospector_catalog import FACTORY_GROUPS,build_group
from module_engine import compile_rack,randomise_rack
import copy,random
from flow_playback import PlaybackQueues
from flow_timing import TimingWorkbench
from flow_conductor import ConductorPane,ConductorMini,QueueConductor
from flow_media import MediaWorkflow
from camera_controls import CameraActions
from playable_actions import PlayableActions
from performance_panel import PerformancePanel
from playable_lifecycle import PlayableLifecycle

from omne_workspace import OmneWorkspace
from context_tray import ContextTrayActions
from capture_ui import CaptureActions
from immediate_actions import ImmediateActions

class NeospectorApp(CaptureActions,ContextTrayActions,ImmediateActions,OmneWorkspace,PlayableLifecycle,PlayableActions,CameraActions,MediaWorkflow,InstrumentApp):
    def close(self,force=False):
        guide=getattr(self,'guides',None)
        if guide and guide.practice is not None:
            guide.leave_practice()
            if guide.practice is not None:return
        if guide:guide.close()
        return super().close(force)
    def __init__(self,test_mode=False):
        super().__init__(test_mode)
        self.app_name='Neospector'
        self.preferences_path=self.cfg/'preferences-neospector-omne-r5.json'
        self.autosave_path=self.cfg/'recovery/neospector-omne-r5-autosave.omne-sequence.json'
        self.update_title();self.deck.scope.set('Master');self.deck.refresh(True)
        from update_ui import UpdateController
        self.update_controller=UpdateController(self)
        if not test_mode and self.auto_check_updates:
            self.after(2200,lambda:self.update_controller.check(silent=True) if not self.closing else None)
        if not test_mode and self.auto_import_media:
            self.after(1000,self.auto_import_folder_if_enabled)
    def read_preferences(self):
        if hasattr(self,'cfg'):
            for filename in ('preferences-neospector-omne-r5.json','preferences-neospector-playable-r4.json','preferences-neospector-flow-r3.json','preferences-neospector-flow-r2.json','preferences-neospector-recovery.json'):
                path=self.cfg/filename
                if path.exists():
                    try:
                        pref=json.loads(path.read_text(encoding='utf-8'))
                        if filename!='preferences-neospector-omne-r5.json':
                            for key in ('layout','panel_states','queue_conductor','quick_conductor'):pref.pop(key,None)
                        return pref
                    except (ValueError,OSError):pass
        return super().read_preferences()

    def refresh_all(self):
        super().refresh_all()
        if hasattr(self,'source_labels'):self.refresh_source_choices()

    def _clock_ui(self):
        super()._clock_ui()
        self.measure_history_budget()
        try:self.refresh_camera_strip();self.refresh_source_choices(periodic=True)
        except Exception:self._phase_error('Camera controls')

    def playback_diagnostics(self):
        now=time.monotonic();last=getattr(self,'_frame_presented_at',None)
        return {'playing':self.playing,'reviewing':self.reviewing,'session_seconds':self.programme_time(),
                'edit_seconds':self.playhead,'programme_frame_seconds':self.programme_frame_time,
                'presented_frames':getattr(self,'_frame_count',0),
                'frame_age_seconds':max(0.,now-last) if last else None,
                'last_render_ms':getattr(self,'_last_render_ms',None),
                'heartbeat_count':getattr(self,'_heartbeat_count',0),
                'last_heartbeat_age_seconds':max(0.,now-getattr(self,'_heartbeat_at',now)),
                'phase_errors':copy.deepcopy(getattr(self,'_phase_errors',{})),
                'preview_quality':self.viewport.quality.get(),'audio_error':self.audio_bus.error,
                'asset_count':len(self.project.assets),'duplicate_aliases':len(self.project.extra.get('asset_aliases',{}))}
    def export_diagnostics(self):
        from diagnostics import export_diagnostics
        out=filedialog.asksaveasfilename(parent=self,title='Save diagnostic report (contains local paths)',
                initialfile='Neospector_OmNe_R5_Diagnostics.zip',defaultextension='.zip',filetypes=[('ZIP','*.zip')])
        if not out:return
        snapshot=copy.deepcopy(self.project);stats=self.playback_diagnostics();state=copy.deepcopy(self.live.state());log=self.log_path;report=self.last_diagnostics
        def work():
            try:
                export_diagnostics(snapshot,out,log,report,state,stats)
                self.events.put(('status','Diagnostics saved · review local paths before sharing. Source media was not included.'))
            except Exception as exc:self.events.put(('status','Diagnostics: '+str(exc)))
        threading.Thread(target=work,name='Write Neospector diagnostic',daemon=True).start()
        self.update_status('Saving playback diagnostics in the background…')

    def compact_queue(self):
        style=ttk.Style(self);style.configure('Queue.TButton',padding=(4,2),font=('TkDefaultFont',9))
        def walk(w):
            if isinstance(w,ttk.Button):w.configure(style='Queue.TButton')
            for child in w.winfo_children():walk(child)
        if hasattr(self,'queue_deck'):walk(self.queue_deck)
        style.configure('Queue.TNotebook.Tab',padding=(7,3),font=('TkDefaultFont',9))
    def console_styles(self):
        c=self.ui_chrome;s=ttk.Style(self)
        s.configure('ConsoleBrand.TLabel',foreground=c['accent'],font=('TkDefaultFont',17,'bold'))
        s.configure('Transport.TFrame',background=c['field_bg'])
        s.configure('TransportMode.TLabel',background=c['field_bg'],foreground=c['accent'],font=('TkDefaultFont',9,'bold'))
        s.configure('TransportTime.TLabel',background=c['field_bg'],foreground=c['foreground'],font=('TkFixedFont',10))
        s.configure('TransportQueue.TLabel',background=c['field_bg'],foreground=c['muted_fg'],font=('TkDefaultFont',9))
        s.configure('TransportPlay.TButton',background=c['accent'],foreground=c['background'],font=('TkDefaultFont',14,'bold'),padding=(10,10))
        s.map('TransportPlay.TButton',background=[('active',c['secondary_accent'])],foreground=[('active',c['background'])])
        s.configure('TransportStop.TButton',font=('TkDefaultFont',11,'bold'),padding=(8,10))
        s.configure('TButton',padding=(6,4))
        s.configure('Current.TLabel',foreground=c['accent'],font=('TkDefaultFont',10,'bold'))
        # UX21: same physical height for main actions, distinct purpose colours.
        for name,bg,fg in (('Play',c['accent'],c['background']),('Record',c['failure_fg'],c['background']),
                           ('Effects',c['button_bg'],c['button_fg']),('EffectsActive',c['tab_selected_bg'],c['selection_fg']),
                           ('Output',c['selection_bg'],c['selection_fg'])):
            key='UX21.'+name+'.TButton'
            s.configure(key,background=bg,foreground=fg,bordercolor=bg,relief='flat',
                        font=('TkDefaultFont',10,'bold'),padding=(10,8))
            s.map(key,background=[('active',c['active_bg']),('pressed',c['selection_bg'])])
        # UX19: semantic, distinct visual hierarchy. Primary live inputs,
        # recording and insertions must not be identical grey toolbar keys.
        def button(name,bg,fg,**extra):
            key='UX19.'+name+'.TButton'
            s.configure(key,background=bg,foreground=fg,bordercolor=bg,relief='flat',padding=(9,6),**extra)
            s.map(key,background=[('active',c['active_bg']),('pressed',c['selection_bg'])],
                      foreground=[('disabled',c['disabled_fg'])])
        button('CameraIdle',c['button_bg'],c['button_fg'],font=('TkDefaultFont',10,'bold'))
        button('CameraLive',c['selection_bg'],c['selection_fg'],font=('TkDefaultFont',10,'bold'))
        button('MicIdle',c['active_bg'],c['active_fg'],font=('TkDefaultFont',10,'bold'))
        button('MicLive',c['success_fg'],c['background'],font=('TkDefaultFont',10,'bold'))
        button('Record',c['failure_fg'],c['background'],font=('TkDefaultFont',10,'bold'))
        button('Signal',c['button_bg'],c['button_fg'],font=('TkDefaultFont',9,'bold'))
        button('Import',c['accent'],c['background'],font=('TkDefaultFont',11,'bold'))
        button('SourceSelected',c['selection_bg'],c['foreground'],font=('TkDefaultFont',9,'bold'))
        button('SourceTab',c['panel_bg'],c['muted_fg'],font=('TkDefaultFont',9,'bold'))
        button('Secondary',c['panel_bg'],c['muted_fg'],font=('TkDefaultFont',9))
        button('Vary',c['secondary_accent'],c['background'],font=('TkDefaultFont',8,'bold'))
        button('Delete',c['failure_fg'],c['background'],font=('TkDefaultFont',9,'bold'))
        s.configure('UX19.Vary.TButton',padding=(5,0))
        s.configure('UX19.Delete.TButton',padding=(3,0))
        # UX20: ownership and source navigation have their own visual grammar.
        s.configure('UX20.SourceGroup.TFrame',background=c['panel_bg'])
        s.configure('UX20.SourceHeading.TLabel',background=c['panel_bg'],foreground=c['foreground'],
                    font=('TkDefaultFont',9,'bold'))
        s.configure('UX20.SourceIdle.TButton',background=c['button_bg'],foreground=c['muted_fg'],
                    padding=(7,5),font=('TkDefaultFont',9,'bold'))
        s.configure('UX20.SourceOpen.TButton',background=c['selection_bg'],foreground=c['selection_fg'],
                    padding=(7,5),font=('TkDefaultFont',9,'bold'))
        s.configure('UX20.OwnerFrame.TFrame',background=c['panel_bg'])
        s.configure('UX20.PowerOn.TButton',background=c['success_fg'],foreground=c['background'],
                    padding=(5,3),font=('TkDefaultFont',9,'bold'))
        s.configure('UX20.PowerOff.TButton',background=c['button_bg'],foreground=c['muted_fg'],
                    padding=(5,3),font=('TkDefaultFont',9,'bold'))
        s.configure('UX20.OwnerTitle.TLabel',background=c['panel_bg'],foreground=c['foreground'],
                    font=('TkDefaultFont',10,'bold'))
        s.configure('UX20.OwnerCount.TLabel',foreground=c['muted_fg'],font=('TkDefaultFont',9))
        s.configure('UX20.TargetIdle.TButton',background=c['button_bg'],foreground=c['button_fg'],padding=(4,3))
        s.configure('UX20.TargetActive.TButton',background=c['selection_bg'],foreground=c['selection_fg'],padding=(4,3),
                    font=('TkDefaultFont',9,'bold'))
        s.configure('UX20.Mixer.TFrame',background=c['panel_bg'])
        s.configure('UX20.MixEdge.TLabel',foreground='#bcd6f5',font=('TkDefaultFont',10,'bold'))
        s.configure('UX25.Signal.TButton',background=c['success_fg'],foreground=c['background'],
                    padding=(8,6),font=('TkDefaultFont',9,'bold'))
        s.configure('UX20.MixRatio.TLabel',foreground=c['foreground'],font=('TkFixedFont',9,'bold'))
        s.configure('UX20.ToolLabel.TLabel',foreground=c['muted_fg'],font=('TkDefaultFont',8,'bold'))
        s.configure('UX20.Small.TButton',padding=(4,2),font=('TkDefaultFont',9))
        s.configure('UX20.Transition.TButton',background=c['button_bg'],foreground=c['button_fg'],padding=(6,3),
                    font=('TkDefaultFont',9,'bold'))
        s.configure('UX20.ReactionOff.TButton',background=c['button_bg'],foreground=c['muted_fg'],padding=(6,3))
        s.configure('UX20.ReactionOn.TButton',background=c['success_fg'],foreground=c['background'],padding=(6,3),
                    font=('TkDefaultFont',9,'bold'))

        # UX40: semantic styles are resolved from the CURRENT theme on every
        # apply_theme call. Old UX28 literal blue-gray values made Space Funk
        # appear permanently selected in other published palettes.
        s.configure('UX28.Group.TFrame',background=c['panel_bg'])
        specifications={
            'LiveIdle':(c['button_bg'],c['button_fg'],'raised',(6,3)),
            'LiveActive':(c['selection_bg'],c['selection_fg'],'sunken',(6,3)),
            'MicIdle':(c['active_bg'],c['active_fg'],'raised',(6,3)),
            'MicActive':(c['success_fg'],c['background'],'sunken',(6,3)),
            'QueueIdle':(c['button_bg'],c['muted_fg'],'flat',(5,3)),
            'QueueOpen':(c['tab_selected_bg'],c['selection_fg'],'sunken',(5,3)),
            'QueueFlash':(c['secondary_accent'],c['background'],'raised',(5,3)),
            'LiveMini':(c['button_bg'],c['button_fg'],'raised',(3,1)),
            'LiveMiniActive':(c['selection_bg'],c['selection_fg'],'sunken',(3,1)),
            'MicMini':(c['active_bg'],c['active_fg'],'raised',(3,1)),
            'MicMiniActive':(c['success_fg'],c['background'],'sunken',(3,1)),
            'Action':(c['button_bg'],c['button_fg'],'flat',(6,3)),
            'Output':(c['selection_bg'],c['selection_fg'],'raised',(6,3)),
            'Record':(c['failure_fg'],c['background'],'raised',(6,3)),
            'Insert':(c['button_bg'],c['button_fg'],'raised',(5,2)),
            'Disclose':(c['field_bg'],c['muted_fg'],'flat',(3,2)),
        }
        for name,(bg,fg,relief,padding) in specifications.items():
            key='UX28.'+name+'.TButton'
            s.configure(key,background=bg,foreground=fg,bordercolor=c['panel_edge'] if name.startswith('Queue') else bg,
                        padding=padding,relief=relief,font=('TkDefaultFont',9,'bold' if name in ('LiveActive','MicActive','QueueOpen','Record') else 'normal'))
            s.map(key,background=[('active',c['active_bg']),('pressed',c['selection_bg'])],
                      foreground=[('disabled',c['disabled_fg']),('active',c['active_fg'])])
        s.configure('UX40.ReactAll.TButton',padding=(2,0),background=c['button_bg'],foreground=c['muted_fg'],font=('TkDefaultFont',8,'bold'))
        s.configure('UX40.ReactAllOn.TButton',padding=(2,0),background=c['success_fg'],foreground=c['background'],font=('TkDefaultFont',8,'bold'))
        s.map('UX40.ReactAll.TButton',background=[('active',c['active_bg'])])
        s.map('UX40.ReactAllOn.TButton',background=[('active',c['accent'])])
        # Match the scale of ordinary toolbar controls; older primary buttons
        # had 16px of vertical padding and overwhelmed neighbouring actions.
        for name in ('Play','Record','Effects','EffectsActive','Output'):
            s.configure('UX21.'+name+'.TButton',padding=(8,4),font=('TkDefaultFont',9,'bold'))
        s.configure('UX20.Transition.TButton',padding=(6,3))
        s.configure('UX20.ReactionOff.TButton',padding=(6,3))
        s.configure('UX20.ReactionOn.TButton',padding=(6,3))
        s.configure('Missing.TButton',foreground=c['accent'],padding=4)
    def apply_theme(self,name,save=True,chrome_override=None):
        super().apply_theme(name,save,chrome_override)
        self.console_styles();self.compact_queue()
        if hasattr(self,'console_root'):
            from instrument_density import compact_tree
            compact_tree(self.console_root)
        if hasattr(self,'conductor_mini'):self.conductor_mini.retheme()
        if hasattr(self,'deck') and not self.gesture:self.deck.refresh(True)
    def update_title(self):
        self.title(('• ' if self.dirty else '')+self.project.name+' · Neospector · '+RELEASE+' · '+VERSION)
    def pause(self):
        self.cancel_pending_play()
        super().pause()
        if hasattr(self,'play_button'):self.play_button.configure(text='▶ PLAY')
    def new_project(self):
        if self.test_mode or self.confirm_discard():
            p=new_instrument();p.extra['playable_intent']=__import__('playable_intent').load_intent(p)
            # R5C10 instruments start with the two ordinary visual voices only.
            # Do not manufacture the retired Foreground slot just to initialise UI state.
            for layer in p.layers:layer.enabled=True
            p.extra['playable_intent']['enabled_roles']=['A','B']
            self.restore_project(p);self.load_catalogue_assets();self.refresh_library();self.refresh_source_choices()
            if not self.test_mode:self.after_idle(self.auto_import_folder_if_enabled)
    def toggle_play(self):
        if not self.playing and getattr(self,'_playable_running',False):
            self._playable_play_requested=True
            return self.update_status('Play queued after preparation. STOP cancels it.')
        if not self.playing and not self.reviewing and not getattr(self,'_playable_running',False):
            from playable_intent import plan_randomise
            try:
                intent=self.source_intent();plan=plan_randomise(self.project,intent,'queues',now=self.playhead,playing=False,live_state={})
                missing=any(not voice(self.project,role).clips for role in plan['queue_roles']) or plan['music_action']=='fill'
                if missing and not any(l.enabled and (l.clips or __import__('queue_model').mode_at(l,self.playhead)['mode']=='camera') for l in self.project.layers):return self.randomise_playable('queues',play_after=True)
            except ValueError as exc:self.update_status('Source preparation: '+str(exc))
        super().toggle_play()
        self.play_button.configure(text='Ⅱ PAUSE' if self.playing else '▶ PLAY')
    def stop_session(self):
        self.pause();self._held_time=0.
        if not self.reviewing:self.set_playhead(0.)
        self.update_status('Session stopped. Sources, effects and retained takes are unchanged.')
    def capture_menu(self):
        menu=tk.Menu(self,tearoff=False)
        menu.add_checkbutton(label='Retain live inputs',variable=self.retain_armed,command=self.toggle_retention)
        menu.add_checkbutton(label='Record control motion',variable=self.record_automation)
        menu.add_separator()
        for seconds in (10,30,60,120):
            menu.add_command(label=f'Keep recent {seconds} seconds',command=lambda n=seconds:(self.capture_seconds.set(str(n)),self.capture_recent()))
        menu.add_command(label='History limits & coverage…',command=self.history_settings)
        menu.add_separator();menu.add_command(label='Output Viewer',command=self.open_output)
        menu.add_command(label='Stop all inputs',command=self.stop_inputs)
        self.popup_menu(menu,self.record_disclosure)
    def music_edit(self,label,edit,*args):
        if self.playing and not self.reviewing and label!='Play Music item now':
            return self.update_status('Pause to retime or reorder Music. Play Next and adding tracks remain available during playback; played history is preserved.')
        result=self.transaction(label,lambda:edit(self.project,*args));self.configure_sound_sources();self.prepare_sound_analysis();self.queue_deck.refresh(True);return result
    def music_take(self,event_id):
        from music_queue import take
        now=self.playhead if self.reviewing else self.programme_time()
        self.music_edit('Play Music item now',lambda p:take(p,event_id,now))
        if not self.playing and not self.reviewing:self.toggle_play()
    def focus_voice(self,role):
        super().focus_voice(role)
        # UX10 rack is the persistent centre panel, not a notebook tab.
        if hasattr(self,'deck'):self.deck.refresh(True)
    def show_startup_window(self,force=False):
        win=super().show_startup_window(force)
        win=self.startup_window
        if not win:return
        win.title('Neospector · Welcome')
        def walk(w):
            if isinstance(w,ttk.Label):
                text=str(w.cget('text'))
                if text=='OmN-e Sequencer':w.configure(text='Neospector')
                elif text.startswith('v0.3.3'):w.configure(text='OmN-e R5 · by Pungent Funk')
            for child in w.winfo_children():walk(child)
        walk(win)
        return win
