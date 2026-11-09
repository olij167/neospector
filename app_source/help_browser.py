"""Search the single command catalogue and open observable guided tasks."""
import tkinter as tk
from tkinter import ttk
from guided_lessons import LESSONS, BY_ID, RECIPES


def focus_command(app, command):
    """Locate an actual visible projection; never invoke it to 'show' it."""
    if getattr(app,'inline_rack_mode',False) and (command.id.startswith('rack.') or command.target=='panel.rack'):
        cell=app.deck.selected_cell()
        role=cell.adapter.owner.extra.get('voice') if cell and cell.adapter.scope=='Layer' else None
        section=app.queue_deck.pages[role].rack_section if role in app.queue_deck.pages else app.whole_rack
        widget=section.add_button if command.id=='rack.add-module' else section.toggle_button
        if widget.winfo_viewable():widget.focus_set();return True
    label=command.label.casefold()
    def walk(parent):
        for widget in parent.winfo_children():
            try:
                if widget.winfo_viewable() and str(widget.cget('text')).casefold().strip('…')==label.strip('…'):
                    return widget
            except (tk.TclError,AttributeError):pass
            found=walk(widget)
            if found:return found
    widget=walk(app)
    if widget:widget.focus_set();return True
    return False


def show(app, selected=None):
    old=getattr(app,'help_window',None)
    if old and old.winfo_exists():
        old.deiconify();old.lift();old.focus_set()
        if selected and getattr(old,'select_command',None):old.select_command(selected)
        return old
    win=tk.Toplevel(app);app.help_window=win;win.title('Help and actions · Neospector')
    win.transient(app);win.geometry('780x610');win.minsize(530,410)
    previous=app.focus_get()
    body=ttk.Frame(win,padding=12);body.pack(fill='both',expand=True)
    body.columnconfigure(0,weight=1);body.rowconfigure(2,weight=1)
    ttk.Label(body,text='What would you like to do?',style='Title.TLabel').grid(row=0,column=0,sticky='w')
    query=tk.StringVar()
    entry=ttk.Entry(body,textvariable=query);entry.grid(row=1,column=0,sticky='ew',pady=(7,9))
    panes=ttk.Panedwindow(body,orient='horizontal');panes.grid(row=2,column=0,sticky='nsew')
    left=ttk.Frame(panes);left.columnconfigure(0,weight=1);left.rowconfigure(1,weight=1)
    right=ttk.Frame(panes);right.columnconfigure(0,weight=1);right.rowconfigure(1,weight=1)
    panes.add(left,weight=3);panes.add(right,weight=2)
    ttk.Label(left,text='Actions · selecting explains, never activates').grid(row=0,column=0,sticky='w')
    rows=ttk.Treeview(left,columns=('where','key'),show='tree headings',selectmode='browse')
    rows.heading('#0',text='Action');rows.column('#0',width=270)
    rows.heading('where',text='Scope');rows.column('where',width=95,stretch=False)
    rows.heading('key',text='Key');rows.column('key',width=70,stretch=False)
    rows.grid(row=1,column=0,sticky='nsew');scroll=ttk.Scrollbar(left,command=rows.yview)
    scroll.grid(row=1,column=1,sticky='ns');rows.configure(yscrollcommand=scroll.set)
    ttk.Label(right,text='Guided tasks · real actions').grid(row=0,column=0,sticky='w')
    lessons=ttk.Treeview(right,show='tree',selectmode='browse');lessons.grid(row=1,column=0,sticky='nsew')
    lscroll=ttk.Scrollbar(right,command=lessons.yview);lscroll.grid(row=1,column=1,sticky='ns');lessons.configure(yscrollcommand=lscroll.set)
    detail=tk.StringVar(value='Choose an action or a guided task. Help does not start a source or recording.')
    ttk.Label(body,textvariable=detail,wraplength=740,justify='left',anchor='nw').grid(row=3,column=0,sticky='ew',pady=(10,7))
    bar=ttk.Frame(body);bar.grid(row=4,column=0,sticky='ew')
    locate=ttk.Button(bar,text='Show control',state='disabled');locate.pack(side='left')
    start=ttk.Button(bar,text='Start guided task',state='disabled');start.pack(side='left',padx=6)
    ttk.Button(bar,text='Close',command=lambda:close()).pack(side='right')
    ttk.Label(body,text='F1 here focuses search · Enter opens a task · Escape closes Help',style='Muted.TLabel').grid(row=5,column=0,sticky='w',pady=(8,0))

    def description(command):
        try:available=command.is_enabled()
        except Exception:available=False
        info=command.help or (command.label+'. Use the '+command.scope+' controls.')
        return info+('  Available now.' if available else '  Unavailable in the current context.')

    def update(*_):
        term=query.get().strip().casefold();rows.delete(*rows.get_children());lessons.delete(*lessons.get_children())
        for command in app.commands.definitions():
            if term and term not in (' '.join((command.id,command.label,command.help,command.scope))).casefold():continue
            rows.insert('','end',iid=command.id,text=command.label,values=(command.scope,command.shortcut))
        for lesson in LESSONS:
            words=' '.join((lesson.id,lesson.title,lesson.area,*(step.instruction for step in lesson.steps)))
            if term and term not in words.casefold():continue
            lessons.insert('','end',iid='lesson:'+lesson.id,text=lesson.title+'  ·  '+lesson.area)
        if not term:
            for title,ids in RECIPES.items():
                parent=lessons.insert('','end',iid='recipe:'+title,text='Recipe · '+title)
                for lesson_id in ids:lessons.insert(parent,'end',iid='recipe:'+title+':'+lesson_id,text='↳ '+BY_ID[lesson_id].title)

    def select_command(cid):
        if rows.exists(cid):rows.selection_set(cid);rows.focus(cid);rows.see(cid);selected_action()
    win.select_command=select_command
    def selected_action(_=None):
        item=rows.focus()
        if not item:return
        lessons.selection_remove(*lessons.selection())
        command=app.commands.get(item);detail.set(description(command))
        locate.configure(state='normal');start.configure(state='disabled')
    def selected_lesson(_=None):
        item=lessons.focus();lid=item.split(':')[-1]
        if lid not in BY_ID:start.configure(state='disabled');return
        rows.selection_remove(*rows.selection());locate.configure(state='disabled');start.configure(state='normal')
        lesson=BY_ID[lid];done=getattr(app,'ux7_lesson_progress',{}).get(lid,{})
        detail.set(lesson.title+' · '+str(len(lesson.steps))+' real steps.'+(' Completed previously.' if done.get('complete') else '')+' '+lesson.steps[0].instruction)
    def locate_action():
        item=rows.focus()
        if not item:return
        command=app.commands.get(item)
        if not focus_command(app,command):detail.set(description(command)+' Find it in '+command.scope+'.')
    def begin(_=None):
        item=lessons.focus();lid=item.split(':')[-1]
        if lid in BY_ID:app.guides.open(lid);return 'break'
    def close():
        win.destroy();app.help_window=None
        try:
            if previous and previous.winfo_exists():previous.focus_set()
        except tk.TclError:pass

    query.trace_add('write',update);rows.bind('<<TreeviewSelect>>',selected_action)
    lessons.bind('<<TreeviewSelect>>',selected_lesson);lessons.bind('<Double-1>',begin);lessons.bind('<Return>',begin)
    locate.configure(command=locate_action);start.configure(command=begin)
    win.protocol('WM_DELETE_WINDOW',close);win.bind('<Escape>',lambda _e:close())
    win.bind('<F1>',lambda _e:(entry.focus_set(),'break')[1]);win.bind('<Control-f>',lambda _e:entry.focus_set())
    update()
    if selected:select_command(selected)
    else:
        focus=previous
        if focus:
            try:label=str(focus.cget('text')).casefold()
            except (tk.TclError,AttributeError):label=''
            if label:
                match=next((d for d in app.commands.definitions() if d.label.casefold()==label),None)
                if match:select_command(match.id)
    entry.focus_set();return win
