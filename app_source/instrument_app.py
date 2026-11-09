"""OmN-e Sequencer v0.3: persistent visual instrument and independent take review.

The Retrospector-derived shell remains native Tk. All source reads, mutations,
recording finalisation and exports run on bounded workers; capture never enables
hardware without an explicit action. Compatibility projects remain untouched.
"""
from __future__ import annotations
from conductor_targets import DEFAULTS
import copy,json,math,os,queue,random,shutil,sys,threading,time,traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
from PIL import Image,ImageTk
import omne_sequencer as base
from sequencer_model import *
from sequencer_model import _encode,_effect_from
from instrument_model import *
from instrument_model import style_dict,style_from
from creative_library import CreativeLibrary
from audio_bus import AudioTransport,add_sound,sound_events
from media_engine import probe_media,kind_for_path,render_project,FFMPEG
from process_tools import Cancelled
from signal_engine import SignalEvaluator,analyze_file,analyze_samples
from programme_view import ProgrammeView,ProgrammeWorker
from instrument_widgets import EffectsDeck,ConductorStrip
from playable_rack import PlayableDeck
from queue_panel import QueueDeck
from refinement_actions import RefinementActions
from media_browser_view import MediaBrowser
from multi_live import MultiLiveInputs
from sound_routes import ensure_route,BUILTINS
from queue_model import mode_at
from instrument_timeline import InstrumentTimeline
from ui_chrome import ResizablePane,tk_scale_theme_options
from effects_engine import make_effect,make_look
from sequence_edit import insert_clip
from performance_capture import capture_with_recordings,OutputRecorder

class InstrumentProgrammeView(ProgrammeView):
    def accept(self,t,image,elapsed):
        bypassed=bool(image.info.get('omne_monitor_bypass',False))
        if bypassed!=self.bypass.get():return  # discard an obsolete audition result
        super().accept(t,image,elapsed)
        if not self.app.reviewing and not bypassed:self.app.accept_programme_frame(t,image,elapsed)
        if self.app.reviewing:self.info.set('REVIEW · '+self.info.get()+' · Programme continues independently')
    def _write(self,param,value):self.app.write_parameter(param,value)
    def press(self,event):
        self.canvas.focus_set();l,c=self.app.get_edit_target()
        if self.app.deck.scope.get()!='Clip' or not c or not self.app.can_edit(c):return
        self.app.begin_gesture('viewport');self.drag=(c,event.x,event.y,c.x.evaluate(self.app.playhead),c.y.evaluate(self.app.playhead))

