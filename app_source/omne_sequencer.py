#!/usr/bin/env python3
"""OmN-e Sequencer v0.2: native local-first audiovisual authoring."""
from __future__ import annotations
import copy, json, math, os, platform, queue, random, subprocess, sys, threading, time, traceback, webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog,colorchooser
from PIL import Image,ImageTk
from builtin_themes import BUILTIN_THEMES,DEFAULT_THEME_NAME,PUBLISHED_THEME_ORDER
from ui_chrome import configure_theme,load_user_themes,resolve_theme_preference,retheme_native_tk_scales,ResizablePane,ToolTip
from family_chrome import FamilyChromeMixin
from sequencer_model import *
from sequence_edit import *
from media_engine import FFMPEG,FFPROBE,FFPLAY,kind_for_path,probe_media,ffplay_audio_command,render_project,EXPORT_PROFILES
from signal_engine import analyze_file,SignalEvaluator
from frame_sources import FrameSources
from process_tools import stop_process,Cancelled,popen_options
from live_sources import LiveInputs
from conductor_view import ConductorView
from timeline_view import TimelineView
from programme_view import ProgrammeView
from control_deck import ControlDeck

APP='Neospector'
from release_identity import VERSION
APP_ID='omne-sequencer'
PROJECT_EXT='.omne-sequence.json'
TEXT_INPUT_WIDGET_CLASSES={'Entry','TEntry','Text','Spinbox','TSpinbox','TCombobox'}

def shortcut_allowed_for_widget_class(widget_class):return str(widget_class or '') not in TEXT_INPUT_WIDGET_CLASSES

def config_dir():
    if os.environ.get('OMNE_SEQUENCER_SANDBOX'):return Path(os.environ['OMNE_SEQUENCER_SANDBOX'])/'config'
    if os.name=='nt':return Path(os.environ.get('APPDATA',Path.home()/'AppData/Roaming'))/'OmN-e Sequencer'
    if sys.platform=='darwin':return Path.home()/'Library/Application Support/OmN-e Sequencer'
    return Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/APP_ID

def cache_dir():
    if os.environ.get('OMNE_SEQUENCER_SANDBOX'):return Path(os.environ['OMNE_SEQUENCER_SANDBOX'])/'cache'
    if os.name=='nt':return Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'OmN-e Sequencer'
    if sys.platform=='darwin':return Path.home()/'Library/Caches/OmN-e Sequencer'
    return Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/APP_ID

def open_path(path):
    if os.name=='nt':os.startfile(str(path))
    else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def format_time(t):
    t=max(0.,t);return f'{int(t//60):02d}:{t%60:05.2f}'

