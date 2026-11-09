"""UX35 shared Preferences browser. File/Welcome/shortcut routes use one window.

Project output dimensions are project-scoped; hardware and appearance defaults
are profile-scoped. Opening Preferences never activates a live input.
"""
from __future__ import annotations
from pathlib import Path
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser
from family_chrome import WEBSITE_URL, SUPPORT_URL

PAGES=(('general','General'),('devices','Devices & Media'),('output','Output'),
       ('recording','Recording'),('appearance','Appearance'))


def _file_url(url):
    # Deliberately open the published site rather than assert a nonexistent
    # update feed or pretend the app verified a newer version.
    return webbrowser.open(url)


class PreferencesWindow(tk.Toplevel):
    def __init__(self,app,page='general'):
        super().__init__(app)
        self.app=app;app.preferences_window=self
        self.title('Neospector · Preferences');self.transient(app)
        self.geometry('810x680');self.minsize(620,500)
        self.vars={};self.pages={}
        chrome=app.ui_chrome
        shell=ttk.Frame(self,padding=12);shell.pack(fill='both',expand=True)
        ttk.Label(shell,text='PREFERENCES',style='Title.TLabel').pack(anchor='w',pady=(0,8))
        book=self.book=ttk.Notebook(shell);book.pack(fill='both',expand=True)
        for key,label in PAGES:
            body=ttk.Frame(book,padding=13);book.add(body,text=label);body.columnconfigure(1,weight=1)
            self.pages[key]=body
        self._general();self._devices();self._output();self._recording();self._appearance()
        # Reserve the footer before allocating the resizable notebook.
        # Otherwise the tall Appearance page can clip Apply/Close at small sizes.
        foot=ttk.Frame(shell);foot.pack(side='bottom',fill='x',pady=(9,0),before=book)
        self.footer_frame=foot
        ttk.Button(foot,text='Close',command=self.close).pack(side='left')
        ttk.Button(foot,text='Apply changes',style='Accent.TButton',command=self.apply).pack(side='right')
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.bind('<Escape>',lambda e:self.close())
        self.select(page)

    def _row(self,page,row,label,variable,kind='entry',values=()):
        root=self.pages[page]
        ttk.Label(root,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=7)
        control=(ttk.Combobox(root,textvariable=variable,values=values,state='readonly') if kind=='select'
                 else ttk.Entry(root,textvariable=variable))
        control.grid(row=row,column=1,sticky='ew',pady=7)
        return control

    def _general(self):
        a=self.app;root=self.pages['general']
        ttk.Label(root,text='At startup',style='Title.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,9))
        ttk.Checkbutton(root,text='Show welcome when Neospector starts',variable=a.show_startup).grid(row=1,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Checkbutton(root,text='Show control hints and tooltips',variable=a.tooltips_enabled).grid(row=2,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Button(root,text='Open Welcome…',command=lambda:a.show_startup_window(True)).grid(row=3,column=0,columnspan=2,sticky='w',pady=9)
        ttk.Label(root,text='Live cameras and microphones remain off until explicitly activated.',style='Muted.TLabel',wraplength=530).grid(row=4,column=0,columnspan=2,sticky='w',pady=(0,20))
        from release_identity import VERSION
        ttk.Separator(root).grid(row=5,column=0,columnspan=2,sticky='ew',pady=(0,12))
        ttk.Label(root,text='Updates & Support',style='Title.TLabel').grid(row=6,column=0,columnspan=2,sticky='w',pady=(0,6))
        ttk.Label(root,text='Neospector '+VERSION,style='Muted.TLabel').grid(row=7,column=0,columnspan=2,sticky='w')
        self.vars['auto_check_updates']=tk.BooleanVar(value=bool(getattr(a,'auto_check_updates',True)))
        self.vars['update_feed_url']=tk.StringVar(value=str(getattr(a,'update_feed_url','')))
        ttk.Checkbutton(root,text='Check for signed updates automatically on startup',
            variable=self.vars['auto_check_updates']).grid(row=8,column=0,columnspan=2,sticky='w',pady=(9,4))
        self._row('general',9,'Signed release feed (HTTPS)',self.vars['update_feed_url'])
        ttk.Button(root,text='Check for updates now',command=a.check_for_updates).grid(row=10,column=0,columnspan=2,sticky='w',pady=(8,4))
        ttk.Label(root,text='Updates are downloaded and installed only with your approval; prior releases and projects remain intact.',
            style='Muted.TLabel',wraplength=540).grid(row=11,column=0,columnspan=2,sticky='w',pady=3)
        ttk.Button(root,text='Support Neospector…',command=lambda:_file_url(SUPPORT_URL)).grid(row=12,column=0,columnspan=2,sticky='w',pady=(12,0))

    def _devices(self):
        a=self.app;root=self.pages['devices']
        self.vars['camera']=tk.StringVar(value=a.last_camera_device)
        self.vars['microphone']=tk.StringVar(value=a.last_microphone_device)
        self.vars['folder']=tk.StringVar(value=a.last_import_folder)
        self.vars['auto_import']=tk.BooleanVar(value=bool(getattr(a,'auto_import_media',False)))
        ttk.Label(root,text='Default sources',style='Title.TLabel').grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,8))
        from device_defaults import available_input_defaults
        devices=available_input_defaults(a)
        self.device_selectors={}
        self.device_selectors['camera']=self._row('devices',1,'Camera device',self.vars['camera'],'select',devices['camera'])
        self.device_selectors['microphone']=self._row('devices',2,'Microphone device',self.vars['microphone'],'select',devices['microphone'])
        def refresh_devices():
            current=available_input_defaults(a)
            for kind,control in self.device_selectors.items():
                selected=self.vars[kind].get()
                control.configure(values=tuple(dict.fromkeys([selected,*current[kind]])))
        ttk.Button(root,text='Refresh devices',command=refresh_devices).grid(row=6,column=0,columnspan=3,sticky='w',pady=(14,0))
        self._row('devices',3,'Media folder',self.vars['folder'])
        def browse():
            choice=filedialog.askdirectory(parent=self,title='Choose default media folder',initialdir=self.vars['folder'].get() or str(Path.home()))
            if choice:self.vars['folder'].set(choice)
        ttk.Button(root,text='Browse…',command=browse).grid(row=3,column=2,padx=(7,0))
        ttk.Checkbutton(root,text='Automatically import media from this folder when starting a new empty project',variable=self.vars['auto_import']).grid(row=4,column=0,columnspan=3,sticky='w',pady=(12,7))
        ttk.Label(root,text='Only supported files in the folder itself are imported; subfolders and symlinks are ignored. A cap prevents unbounded scans. Selecting defaults does not start capture.',style='Muted.TLabel',wraplength=520).grid(row=5,column=0,columnspan=3,sticky='w',pady=5)

    def _output(self):
        a=self.app;root=self.pages['output']
        ttk.Label(root,text='Programme format',style='Title.TLabel').grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,8))
        for key,label,row in (('width','Width (px)',1),('height','Height (px)',2),('fps','Frame rate (fps)',3)):
            self.vars[key]=tk.StringVar(value=str(getattr(a.project,key)))
            self._row('output',row,label,self.vars[key])
        self.vars['preview']=tk.StringVar(value=str(a.viewport.quality.get()))
        self._row('output',4,'Preview quality',self.vars['preview'],'select',('180','270','360','540','720'))
        ttk.Label(root,text='Programme dimensions belong to the open project. Recording delivery settings are independent.',style='Muted.TLabel',wraplength=550).grid(row=5,column=0,columnspan=3,sticky='w',pady=(7,6))

        # Former SequenceSettings popup, embedded as the next group on this page.
        presets={'HD · 1280 × 720':(1280,720),'Full HD · 1920 × 1080':(1920,1080),
            'Portrait · 1080 × 1920':(1080,1920),'Square · 1080 × 1080':(1080,1080),
            'Small · 640 × 360':(640,360),'Portrait · 1080 × 1350':(1080,1350)}
        group=self.output_advanced=ttk.LabelFrame(root,text='Canvas & sequence',padding=(10,9))
        group.grid(row=6,column=0,columnspan=3,sticky='nsew',pady=(5,10))
        group.columnconfigure(1,weight=1)
        self.vars['project_name']=tk.StringVar(value=str(a.project.name))
        self.vars['duration']=tk.StringVar(value=str(a.project.duration))
        self.vars['background']=tk.StringVar(value=str(a.project.background))
        dims=(int(a.project.width),int(a.project.height))
        matched=next((k for k,v in presets.items() if v==dims),'Custom')
        self.vars['output_preset']=tk.StringVar(value=matched)
        def add(row,label,variable):
            ttk.Label(group,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=4)
            entry=ttk.Entry(group,textvariable=variable)
            entry.grid(row=row,column=1,sticky='ew',pady=4)
            return entry
        add(0,'Project name',self.vars['project_name'])
        ttk.Label(group,text='Canvas preset').grid(row=1,column=0,sticky='w',pady=4)
        combo=ttk.Combobox(group,textvariable=self.vars['output_preset'],values=tuple(presets)+('Custom',),state='readonly')
        combo.grid(row=1,column=1,sticky='ew',pady=4)
        def choose_preset(_event=None):
            size=presets.get(self.vars['output_preset'].get())
            if size:
                self.vars['width'].set(str(size[0]));self.vars['height'].set(str(size[1]))
        combo.bind('<<ComboboxSelected>>',choose_preset)
        add(2,'Minimum duration (s)',self.vars['duration'])
        add(3,'Background colour',self.vars['background'])
        ttk.Label(group,text='Clips can extend beyond the minimum duration. Hex colour, for example #0C0710.',style='Muted.TLabel',wraplength=540).grid(row=4,column=0,columnspan=2,sticky='w',pady=(5,2))
        ttk.Button(root,text='Open output viewer',command=a.open_output).grid(row=7,column=0,columnspan=3,sticky='w',pady=(0,6))

    def _recording(self):
        a=self.app;root=self.pages['recording'];rs=a.recording_settings
        ttk.Label(root,text='Capture and delivery',style='Title.TLabel').grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,8))
        for key,label,row in (('record_name','Recording name',1),('record_dir','Recording folder',2),('record_fps','Recording fps',5)):
            self.vars[key]=tk.StringVar(value=str(rs.get({'record_name':'name','record_dir':'directory','record_fps':'fps'}[key],'')))
            self._row('recording',row,label,self.vars[key])
        def browse():
            d=filedialog.askdirectory(parent=self,title='Choose recording folder',initialdir=self.vars['record_dir'].get() or str(Path.home()))
            if d:self.vars['record_dir'].set(d)
        ttk.Button(root,text='Browse…',command=browse).grid(row=2,column=2,padx=(7,0))
        labels=a._record_profile_labels();self.profile_labels=labels
        self.vars['record_profile']=tk.StringVar(value=next((label for label,key in labels.items() if key==rs.get('profile','web')),next(iter(labels))))
        self._row('recording',3,'Format',self.vars['record_profile'],'select',tuple(labels))
        self.vars['record_resolution']=tk.StringVar(value=str(rs.get('resolution','Programme')))
        self._row('recording',4,'Resolution',self.vars['record_resolution'],'select',('Programme','1920 × 1080','1280 × 720','960 × 540','640 × 360'))
        ttk.Label(root,text='Record does not start when these settings are changed.',style='Muted.TLabel').grid(row=6,column=0,columnspan=3,sticky='w',pady=10)

    def _appearance(self):
        """Appearance IS Theme Studio: no nested dialog, no duplicate selector."""
        from ui_chrome import ThemeEditor
        root=self.pages['appearance']
        root.rowconfigure(0,weight=1)
        root.columnconfigure(0,weight=1)
        self.theme_editor=ThemeEditor(root,self.app,embedded=True)
        self.theme_editor.grid(row=0,column=0,columnspan=3,sticky='nsew')
        self.vars['theme']=self.theme_editor.base

    def close(self):
        if hasattr(self,'theme_editor') and self.theme_editor.winfo_exists():
            self.theme_editor.discard_preview()
        self.destroy()

    def select(self,key):
        if key=='updates':key='general'
        if key not in self.pages:key='general'
        self.book.select(self.pages[key]);self.lift();return self
    def active_page(self):
        selected=str(self.book.select())
        return next((k for k,v in self.pages.items() if str(v)==selected),'general')
    def apply(self):
        a=self.app
        try:
            folder_value=self.vars['folder'].get().strip()
            folder=Path(folder_value).expanduser() if folder_value else None
            if self.vars['auto_import'].get() and (folder is None or not folder.is_dir()):
                raise ValueError('Choose an existing folder to enable automatic media import.')
            width=int(self.vars['width'].get());height=int(self.vars['height'].get());fps=float(self.vars['fps'].get())
            name=self.vars['project_name'].get().strip() or 'Untitled sequence'
            duration=float(self.vars['duration'].get())
            background=self.vars['background'].get().strip()
            if not (0.1<=duration<=86400):raise ValueError('Minimum duration must be 0.1 seconds to 24 hours.')
            if not re.fullmatch(r'#[0-9A-Fa-f]{6}',background):raise ValueError('Background must be a six-digit hex colour, such as #0C0710.')
            if not (16<=width<=8192 and 16<=height<=8192 and 1<=fps<=120):raise ValueError('Output requires dimensions 16–8192 and frame rate 1–120.')
            record_fps=int(self.vars['record_fps'].get())
            if not 1<=record_fps<=60:raise ValueError('Recording FPS must be 1–60.')
            record_folder=Path(self.vars['record_dir'].get()).expanduser()
            # Recording creates its destination directory on first use.
            # It is normal for ~/Videos/Neospector not to exist yet.
            preview=self.vars['preview'].get()
            if preview not in ('180','270','360','540','720'):raise ValueError('Choose a supported preview quality.')
            from signed_updates import validated_feed_url
            validated_feed_url(self.vars['update_feed_url'].get().strip())
            if self.theme_editor.base.get() not in a.available_themes:raise ValueError('Choose a known theme.')
            camera=self.vars['camera'].get().strip();mic=self.vars['microphone'].get().strip()
            if not camera or not mic:raise ValueError('A default device name is required.')
        except (ValueError,OSError) as e:
            messagebox.showerror('Preferences',str(e),parent=self);return False
        a.last_camera_device=camera;a.last_microphone_device=mic;a.last_import_folder=str(folder) if folder else ''
        a.auto_import_media=bool(self.vars['auto_import'].get())
        a.auto_check_updates=bool(self.vars['auto_check_updates'].get())
        a.update_feed_url=self.vars['update_feed_url'].get().strip()
        a.recording_settings.update(name=self.vars['record_name'].get().strip() or 'Neospector Recording',
            directory=str(record_folder),profile=self.profile_labels[self.vars['record_profile'].get()],
            resolution=self.vars['record_resolution'].get(),fps=record_fps)
        if (a.project.width,a.project.height,a.project.fps,a.project.name,a.project.duration,a.project.background)!=(width,height,fps,name,duration,background):
            def update():
                a.project.width=width;a.project.height=height;a.project.fps=fps
                a.project.name=name;a.project.duration=duration;a.project.background=background
            a.transaction('Programme output preferences',update)
            if hasattr(a,'timeline'):a.timeline.zoom_fit()
        a.viewport.quality.set(preview)
        self.theme_editor.persist()
        a.set_tooltips();a.save_preferences()
        return True


def show(app,page='general'):
    old=getattr(app,'preferences_window',None)
    if old is not None and old.winfo_exists():
        old.deiconify();old.lift();return old.select(page)
    return PreferencesWindow(app,page)