class InstrumentApp(RefinementActions,base.SequencerApp):
    def __init__(self,test_mode=False):
        self.reviewing=False;self._review_state=None;self._programme_snapshot=None;self._programme_snapshot_key=None;self.mutating=False;self.mutation_ticket=0;self.pending_mutation=None
        self.recorded_segments=[];self.retention_lock=threading.RLock();self.retention_busy=False;self.capture_busy=False;self.output_recording=None;self.output_retention_start=None;self.output_integrity=None;self.output_auto_retention=False;self.output_busy=False;self.output_path=None;self.output_window=None;self.output_photo=None;self.programme_image=None;self.programme_frame_time=0.;self._held_time=0.;self._last_evolve=-1.;self._last_treatment=-1.;self._signal_key=None;self._last_audio_snapshot=None;self._last_sound_block=None
        self.save_lock=threading.RLock();self._io_closed=False;self._last_labels=0.;self._catalog_payloads={};self.io=ThreadPoolExecutor(max_workers=2,thread_name_prefix='Instrument storage');self._futures=[];self._mutation_thread=None
        # UX39: live parameter changes are synchronised at preview cadence,
        # not at raw pointer-motion cadence. Never schedule model mutations off-thread.
        self._ux39_parameter_job=None
        self._ux39_parameter_pending=False
        self._ux39_parameter_last=0.0
        self._ux39_parameter_changes=0
        self._ux39_parameter_frames=0
        self.audio_bus=AudioTransport(lambda msg:self.events.put(('status',msg)) if hasattr(self,'events') else None)
        super().__init__(test_mode=test_mode)
        self.preferences_path=self.cfg/'preferences-v031.json';self.autosave_path=self.cfg/'recovery/v031-autosave.omne-sequence.json'
        self.title('OmN-e Sequencer · Visual Instrument · 0.3.1 R1')
        self.load_catalogue_assets();self.load_saved_takes();self.refresh_library()
        self.load_layout(self.read_preferences())
    def read_preferences(self):
        preferred=self.cfg/'preferences-v031.json'
        if preferred.exists():
            try:return json.loads(preferred.read_text(encoding='utf-8'))
            except (ValueError,OSError):pass
        return super().read_preferences()
    def load_catalogue_assets(self):
        try:
            raw=self.catalog.assets();parsed=project_from_dict({'assets':{a['id']:a for a in raw}})
            for aid,asset in parsed.assets.items():
                if asset.kind!='camera':self.project.assets.setdefault(aid,asset)
        except Exception as exc:self.log('Catalogue load: '+str(exc))
    def load_saved_takes(self):
        folder=self.cfg/'captured-takes'
        if not folder.exists():return
        for path in sorted(folder.glob('*/Captured.omne-sequence.json'),reverse=True)[:100]:
            try:self.takes.append({'project':load_project(path),'path':path})
            except Exception as exc:self.log('Take catalogue: '+str(exc))
        self.refresh_takes()
    def persist_assets(self,before):
        old=before.get('assets',{});changed=[]
        for aid,asset in self.project.assets.items():
            if asset.kind=='camera':continue
            raw=_encode(asset)
            if raw!=old.get(aid):changed.append(copy.deepcopy(asset))
        if changed:self.io.submit(self.catalog.persist_project_assets,self.project.id,changed,time.monotonic_ns())
    def _ux39_flush_parameter(self):
        """Coalesced UI/frame notification; the parameter itself was already written."""
        self._ux39_parameter_job=None
        if not self._ux39_parameter_pending or self.closing:return
        self._ux39_parameter_pending=False
        self._ux39_parameter_last=time.monotonic()
        self._ux39_parameter_frames+=1
        # Deliberately bypass InstrumentApp.changed: queue/sound routing and
        # treatment history are structural concerns, not per-pixel fader work.
        base.SequencerApp.changed(self,redraw=False)

    def _ux39_schedule_parameter(self):
        self._ux39_parameter_changes+=1
        self._ux39_parameter_pending=True
        if self._ux39_parameter_job is not None:return
        elapsed=time.monotonic()-self._ux39_parameter_last
        if elapsed>=.033:
            self._ux39_flush_parameter()
        else:
            self._ux39_parameter_job=self.after(max(1,int((.033-elapsed)*1000)),self._ux39_flush_parameter)

    def _ux39_complete_parameter(self,discard=False):
        job=self._ux39_parameter_job
        if job is not None:
            try:self.after_cancel(job)
            except tk.TclError:pass
            self._ux39_parameter_job=None
        if discard:self._ux39_parameter_pending=False
        else:self._ux39_flush_parameter()

    def changed(self,redraw=False):
        # A real commit (including the release of a slider) can update all
        # dependent playback surfaces, but motion itself never does this.
        self._ux39_complete_parameter()
        if hasattr(self,'deck') and hasattr(self.deck,'flush_history'):self.deck.flush_history()
        super().changed(redraw)
        if hasattr(self,'queue_deck'):self.queue_deck.refresh(False)
        if hasattr(self,'live'):self.configure_sound_sources()
    def build_ui(self):
        self.live=MultiLiveInputs();self.audio_bus.live_inputs=self.live
        prefs=self.read_preferences();self.last_camera_device=prefs.get('camera_device','/dev/video0' if sys.platform.startswith('linux') else '0');self.last_microphone_device=prefs.get('microphone_device','default' if sys.platform.startswith('linux') else '0');self.last_import_folder=prefs.get('import_folder',str(Path.home()));self.recent_import_folders=prefs.get('recent_import_folders',[]);self.import_window=None;self.precision_visible=tk.BooleanVar(value=False)
        self.project=new_instrument();self.history=ProjectHistory(self.project);self.selected_layer_id=self.project.layers[0].id
        self.evolve=tk.BooleanVar(value=False);self.retention_enabled=False;self.retain_armed=tk.BooleanVar(value=False);self.retain_armed.trace_add('write',lambda *_:setattr(self,'retention_enabled',bool(self.retain_armed.get())));self.capture_seconds=tk.StringVar(value='30');self.album=tk.StringVar(value='all');self.album_label=tk.StringVar(value='All media');self.mode_label=tk.StringVar(value='PROGRAMME');self.voice_labels={};self.catalog=CreativeLibrary(self.cfg/'creative-library.sqlite3');self.takes=[];self._catalog_futures=[]
        self.cache=base.cache_dir()/'v031';self.cache.mkdir(parents=True,exist_ok=True);self.log_path=self.cache/'session.log';self.preferences_path=self.cfg/'preferences-v031.json';self.autosave_path=self.cfg/'recovery/v031-autosave.omne-sequence.json'
        root=ttk.Frame(self,padding=6);root.pack(fill='both',expand=True);root.columnconfigure(0,weight=1);root.rowconfigure(2,weight=1)
        menu=tk.Menu(self);self.configure(menu=menu)
        for title,items in [('File',[('New instrument',self.new_project),('Open…',self.open_project),('Save',self.save_project),('Save as…',lambda:self.save_project(as_new=True)),('Canvas / sequence settings',self.sequence_settings),('Export…',self.export_video),('Diagnostics…',self.export_diagnostics),('Exit',self.close)]),('Edit',[('Undo',self.undo),('Redo',self.redo),('Split',self.split_current),('Replace media',self.replace_current),('Insert before',lambda:self.insert_near(False)),('Insert after',lambda:self.insert_near(True)),('Duplicate',self.duplicate_current),('Delete',self.delete_current),('+ Text',self.add_text),('+ Shape',self.add_shape)]),('View',[('Theme Studio',self.open_theme_studio),('Import theme',self.open_theme_import),('Welcome',lambda:self.show_startup_window(True)),('Reset layout',lambda:self.load_layout({})),('Output Viewer',self.open_output),('Quick guide',self.quick_guide)])]:
            sub=tk.Menu(menu,tearoff=False);menu.add_cascade(label=title,menu=sub)
            for label,fn in items:sub.add_command(label=label,command=fn)
        top=ttk.Frame(root);top.grid(row=0,column=0,sticky='ew',pady=(1,5));ttk.Label(top,text='OmN-e  /  Sequencer',style='Title.TLabel').pack(side='left',padx=(2,14))
        for text,fn in [('Open',self.open_project),('Save',self.save_project),('Import…',self.add_media)]:ttk.Button(top,text=text,width=9,command=fn).pack(side='left',padx=2)
        self.camera_button=ttk.Button(top,text='📷 Camera',width=10,command=lambda:self.quick_camera('A'));self.camera_button.pack(side='left',padx=(8,2));self.mic_button=ttk.Button(top,text='Mic',width=6,command=self.quick_microphone);self.mic_button.pack(side='left',padx=2)
        ttk.Button(top,text='Export…',style='Accent.TButton',width=9,command=self.export_video).pack(side='right',padx=2);ttk.Button(top,text='Theme',width=7,command=self.open_theme_studio).pack(side='right',padx=2);self.live_button=ttk.Button(top,text='Sources',width=8,command=self.open_live);self.live_button.pack(side='right',padx=2);ttk.Button(top,text='Output',width=8,command=self.open_output).pack(side='right',padx=2)
        performance=ttk.Frame(root);performance.grid(row=1,column=0,sticky='ew',pady=(0,5));ttk.Label(performance,textvariable=self.mode_label,style='Muted.TLabel',width=15).pack(side='left',padx=3)
        self.play_button=ttk.Button(performance,text='▶ Play',width=8,command=self.toggle_play);self.play_button.pack(side='left');ttk.Button(performance,text='Return to Programme',width=15,command=self.go_live).pack(side='left',padx=3)
        ttk.Label(performance,textvariable=self.transport_time,width=22).pack(side='left',padx=5);ttk.Checkbutton(performance,text='Monitor mute',variable=self.mute,command=self.restart_audio).pack(side='left',padx=3)
        self.record_button=ttk.Button(performance,text='● Record output',command=self.toggle_output_record);self.record_button.pack(side='right',padx=2)
        ttk.Button(performance,text='Capture recent',command=self.capture_recent).pack(side='right',padx=3);ttk.Combobox(performance,textvariable=self.capture_seconds,values=['10','30','60','120'],width=5).pack(side='right');ttk.Label(performance,text='seconds').pack(side='right',padx=3)
        ttk.Checkbutton(performance,text='Retain live inputs',variable=self.retain_armed,command=self.toggle_retention).pack(side='right',padx=5)
        self.main_panes=ResizablePane(root,tk.VERTICAL,self.ui_chrome);self.main_panes.grid(row=2,column=0,sticky='nsew');work=ttk.Frame(self.main_panes);bottom=ttk.Frame(self.main_panes);self.main_panes.add(work,minsize=330);self.main_panes.add(bottom,minsize=285);self.main_panes.bind('<Double-Button-1>',lambda e:self.load_layout({}),add='+')
        self.workspace_panes=ResizablePane(work,tk.HORIZONTAL,self.ui_chrome);self.workspace_panes.pack(fill='both',expand=True);lib=ttk.Frame(self.workspace_panes);vp=ttk.Frame(self.workspace_panes);voices=ttk.Frame(self.workspace_panes,padding=5);self.workspace_panes.add(lib,minsize=220);self.workspace_panes.add(vp,minsize=320);self.workspace_panes.add(voices,minsize=285)
        self.build_library(lib);self.viewport=InstrumentProgrammeView(vp,self);self.viewport.quality.set(self.read_preferences().get('preview_quality','360'));self.viewport.pack(fill='both',expand=True)
        self.queue_deck=QueueDeck(voices,self);self.queue_deck.pack(fill='both',expand=True)
        self.retention_info=tk.StringVar(value='Live history off');self.audio_info=tk.StringVar(value='No soundtrack')
        bottom.columnconfigure(0,weight=1);bottom.rowconfigure(2,weight=1)
        self.conductor=ConductorStrip(bottom,self)
        strip=ttk.Frame(bottom,padding=(5,3));strip.grid(row=0,column=0,sticky='ew');self.precision_button=ttk.Button(strip,text='Timing ▾',command=self.toggle_precision);self.precision_button.pack(side='left');ttk.Button(strip,text='Conductor…',command=self.conductor.recipe).pack(side='left',padx=4);ttk.Checkbutton(strip,text='Evolve',variable=self.evolve,command=self.toggle_evolve).pack(side='left',padx=5);ttk.Checkbutton(strip,text='Record control motion',variable=self.record_automation).pack(side='right',padx=4);ttk.Label(strip,text='Sources choose the picture. Modules play it.',style='Muted.TLabel').pack(side='right',padx=12)
        self.timeline=InstrumentTimeline(bottom,self);self.timeline.grid(row=1,column=0,sticky='ew');self.timeline.configure(height=163);self.timeline.grid_propagate(False);self.timeline.grid_remove()
        self.deck=PlayableDeck(bottom,self);self.deck.grid(row=2,column=0,sticky='nsew',pady=(2,0))
        status=ttk.Frame(root);status.grid(row=3,column=0,sticky='ew',pady=(5,0));status.columnconfigure(0,weight=1);ttk.Label(status,textvariable=self.status,style='Muted.TLabel').grid(row=0,column=0,sticky='ew');self.progress=ttk.Progressbar(status,length=95,maximum=100);self.progress.grid(row=0,column=1,padx=4);self.cancel_button=ttk.Button(status,text='Cancel export',command=lambda:self.render_cancel.set(),state='disabled');self.cancel_button.grid(row=0,column=2);ttk.Button(status,text='Diagnostics',command=self.export_diagnostics).grid(row=0,column=3,padx=4)
        self.range_label=ttk.Label(status,text='',style='Muted.TLabel');self.range_label.grid(row=1,column=0,sticky='w')
        self.background_events=queue.Queue();self.background_worker=ProgrammeWorker(self.background_events,self.live)
        self._browser_key=None;self._take_key=None
        self.compact_widgets(root)
        self.deck.randomise_button.configure(style='Accent.TButton')
    def build_library(self,parent):
        outer=ttk.Frame(parent,padding=5);outer.pack(fill='both',expand=True);ttk.Label(outer,text='CREATIVE LIBRARY',style='Title.TLabel').pack(anchor='w',pady=(0,4))
        self.library_tabs=ttk.Notebook(outer);self.library_tabs.pack(fill='both',expand=True)
        sources=ttk.Frame(self.library_tabs,padding=4);self.library_tabs.add(sources,text='Media');sources.columnconfigure(0,weight=1);sources.rowconfigure(2,weight=1)
        albums=ttk.Frame(sources);albums.grid(row=0,column=0,sticky='ew',pady=2);self.album_box=ttk.Combobox(albums,textvariable=self.album_label,state='readonly',values=['All media'],width=17);self.album_box.pack(side='left',fill='x',expand=True);self.album_box.bind('<<ComboboxSelected>>',lambda e:self.choose_album());ttk.Button(albums,text='+',width=3,command=self.new_album).pack(side='right',padx=(3,0))
        self.library=MediaBrowser(sources,self,on_visible=self.main_browser_visible,compact=True);self.library.thumb.set('Small');self.library.grid(row=2,column=0,sticky='nsew')
        self.search=self.library.query
        self.library.bind('<<TreeviewSelect>>',self.asset_selected);self.library.bind('<Double-1>',lambda e:self.assign_selected());self.library.bind('<Button-3>',self.library_menu);self.library.bind('<ButtonRelease-1>',self.library_drop,add='+')
        self.asset_summary=tk.StringVar(value='Import media or open First Light.');ttk.Label(sources,textvariable=self.asset_summary,style='Muted.TLabel',wraplength=245,justify='left').grid(row=3,column=0,sticky='ew',pady=5)
        row=ttk.Frame(sources);row.grid(row=4,column=0,sticky='ew')
        for title,role in [('+ A','A'),('+ B','B'),('+ C','C'),('+ D','D')]:ttk.Button(row,text=title,width=6,command=lambda r=role:self.queue_selected(r)).pack(side='left',padx=1)
        row=ttk.Frame(sources);row.grid(row=5,column=0,sticky='ew',pady=3);ttk.Button(row,text='Defaults…',width=9,command=self.batch_personality).pack(side='left');ttk.Button(row,text='Sound',width=7,command=self.queue_sound_selected).pack(side='left',padx=2);ttk.Button(row,text='Album…',width=7,command=self.membership).pack(side='right')
        ttk.Button(sources,text='Open First Light instrument',command=self.open_example).grid(row=6,column=0,sticky='ew',pady=2)
        self.place_mode=tk.StringVar(value='place')
        ingredients=ttk.Frame(self.library_tabs,padding=4);self.library_tabs.add(ingredients,text='Patches');self.ingredients_tree=ttk.Treeview(ingredients,columns=('kind',),show='tree headings',selectmode='browse');self.ingredients_tree.heading('#0',text='Saved ingredient');self.ingredients_tree.heading('kind',text='Type');self.ingredients_tree.column('#0',width=155);self.ingredients_tree.column('kind',width=65,stretch=False);self.ingredients_tree.pack(fill='both',expand=True);self.ingredients_tree.bind('<Double-1>',lambda e:self.apply_selected_ingredient())
        for label,fn in [('Apply selected',self.apply_selected_ingredient),('Keep current…',self.keep_ingredient),('Import ingredient…',self.import_ingredient),('Export selected…',self.export_ingredient)]:ttk.Button(ingredients,text=label,command=fn).pack(fill='x',pady=2)
        takes=ttk.Frame(self.library_tabs,padding=4);self.library_tabs.add(takes,text='Takes');self.take_tree=ttk.Treeview(takes,show='tree',selectmode='browse');self.take_tree.pack(fill='both',expand=True);self.take_tree.bind('<Double-1>',lambda e:self.open_selected_take());ttk.Button(takes,text='Review selected take',command=self.open_selected_take).pack(fill='x',pady=3);ttk.Button(takes,text='Open saved take…',command=self.open_take_file).pack(fill='x');ttk.Label(takes,text='Review has its own cursor. Programme keeps running.',style='Muted.TLabel',wraplength=220,justify='left').pack(fill='x',pady=8)
    def build_voices(self,parent):
        ttk.Label(parent,text='VOICES  /  MIX',style='Title.TLabel').pack(anchor='w',pady=(0,4))
        for role in VOICES:
            frame=ttk.LabelFrame(parent,text=role,padding=6);frame.pack(fill='x',pady=3);v=tk.StringVar(value='No source');self.voice_labels[role]=v;ttk.Label(frame,textvariable=v,wraplength=190,style='Muted.TLabel').pack(anchor='w')
            row=ttk.Frame(frame);row.pack(fill='x',pady=(3,0));ttk.Button(row,text='Effects',width=7,command=lambda r=role:self.focus_voice(r)).pack(side='left');ttk.Button(row,text='Assign',width=7,command=lambda r=role:self.queue_selected(r)).pack(side='right')
        ttk.Button(parent,text='A ↔ B mixing controls',command=lambda:(self.deck.scope.set('Mix'),self.deck.refresh(force=True))).pack(fill='x',pady=5)
        ttk.Button(parent,text='Soundtrack / crossfades…',command=self.soundtrack_dialog).pack(fill='x',pady=3)
        ttk.Button(parent,text='Keep patch…',command=lambda:self.keep_ingredient('patch')).pack(fill='x',pady=3)
        self.retention_info=tk.StringVar(value='Live history is off · files stay editable');ttk.Label(parent,textvariable=self.retention_info,style='Muted.TLabel',wraplength=185,justify='left').pack(fill='x',pady=6)
        self.audio_info=tk.StringVar(value='No soundtrack');ttk.Label(parent,textvariable=self.audio_info,style='Muted.TLabel',wraplength=185,justify='left').pack(fill='x',pady=3)
        ttk.Checkbutton(parent,text='Record control motion',variable=self.record_automation).pack(anchor='w')
    def compact_widgets(self,root):
        style=ttk.Style(self);style.configure('Compact.TButton',padding=(5,2),font=('TkDefaultFont',9));style.configure('Compact.Accent.TButton',padding=(5,2),font=('TkDefaultFont',9))
        def walk(w):
            if isinstance(w,ttk.Button):w.configure(style='Compact.Accent.TButton' if 'Accent' in str(w.cget('style')) else 'Compact.TButton')
            for child in w.winfo_children():walk(child)
        walk(root)
    def programme_project(self):return self._review_state['project'] if self.reviewing else self.project
    def programme_time(self):return max(0.,self.play_origin+time.monotonic()-self.play_started_at) if self.playing else (self._held_time if self.reviewing else self.playhead)
    def programme_size(self):
        p=self.programme_project();quality=self.viewport.quality.get();limit=p.width if quality=='Full' else int(quality);ratio=min(1,limit/p.width)
        return max(16,round(p.width*ratio/2)*2),max(16,round(p.height*ratio/2)*2)
    def programme_revision(self):return self._review_state['revision'] if self.reviewing else self.revision
    def snapshot(self):
        if self._snapshot_revision!=self.revision:
            memo={id(a):a for a in (self.project.analysis,self.project.recorded_analysis,self.project.waveform) if a is not None}
            self._snapshot=copy.deepcopy(self.project,memo);self._snapshot_revision=self.revision
        return self._snapshot
    def programme_snapshot(self):
        if not self.reviewing:return self.snapshot()
        p=self.programme_project();key=(id(p),self.programme_revision())
        if self._programme_snapshot_key!=key:
            self._programme_snapshot=copy.deepcopy(p,{id(a):a for a in (p.analysis,p.recorded_analysis,p.waveform) if a is not None});self._programme_snapshot_key=key
        return self._programme_snapshot
    def signal_evaluator(self):
        key=(id(self.project.analysis),id(self.project.recorded_analysis))
        if self._signals is None:self._signals=SignalEvaluator(self.project,self.live.signal)
        elif key!=self._signal_key:self._signals.cache.clear()
        self._signals.project=self.project;self._signal_key=key;return self._signals
    def get_edit_target(self):
        if self.project.instrument_mode and not self.gesture and self.follow_playhead.get():
            l=self.selected_layer()
            if not l:return None,None
            from queue_model import current,mode_at
            return l,None if mode_at(l,self.playhead)['mode']=='camera' else current(l,self.playhead)
        return super().get_edit_target()
    def parameter_edit_clock(self,owner,t):
        """Clip keys use queue time; layer and final-output controls use session time."""
        if not isinstance(owner,Clip):return t
        gesture=self.gesture
        clocks=gesture.setdefault('clip_clocks',{}) if gesture else {}
        clock=clocks.get(id(owner))
        if clock is None:
            layer=next((l for l in self.project.layers if any(c is owner for c in l.clips)),None)
            if layer is None:return t
            clock={'layer':layer,'preserved_at':None};clocks[id(owner)]=clock
        layer=clock['layer']
        from queue_model import queue_position
        q=queue_position(layer,t)
        if self.playing and not self.reviewing and gesture:
            from queue_policies import preserve_visual_history
            epoch=t-q if layer.extra.get('queue_policy')=='repeat' else self.gesture_time
            at=max(self.gesture_time,epoch)
            if clock['preserved_at'] is None or at>clock['preserved_at']+1e-7:
                preserve_visual_history(layer,at);clock['preserved_at']=at
        return q-float(owner.extra.get('captured_queue_offset',0.))

    def write_parameter(self,param,value,owner=None):
        value=max(param.minimum,min(param.maximum,float(value)))
        edit_time=self.parameter_edit_clock(owner,self.gesture_time) if isinstance(owner,Clip) else self.gesture_time
        if self.playing and not self.reviewing and self.record_automation.get():
            t=round(self.programme_time()*self.project.fps)/self.project.fps
            if isinstance(owner,Clip):t=self.parameter_edit_clock(owner,t)
            start=edit_time;mode=param.mode
            if not param.keyframes:param.add_keyframe(0,param.value)
            if self.gesture and not self.gesture.get('parameter_started',{}).get(id(param)):
                param.add_keyframe(max(0,start-1/self.project.fps),param.animated_value(start) if mode=='animate' else param.value);self.gesture.setdefault('parameter_started',{})[id(param)]=True
            param.add_keyframe(t,value);param.value=value
            if mode=='react':param.mode='react';param.combine_animation=True
        elif param.mode=='animate' or (param.mode=='react' and param.combine_animation and param.keyframes):
            mode=param.mode
            param.add_keyframe(edit_time,value)
            param.mode=mode
        else:param.value=value
        if hasattr(owner,'manual'):owner.manual=True
        param.extra['conductor_locked']=True
        if self.gesture and self.gesture.get('kind')=='program':
            self._ux39_schedule_parameter()
        else:self.changed(redraw=False)
    def transaction(self,label,fn):
        if self.gesture:self.end_gesture()
        before=project_to_dict(self.project);self.history.checkpoint_snapshot(before);t=self.programme_time() if self.playing and not self.reviewing else None
        try:
            result=fn()
            self.deck.flush_history()
            if t is not None:
                from rack_owners import preserve_clip_treatment_history
                preserve_clip_treatment_history(before,self.project,t)
                archive_styles(project_from_dict(before),self.project,t)
        except Exception as exc:
            self.project=project_from_dict(before);self.history.current=self.project
            if self.history.undo_stack:self.history.undo_stack.pop()
            self.revision+=1;self.refresh_all();self.update_status(label+': '+str(exc));self.log(traceback.format_exc())
            if not self.test_mode:messagebox.showerror(label,str(exc),parent=self)
            return None
        if before==project_to_dict(self.project):
            if self.history.undo_stack:self.history.undo_stack.pop()
        else:self.changed(redraw=True);self.persist_assets(before)
        self.refresh_all();self.update_status(label);return result
    def end_gesture(self):
        self._ux39_complete_parameter()
        if self.gesture and self.playing and not self.reviewing and self.gesture['kind']=='program':
            from rack_owners import preserve_clip_treatment_history
            preserve_clip_treatment_history(self.gesture['before'],self.project,self.gesture_time)
            archive_styles(project_from_dict(self.gesture['before']),self.project,self.gesture_time)
        super().end_gesture()
    def cancel_gesture(self):
        self._ux39_complete_parameter(discard=True)
        return super().cancel_gesture()
    def request_preview(self):
        super().request_preview()
        if self.playing:self.audio_bus.update(self.programme_snapshot())
    def write_recovery(self):
        self._autosave_after=None
        if self.test_mode:return
        if self.gesture:self._autosave_after=self.after(2000,self.write_recovery);return
        snap=self.snapshot();path=self.autosave_path
        if self._io_closed:self._safe_save(snap,path)
        else:self.io.submit(self._safe_save,snap,path)
    def _safe_save(self,p,path):
        try:
            with self.save_lock:save_project(copy.deepcopy(p),path)
        except Exception as exc:self.events.put(('log','Save: '+str(exc)))
    def save_project(self,as_new=False):
        path=None if as_new else self.project_path
        if path is None:
            chosen=filedialog.asksaveasfilename(parent=self,title='Save instrument / take',defaultextension=base.PROJECT_EXT,filetypes=[('OmN-e project','*.json')])
            if not chosen:return False
            path=Path(chosen)
        snapshot=self.snapshot();pid=self.project.id;revision=self.revision;self.update_status('Saving in background; Programme continues…')
        def work():
            try:
                with self.save_lock:save_project(copy.deepcopy(snapshot),path)
                def done():
                    if self.project.id==pid:
                        self.project_path=path
                        if self.revision==revision:self.dirty=False
                        self.update_title()
                        if hasattr(self,'recent_projects'):
                            self.recent_projects=list(dict.fromkeys([str(path),*self.recent_projects]))[:8];self.save_preferences()
                    self.update_status('Saved '+path.name)
                self.events.put(('call',done))
            except Exception as exc:self.events.put(('status','Save failed: '+str(exc)))
        self.io.submit(work);return True
    def new_project(self):
        if self.test_mode or self.confirm_discard():
            self.restore_project(new_instrument());self.load_catalogue_assets();self.refresh_library()
    def restore_project(self,project,path=None,*,new_history=True):
        if self.live.recording:
            self.update_status('Disarm input retention and let its segment finish before opening a different session.');return
        if self.output_recording or self.capture_busy:
            self.update_status('Finish the active recording/capture before replacing its session.');return
        from input_gestures import finish_active_input
        finish_active_input(self,cancel=True)
        if project.id!=self.project.id and getattr(self.live,'camera_sources',None):
            self.live.stop_camera()  # no previous project's live pixels cross a project boundary
        self.reviewing=False;self._review_state=None;self.evolve.set(False);self.mode_label.set('PROGRAMME');self._held_time=0.;super().restore_project(project,path,new_history=new_history);self.deck.scope.set('Master');self.deck.refresh(force=True)
        if path and hasattr(self,'recent_projects'):
            self.recent_projects=list(dict.fromkeys([str(Path(path)),*self.recent_projects]))[:8];self.save_preferences()
    def review_take(self,take,path=None):
        from input_gestures import finish_active_input
        finish_active_input(self)
        if self.reviewing and self.project.id==take.id:
            self.update_status('Reviewing current Draft · edits and Undo are preserved')
            return
        if self.reviewing and self.project.id!=take.id:self._remember_take(self.project,self.project_path)
        if not self.reviewing:self._review_state={'project':self.project,'history':self.history,'path':self.project_path,'dirty':self.dirty,'revision':self.revision};self._held_time=self.playhead
        self.reviewing=True;self.project=take;self.history=ProjectHistory(take);self.project_path=Path(path) if path else None;self.dirty=False;self.revision+=1;self.selected_layer_id=take.layers[0].id;self.selected_clip_id=None;self.selected_transition_id=None;self.selected_asset_id=None;self.gesture=None
        bounds=take.extra.get('capture_range',[0,take.max_end()]);self.range_in,self.range_out=bounds;self.playhead=bounds[0];self.mode_label.set('REVIEW · OFF AIR');self.thumbnails={};self.small_thumbnails={};self.thumb_pending=set();self.refresh_all();self.timeline.zoom_fit();self.update_status('Review has its own cursor. Return to Programme restores the live instrument; export uses the marked take range.')
    def go_live(self):
        if not self.reviewing:return
        self._remember_take(self.project,self.project_path)
        now=self.programme_time();saved=self._review_state;self.project=saved['project'];self.history=saved['history'];self.project_path=saved['path'];self.dirty=saved['dirty'];self.revision=max(self.revision,saved['revision'])+1;self.reviewing=False;self._review_state=None;self.playhead=now;self._held_time=now;self.range_in=self.range_out=None;self.selected_layer_id=self.project.layers[0].id;self.selected_clip_id=None;self.selected_transition_id=None;self.mode_label.set('PROGRAMME');self.thumbnails={};self.small_thumbnails={};self.thumb_pending=set();self.refresh_all();self.update_status('Programme restored · review edits remain in Drafts')
    def _remember_take(self,take,path=None):
        path=Path(path) if path else self.cfg/'captured-takes'/take.id/'Captured.omne-sequence.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        self.io.submit(self._safe_save,copy.deepcopy(take),path)
        item=next((x for x in self.takes if x['project'].id==take.id),None)
        if item:item.update(project=take,path=path)
        else:self.takes.append({'project':take,'path':path})
        self.refresh_takes()
    def open_selected_take(self):
        selected=self.take_tree.selection()
        if selected:
            item=next((x for x in self.takes if x['project'].id==selected[0]),None)
            if item:self.review_take(item['project'],item.get('path'))
    def open_take_file(self):
        path=filedialog.askopenfilename(parent=self,title='Review take without stopping Programme',filetypes=[('OmN-e project','*.json')])
        if path:
            try:self.review_take(load_project(path),path)
            except Exception as exc:messagebox.showerror('Review take',str(exc),parent=self)
    def refresh_takes(self):
        if not hasattr(self,'take_tree'):return
        self.take_tree.delete(*self.take_tree.get_children())
        for item in self.takes:self.take_tree.insert('','end',iid=item['project'].id,text=item['project'].name)
    def pause(self):
        self._held_time=self.programme_time();self.playing=False;self.audio_bus.stop()
        if not self.reviewing:self.playhead=self._held_time
        if hasattr(self,'play_button'):self.play_button.configure(text='▶ Play')
    def toggle_play(self):
        if self.playing:self.pause();return
        t=self._held_time if self.reviewing else self.playhead
        if t>=self.programme_project().max_end():t=0.
        self.play_origin=t;self.play_started_at=time.monotonic();self.playing=True;self.play_button.configure(text='Ⅱ Hold');self.restart_audio()
    def restart_audio(self):
        self.audio_bus.muted=self.mute.get()
        if not self.playing:return
        self.audio_bus.update(self.programme_snapshot())
        if (not self.audio_bus.thread or not self.audio_bus.thread.is_alive()) and not self.test_mode:self.audio_bus.start(self.programme_snapshot(),self.programme_time())
    def set_playhead(self,t):
        if self.playing and not self.reviewing:
            # Timeline selection never seeks the performance. Hold for deliberate seeking.
            self.update_status('Programme is playing. Hold it to seek, or capture a take for independent review.');return
        if hasattr(self,'viewport'):self.viewport.invalidate()
        self.playhead=max(0,min(self.project.max_end(),float(t)))
        if not self.reviewing:self._held_time=self.playhead
        self.transport_time.set(base.format_time(self.playhead)+' / '+base.format_time(self.project.max_end()))
        if hasattr(self,'timeline'):self.timeline.draw_playhead();self.deck.refresh();self.viewport.request()
    def extend_continuous_sources(self,p,now):
        changed=False
        for layer in p.layers:
            for clip in layer.clips:
                if clip.extra.get('continuous') and not clip.locked and not clip.timing_locked and not layer.locked and clip.end<now+12:
                    if not any(c is not clip and c.start>clip.start for c in layer.clips):
                        clip.duration=max(clip.duration,now+45-clip.start);changed=True
        if changed:
            p.duration=max(p.duration,now+45)
            if self.reviewing:self._review_state['revision']+=1
            else:self.revision+=1
            self.timeline.schedule()
        return any(c.extra.get('continuous') for l in p.layers for c in l.clips)
    def clock(self):
        if self.closing:return
        if getattr(self,'_clock_running',False):return
        token=getattr(self,'_clock_after',None)
        if token:
            try:self.after_cancel(token)
            except tk.TclError:pass
        self._clock_after=None;self._clock_running=True
        self._heartbeat_count=getattr(self,'_heartbeat_count',0)+1
        self._heartbeat_at=time.monotonic()
        try:self._clock_tick()
        except Exception:self._phase_error('Transport')
        finally:
            self._clock_running=False
            if not self.closing:self._clock_after=self.after(40,self.clock)
    def _clock_ui(self):
        # Rendering/transport requests do not depend on a control panel refresh.
        try:
            self.timeline.draw_playhead()
            now=time.monotonic()
            if now-getattr(self,'_last_controls_at',-1.)>=.10:
                if not (self.gesture and self.gesture.get('kind')=='program'):
                    self.deck.refresh()
                self._last_controls_at=now
        except Exception:self._phase_error('Control refresh')
    def _clock_tick(self):
        if self.closing:return
        now=self.programme_time();p=self.programme_project()
        self.live_button.configure(text='Inputs ●' if self.live.camera or self.live.microphone else 'Inputs…')
        self.mic_button.configure(text='Mic ●' if self.live.source_states().get(__import__('sound_routes').source_id(self.last_microphone_device),{}).get('state')=='live' else 'Mic')
        if self.playing:
            continuous=self.extend_continuous_sources(p,now)
            if self.output_recording or self.evolve.get() or self.live.camera or self.live.recording or continuous or (p.extra.get('music_queue_policy')=='repeat' and __import__('music_queue').items(p)) or any(l.enabled and (l.extra.get('queue_policy')=='repeat' and l.clips or mode_at(l,now)['mode']=='hold') for l in p.layers):
                if p.duration<now+15:
                    p.duration=now+45
                    if self.reviewing:self._review_state['revision']+=1
                    else:self.revision+=1
            elif now>=p.max_end():self.pause();now=self.programme_time()
            if not self.reviewing:self.playhead=now
            self.transport_time.set(base.format_time(self.playhead)+(' · LIVE '+base.format_time(now) if self.reviewing else ' / '+base.format_time(p.max_end())))
            self.viewport.request();self._clock_ui()
        elif self.live.camera or self.live.microphone:self.viewport.request();self._clock_ui()
        if self.reviewing or self.viewport.bypass.get():
            self.background_worker.submit(self.programme_revision(),self.programme_snapshot(),now,self.programme_size(),False)
        for _ in range(4):
            try:event=self.background_events.get_nowait()
            except queue.Empty:break
            if event[0]=='programme' and event[1]==self.programme_revision():self.accept_programme_frame(event[2],event[3],event[4])
            elif event[0]=='programme_error':self.log(event[-1])
        if time.monotonic()-self._last_labels>.25:
            self.refresh_voice_labels(now);self.queue_deck.refresh();self._last_labels=time.monotonic()
        if self.playing and self.evolve.get() and not self.mutating and now-self._last_evolve>=4:
            self._last_evolve=now;self.evolve_next()
        if self.retain_armed.get() and self.live.recording and not self.retention_busy and time.monotonic()-self.live.recording['clock']>=30:self.rotate_retention()
        if self.output_recording and not self.output_recording.error and not self.retention_busy:
            from recording_integrity import validate_live_state
            failure=validate_live_state(self.programme_project(),self.live,now)
            if failure:self.output_recording.error=failure
        if self.output_recording and self.output_recording.error:self.update_status('Recording needs attention: '+self.output_recording.error)
    def accept_programme_frame(self,t,image,elapsed):
        self.programme_image=image;self.programme_frame_time=t;self.programme_frame_revision=self.revision;self.programme_frame_project_id=self.project.id;self._frame_count=getattr(self,'_frame_count',0)+1;self._frame_presented_at=time.monotonic();self._last_render_ms=elapsed*1000.
        if self.output_recording:self.output_recording.submit(t,image)
        if self.output_window and self.output_window.winfo_exists():
            cv=self.output_canvas;w=max(1,cv.winfo_width());h=max(1,cv.winfo_height());ratio=min(w/image.width,h/image.height);sz=(max(1,int(image.width*ratio)),max(1,int(image.height*ratio)));self.output_photo=ImageTk.PhotoImage(image.resize(sz,Image.Resampling.BILINEAR));cv.delete('all');cv.create_image(w/2,h/2,image=self.output_photo)
    def open_output(self):
        if self.output_window and self.output_window.winfo_exists():self.output_window.deiconify();self.output_window.lift();return
        w=tk.Toplevel(self);self.output_window=w;w.title('Neospector · Output Viewer');w.geometry('960x590');w.minsize(480,320)
        tools=ttk.Frame(w,padding=(6,4));tools.pack(fill='x');ttk.Label(tools,text='OUTPUT VIEWER',style='Title.TLabel').pack(side='left')
        full=tk.BooleanVar(value=False)
        def fullscreen(value=None):
            state=(not bool(w.attributes('-fullscreen'))) if value is None else bool(value);w.attributes('-fullscreen',state);full.set(state)
        ttk.Checkbutton(tools,text='Full screen',variable=full,command=lambda:fullscreen(full.get())).pack(side='right',padx=(5,0));ttk.Button(tools,text='Close',command=w.destroy).pack(side='right')
        self.output_canvas=tk.Canvas(w,bg='black',highlightthickness=0);self.output_canvas.pack(fill='both',expand=True)
        w.bind('<F11>',lambda e:fullscreen());w.bind('<Escape>',lambda e:fullscreen(False))
        if self.programme_image:self.accept_programme_frame(self.programme_frame_time,self.programme_image,0)
    def save_preferences(self):
        super().save_preferences()
        try:
            path=self.preferences_path;data=json.loads(path.read_text());data.update(preview_quality=self.viewport.quality.get(),camera_device=self.last_camera_device,microphone_device=self.last_microphone_device,import_folder=self.last_import_folder,recent_import_folders=self.recent_import_folders);path.write_text(json.dumps(data,indent=2))
        except (OSError,ValueError):pass
    def load_layout(self,pref):
        def apply():
            if self.closing:return
            self.update_idletasks();d=pref.get('layout',{});w=self.workspace_panes.winfo_width();h=self.main_panes.winfo_height();self.main_panes.sashpos(0,int(d.get('main',max(345,h*.52))));self.workspace_panes.sashpos(0,int(d.get('workspace0',max(240,w*.20))));self.workspace_panes.sashpos(1,int(d.get('workspace1',w-295)));self.timeline.zoom_fit()
        self.after(150,apply)
    def refresh_all(self):
        super().refresh_all()
        if hasattr(self,'voice_labels'):self.refresh_voice_labels(self.programme_time());self.refresh_ingredients()
    def refresh_voice_labels(self,t):
        p=self.project;cursor=self.playhead if self.reviewing else t
        for role,v in self.voice_labels.items():
            l=next((l for l in p.layers if l.extra.get('voice')==role),None)
            active=[c for c in l.clips if c.start<=cursor<c.end] if l else []
            a=p.asset(max(active,key=lambda c:c.start).asset_id) if active else None
            text=(a.name[:27] if a else 'Empty · choose a source') if l else 'Legacy project'
            if v.get()!=text:v.set(text)
        sound_key=(id(self.programme_project()),self.programme_revision())
        if getattr(self,'_sound_label_key',None)!=sound_key:self._sound_label_events=sound_events(self.programme_project());self._sound_label_key=sound_key
        sounds=self._sound_label_events;active=[e for e in sounds if e['start']<=t<e['start']+e['duration']];names=[self.programme_project().asset(e['asset_id']).name for e in active];self.audio_info.set('Sound · '+(' + '.join(names)[:110] if names else 'none'))
        if self.retain_armed.get():self.retention_info.set('● Input history armed\n'+(f'{len(self.recorded_segments)} completed segments' if self.recorded_segments else 'Recording first segment'))
    def focus_voice(self,role):
        l=next((l for l in self.project.layers if l.extra.get('voice')==role),None)
        if not l:return self.update_status('This is a legacy composition. Use its layer headers, or start a new instrument.')
        self.selected_layer_id=l.id;self.selected_clip_id=None;self.follow_playhead.set(True);self.deck.scope.set('Layer');self.deck.refresh(force=True);self.timeline.schedule()
    def refresh_library(self):
        if not hasattr(self,'library'):return
        album=self.album.get();members=self.catalog.member_ids(album) if album!='all' else None
        assets=[a for a in self.project.assets.values() if members is None or a.id in members]
        key=tuple((a.id,a.name,a.path,a.duration,json.dumps(a.metadata.get('sequence_preferences',{}),sort_keys=True)) for a in assets)
        if key!=getattr(self,'_browser_key',None):self._browser_key=key;self.library.set_assets(assets)
        self.library.schedule()
        albums=self.catalog.albums();self._albums={'All media':'all',**{a['name']:a['id'] for a in albums}};self.album_box.configure(values=list(self._albums));self.album_label.set(next((n for n,i in self._albums.items() if i==album),'All media'))
    def choose_album(self):self.album.set(self._albums.get(self.album_label.get(),'all'));self.refresh_library()
    def new_album(self):
        name=simpledialog.askstring('New album','Album name (media is referenced, never moved):',parent=self)
        if name:
            aid=self.catalog.create_album(name);self.album.set(aid);self.refresh_library()
    def membership(self):
        ids=list(self.library.selection())
        if not ids:return self.update_status('Select one or more sources first. Ctrl/Cmd adds; Shift selects a range.')
        w=tk.Toplevel(self);w.title('Albums · selected sources');w.transient(self);body=ttk.Frame(w,padding=14);body.pack(fill='both',expand=True)
        albums=self.catalog.albums()
        if not albums:ttk.Label(body,text='Create an album with + beside the album selector.').pack()
        for album in albums:
            row=ttk.Frame(body);row.pack(fill='x',pady=3);ttk.Label(row,text=album['name'],width=25).pack(side='left')
            ttk.Button(row,text='Add',command=lambda a=album:self._change_members(a['id'],ids,True)).pack(side='left');ttk.Button(row,text='Remove',command=lambda a=album:self._change_members(a['id'],ids,False)).pack(side='left',padx=4)
        ttk.Button(body,text='Done',command=w.destroy).pack(anchor='e',pady=8)
    def _change_members(self,album,ids,add):
        if add:self.catalog.add_members(album,ids)
        else:self.catalog.remove_members(album,ids)
        self.refresh_library();self.update_status('Album membership updated; source files were not changed')
    def asset_selected(self,event=None):
        super().asset_selected(event)
        selected=self.library.selection()
        if len(selected)>1:self.asset_summary.set(f'{len(selected)} sources selected · batch Personality / Album available')
        elif selected:
            a=self.project.asset(selected[0]);pref=a.metadata.get('sequence_preferences',{});self.asset_summary.set(f'{a.name[:25]} · {a.kind}\n{pref.get("clip_min",self.project.conductor.clip_min):g}–{pref.get("clip_max",self.project.conductor.clip_max):g}s · weight {pref.get("weight",1):g}'+(' · sound' if a.kind=='audio' or a.metadata.get('has_audio') else ''))
    def batch_personality(self):
        selected=list(self.library.selection())
        if not selected and self.selected_asset_id:selected=[self.selected_asset_id]
        if not selected:return self.update_status('Select media to set its personality')
        from instrument_library_ui import PersonalityDialog
        PersonalityDialog(self,selected)
    def asset_preferences(self,aid):
        from instrument_library_ui import PersonalityDialog
        PersonalityDialog(self,[aid])
    def add_media(self):
        from instrument_library_ui import ImportStage
        if self.import_window and self.import_window.winfo_exists():self.import_window.lift();return
        self.import_window=ImportStage(self)
    def add_song(self):
        self.add_media();self.import_window.use.set('Add to sound queue')
    def import_files(self,paths,as_song=False,album=None,staged=None,use='Library only'):
        if self.importing:return self.update_status('Another import is running; allow it to finish first.')
        self.importing=True;pid=self.project.id;target_album=album or self.album.get();metadata=staged or {}
        if as_song:use='Add to sound queue'
        paths=tuple(paths)
        def work():
            from media_browser_model import fingerprint
            result=[];errors=[]
            for path in paths:
                try:
                    cached=metadata.get(str(Path(path).resolve()))
                    info=copy.deepcopy(cached['info']) if cached and tuple(cached.get('fingerprint',()))==tuple(fingerprint(path)) else probe_media(path)
                    kind=kind_for_path(path)
                    if as_song and not info.get('has_audio'):raise ValueError('This file has no audio stream')
                    result.append((str(Path(path).resolve()),kind,info,None))
                except Exception as exc:errors.append(Path(path).name+': '+str(exc))
            self.events.put(('call',lambda:self.accept_import_v03(pid,result,errors,as_song,target_album,use)))
        threading.Thread(target=work,name='Commit staged import',daemon=True).start();self.update_status('Importing included sources · Programme continues…')
    def accept_import_v03(self,pid,result,errors,as_song,album,use='Library only'):
        self.importing=False
        if self.project.id!=pid:return self.update_status('Import belongs to the previous editing target. Add those files to the current project again.')
        new=[]
        def do():
            for path,kind,info,analysis in result:
                a=add_asset(self.project,path=path,kind=kind,name=Path(path).name,duration=info['duration'],width=info['width'],height=info['height'],metadata=info);new.append(a);self.selected_asset_id=a.id
        if result:
            self.transaction(f'Imported {len(result)} source(s)',do)
            for a in new:self.io.submit(self.catalog.put_asset,copy.deepcopy(a))
            if album!='all':self.catalog.add_members(album,[a.id for a in new]);self.refresh_library()
            ids=[a.id for a in new]
            from import_destinations import apply
            apply(self,ids,'Add to sound queue' if as_song else use)
            self.update_status(f'Imported {len(new)} sources · '+use)
        if errors:
            self.log('\n'.join(errors));self.update_status('Some media could not be imported: '+errors[0])
            if not self.test_mode:messagebox.showerror('Import results','\n\n'.join(errors),parent=self)
    def assign_selected(self,role=None):
        aid=self.selected_asset_id
        if not aid:return self.update_status('Select a source in the Library first')
        asset=self.project.asset(aid)
        if asset and asset.kind=='audio':
            self.queue_sound_selected([aid])
            return self.update_status('Added to Music Queue · press PLAY. Use Timing to see music and pictures together.')
        role=role or self.selected_layer().extra.get('voice')
        if not self.project.instrument_mode or not role:return self.place_selected_asset()
        def do():
            now=self.programme_time() if self.playing and not self.reviewing else self.playhead
            c=assign_source(self.project,role,aid,now,performing=bool(self.playing and not self.reviewing),duration=max(60,self.project.max_end()-now));c.extra['continuous']=True;self.selected_layer_id=voice(self.project,role).id;self.selected_clip_id=c.id;self.deck.scope.set('Layer');return c
        return self.transaction('Assign source to '+role+' · persistent rack retained',do)
    def use_selected_sound(self,fade=None):
        a=self.project.asset(self.selected_asset_id)
        if not a:return
        if a.kind!='audio' and not a.metadata.get('has_audio'):return self.update_status('This source has no sound. Choose an audio file or video with an audio stream.')
        if fade is None:
            fade=simpledialog.askfloat('Sound transition','Crossfade seconds (0 = cut):',initialvalue=2.,minvalue=0,maxvalue=30,parent=self)
            if fade is None:return
        start=self.programme_time() if self.playing and not self.reviewing else self.playhead
        self.transaction('Use soundtrack · picture is unchanged',lambda:add_sound(self.project,a.id,start=start,fade=fade));self.prepare_sound_analysis()
    def prepare_sound_analysis(self,project=None):
        from sound_analysis_window import analysis_signature,analysis_window
        target=project or self.project
        if not sound_events(target):
            self._audio_analysis_key=None
            if target.extra.pop('sound_analysis_signature',None) is not None:
                if self.playing and target is self.programme_project() and target.analysis:
                    history=target.extra.setdefault('analysis_history',[])
                    origin=history[-1]['end'] if history else 0.;now=self.programme_time()
                    if now>origin:history.append({'start':origin,'end':now,'data':target.analysis})
                target.analysis=None;target.waveform=[]
                if self.reviewing and target is self.programme_project():self._review_state['revision']+=1
                else:self.changed()
            return
        snapshot=copy.deepcopy(target);key=analysis_signature(snapshot);pid=snapshot.id
        if getattr(self,'_audio_analysis_key',None)==(pid,key):return
        self._audio_analysis_key=(pid,key)
        def work():
            from audio_bus import render_audio
            folder=self.cache/'analysis';folder.mkdir(exist_ok=True);wav=folder/(new_id('mix')+'.wav')
            try:
                start,end,repeat=analysis_window(snapshot)
                render_audio(snapshot,wav,start,end,purpose='react');data=analyze_file(wav,ffmpeg=FFMPEG)
                data['offset']=start
                if repeat:data['repeat_window']=repeat
                def done():
                    p=self.programme_project() if self.programme_project().id==pid else self.project
                    if p.id!=pid or analysis_signature(p)!=key:return
                    if self.playing and p is self.programme_project():
                        history=p.extra.setdefault('analysis_history',[]);origin=history[-1]['end'] if history else 0.;now=max(start,self.programme_time())
                        if now>origin and p.analysis:history.append({'start':origin,'end':now,'data':p.analysis})
                    p.analysis=data;p.waveform=data.get('waveform',[]);p.extra['sound_analysis_signature']=key
                    if self.reviewing and p is self.programme_project():self._review_state['revision']+=1
                    else:self.changed();self.timeline.schedule()
                    self.update_status('Soundtrack mix and spectral reaction analysis ready')
                self.events.put(('call',done))
            except Exception as exc:self.events.put(('status','Soundtrack plays; mixed analysis failed: '+str(exc)))
            finally:wav.unlink(missing_ok=True)
        self.io.submit(work)
    def insert_near(self,after=False):
        found=self.current_clip();a=self.project.asset(self.selected_asset_id)
        if not found or not a:return self.update_status('Select a timeline clip and a Library replacement/source first')
        if a.kind=='audio':return self.use_selected_sound()
        l,c=found;start=c.end if after else c.start;pref=a.metadata.get('sequence_preferences',{});duration=float(pref.get('clip_min',min(5.,a.duration or 5.)))
        def do():
            new=Clip(new_id('clp'),a.id,channel=c.channel,start=start,duration=duration,manual=True,in_point=float(pref.get('source_in',0)),source_policy=pref.get('source_policy','loop'));
            if 'source_out' in pref:new.extra['source_window']=[float(pref.get('source_in',0)),float(pref['source_out'])]
            insert_clip(self.project,l,new,'insert');self.selected_clip_id=new.id;self.deck.scope.set('Clip');return new
        return self.transaction('Insert source '+('after' if after else 'before')+' selected clip',do)
    def library_menu(self,event):
        iid=self.library.identify_row(event.y)
        if not iid:return
        if iid not in self.library.selection():self.library.selection_set(iid)
        self.selected_asset_id=iid;self.asset_selected();m=tk.Menu(self,tearoff=False)
        asset=self.project.asset(iid)
        actions=[]
        if asset and asset.kind!='audio':
            actions.extend([('Assign to A',lambda:self.assign_selected('A')),('Assign to B',lambda:self.assign_selected('B')),('Assign to C',lambda:self.assign_selected('C')),('Assign to D',lambda:self.assign_selected('D')),('Replace clip, keep treatment',self.replace_current)])
        if asset and (asset.kind=='audio' or asset.metadata.get('has_audio')):
            actions.append(('Add to Music Queue',self.queue_sound_selected))
        actions.extend([('Personality / ranges…',self.batch_personality),('Albums…',self.membership),('Edit source…',lambda:self.edit_asset(iid)),('Relink…',self.relink_asset)])
        for text,fn in actions:m.add_command(label=text,command=fn)
        from contextual_surface import post_native_menu
        post_native_menu(self,m,self.library,event)
    def use_album_pool(self):
        album=self.album.get()
        if album=='all':return self.update_status('Choose an album in the Library first')
        ids=sorted(self.catalog.member_ids(album));self.transaction('Use album as procedural pool',lambda:self.project.conductor.extra.__setitem__('pool_ids',ids))
    def save_ingredient_named(self,name,kind='rack'):
        l,c=self.get_edit_target();scope=self.deck.scope.get()
        if scope=='Layer' and getattr(self.deck,'history_layer',None) is l:l=self.deck.owner
        if kind=='recipe':payload={'conductor':_encode(self.project.conductor),'source_names':[self.project.asset(i).name for i in self.project.conductor.extra.get('pool_ids',[]) if self.project.asset(i)]};payload['conductor'].get('extra',{}).pop('pool_ids',None)
        elif kind=='patch':payload={'voices':{x.extra.get('voice',x.name):style_dict(x) for x in self.project.layers},'master':_encode(self.project.master_rack),'mix':_encode(self.project.voice_mix),'mixer_mode':self.project.voice_mixer_mode,'blend':self.project.voice_blend,'source_binding':'roles; source files are not embedded'}
        elif kind=='transition':
            found=self.project.transition(self.selected_transition_id)
            if not found:raise ValueError('Select a transition bridge first')
            tr=found[1];payload={k:v for k,v in _encode(tr).items() if k not in ('id','from_clip','to_clip','start')}
        else:
            rack=self.project.master_rack if scope=='Master' else c.rack if scope=='Clip' and c else l.rack
            payload={'rack':_encode(rack)}
        saved=self.catalog.save_ingredient(name,kind,payload);self.refresh_ingredients();self.update_status('Saved '+name+' · immutable ingredient revision');return saved
    def keep_ingredient(self,kind=None):
        w=tk.Toplevel(self);w.title('Keep an ingredient');w.transient(self);b=ttk.Frame(w,padding=16);b.pack(fill='both',expand=True)
        ttk.Label(b,text='Keep what worked',style='Title.TLabel').pack(anchor='w');v=tk.StringVar(value=kind or ('transition' if self.deck.scope.get()=='Transition' else 'rack'));name=tk.StringVar(value='My '+v.get())
        ttk.Combobox(b,textvariable=v,values=['rack','patch','recipe','transition'],state='readonly').pack(fill='x',pady=8);ttk.Entry(b,textvariable=name,width=44).pack(fill='x');ttk.Label(b,text='Racks and patches keep animation and reaction mappings.\nPatches bind to visual channel roles, not original filenames.\nRecipes preserve allowed ranges and probabilities.',style='Muted.TLabel',justify='left').pack(pady=10)
        def save():
            try:self.save_ingredient_named(name.get(),v.get());w.destroy()
            except Exception as exc:messagebox.showerror('Keep',str(exc),parent=w)
        ttk.Button(b,text='Save ingredient · keep playing',command=save).pack(anchor='e')
    def refresh_ingredients(self):
        if not hasattr(self,'ingredients_tree'):return
        entries=self.catalog.ingredients()
        if not entries:
            for name in ('Generation Loss','Compact Scan','CCD Afterglow','Chroma Bleed','Liquid Motion','River Memory'):self.catalog.save_ingredient(name,'rack',{'rack':_encode(make_look(name))})
            entries=self.catalog.ingredients()
        key=tuple((e['id'],e['revision']) for e in entries)
        if key==getattr(self,'_ingredients_key',None):return
        self._ingredients_key=key;self.ingredients_tree.delete(*self.ingredients_tree.get_children())
        for e in entries:self.ingredients_tree.insert('','end',iid=e['id'],text=e['name']+f' · r{e["revision"]}',values=(e['kind'],))
    def apply_ingredient(self,ingredient):
        payload=copy.deepcopy(ingredient['payload']);kind=ingredient['kind'];l,c=self.get_edit_target()
        def apply():
            if kind=='rack':
                from module_engine import compile_rack
                rack=[_effect_from(x) for x in payload.get('rack',[])];compile_rack(rack);owner=self.project if self.deck.scope.get()=='Master' else c if self.deck.scope.get()=='Clip' and c else self.deck.owner if self.deck.scope.get()=='Layer' else l
                if not self.can_edit(owner):return
                if owner is self.project:self.project.master_rack=rack
                else:owner.rack=rack
            elif kind=='patch':
                self.deck.history_layer=None;self.deck.history_proxy=None
                for target in self.project.layers:
                    raw=payload.get('voices',{}).get(target.extra.get('voice',target.name))
                    if raw and not target.locked:store_style(target,self.playhead,style_from(raw,target))
                self.project.master_rack=[_effect_from(x) for x in payload.get('master',[])];from sequencer_model import _parameter_from
                self.project.voice_mix=_parameter_from(payload.get('mix'),ProgrammableParameter(.35,0,1));self.project.voice_mixer_mode=payload.get('mixer_mode','blend');self.project.voice_blend=payload.get('blend','screen')
            elif kind=='recipe':self.project.conductor=project_from_dict({'conductor':payload['conductor']}).conductor
            elif kind=='transition':
                found=self.project.transition(self.selected_transition_id)
                if not found:raise ValueError('Select a transition to apply this ingredient')
                t=found[1]
                if t.locked:raise ValueError('Unlock this transition first')
                for key in ('kind','softness','easing','colour'):
                    if key in payload:setattr(t,key,payload[key])
                from sequence_edit import set_transition_duration
                set_transition_duration(self.project,t.id,float(payload.get('duration',t.duration)))
            else:raise ValueError('This ingredient type is not a supported live target in R1')
            self.project.extra.setdefault('ingredient_uses',[]).append({'id':ingredient['id'],'revision':ingredient['revision'],'name':ingredient['name']})
        return self.transaction('Apply '+ingredient['name'],apply)
    def apply_selected_ingredient(self):
        ids=self.ingredients_tree.selection()
        if ids:self.apply_ingredient(self.catalog.ingredient(ids[0]))
    def export_ingredient(self):
        ids=self.ingredients_tree.selection()
        if not ids:return
        path=filedialog.asksaveasfilename(parent=self,title='Export reusable ingredient',defaultextension='.omne-ingredient.json')
        if path:
            try:self.catalog.export_ingredient(ids[0],path);self.update_status('Ingredient exported without media files')
            except Exception as exc:messagebox.showerror('Ingredient',str(exc),parent=self)
    def import_ingredient(self):
        path=filedialog.askopenfilename(parent=self,title='Import ingredient',filetypes=[('OmN-e ingredient','*.json')])
        if path:
            try:self.catalog.import_ingredient(path);self.refresh_ingredients()
            except Exception as exc:messagebox.showerror('Ingredient',str(exc),parent=self)
    def mutate(self,seed=None,scope=None,*,evolving=False):
        if self.mutating:return self.update_status('Preparing a candidate already; current Programme is unchanged.')
        try:seed=int(self.conductor.seed.get()) if seed is None else int(seed)
        except ValueError:return self.update_status('Enter an integer seed')
        scope=scope or self.conductor.scope.get();target=self.programme_project() if evolving else self.project;pid=target.id;revision=self.programme_revision() if evolving else self.revision
        if scope=='effects' and not evolving and self.deck.scope.get()!='Clip' and target.instrument_mode:
            start=self.programme_time() if self.playing and not self.reviewing else self.playhead
            return self.transaction('Vary voice effects · source sequence preserved',lambda:vary_rack(self.project,seed,self.selected_layer_id,start=start,duration=2))
        snapshot=copy.deepcopy(target);now=self.programme_time();live_target=target is self.programme_project() and self.playing
        interval=(now+.25,max(now+35,snapshot.duration)) if evolving else tuple(sorted((self.range_in,self.range_out))) if scope=='range' and self.range_in is not None and self.range_out is not None else (now,snapshot.max_end()) if live_target else None
        if evolving:snapshot.duration=now+45;interval=(now+.25,snapshot.duration)
        layer_id=self.selected_layer_id if scope in ('layer','channel','media','effects','motion','transitions') and not evolving else None;channel=self.selected_channel.get() if scope=='channel' else None
        self.mutating=True;self.mutation_ticket+=1;ticket=self.mutation_ticket;self.update_status('Preparing '+scope+' variation · Programme continues…')
        def work():
            try:
                count=mutate_instrument(snapshot,seed,scope=scope,layer_id=layer_id,channel=channel,time_range=interval)
                def commit():
                    self.mutating=False
                    current=self.programme_project() if evolving else self.project;rev=self.programme_revision() if evolving else self.revision
                    if ticket!=self.mutation_ticket or current.id!=pid or rev!=revision:return self.update_status('Candidate discarded: you edited its target while it was preparing. Current work is preserved.')
                    if evolving and self.reviewing:self._review_state['project']=snapshot;self._review_state['history'].current=snapshot;self._review_state['revision']+=1;self._review_state['dirty']=True
                    else:
                        self.history.checkpoint();self.project=snapshot;self.history.current=snapshot;self.changed(redraw=True);self.refresh_all()
                    self.update_status('Conductor prepared future material' if evolving else 'Variation ready · manual edits and locks preserved');self.audio_bus.update(self.programme_snapshot())
                self.events.put(('call',commit))
            except Exception as exc:
                msg=str(exc)
                def fail():self.mutating=False;self.update_status('Mutation: '+msg);self.log('Mutation: '+msg)
                self.events.put(('call',fail))
        self._mutation_thread=threading.Thread(target=work,name='Conductor resolver',daemon=True);self._mutation_thread.start()
    def toggle_evolve(self):
        if self.evolve.get():
            if not self.playing:self.toggle_play()
            self._last_evolve=-1.;self.update_status('Conductor evolves future material. Hold Evolve to stop decisions, not playback.')
        else:self.update_status('Conductor held · sources, effects and audio continue')
    def evolve_next(self):
        p=self.programme_project();now=self.programme_time();options=p.conductor.extra;seed=p.mutation_seed+int(now//4)+1
        interval=max(3.,float(options.get('treatment_interval',12)))
        if options.get('evolve_treatment',DEFAULTS['evolve_treatment']) and now-self._last_treatment>=interval:
            self._last_treatment=now;before=copy.deepcopy(p);vary_rack(p,seed,start=now,duration=max(1.,interval*.8))
            if any(len(a.rack)!=len(b.rack) for a,b in zip(before.layers,p.layers)):archive_styles(before,p,now)
            if self.reviewing:self._review_state['revision']+=1;self._review_state['dirty']=True
            else:self.changed();self.deck.refresh(force=True)
        if options.get('evolve_sound',DEFAULTS['evolve_sound']):
            events=sound_events(p);finish=max((e['start']+e['duration'] for e in events),default=now)
            if finish<now+3:
                pool=[a for a in p.assets.values() if (a.kind=='audio' or a.metadata.get('has_audio')) and a.duration>2 and a.metadata.get('sequence_preferences',{}).get('enabled',True) and a.metadata.get('sequence_preferences',{}).get('weight',1)>0]
                eligible=[a for a in pool if a.id!=p.audio_asset_id] or pool
                if eligible:
                    from conductor import stream
                    rng=stream(seed,'soundtrack');a=rng.choices(eligible,weights=[a.metadata.get('sequence_preferences',{}).get('weight',1) for a in eligible],k=1)[0]
                    self.install_sound(p,a.id,start=max(now+.15,finish-1.5),fade=min(1.5,max(0.,finish-now-.15)))
        if not options.get('evolve_sources',DEFAULTS['evolve_sources']):return
        last=min([max((c.end for c in l.clips),default=0) for l in p.layers[:2]] or [0])
        if last>now+20:return
        self.mutate(seed,scope='sequence',evolving=True)
    def install_sound(self,p,aid,*,start=0.,fade=0.,in_point=0.,duration=None):
        add_sound(p,aid,start=start,fade=fade,in_point=in_point,duration=duration)
        if self.reviewing and p is self.programme_project():self._review_state['revision']+=1;self._review_state['dirty']=True
        else:self.changed()
        self.prepare_sound_analysis(project=p)
    def open_example(self):
        root=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1];path=root/'examples/First Light.omne-sequence.json'
        try:
            original=load_project(path);p=new_instrument();p.name='First Light · Visual Instrument';p.assets=copy.deepcopy(original.assets);p.audio_asset_id=original.audio_asset_id;p.analysis=original.analysis;p.waveform=original.waveform;p.duration=original.duration;p.width=1280;p.height=720;p.fps=30;p.conductor.clip_min=3;p.conductor.clip_max=6;p.conductor.layering=.5;p.conductor.intensity=.25;p.conductor.reaction=.55
            p.conductor.extra['pool_ids']=[a.id for a in p.assets.values() if a.kind in ('video','image')];mutate_instrument(p,731)
            voice(p,'A').rack=make_look('Chroma Bleed');voice(p,'B').rack=[make_effect('mirror')];p.voice_mix.value=.3
            for fx in voice(p,'A').rack:
                for par in fx.params.values():
                    if par.maximum<=1:par.value=min(par.value,.12)
            self.restore_project(p);self.set_playhead(2.);self.update_status('First Light · choose A or B, play the effects rack, then Keep what works')
        except Exception as exc:self.log(traceback.format_exc());self.update_status('Example: '+str(exc))
    def soundtrack_dialog(self):
        from instrument_sound_ui import SoundtrackDialog
        SoundtrackDialog(self)
    def open_live(self):
        from sound_panel import SoundSourcesWindow
        if self.live_window and self.live_window.winfo_exists():self.live_window.lift();return
        self.live_window=SoundSourcesWindow(self)
    def toggle_retention(self):
        if self.retention_busy:return self.update_status('Finishing the current input-history segment…')
        if self.retain_armed.get():
            if not ((self.live.camera and self.live.camera.state=='live') or (self.live.microphone and self.live.microphone.state=='live')):
                self.retain_armed.set(False);self.update_status('Start a live input, wait for its signal, then arm retention.');return
            if not self.playing:self.toggle_play()
            try:self.live.start_recording(self.cache/'input-history',self.programme_time());self.update_status('Input history armed · raw camera / audio retained locally in 30-second segments')
            except Exception as exc:self.retain_armed.set(False);self.update_status(str(exc))
        elif self.live.recording:self.rotate_retention(restart=False)
        else:self.retention_info.set('Live history off · file-based performance remains editable')
    def _roll_inputs(self,restart=True):
        with self.retention_lock:
            if self.live.recording:
                take=self.live.stop_recording();self.recorded_segments.append(take)
                if take.get('error'):self.events.put(('status','Retained input reported: '+take['error']))
            if restart and not self.closing and self.retention_enabled:self.live.start_recording(self.cache/'input-history',self.programme_time())
            return list(self.recorded_segments)
    def retention_cutoff(self,now):
        cutoff=now-600
        return min(cutoff,self.output_retention_start) if self.output_retention_start is not None else cutoff
    def rotate_retention(self,restart=True):
        if self.retention_busy:return
        self.retention_busy=True
        def work():
            try:
                self._roll_inputs(restart)
                # Raw rolling segments older than ten minutes expire unless copied
                # into a captured take. Deletions are restricted to our own cache.
                with self.retention_lock:
                    cutoff=self.retention_cutoff(self.programme_time());old=[s for s in self.recorded_segments if s['start']+s['duration']<cutoff];self.recorded_segments=[s for s in self.recorded_segments if s not in old]
                    for s in old:
                        for key in ('video','audio','manifest'):
                            path=Path(s[key]) if s.get(key) else None
                            if path and path.parent.resolve()==(self.cache/'input-history').resolve():path.unlink(missing_ok=True)
                self.events.put(('status','Input history ready · '+str(len(self.recorded_segments))+' retained segments'))
            except Exception as exc:self.events.put(('status','Input history: '+str(exc)))
            finally:self.retention_busy=False
        threading.Thread(target=work,name='Retain live history',daemon=True).start()
    def capture_recent(self):
        if self.capture_busy:return self.update_status('A capture is being finalised; Programme continues.')
        try:seconds=float(self.capture_seconds.get())
        except ValueError:return self.update_status('Enter capture length in seconds')
        limit=self.retention_limits()['seconds'] if hasattr(self,'retention_limits') else 600
        if not math.isfinite(seconds) or not 0<seconds<=limit:return self.update_status(f'Capture length must be between 0 and {limit:g} seconds')
        end=self.programme_time();start=max(0,end-seconds)
        if end-start<.1:return self.update_status('Play a little of the instrument before capturing its history')
        snapshot=copy.deepcopy(self.programme_project());self.capture_busy=True;self.update_status('Pinning recent history · Programme keeps playing…')
        folder=self.cfg/'captured-takes'/new_id('take');folder.mkdir(parents=True,exist_ok=True)
        reservation=self.reserve_history(start,end) if hasattr(self,'reserve_history') else None
        def work():
            try:
                with self.retention_lock:
                    segments=self._roll_inputs(restart=True) if self.live.recording else list(self.recorded_segments)
                from contextlib import nullcontext
                with (nullcontext() if reservation else self.retention_lock):
                    take=capture_with_recordings(snapshot,start,end,segments)
                    # Copy retained recordings to durable take storage before they
                    # are eligible for cache eviction. Original user media stays linked.
                    mapping={}
                    for asset in take.assets.values():
                        source=Path(asset.path) if asset.path else None
                        if source and source.is_file() and source.parent.resolve()==(self.cache/'input-history').resolve():
                            target=folder/source.name
                            if str(source) not in mapping:shutil.copy2(source,target);mapping[str(source)]=str(target)
                            asset.path=mapping[str(source)]
                    path=folder/'Captured.omne-sequence.json';save_project(take,path)
                def done():
                    self.capture_busy=False;self._remember_take(take,path)
                    if hasattr(self,'capture_draft_ready'):self.capture_draft_ready(take,path)
                    else:
                        tab=next((tab for tab in self.library_tabs.tabs() if self.library_tabs.tab(tab,'text')=='Takes'),None)
                        if tab:self.library_tabs.select(tab)
                    self.update_status(f'Captured {end-start:.1f}s · Draft saved locally. Review it without stopping Programme.')
                self.events.put(('call',done))
            except Exception as exc:
                msg=str(exc);self.events.put(('call',lambda:self._capture_failed(msg)))
            finally:
                if reservation:self.release_history(reservation)
        threading.Thread(target=work,name='Capture recent performance',daemon=True).start()
    def _capture_failed(self,msg):
        self.capture_busy=False;self.update_status('Capture: '+msg);self.log('Capture: '+msg)
        if not self.test_mode:messagebox.showerror('Capture needs retained inputs',msg,parent=self)
    def toggle_output_record(self):
        if self.output_busy:return self.update_status('Finishing recording; Programme continues…')
        if self.output_recording:
            rec=self.output_recording;self.output_recording=None;self.output_busy=True;end=min(self.programme_time(),getattr(self,'_record_stop_at',math.inf));snapshot=copy.deepcopy(self.programme_project());path=self.output_path
            if hasattr(self,'refresh_record_controls'):self.refresh_record_controls()
            elif hasattr(self,'record_button'):self.record_button.configure(text='Finalising…')
            self.update_status('Finishing output recording without stopping Programme…')
            def finish():
                try:
                    from sound_routes import external_intervals
                    from recording_integrity import prepare_recording_integrity
                    needs_retained=bool(external_intervals(snapshot,'sound',rec.start,end) or external_intervals(snapshot,'react',rec.start,end))
                    with self.retention_lock:
                        segments=self._roll_inputs(restart=not self.output_auto_retention) if needs_retained and self.live.recording else list(self.recorded_segments)
                    integrity=prepare_recording_integrity(snapshot,rec.start,end,segments)
                    rec.finish(snapshot,end,path,integrity=integrity);self.events.put(('status','Programme recording validated · '+str(path)))
                except Exception as exc:self.events.put(('status','Recording could not finish: '+str(exc)));self.events.put(('log',traceback.format_exc()));rec.close()
                finally:self.events.put(('call',lambda:self._recording_done()))
            threading.Thread(target=finish,name='Finalise Programme recording',daemon=True).start();return
        if self.reviewing:return self.update_status('Return to Programme before recording new output.')
        prepared=self.prepare_output_recording() if hasattr(self,'prepare_output_recording') else None
        if prepared is None and hasattr(self,'prepare_output_recording'):return
        if prepared is None:
            path=filedialog.asksaveasfilename(parent=self,title='Record actual Programme output (new file)',defaultextension='.mp4',filetypes=[('MP4','*.mp4')])
            if not path:return
            prepared={'path':Path(path),'profile':'web','size':self.programme_size(),'fps':20}
        path=Path(prepared['path'])
        try:
            from recording_integrity import preflight_recording
            # Validate before transport/device side effects. A second live check is
            # made after Play starts and immediately before the recorder is created.
            plan=preflight_recording(self.programme_project(),self.live,path,self.programme_time())
            if not self.playing:self.toggle_play()
            if plan['needs_retention'] and not self.live.recording:
                self.output_auto_retention=not bool(self.retain_armed.get())
                self.retain_armed.set(True);self.toggle_retention()
                if not self.live.recording:raise ValueError('Cannot record: retained audio could not be armed for a contributing Sound/React route.')
            start_time=self.programme_time();plan=preflight_recording(self.programme_project(),self.live,path,start_time)
            directory=self.cache/'recordings'/new_id('record');self.output_path=path
            self.output_recording=OutputRecorder(directory,start_time,tuple(prepared['size']),fps=int(prepared['fps']),profile=str(prepared.get('profile','web')))
            # Start from the picture currently presented to the performer. A
            # short take may end before the next asynchronous Programme frame;
            # its first held frame must still be the actual current output.
            image=self.programme_image
            if (image is not None and image is self.viewport.image
                    and getattr(self,'programme_frame_project_id',None)==self.project.id
                    and not self.viewport.bypass.get()):
                self.output_recording.submit(start_time,image)
            self.output_retention_start=self.output_recording.start;self.output_integrity=plan
            if not getattr(self,'_recording_kind',None):self._recording_kind='manual'
            if hasattr(self,'refresh_record_controls'):self.refresh_record_controls()
            elif hasattr(self,'record_button'):self.record_button.configure(text='■ Stop recording')
            retained=' · retained Sound/React armed' if plan['needs_retention'] else ''
            self.update_status(f'Recording Programme · {prepared["size"][0]} × {prepared["size"][1]} · {prepared["fps"]} fps · {prepared.get("profile","web")}{retained}')
        except Exception as exc:
            if self.output_auto_retention:
                self.retain_armed.set(False)
                if self.live.recording:self.rotate_retention(restart=False)
            self.output_auto_retention=False;self.output_recording=None;self.output_integrity=None;self._recording_kind=None
            if hasattr(self,'refresh_record_controls'):self.refresh_record_controls()
            self.update_status('Recording: '+str(exc))
    def _recording_done(self):
        if self.output_auto_retention:
            self.retain_armed.set(False)
            if self.live.recording:self.rotate_retention(restart=False)
        self._record_stop_at=math.inf;self.output_retention_start=None;self.output_integrity=None;self.output_auto_retention=False;self.output_busy=False;self._recording_kind=None;self._recording_sequence_label='';self._duration_record=None
        if hasattr(self,'refresh_record_controls'):self.refresh_record_controls()
        elif hasattr(self,'record_button'):self.record_button.configure(text='● Record output')
    def start_export(self,path,profile='web',size=None,start=0.,end=None,overwrite=False):
        if self.rendering:return
        self.rendering=True;self.render_cancel=threading.Event();self.cancel_button.configure(state='normal');self.progress['value']=0;snapshot=copy.deepcopy(self.project);report=self.cache/'exports'/new_id('job');report.mkdir(parents=True);self.last_diagnostics=report
        def work():
            try:
                (report/'project.omne-sequence.json').write_text(json.dumps(project_to_dict(snapshot),indent=2))
                result=render_project(snapshot,path,start=start,end=end,profile=profile,size=size,overwrite=overwrite,cancel=self.render_cancel,diagnostics_dir=report,progress=lambda text:self.events.put(('export_progress',text)));self.events.put(('export_done',str(result),str(report)))
            except Cancelled:self.events.put(('export_cancelled',str(report)))
            except Exception as exc:(report/'failure.txt').write_text(traceback.format_exc());self.events.put(('export_failed',str(exc),str(report)))
        threading.Thread(target=work,name='Independent take export',daemon=True).start();self.update_status('Exporting a frozen snapshot. Programme and its decoder remain independent.')
    def quick_guide(self):return self.quick_guide_refined()
    def close(self,force=False):
        if self.closing:return
        if not force and self.rendering:
            if not messagebox.askyesno('OmN-e Sequencer','Cancel the running export and close?',parent=self):return
            self.render_cancel.set()
        if not force and (self.output_recording or self.output_busy or self.capture_busy):
            messagebox.showinfo('Finish capture first','Stop and finalise recording/capture before closing. Programme is still running.',parent=self);return
        if not force and not self.confirm_discard():return
        if self.output_recording:self.output_recording.close();self.output_recording=None
        if getattr(self,'route_analysis_job',None):
            try:self.after_cancel(self.route_analysis_job)
            except tk.TclError:pass
        self.evolve.set(False);self.retain_armed.set(False);self.mutation_ticket+=1;self.audio_bus.stop()
        if hasattr(self,'background_worker'):self.background_worker.close()
        if self.reviewing:self._remember_take(self.project,self.project_path)
        # Allow already-started saves to finish before closing the local catalogue.
        self._io_closed=True
        self.io.shutdown(wait=True,cancel_futures=True)
        try:self.catalog.close()
        except Exception:pass
        if hasattr(self,'stop_camera_tasks'):self.stop_camera_tasks()
        self.live.close()
        super().close(force=True)