class SequencerApp(FamilyChromeMixin,tk.Tk):
    def __init__(self,test_mode=False):
        super().__init__()
        from ui_collection import activate
        activate(self)
        self.test_mode=test_mode;self.app_name=APP;self.cfg=config_dir();self.cfg.mkdir(parents=True,exist_ok=True)
        self.cache=cache_dir()/'v02';self.cache.mkdir(parents=True,exist_ok=True);self.log_path=self.cache/'session.log'
        self.preferences_path=self.cfg/'preferences-v02.json';self.user_theme_path=self.cfg/'user_themes.json';self.autosave_path=self.cfg/'recovery'/'v02-autosave.omne-sequence.json'
        self.user_themes=load_user_themes(self.user_theme_path);self.published_themes=list(PUBLISHED_THEME_ORDER);self.theme_library=copy.deepcopy(BUILTIN_THEMES);self.theme_library.update(copy.deepcopy(self.user_themes));self.available_themes=list(dict.fromkeys(self.published_themes+list(self.user_themes)))
        pref=self.read_preferences();initial=resolve_theme_preference(pref.get('theme_name'),self.user_themes,self.published_themes)
        self.ui_chrome=copy.deepcopy(self.theme_library[initial]);self.theme_name=tk.StringVar(value=initial);self.tooltips_enabled=tk.BooleanVar(value=bool(pref.get('tooltips',True)));self.show_startup=tk.BooleanVar(value=bool(pref.get('show_startup',True)));self.tip_instances=[];self.startup_window=None
        configure_theme(self,self.ui_chrome);self.refine_widget_theme();self.geometry(pref.get('geometry','1440x940'));self.minsize(1080,740);self.title(APP+' '+VERSION)
        self.project=Project();self.project.ensure_layer();self.history=ProjectHistory(self.project);self.project_path=None;self.dirty=False;self.revision=0;self._snapshot_revision=-1;self._snapshot=None;self._signal_revision=-1;self._signals=None
        self.playhead=0.;self.playing=False;self.play_origin=0.;self.play_started_at=0.;self.audio_process=None;self.selected_layer_id=self.project.layers[0].id;self.selected_clip_id=None;self.selected_transition_id=None;self.selected_asset_id=None
        self.record_automation=tk.BooleanVar(value=True);self.follow_playhead=tk.BooleanVar(value=True);self.selected_channel=tk.StringVar(value='A');self.gesture=None;self.gesture_time=0.;self.range_in=None;self.range_out=None;self.events=queue.Queue();self.live=LiveInputs();self.thumbnails={};self.small_thumbnails={};self.thumb_pending=set();self.thumb_queue=queue.Queue(maxsize=300);self.closing=False
        self.status=tk.StringVar(value='Ready · local files · source media stays untouched');self.transport_time=tk.StringVar(value='00:00.00');self.mute=tk.BooleanVar(value=False);self.rendering=False;self.render_cancel=threading.Event();self.importing=False;self.last_diagnostics=None;self._autosave_after=None;self._preview_after=None;self._deck_after=None;self.last_error='';self.live_window=None
        self.build_ui();self.bind_shortcuts();self.load_layout(pref);self.protocol('WM_DELETE_WINDOW',self.close)
        self.thumb_thread=threading.Thread(target=self.thumbnail_worker,name='Media thumbnails',daemon=True);self.thumb_thread.start()
        self._poll_after=self.after(40,self.poll_events);self._clock_after=self.after(80,self.clock);self.refresh_all()
        if not test_mode:
            if self.autosave_path.exists():self.after(500,self.offer_recovery)
            elif self.show_startup.get():self.after(300,self.show_startup_window)
        self.log('START '+VERSION+' '+platform.platform())
    def focus_get(self):
        """Tk can focus native menu/combobox windows absent from Python's widget tree."""
        try:return super().focus_get()
        except (KeyError,tk.TclError):return None
    def _phase_error(self,phase):
        # One UI fault must not permanently kill a transport or mailbox timer.
        now=time.monotonic();errors=getattr(self,'_phase_errors',{})
        item=errors.setdefault(phase,{'count':0,'last_logged':-100.})
        item['count']+=1;item['message']=str(sys.exc_info()[1])
        if now-item['last_logged']>5:
            self.log(phase+' (continuing): '+traceback.format_exc());item['last_logged']=now
            self.update_status(phase+' needs attention · playback continues · Diagnostics records the error')
        self._phase_errors=errors
    def t(self,key,default):return default
    def format_time(self,t):return format_time(t)
    def log(self,text):
        try:
            with self.log_path.open('a',encoding='utf-8') as f:f.write(time.strftime('%Y-%m-%d %H:%M:%S')+' '+text+'\n')
        except OSError:pass
    def report_callback_exception(self,exc_type,exc,tb):
        text=''.join(traceback.format_exception(exc_type,exc,tb));self.log(text);self.update_status('Interface error: '+str(exc)+' · Diagnostics retains the traceback')
        if self.test_mode:sys.stderr.write(text)
    def add_tip(self,widget,text):
        if text=='theme':text='The same six approved Funk presets and Theme Studio as Retrospector.'
        if len(self.tip_instances)>160:self.clean_tips()
        tip=ToolTip(widget,text,self.ui_chrome);tip.set_enabled(self.tooltips_enabled.get());self.tip_instances.append(tip);return widget
    def build_ui(self):
        root=ttk.Frame(self,padding=6);root.pack(fill='both',expand=True);root.columnconfigure(0,weight=1);root.rowconfigure(1,weight=1)
        menu=tk.Menu(self);self.configure(menu=menu)
        file=tk.Menu(menu,tearoff=False);menu.add_cascade(label='File',menu=file)
        for text,cmd in [('New sequence',self.new_project),('Open…',self.open_project),('Save',self.save_project),('Save as…',lambda:self.save_project(as_new=True)),('Sequence settings…',self.sequence_settings),('Export…',self.export_video),('Export diagnostics…',self.export_diagnostics),('Exit',self.close)]:file.add_command(label=text,command=cmd)
        edit=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Edit',menu=edit)
        for text,cmd in [('Undo',self.undo),('Redo',self.redo),('Split at playhead',self.split_current),('Duplicate clip',self.duplicate_current),('Replace media, keep treatment',self.replace_current),('Delete clip',self.delete_current),('Relink selected media…',self.relink_asset)]:edit.add_command(label=text,command=cmd)
        view=tk.Menu(menu,tearoff=False);menu.add_cascade(label='View',menu=view)
        for text,cmd in [('Theme Studio',self.open_theme_studio),('Import theme',self.open_theme_import),('Welcome',lambda:self.show_startup_window(True)),('Reset pane layout',lambda:self.load_layout({})),('Fit song',lambda:self.timeline.zoom_fit())]:view.add_command(label=text,command=cmd)
        helpmenu=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Help',menu=helpmenu);helpmenu.add_command(label='Quick guide',command=self.quick_guide);helpmenu.add_command(label='Session log',command=lambda:open_path(self.log_path))
        top=ttk.Frame(root);top.grid(row=0,column=0,sticky='ew')
        ttk.Label(top,text='OmN-e  /  Sequencer',style='Title.TLabel').pack(side='left',padx=(2,16))
        for text,cmd in [('Open',self.open_project),('Save',self.save_project),('+ Media',self.add_media),('+ Song',self.add_song),('+ Text',self.add_text),('+ Shape',self.add_shape)]:ttk.Button(top,text=text,width=max(5,len(text)+1),command=cmd).pack(side='left',padx=2)
        ttk.Button(top,text='Export…',width=8,style='Accent.TButton',command=self.export_video).pack(side='right',padx=2)
        ttk.Button(top,text='Theme',width=6,command=self.open_theme_studio).pack(side='right',padx=2)
        self.live_button=ttk.Button(top,text='Live Inputs',width=11,command=self.open_live);self.live_button.pack(side='right',padx=2)
        self.main_panes=ResizablePane(root,tk.VERTICAL,self.ui_chrome);self.main_panes.grid(row=1,column=0,sticky='nsew',pady=(6,2))
        work=ttk.Frame(self.main_panes);bottom=ttk.Frame(self.main_panes);self.main_panes.add(work,minsize=330);self.main_panes.add(bottom,minsize=245)
        self.main_panes.set_bounds_provider(lambda i:(330,max(330,self.main_panes.winfo_height()-245)))
        self.main_panes.bind('<Double-Button-1>',lambda e:self.load_layout({}),add='+')
        self.workspace_panes=ResizablePane(work,tk.HORIZONTAL,self.ui_chrome);self.workspace_panes.pack(fill='both',expand=True)
        lib=ttk.Frame(self.workspace_panes);vp=ttk.Frame(self.workspace_panes);deck=ttk.Frame(self.workspace_panes)
        self.workspace_panes.add(lib,minsize=165);self.workspace_panes.add(vp,minsize=360);self.workspace_panes.add(deck,minsize=280)
        def bounds(i):
            w=self.workspace_panes.winfo_width()
            return (165,max(165,w-650)) if i==0 else (max(525,self.workspace_panes.sashpos(0)+365),max(530,w-280))
        self.workspace_panes.set_bounds_provider(bounds)
        self.workspace_panes.bind('<Double-Button-1>',lambda e:self.load_layout({}),add='+')
        self.build_library(lib);self.deck=ControlDeck(deck,self);self.deck.pack(fill='both',expand=True);self.viewport=ProgrammeView(vp,self);self.viewport.pack(fill='both',expand=True)
        self.conductor=ConductorView(bottom,self);self.conductor.pack(fill='x');self.timeline=TimelineView(bottom,self);self.timeline.pack(fill='both',expand=True)
        transport=ttk.Frame(root);transport.grid(row=2,column=0,sticky='ew',pady=3)
        self.play_button=ttk.Button(transport,text='▶ Play',command=self.toggle_play,width=10);self.play_button.pack(side='left')
        ttk.Button(transport,text='|◀',width=4,command=lambda:self.set_playhead(0)).pack(side='left',padx=2)
        for text,delta in [('◀',-1),('▶',1)]:ttk.Button(transport,text=text,width=3,command=lambda d=delta:self.set_playhead(self.playhead+d/self.project.fps)).pack(side='left',padx=1)
        ttk.Label(transport,textvariable=self.transport_time).pack(side='left',padx=8)
        ttk.Checkbutton(transport,text='Mute song',variable=self.mute,command=self.restart_audio).pack(side='left',padx=3)
        for text,cmd in [('In [I]',lambda:self.set_range('in')),('Out [O]',lambda:self.set_range('out')),('Clear range',self.clear_range),('+ Marker',self.add_marker)]:ttk.Button(transport,text=text,width=max(5,len(text)+1),command=cmd).pack(side='left',padx=2)
        self.range_label=ttk.Label(transport,text='',style='Muted.TLabel');self.range_label.pack(side='right')
        status=ttk.Frame(root);status.grid(row=3,column=0,sticky='ew');status.columnconfigure(0,weight=1)
        ttk.Label(status,textvariable=self.status,style='Muted.TLabel',anchor='w').grid(row=0,column=0,sticky='ew')
        self.progress=ttk.Progressbar(status,length=140,maximum=100);self.progress.grid(row=0,column=1,padx=6)
        self.cancel_button=ttk.Button(status,text='Cancel export',command=self.render_cancel.set,state='disabled');self.cancel_button.grid(row=0,column=2)
        ttk.Button(status,text='Diagnostics',command=self.export_diagnostics).grid(row=0,column=3,padx=4)
    def build_library(self,parent):
        outer=ttk.Frame(parent,padding=5);outer.pack(fill='both',expand=True);outer.columnconfigure(0,weight=1);outer.rowconfigure(2,weight=1)
        ttk.Label(outer,text='LIBRARY',style='Title.TLabel').grid(row=0,column=0,sticky='w')
        self.search=tk.StringVar();entry=ttk.Entry(outer,textvariable=self.search);entry.grid(row=1,column=0,sticky='ew',pady=(6,4));self.search.trace_add('write',lambda *_:self.refresh_library())
        self.add_tip(entry,'Filter local sources by name or type. Drag a source onto the timeline or use Place at playhead.')
        self.library=ttk.Treeview(outer,columns=('type','duration'),show='tree headings',selectmode='browse');self.library.heading('#0',text='Source');self.library.column('#0',width=140,minwidth=90);self.library.heading('type',text='Type');self.library.column('type',width=52,minwidth=40,stretch=False);self.library.heading('duration',text='Time');self.library.column('duration',width=48,minwidth=40,stretch=False)
        self.library.grid(row=2,column=0,sticky='nsew');library_scroll=ttk.Scrollbar(outer,orient='vertical',command=self.library.yview);library_scroll.grid(row=2,column=1,sticky='ns');self.library.configure(yscrollcommand=library_scroll.set);self.library.bind('<<TreeviewSelect>>',self.asset_selected);self.library.bind('<Double-1>',lambda e:self.place_selected_asset());self.library.bind('<ButtonRelease-1>',self.library_drop,add='+');self.library.bind('<Button-3>',self.library_menu)
        self.asset_summary=tk.StringVar(value='Add files or use an included example.');ttk.Label(outer,textvariable=self.asset_summary,style='Muted.TLabel',wraplength=235,justify='left').grid(row=3,column=0,sticky='ew',pady=5)
        row=ttk.Frame(outer);row.grid(row=4,column=0,sticky='ew');self.place_mode=tk.StringVar(value='place');ttk.Combobox(row,values=['place','insert','overwrite'],textvariable=self.place_mode,state='readonly',width=11).pack(side='left');ttk.Button(row,text='Place here',command=self.place_selected_asset).pack(side='right')
        ttk.Button(outer,text='Replace current, keep treatment',command=self.replace_current).grid(row=5,column=0,sticky='ew',pady=4)
        ttk.Button(outer,text='Open example sequence',command=self.open_example).grid(row=6,column=0,sticky='ew',pady=(0,3))
    def refine_widget_theme(self):
        # Keep the inherited theme definitions intact; repair native readonly state
        # colours in the host so dark fields do not become light/invisible.
        c=self.ui_chrome;style=ttk.Style(self)
        style.map('TCombobox',fieldbackground=[('readonly',c['field_bg'])],foreground=[('readonly',c['foreground'])],selectbackground=[('readonly',c['selection_bg'])],selectforeground=[('readonly',c['foreground'])])
    def clean_tips(self):
        alive=[]
        for tip in self.tip_instances:
            try:exists=tip.widget.winfo_exists()
            except tk.TclError:exists=False
            if exists:alive.append(tip)
            else:tip._cancel();tip._hide()
        self.tip_instances=alive
    def apply_theme(self,name,save=True,chrome_override=None):
        self.ui_chrome=copy.deepcopy(chrome_override if chrome_override is not None else self.theme_library.get(name,self.ui_chrome));configure_theme(self,self.ui_chrome);self.refine_widget_theme();self.clean_tips()
        if chrome_override is None:self.theme_name.set(name)
        for tip in self.tip_instances:tip.chrome=self.ui_chrome
        for pane in (self.main_panes,self.workspace_panes):pane.configure(bg=self.ui_chrome['sash_color'],sashwidth=self.ui_chrome['sash_width'],handlesize=self.ui_chrome['handle_size'],handlepad=self.ui_chrome['handle_offset'])
        retheme_native_tk_scales(self,self.ui_chrome);self.viewport.set_theme();self.deck.scroll.set_theme();self.timeline.redraw()
        if save and chrome_override is None:self.save_preferences()
    def read_preferences(self):
        try:return json.loads(self.preferences_path.read_text()) if self.preferences_path.exists() else {}
        except (OSError,ValueError):return {}
    def save_preferences(self):
        if self.test_mode:return
        try:
            d={'theme_name':self.theme_name.get(),'tooltips':self.tooltips_enabled.get(),'show_startup':self.show_startup.get(),'geometry':self.geometry(),'layout':{'main':self.main_panes.sashpos(0),'workspace0':self.workspace_panes.sashpos(0),'workspace1':self.workspace_panes.sashpos(1)}}
            tmp=self.preferences_path.with_suffix('.tmp');tmp.write_text(json.dumps(d,indent=2));tmp.replace(self.preferences_path)
        except (OSError,tk.TclError):pass
    def load_layout(self,pref):
        def do():
            if self.closing:return
            self.update_idletasks();d=pref.get('layout',{});w=self.workspace_panes.winfo_width();h=self.main_panes.winfo_height()
            self.main_panes.sashpos(0,int(d.get('main',max(330,h*.49))));self.workspace_panes.sashpos(0,int(d.get('workspace0',w*.18)));self.workspace_panes.sashpos(1,int(d.get('workspace1',w*.75)));self.timeline.zoom_fit()
        self.after(180,do)
    def bind_shortcuts(self):
        for key,cmd in [('<Control-s>',self.save_project),('<Control-Shift-S>',lambda:self.save_project(as_new=True)),('<Control-o>',self.open_project),('<Control-n>',self.new_project),('<Control-z>',self.undo),('<Control-y>',self.redo),('<Control-Shift-Z>',self.redo)]:self.bind_all(key,lambda e,f=cmd:(f(),'break')[1])
        for key,cmd in [('<space>',self.toggle_play),('<Key-m>',self.mutate),('<Key-i>',lambda:self.set_range('in')),('<Key-o>',lambda:self.set_range('out')),('<Key-s>',self.split_current),('<Delete>',self.delete_current),('<Left>',lambda:self.set_playhead(self.playhead-1/self.project.fps)),('<Right>',lambda:self.set_playhead(self.playhead+1/self.project.fps))]:self.bind_all(key,lambda e,f=cmd:self.shortcut(e,f))
        self.bind_all('<Escape>',lambda e:self.cancel_gesture())
    def shortcut(self,event,fn):
        focus=self.focus_get()
        if not shortcut_allowed_for_widget_class(focus.winfo_class() if focus else ''):return
        fn();return 'break'
    def snapshot(self):
        if self._snapshot_revision!=self.revision:self._snapshot=copy.deepcopy(self.project);self._snapshot_revision=self.revision
        return self._snapshot
    def signal_evaluator(self):
        if self._signal_revision!=self.revision:self._signals=SignalEvaluator(self.project,self.live.signal);self._signal_revision=self.revision
        return self._signals
    def selected_layer(self):return next((l for l in self.project.layers if l.id==self.selected_layer_id),self.project.layers[0] if self.project.layers else None)
    def get_edit_target(self):
        if self.gesture and self.gesture.get('target'):
            lid,cid=self.gesture['target'];l=next((l for l in self.project.layers if l.id==lid),None);found=self.project.clip(cid);return l,found[1] if found else None
        layer=self.selected_layer()
        if not layer:return None,None
        if not self.follow_playhead.get():
            found=self.project.clip(self.selected_clip_id);return (found if found else (layer,None))
        clips=[c for c in layer.clips if c.channel==self.selected_channel.get() and c.start-1e-7<=self.playhead<c.end-1e-7]
        clip=max(clips,key=lambda c:c.start,default=None)
        return layer,clip
    def can_edit(self,owner):
        if owner is None:return True
        if isinstance(owner,Clip):
            found=self.project.clip(owner.id);locked=owner.locked or (found and found[0].locked)
        elif isinstance(owner,Layer):locked=owner.locked
        elif hasattr(owner,'from_clip'):
            found=self.project.transition(owner.id);locked=owner.locked or (found and found[0].locked)
        else:locked=False
        if locked:self.update_status('Unlock the target before editing it.');return False
        return True
    def begin_gesture(self,kind):
        if self.gesture:return
        layer,clip=self.get_edit_target();self.gesture_time=self.playhead
        self.gesture={'kind':kind,'before':project_to_dict(self.project),'target':(layer.id if layer else None,clip.id if clip else None)};self.history.checkpoint_snapshot(self.gesture['before'])
    def end_gesture(self):
        if not self.gesture:return
        before=self.gesture['before'];kind=self.gesture['kind'];self.gesture=None
        if before==project_to_dict(self.project) and self.history.undo_stack:self.history.undo_stack.pop()
        else:self.changed(redraw=True)
        # Parameter gestures update existing faders, not rack topology. A forced
        # rebuild here caused the chassis and neighbouring parameter rows to
        # flicker every time the user released a slider.
        self.deck.refresh(force=(kind!='program'));self.conductor.refresh()
    def cancel_gesture(self):
        if not self.gesture:return
        before=self.gesture['before'];self.gesture=None
        if self.history.undo_stack:self.history.undo_stack.pop()
        self.project=project_from_dict(before);self.history.current=self.project;self.changed(redraw=True);self.refresh_all();self.update_status('Gesture cancelled; previous state restored')
    def transaction(self,label,fn):
        if self.gesture:self.end_gesture()
        before=project_to_dict(self.project);self.history.checkpoint_snapshot(before)
        try:result=fn()
        except Exception as exc:
            self.project=project_from_dict(before);self.history.current=self.project
            if self.history.undo_stack:self.history.undo_stack.pop()
            self.revision+=1;self.refresh_all();self.update_status(label+': '+str(exc));self.log(label+' failed\n'+traceback.format_exc())
            if not self.test_mode:messagebox.showerror(label,str(exc),parent=self)
            return None
        if before==project_to_dict(self.project):
            if self.history.undo_stack:self.history.undo_stack.pop()
        else:self.changed(redraw=True)
        self.refresh_all();self.update_status(label);return result
    def changed(self,redraw=False):
        self.dirty=True;self.revision+=1;self.update_title()
        if self._preview_after is None:self._preview_after=self.after(35,self.request_preview)
        if redraw and hasattr(self,'timeline'):self.timeline.schedule()
        if self._autosave_after:
            try:self.after_cancel(self._autosave_after)
            except tk.TclError:pass
        self._autosave_after=self.after(2000,self.write_recovery)
    def request_preview(self):self._preview_after=None;self.viewport.request()
    def update_title(self):self.title(f'{"* " if self.dirty else ""}{self.project.name} · {APP} {VERSION}')
    def write_recovery(self):
        self._autosave_after=None
        if self.gesture:self._autosave_after=self.after(2000,self.write_recovery);return
        if self.test_mode:return
        try:save_project(copy.deepcopy(self.project),self.autosave_path)
        except Exception as exc:self.log('Autosave: '+str(exc))
    def restore_project(self,project,path=None,*,new_history=True):
        self.pause();self.project=project;self.project.ensure_layer();self.project_path=Path(path) if path else None
        if new_history:self.history=ProjectHistory(project)
        else:self.history.current=project
        self.selected_layer_id=project.layers[0].id;self.selected_clip_id=None;self.selected_transition_id=None;self.selected_asset_id=None;self.playhead=0.;self.range_in=self.range_out=None;self.gesture=None;self.revision+=1;self.thumbnails={};self.small_thumbnails={};self.thumb_pending=set();self.dirty=False;self.refresh_all();self.timeline.zoom_fit()
    def confirm_discard(self):
        if not self.dirty:return True
        result=messagebox.askyesnocancel(APP,'Save changes before replacing this sequence?',parent=self)
        if result is None:return False
        return bool(self.save_project()) if result else True
    def new_project(self):
        if self.confirm_discard():self.restore_project(Project())
    def open_project(self,path=None):
        if not self.confirm_discard():return
        path=path or filedialog.askopenfilename(parent=self,filetypes=[('OmN-e sequence','*.json'),('All files','*')])
        if not path:return
        try:self.restore_project(load_project(path),path);self.update_status('Opened '+Path(path).name)
        except Exception as exc:messagebox.showerror('Open sequence',str(exc),parent=self)
    def open_example(self):
        path=(Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])/'examples'/'First Light.omne-sequence.json'
        if not path.exists():self.update_status('Example is not present in this source checkout');return
        self.open_project(str(path))
    def save_project(self,as_new=False):
        path=None if as_new else self.project_path
        if path is None:
            chosen=filedialog.asksaveasfilename(parent=self,title='Save sequence',defaultextension=PROJECT_EXT,filetypes=[('OmN-e sequence','*'+PROJECT_EXT)])
            if not chosen:return False
            path=Path(chosen)
        try:save_project(self.project,path);self.project_path=path;self.dirty=False;self.update_title();self.update_status('Saved '+path.name);return True
        except Exception as exc:messagebox.showerror('Save sequence',str(exc),parent=self);return False
    def offer_recovery(self):
        if self.closing:return
        try:
            if self.autosave_path.exists() and messagebox.askyesno(APP,'A v0.2 recovery snapshot is available. Open it?\n\nThe v0.1 recovery file is kept separately.',parent=self):
                self.restore_project(load_project(self.autosave_path));self.dirty=True;self.update_title()
        except Exception as exc:self.log('Recovery: '+str(exc))
        if self.show_startup.get():self.show_startup_window()
    def undo(self):
        if self.gesture:self.cancel_gesture();return
        p=self.history.undo()
        if p:self.project=p;self.revision+=1;self.dirty=True;self.refresh_all();self.update_status('Undo')
    def redo(self):
        p=self.history.redo()
        if p:self.project=p;self.revision+=1;self.dirty=True;self.refresh_all();self.update_status('Redo')
    def set_playhead(self,t):
        self.playhead=max(0.,min(self.project.max_end(),float(t)));self.transport_time.set(format_time(self.playhead)+' / '+format_time(self.project.max_end()))
        if self.playing:self.play_origin=self.playhead;self.play_started_at=time.monotonic();self.restart_audio()
        if hasattr(self,'timeline'):self.timeline.draw_playhead();self.deck.refresh();self.viewport.request()
    def select_layer(self,layer_id,channel='A'):
        self.selected_layer_id=layer_id;self.selected_channel.set(channel);self.selected_transition_id=None;self.timeline.redraw();self.deck.refresh(force=True)
    def current_clip(self):
        l,c=self.get_edit_target()
        if c:return l,c
        self.update_status('Choose a clip in the active channel or move the playhead over it.');return None
    def split_current(self):
        found=self.current_clip()
        if found:
            new=self.transaction('Split clip',lambda:split_clip(self.project,found[1].id,self.playhead))
            if new:self.selected_clip_id=new.id;self.deck.refresh(force=True)
    def duplicate_current(self):
        found=self.current_clip()
        if found:self.transaction('Duplicate clip',lambda:duplicate_clip(self.project,found[1].id))
    def delete_current(self):
        found=self.current_clip()
        if found:self.transaction('Delete clip',lambda:remove_clip(self.project,found[1].id,ripple=self.timeline.ripple.get()))
    def replace_current(self):
        found=self.current_clip()
        if found and self.selected_asset_id:self.transaction('Replace media; treatment retained',lambda:replace_clip_media(self.project,found[1].id,self.selected_asset_id))
        elif not self.selected_asset_id:self.update_status('First select a replacement source in the Library.')
    def transition_current(self):
        found=self.current_clip()
        if not found:return
        l,c=found
        def do():
            tr=add_transition(self.project,l.id,c.id,'dissolve',.6);l.mixer_mode='auto';self.selected_transition_id=tr.id;self.deck.scope.set('Transition');return tr
        tr=self.transaction('Add transition',do)
        if tr:self.set_playhead(tr.start+tr.duration/2);self.deck.refresh(force=True)
    def add_layer(self):
        def do():
            l=Layer(new_id('lyr'),f'Layer {len(self.project.layers)+1}');self.project.layers.append(l);self.selected_layer_id=l.id;return l
        self.transaction('Add layer',do)
    def reorder_layer(self,lid,delta):
        l=next(l for l in self.project.layers if l.id==lid)
        if l.locked:return self.update_status('Unlock the layer to move it')
        i=self.project.layers.index(l);j=max(0,min(len(self.project.layers)-1,i+delta))
        self.transaction('Reorder layer',lambda:self.project.layers.insert(j,self.project.layers.pop(i)))
    def rename_layer(self,lid):
        l=next(l for l in self.project.layers if l.id==lid);name=simpledialog.askstring('Layer name','Name:',initialvalue=l.name,parent=self)
        if name and self.can_edit(l):self.transaction('Rename layer',lambda:setattr(l,'name',name))
    def delete_layer(self,lid):
        l=next(l for l in self.project.layers if l.id==lid)
        if not self.can_edit(l):return
        if any(c.locked for c in l.clips):return self.update_status('This layer contains locked clips. Unlock them before deleting.')
        if not messagebox.askyesno('Delete layer',f'Delete “{l.name}” and its clips? Undo is available.',parent=self):return
        def do():self.project.layers.remove(l);self.project.ensure_layer();self.selected_layer_id=self.project.layers[0].id
        self.transaction('Delete layer',do)
    def set_range(self,end):
        if end=='in':self.range_in=self.playhead
        else:self.range_out=self.playhead
        self.timeline.redraw();self.refresh_range()
    def clear_range(self):self.range_in=self.range_out=None;self.timeline.redraw();self.refresh_range()
    def refresh_range(self):
        self.range_label.configure(text=f'Range {format_time(self.range_in)} → {format_time(self.range_out)}' if self.range_in is not None and self.range_out is not None else '')
    def add_marker(self):
        text=simpledialog.askstring('Marker','Marker name:',initialvalue='Section',parent=self)
        if text:self.transaction('Add marker',lambda:self.project.markers.append({'time':self.playhead,'name':text}))
    def mutate(self):
        try:seed=int(self.conductor.seed.get())
        except ValueError:self.update_status('Seed must be an integer');return
        scope=self.conductor.scope.get();kwargs={'scope':scope}
        if scope in ('layer','channel'):kwargs['layer_id']=self.selected_layer_id
        if scope=='channel':kwargs['channel']=self.selected_channel.get()
        if scope=='range':
            if self.range_in is None or self.range_out is None:return self.update_status('Mark range In and Out before mutating a range.')
            kwargs['time_range']=tuple(sorted((self.range_in,self.range_out)))
        self.pause();result=self.transaction('Mutate '+scope,lambda:mutate_project(self.project,seed,**kwargs))
        if result is not None:self.timeline.zoom_fit();self.update_status(f'Mutated {scope} · seed {seed} · manual edits and locks preserved')
    def add_media(self):
        paths=filedialog.askopenfilenames(parent=self,title='Add local media',filetypes=[('Media','*.mp4 *.mov *.mkv *.webm *.avi *.png *.jpg *.jpeg *.gif *.webp *.tif *.wav *.mp3 *.flac *.m4a *.ogg'),('All files','*')])
        if paths:self.import_files(paths)
    def add_song(self):
        path=filedialog.askopenfilename(parent=self,title='Choose song',filetypes=[('Audio','*.wav *.mp3 *.flac *.m4a *.ogg *.opus *.aac'),('All files','*')])
        if path:self.import_files([path],as_song=True)
    def import_files(self,paths,as_song=False):
        if self.importing:return self.update_status('Another import is still running.')
        self.importing=True;project_id=self.project.id
        def work():
            result=[];errors=[]
            for path in paths:
                try:
                    self.events.put(('status','Inspecting '+Path(path).name));kind=kind_for_path(path);info=probe_media(path)
                    if as_song or (kind=='audio' and self.project.audio_asset_id is None):analysis=analyze_file(path,ffmpeg=FFMPEG)
                    else:analysis=None
                    result.append((str(Path(path).resolve()),kind,info,analysis))
                except Exception as exc:errors.append(Path(path).name+': '+str(exc));self.events.put(('log',traceback.format_exc()))
            self.events.put(('import',project_id,result,errors,as_song))
        threading.Thread(target=work,name='Import and audio analysis',daemon=True).start()
    def accept_import(self,project_id,result,errors,as_song):
        self.importing=False
        if self.project.id!=project_id:return self.update_status('Import completed for a previous project; add the files again to this project.')
        def do():
            for path,kind,info,analysis in result:
                asset=add_asset(self.project,path=path,kind=kind,name=Path(path).name,duration=info['duration'],width=info['width'],height=info['height'],metadata=info);self.selected_asset_id=asset.id
                if analysis and (as_song or self.project.audio_asset_id is None):self.project.audio_asset_id=asset.id;self.project.duration=max(info['duration'],max([0]+[c.end for l in self.project.layers for c in l.clips]));self.project.analysis=analysis;self.project.waveform=analysis['waveform'];self.project.beats=[]
        if result:self.transaction('Imported '+str(len(result))+' source(s)',do);self.timeline.zoom_fit()
        if errors:messagebox.showerror('Some files were not imported','\n\n'.join(errors),parent=self)
    def asset_selected(self,event=None):
        sel=self.library.selection()
        if not sel:return
        self.selected_asset_id=sel[0];a=self.project.asset(sel[0])
        if a:self.asset_summary.set(f'{a.name}\n{a.kind.title()} · {a.width} × {a.height}'+(f' · {a.duration:.1f}s' if a.duration else ''))
    def refresh_library(self):
        if not hasattr(self,'library'):return
        selected=self.selected_asset_id;query=self.search.get().casefold();self.library.delete(*self.library.get_children())
        for a in self.project.assets.values():
            if query and query not in (a.name+' '+a.kind).casefold():continue
            enabled=a.metadata.get('sequence_preferences',{}).get('enabled',True);name=('× ' if not enabled else '')+a.name
            self.library.insert('', 'end',iid=a.id,text=name,values=(a.kind,f'{a.duration:.1f}s' if a.duration else ''))
            if a.kind!='audio':self.request_thumbnail(a)
        if selected in self.library.get_children():self.library.selection_set(selected)
    def request_thumbnail(self,asset):
        if asset.id in self.thumbnails or asset.id in self.thumb_pending or asset.kind in ('camera','audio'):return
        self.thumb_pending.add(asset.id)
        try:self.thumb_queue.put_nowait((self.project.id,copy.deepcopy(asset),self.project.width,self.project.height))
        except queue.Full:self.thumb_pending.discard(asset.id)
    def thumbnail_worker(self):
        source=FrameSources(max_readers=1)
        try:
            while not self.closing:
                try:task=self.thumb_queue.get(timeout=.2)
                except queue.Empty:continue
                if task is None:return
                pid,asset,w,h=task
                try:image=source.frame(asset,min(1,asset.duration/4),(128,72),reader_key=asset.id,project_size=(w,h));self.events.put(('thumbnail',pid,asset.id,image))
                except Exception as exc:self.events.put(('thumbnail_error',asset.id,str(exc)))
        finally:source.close()
    def library_drop(self,event):
        sel=self.library.selection()
        if not sel:return
        self.selected_asset_id=sel[0]
        target=self.winfo_containing(event.x_root,event.y_root)
        if target and str(target).startswith(str(self.timeline.canvas)):
            x=event.x_root-self.timeline.canvas.winfo_rootx();y=event.y_root-self.timeline.canvas.winfo_rooty();t=self.timeline.canvas.canvasx(x)/self.timeline.pps;row,ch=self.timeline.row_at(self.timeline.canvas.canvasy(y))
            if row:self.selected_layer_id=row['layer'].id;self.selected_channel.set(ch);self.set_playhead(t);self.place_selected_asset()
        elif target and str(target).startswith(str(self.viewport)):self.place_selected_asset()
    def place_selected_asset(self):
        a=self.project.asset(self.selected_asset_id);l=self.selected_layer()
        if a is None:return self.update_status('Select a visual source in the Library.')
        if a.kind=='audio':return self.update_status('Use “Use as song” from the Library menu, or enable a recorded audio take in Live Inputs.')
        if not l or not self.can_edit(l):return
        duration=min(a.duration,6.) if a.duration>0 else 4.
        def do():
            c=Clip(new_id('clp'),a.id,self.selected_channel.get(),self.playhead,max(1/self.project.fps,duration),manual=True);insert_clip(self.project,l,c,self.place_mode.get());self.selected_clip_id=c.id;self.deck.scope.set('Clip');return c
        self.transaction('Place media at playhead',do)
    def library_menu(self,event):
        iid=self.library.identify_row(event.y)
        if not iid:return
        self.library.selection_set(iid);self.selected_asset_id=iid;self.asset_selected();a=self.project.asset(iid)
        menu=tk.Menu(self,tearoff=False)
        for text,cmd in [('Place at playhead',self.place_selected_asset),('Replace current, keep treatment',self.replace_current),('Edit source / name…',lambda:self.edit_asset(iid)),('Sequence preferences…',lambda:self.asset_preferences(iid)),('Relink…',self.relink_asset),('Remove from pool',self.remove_asset)]:menu.add_command(label=text,command=cmd)
        if a.kind=='audio':menu.add_command(label='Use as song',command=lambda:self.import_files([a.path],as_song=True))
        from contextual_surface import post_native_menu
        post_native_menu(self,menu,self.library,event)
    def remove_asset(self):
        aid=self.selected_asset_id
        if any(c.asset_id==aid for l in self.project.layers for c in l.clips) or aid==self.project.audio_asset_id:return self.update_status('This source is in use. Remove or replace its clips before removing it from the pool.')
        self.transaction('Remove unused source',lambda:self.project.assets.pop(aid,None))
    def relink_asset(self):
        a=self.project.asset(self.selected_asset_id)
        if not a or a.kind not in ('image','video','audio'):return
        path=filedialog.askopenfilename(parent=self,title='Relink '+a.name)
        if not path:return
        try:
            info=probe_media(path)
            if kind_for_path(path)!=a.kind:raise ValueError('Relink must retain the source type; use Replace for a different visual type')
            def do():a.path=str(Path(path).resolve());a.duration=info['duration'];a.width=info['width'];a.height=info['height'];a.metadata.update(info)
            self.transaction('Relink source',do);self.thumbnails.pop(a.id,None);self.thumb_pending.discard(a.id);self.refresh_library()
        except Exception as exc:messagebox.showerror('Relink',str(exc),parent=self)
    def add_text(self):
        text=simpledialog.askstring('Add text','Text:',initialvalue='OmN-e',parent=self)
        if text:
            def do():
                a=add_asset(self.project,path='',kind='text',name=text[:40],metadata={'text':text,'font_size':64,'colour':'#ffffff'});self.selected_asset_id=a.id
            self.transaction('Add text source',do);self.place_selected_asset()
    def add_shape(self):
        def do():
            a=add_asset(self.project,path='',kind='shape',name='Shape',metadata={'shape':'ellipse','colour':self.ui_chrome['accent']});self.selected_asset_id=a.id
        self.transaction('Add shape source',do);self.place_selected_asset()
    def edit_asset(self,aid):
        from source_dialogs import AssetDialog
        a=self.project.asset(aid)
        if a:AssetDialog(self,a)
    def asset_preferences(self,aid):
        from source_dialogs import AssetPreferences
        a=self.project.asset(aid)
        if a:AssetPreferences(self,a)
    def sequence_settings(self):
        # UX37: canvas and sequence controls are inline in Output preferences.
        return self.open_preferences('output')
    def pause(self):
        self.playing=False
        if hasattr(self,'play_button'):self.play_button.configure(text='▶ Play')
        stop_process(self.audio_process);self.audio_process=None
    def toggle_play(self):
        if self.playing:self.pause();return
        if self.playhead>=self.project.max_end():self.playhead=0.
        self.playing=True;self.play_origin=self.playhead;self.play_started_at=time.monotonic();self.play_button.configure(text='Ⅱ Pause');self.restart_audio()
    def restart_audio(self):
        stop_process(self.audio_process);self.audio_process=None
        if not self.playing or self.mute.get():return
        a=self.project.asset(self.project.audio_asset_id)
        if a:
            try:self.audio_process=subprocess.Popen(ffplay_audio_command(a.path,self.playhead),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**popen_options())
            except Exception as exc:self.update_status('Song playback: '+str(exc));self.log(str(exc))
    def clock(self):
        if self.closing:return
        self.live_button.configure(text='Live ●' if self.live.camera or self.live.microphone else 'Live Inputs')
        if self.playing:
            elapsed=self.play_origin+time.monotonic()-self.play_started_at
            self.playhead=elapsed if self.live.recording else min(self.project.max_end(),elapsed)
            self.transport_time.set(format_time(self.playhead)+' / '+format_time(self.project.max_end()));self.timeline.draw_playhead();self.deck.refresh();self.viewport.request()
            if self.playhead>=self.project.max_end() and not self.live.recording:self.pause()
        elif self.live.camera or self.live.microphone:self.viewport.request();self.deck.refresh()
        self.after(80,self.clock)
    def export_video(self):
        from source_dialogs import ExportDialog
        if self.rendering:return self.update_status('An export is already running.')
        ExportDialog(self)
    def start_export(self,path,profile='web',size=None,start=0.,end=None,overwrite=False):
        if self.rendering:return
        self.pause();self.rendering=True;self.render_cancel=threading.Event();self.cancel_button.configure(state='normal');self.progress['value']=0
        snapshot=copy.deepcopy(self.project);report=self.cache/'exports'/('job-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()%1000000));report.mkdir(parents=True);self.last_diagnostics=report
        (report/'project.omne-sequence.json').write_text(json.dumps(project_to_dict(snapshot),indent=2))
        def work():
            try:
                result=render_project(snapshot,path,start=start,end=end,profile=profile,size=size,overwrite=overwrite,cancel=self.render_cancel,diagnostics_dir=report,progress=lambda text:self.events.put(('export_progress',text)))
                self.events.put(('export_done',str(result),str(report)))
            except Cancelled:self.events.put(('export_cancelled',str(report)))
            except Exception as exc:
                message=str(exc);trace=traceback.format_exc();(report/'failure.txt').write_text(trace);self.events.put(('export_failed',message,str(report)))
        threading.Thread(target=work,name='Frame export',daemon=True).start()
    def export_diagnostics(self):
        from diagnostics import export_diagnostics
        out=filedialog.asksaveasfilename(parent=self,title='Save diagnostics (contains file paths, not source media)',defaultextension='.zip',initialfile='OmN-e_Sequencer_v02_Diagnostics.zip',filetypes=[('ZIP','*.zip')])
        if not out:return
        try:
            export_diagnostics(self.project,out,self.log_path,self.last_diagnostics,self.live.state());self.update_status('Diagnostics saved · review local filenames and paths before sharing')
        except Exception as exc:messagebox.showerror('Diagnostics',str(exc),parent=self)
    def open_live(self):
        from live_panel import LivePanel
        if self.live_window and self.live_window.winfo_exists():self.live_window.lift();return
        self.live_window=LivePanel(self)
    def refresh_all(self):
        self.project.ensure_layer()
        if not any(l.id==self.selected_layer_id for l in self.project.layers):self.selected_layer_id=self.project.layers[0].id
        self.refresh_library();self.conductor.refresh();self.timeline.redraw();self.deck.refresh(force=True);self.viewport.request();self.refresh_range();self.update_title();self.transport_time.set(format_time(self.playhead)+' / '+format_time(self.project.max_end()))
    def update_status(self,text):self.status.set(str(text).replace('\n',' ')[:230])
    def poll_events(self):
        if self.closing:return
        token=getattr(self,'_poll_after',None)
        if token:
            try:self.after_cancel(token)
            except tk.TclError:pass
        self._poll_after=None
        try:self._poll_events_once()
        except Exception:self._phase_error('Worker event')
        finally:
            if not self.closing:self._poll_after=self.after(35,self.poll_events)
    def _poll_events_once(self):
        if self.closing:return
        for _ in range(100):
            try:event=self.events.get_nowait()
            except queue.Empty:break
            name=event[0]
            if name=='programme':
                _,revision,t,image,elapsed=event
                if self.viewport.accepts_result(revision,t,image):self.viewport.accept(t,image,elapsed);self.last_error=''
            elif name=='programme_error':
                _,revision,t,msg,trace=event
                if revision==self.revision:
                    self.viewport.fail(msg)
                    if msg!=self.last_error:self.log(trace);self.last_error=msg;self.update_status('Programme: '+msg)
            elif name=='thumbnail':
                _,pid,aid,image=event
                if pid==self.project.id:
                    self.thumbnails[aid]=ImageTk.PhotoImage(image)
                    if not hasattr(self,'small_thumbnails'):self.small_thumbnails={}
                    self.small_thumbnails[aid]=ImageTk.PhotoImage(image.resize((40,24),Image.Resampling.BILINEAR));self.timeline.schedule()
                    if self.library.exists(aid):self.library.item(aid,image=self.thumbnails[aid])
            elif name=='thumbnail_error':self.log('Thumbnail '+event[1]+': '+event[2])
            elif name=='import':self.accept_import(*event[1:])
            elif name=='status':self.update_status(event[1])
            elif name=='log':self.log(event[1])
            elif name=='export_progress':
                self.update_status(event[1])
                import re
                match=re.search(r'(\d+(?:\.\d+)?)%',event[1])
                if match:self.progress['value']=float(match[1])
            elif name in ('export_done','export_failed','export_cancelled'):
                self.rendering=False;self.cancel_button.configure(state='disabled');self.progress['value']=100 if name=='export_done' else 0
                if name=='export_done':
                    self.update_status('Export complete · '+event[1]);self.log('EXPORT PASS '+event[1])
                    if not self.test_mode:messagebox.showinfo('Export complete','Validated video and audio:\n'+event[1]+'\n\nDiagnostics:\n'+event[2],parent=self)
                elif name=='export_failed':
                    self.update_status('Export failed · original output preserved · see Diagnostics');self.log(event[1])
                    if not self.test_mode:messagebox.showerror('Export failed',event[1]+'\n\nDiagnostics: '+event[2],parent=self)
                else:self.update_status('Export cancelled · previous output preserved')
            elif name=='call':event[1]()
    def quick_guide(self):
        text=('Generate: add a song and media, set the Conductor, then MUTATE.\n\nEdit: choose the active layer and A or B. Follow Playhead edits the clip at the current time; turn it off to pin your selection. The Programme always shows the complete result.\n\nTimeline: drag to move; edges trim; Alt-drag slips; S splits. Shift-drag the ruler or I / O marks a range. Right-click a clip or layer for actions. Manual edits are protected from Mutate until you clear Protect.\n\nControls: ● = Static, ◆ = Animate, ≈ = React. Click the symbol for numeric ranges, project-time keyframes and audio mapping. Values update live. Enter finishes a typed edit; Escape cancels.\n\nLive: start inputs explicitly. Record raw takes before export. Live input is never enabled by opening a project.\n\nExport: choose Web, Small, Lossless master or Transparent. Diagnostics saves project paths and logs, not source media. Preview is CPU-rendered; lower monitor quality for complex stacks.')
        messagebox.showinfo('Sequencer · quick guide',text,parent=self)
    def close(self,force=False):
        if self.closing:return
        if not force and self.rendering:
            if not messagebox.askyesno(APP,'Cancel the running export and close?',parent=self):return
            self.render_cancel.set()
        if not force and not self.confirm_discard():return
        self.save_preferences();self.closing=True;self.render_cancel.set();self.pause()
        try:self.live.stop_all()
        except Exception as exc:self.log('Stop capture: '+str(exc))
        self.viewport.worker.close()
        try:self.thumb_queue.put_nowait(None)
        except queue.Full:pass
        self.thumb_thread.join(timeout=1)
        if not self.test_mode:
            if self.dirty:self.write_recovery()
            else:
                try:self.autosave_path.unlink(missing_ok=True)
                except OSError:pass
        # Cancel Tcl timers before destroying the commands they refer to.
        for token in self.tk.splitlist(self.tk.call('after','info')):
            try:self.tk.call('after','cancel',token)
            except tk.TclError:pass
        for tip in self.tip_instances:tip._cancel();tip._hide()
        self.destroy()
        from ui_collection import deactivate
        deactivate(self)


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--audio-loopback-worker':
        from system_audio_worker import main as loopback_main
        loopback_main(sys.argv[2]);return
    # Keep the compatibility editor importable without making it the launch target.
    from instrument_app import InstrumentApp
    app=InstrumentApp()
    if len(sys.argv)>1:
        path=sys.argv[1]
        if Path(path).is_file():app.after(650,lambda:app.open_project(path))
    app.mainloop()

if __name__=='__main__':main()
