"""UX36 Welcome: project launch, recent work, defaults, and appearance.

All destinations are mirrored in the File menu. Nothing in this window
starts an input or imports media before the user takes an explicit action.
"""
from __future__ import annotations
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
from release_identity import VERSION
from device_defaults import available_input_defaults


def show(app,force=False):
    old=getattr(app,'startup_window',None)
    if old is not None and old.winfo_exists():
        old.deiconify();old.lift();return old
    if not force and not app.show_startup.get():return None
    win=tk.Toplevel(app);app.startup_window=win
    win.title('OmN-e · Neospector · Welcome');win.transient(app)
    win.geometry('800x650');win.minsize(515,435)
    before=app.focus_get()
    def close():
        if app.startup_window is win:app.startup_window=None
        if win.winfo_exists():win.destroy()
        try:
            if before is not None and before.winfo_exists():before.focus_set()
        except tk.TclError:pass
    win.protocol('WM_DELETE_WINDOW',close)
    win.bind('<Escape>',lambda e:(close(),'break')[1])
    def launch(action,discard=False):
        if discard and not app.confirm_discard():return False
        result=action()
        if win.winfo_exists():close()
        return result
    chrome=app.ui_chrome;bg=chrome.get('panel_bg','#1d202c');fg=chrome.get('foreground','#ececf5')
    muted=chrome.get('muted_fg','#a6aaca');accent=chrome.get('accent','#8dabef')
    surface=chrome.get('field_bg','#171b29')
    font=chrome.get('font_family','TkDefaultFont')
    def label(parent,text,size=10,weight='normal',color=None):
        widget=tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color or fg,
            font=(font,size,weight),anchor='w',justify='left')
        widget._welcome_colour_role=('accent' if color==accent else 'muted_fg' if color==muted else 'foreground')
        widget._welcome_font_size=size
        widget._welcome_font_weight=weight
        return widget
    footer=ttk.Frame(win,padding=(15,8));footer.pack(side='bottom',fill='x')
    ttk.Checkbutton(footer,text='Show at startup',variable=app.show_startup,command=app.save_preferences).pack(side='left')
    win.support_button=ttk.Button(footer,text='Support',command=app.open_support_site)
    win.support_button.pack(side='left',padx=(12,0))
    ttk.Button(footer,text='Check for Updates',command=app.check_for_updates).pack(side='left',padx=6)
    app.welcome_continue=ttk.Button(footer,text='Continue to instrument',style='Accent.TButton',command=close)
    app.welcome_continue.pack(side='right')
    ttk.Separator(win).pack(side='bottom',fill='x')
    wrap=tk.Frame(win,bg=bg);wrap.pack(fill='both',expand=True)
    canvas=tk.Canvas(wrap,bg=bg,highlightthickness=0,borderwidth=0)
    win.welcome_canvas=canvas
    scroll=ttk.Scrollbar(wrap,orient='vertical',command=canvas.yview)
    scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
    canvas.configure(yscrollcommand=scroll.set)
    body=tk.Frame(canvas,bg=bg,padx=20,pady=16);node=canvas.create_window(0,0,window=body,anchor='nw')
    body.columnconfigure(0,weight=1)
    body.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all')))
    title_row=tk.Frame(body,bg=bg);title_row.grid(row=0,column=0,sticky='ew')
    win.brand_heading=label(title_row,'OmN-e',21,'bold',accent);win.brand_heading.pack(side='left')
    win.product_title=label(title_row,'Neospector',17,'bold',fg);win.product_title.pack(side='left',padx=(10,0))
    win.tagline=label(body,'by Pungent Funk',9,'normal',muted);win.tagline.grid(row=1,column=0,sticky='w',pady=(0,12))
    ttk.Separator(body).grid(row=2,column=0,sticky='ew',pady=(0,12))
    label(body,'PROJECT',9,'bold',accent).grid(row=3,column=0,sticky='w',pady=(0,7))
    actions=ttk.Frame(body);actions.grid(row=4,column=0,sticky='ew')
    start_buttons=[
        ttk.Button(actions,text='New Project',style='Accent.TButton',command=lambda:launch(app.new_project)),
        ttk.Button(actions,text='Open Project…',command=lambda:launch(app.open_project)),
        ttk.Button(actions,text='Import Media…',command=lambda:launch(app.add_media)),
    ]
    for index,button in enumerate(start_buttons):button.grid(row=0,column=index,sticky='w',padx=(0,8))
    win._welcome_columns=3
    def reflow(event):
        canvas.itemconfigure(node,width=event.width)
        columns=1 if event.width<670 else 3
        if win._welcome_columns==columns:return
        win._welcome_columns=columns
        for button in start_buttons:button.grid_forget()
        for col in range(3):actions.columnconfigure(col,weight=1 if col<columns else 0)
        for i,button in enumerate(start_buttons):
            button.grid(row=i//columns,column=i%columns,sticky='ew' if columns==1 else 'w',padx=(0,8),pady=(0,5))
    canvas.bind('<Configure>',reflow)
    recent=tk.Frame(body,bg=surface,highlightthickness=1,highlightbackground=chrome.get('border','#394357'),padx=12,pady=9)
    recent.grid(row=5,column=0,sticky='ew',pady=(12,15));recent.columnconfigure(0,weight=1)
    recent._welcome_surface=True
    label(recent,'RECENT PROJECTS',9,'bold',accent).grid(row=0,column=0,sticky='w',pady=(0,5))
    paths=[]
    for name in getattr(app,'recent_projects',[]):
        p=Path(name).expanduser()
        if p.is_file() and p not in paths:paths.append(p)
    win.recent_project_actions={}
    if not paths:label(recent,'No recent projects yet.',9,'normal',muted).grid(row=1,column=0,sticky='w',pady=3)
    for i,p in enumerate(paths[:6],1):
        row=ttk.Frame(recent);row.grid(row=i,column=0,sticky='ew',pady=2);row.columnconfigure(0,weight=1)
        ttk.Label(row,text=p.stem,anchor='w').grid(row=0,column=0,sticky='ew')
        ttk.Label(row,text=str(p.parent),style='Muted.TLabel',width=24,anchor='e').grid(row=0,column=1,sticky='e',padx=(7,10))
        cmd=lambda path=p:launch(lambda:app.open_project(str(path)))
        win.recent_project_actions[str(p)]=cmd
        ttk.Button(row,text='Open',command=cmd,width=7).grid(row=0,column=2)
    label(body,'DEFAULT INPUTS & MEDIA',9,'bold',accent).grid(row=6,column=0,sticky='w',pady=(0,6))
    inputs=ttk.Frame(body,padding=(7,5));inputs.grid(row=7,column=0,sticky='ew');inputs.columnconfigure(1,weight=1)
    win.preferences_actions={key:(lambda p=key:app.open_preferences(p)) for key in ('general','devices','output','recording','appearance')}
    choices=available_input_defaults(app)
    win.camera_default=tk.StringVar(value=str(app.last_camera_device))
    win.microphone_default=tk.StringVar(value=str(app.last_microphone_device))
    for row,name,kind,var in ((0,'Camera','camera',win.camera_default),(1,'Microphone','microphone',win.microphone_default)):
        ttk.Label(inputs,text=name,width=20).grid(row=row,column=0,sticky='w',pady=4)
        selection=ttk.Combobox(inputs,textvariable=var,state='readonly',values=choices[kind],width=36)
        selection.grid(row=row,column=1,columnspan=2,sticky='ew',pady=4)
        def save_device(_event=None,key=kind,value=var):
            setattr(app,'last_camera_device' if key=='camera' else 'last_microphone_device',value.get())
            prefs=getattr(app,'preferences_window',None)
            if prefs and prefs.winfo_exists():prefs.vars[key].set(value.get())
            app.save_preferences()
        selection.bind('<<ComboboxSelected>>',save_device)
        if kind=='camera':win.camera_selector=selection
        else:win.microphone_selector=selection
    ttk.Label(inputs,text='Auto-import folder',width=20).grid(row=2,column=0,sticky='w',pady=4)
    win.folder_default=tk.StringVar(value=str(app.last_import_folder))
    win.folder_entry=ttk.Entry(inputs,textvariable=win.folder_default)
    win.folder_entry.grid(row=2,column=1,sticky='ew',pady=4)
    def save_folder(_event=None):
        folder=win.folder_default.get().strip()
        app.last_import_folder=folder
        prefs=getattr(app,'preferences_window',None)
        if prefs and prefs.winfo_exists():prefs.vars['folder'].set(folder)
        app.save_preferences()
    win.folder_entry.bind('<FocusOut>',save_folder)
    win.folder_entry.bind('<Return>',lambda e:(save_folder(),'break')[1])
    def browse():
        folder=filedialog.askdirectory(parent=win,title='Choose default media folder',initialdir=win.folder_default.get() or str(Path.home()))
        if folder:win.folder_default.set(folder);save_folder()
    ttk.Button(inputs,text='Browse…',command=browse).grid(row=2,column=2,sticky='e',padx=(7,0))
    win.auto_import_variable=tk.BooleanVar(value=bool(app.auto_import_media))
    win.auto_import_toggle=ttk.Checkbutton(inputs,text='Import supported files automatically when starting a new empty project',
        variable=win.auto_import_variable)
    def toggle_import():
        app.auto_import_media=bool(win.auto_import_variable.get())
        app.save_preferences()
    win.auto_import_toggle.configure(command=toggle_import)
    win.auto_import_toggle.grid(row=3,column=0,columnspan=3,sticky='w',pady=(7,4))
    row=ttk.Frame(body);row.grid(row=8,column=0,sticky='ew',pady=(10,13))
    ttk.Button(row,text='Preferences…',command=win.preferences_actions['general']).pack(side='left')
    label(body,'APPEARANCE',9,'bold',accent).grid(row=9,column=0,sticky='w',pady=(0,6))
    appearance=ttk.Frame(body);appearance.grid(row=10,column=0,sticky='ew',pady=(0,9))
    ttk.Label(appearance,text='Theme').pack(side='left')
    win.theme_var=app.theme_name
    win.theme_combo=ttk.Combobox(appearance,textvariable=win.theme_var,values=app.available_themes,state='readonly',width=21)
    app.startup_theme_combo=win.theme_combo
    win.theme_combo.pack(side='left',padx=9)
    win.theme_combo.bind('<<ComboboxSelected>>',lambda _e:app.apply_welcome_theme(win.theme_var.get()))
    ttk.Button(appearance,text='Edit Appearance…',command=win.preferences_actions['appearance']).pack(side='left',padx=4)
    ttk.Label(body,text='Local-first instrument  ·  '+VERSION,style='Muted.TLabel').grid(row=11,column=0,sticky='w',pady=(8,0))
    def wheel(event):
        if not win.winfo_exists():return
        direction=-1 if getattr(event,'num',0)==4 or getattr(event,'delta',0)>0 else 1
        canvas.yview_scroll(direction*3,'units');return 'break'
    def scroll_bind(widget):
        for event in ('<MouseWheel>','<Button-4>','<Button-5>'):widget.bind(event,wheel,add='+')
        for child in widget.winfo_children():scroll_bind(child)
    scroll_bind(body);scroll_bind(canvas)
    def retheme():
        # Existing Welcome uses native Tk frames/labels alongside ttk widgets.
        # ttk responds to a theme change, but native Tk has to be refreshed in
        # place. Never destroy/recreate the window (preserves scroll and focus).
        if not win.winfo_exists():return
        palette=app.ui_chrome
        ground=palette.get('panel_bg','#1d202c')
        surface_colour=palette.get('field_bg','#171b29')
        family=palette.get('font_family','TkDefaultFont')
        def visit(widget):
            if isinstance(widget,tk.Frame):
                colour=surface_colour if getattr(widget,'_welcome_surface',False) else ground
                widget.configure(bg=colour)
                if getattr(widget,'_welcome_surface',False):
                    widget.configure(highlightbackground=palette.get('border',palette.get('panel_edge','#394357')))
            elif isinstance(widget,tk.Label) and hasattr(widget,'_welcome_colour_role'):
                role=widget._welcome_colour_role
                widget.configure(bg=widget.master.cget('bg'),fg=palette.get(role,palette.get('foreground','#ececf5')),
                    font=(family,widget._welcome_font_size,widget._welcome_font_weight))
            elif isinstance(widget,tk.Canvas):widget.configure(bg=ground)
            for child in widget.winfo_children():visit(child)
        visit(wrap)
    win.retheme=retheme
    win.after_idle(app.welcome_continue.focus_set)
    return win
