"""Immediate occurrence-pair boundary editing with one Undo per gesture."""
from __future__ import annotations
import copy
import math
import tkinter as tk
from tkinter import ttk
from queue_transitions import boundary, set_boundary, VISUAL_KINDS


def open_queue_transition(app, role, from_id, to_id=None):
    try:
        info = boundary(app.project, role, from_id, to_id)
    except ValueError as exc:
        app.update_status(str(exc))
        return
    title = ('Music' if role == 'Music' else 'Channel ' + role) + (' · Loop boundary' if info.get('seam') else ' · Transition')
    key = ('queue-boundary', role, info['from_id'], info['to_id'])
    def build(parent):
        host = ttk.Frame(parent); host.pack(fill='both', expand=True)
        footer = ttk.Frame(host); footer.pack(side='bottom', fill='x')
        canvas = tk.Canvas(host, height=220, highlightthickness=0, bg=app.ui_chrome['field_bg'])
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(host, command=canvas.yview)
        scrollbar.pack(side='right', fill='y'); canvas.configure(yscrollcommand=scrollbar.set)
        editor = BoundaryEditor(canvas, app, role, info, footer_parent=footer)
        window = canvas.create_window(0, 0, anchor='nw', window=editor)
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        editor.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')), add='+')
        def scroll(event):
            direction = -1 if getattr(event, 'num', None) == 4 or getattr(event, 'delta', 0) > 0 else 1
            canvas.yview_scroll(direction * 2, 'units'); return 'break'
        def bind_scroll(widget):
            for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):widget.bind(event, scroll, add='+')
            for child in widget.winfo_children():bind_scroll(child)
        bind_scroll(editor)
        return editor
    if hasattr(app, 'open_context_tray'):
        return app.open_context_tray(key, title, build)
    # Compatibility with the previous shell: keep the editor beside this queue.
    page = app.queue_deck.pages[role]
    if getattr(page, 'boundary_editor', None):
        page.boundary_editor.destroy()
    page.boundary_editor = ttk.LabelFrame(page, text=title, padding=4)
    page.boundary_editor.pack(side='bottom', fill='x', before=page.append_drop)
    return build(page.boundary_editor)


class BoundaryEditor(ttk.Frame):
    def __init__(self, parent, app, role, info, footer_parent=None):
        super().__init__(parent, padding=5)
        self.app, self.role, self.info = app, role, info
        self.project = app.project
        self.is_seam=bool(info.get('seam'))
        self.choices = {'cut':'Cut','seam_fade':'Fade through silence' if role=='Music' else 'Fade through background'} if self.is_seam else {'cut': 'Cut', 'crossfade': 'Crossfade'} if role == 'Music' else VISUAL_KINDS
        self.default_kind=next(label for key,label in self.choices.items() if key!='cut')
        self.kind = tk.StringVar(value=self.choices.get(info['kind'], 'Cut'))
        self.seconds = tk.StringVar(value=f"{info['seconds']:.3f}")
        self.preview_value = tk.DoubleVar(value=info['seconds'])
        self.message = tk.StringVar()
        self.drag_start = None
        self.gesture_token = None
        self.analysis_dirty = False
        self.entry_text = self.seconds.get()
        self.audition_window = None
        names = info['names']
        self.names_label = ttk.Label(self, text=names[0] + '  →  ' + names[1],
                                     style='Title.TLabel', wraplength=400)
        self.names_label.pack(fill='x')
        if self.is_seam:ttk.Label(self,text='Last → first · total fade time split across both edges. Queue length stays fixed.',wraplength=410).pack(fill='x')
        row = ttk.Frame(self); row.pack(fill='x', pady=4)
        box = ttk.Combobox(row, values=list(self.choices.values()), textvariable=self.kind,
                           state='readonly', width=16)
        box.pack(side='left')
        box.bind('<<ComboboxSelected>>', self.choose_kind)
        self.entry = ttk.Entry(row, textvariable=self.seconds, width=8)
        self.entry.pack(side='left', padx=(6, 2))
        ttk.Label(row, text='seconds').pack(side='left')
        self.entry.bind('<FocusIn>', self.begin)
        self.entry.bind('<FocusOut>', self.finish)
        self.entry.bind('<Return>', self.finish)
        self.entry.bind('<KP_Enter>', self.finish)
        self.entry.bind('<Escape>', self.reset)
        self.entry.bind('<KeyRelease>', self.preview_entry)
        self.canvas = tk.Canvas(self, height=66, highlightthickness=0, takefocus=True)
        self.canvas.pack(fill='x', pady=3)
        self.canvas.bind('<Configure>', lambda e: self.draw())
        self.canvas.bind('<Button-1>', self.start_drag)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.finish)
        self.canvas.bind('<Left>', lambda e: self.nudge(-1))
        self.canvas.bind('<Right>', lambda e: self.nudge(1))
        self.canvas.bind('<Escape>', self.reset)
        self.canvas.bind('<FocusOut>', self.finish)
        self.scale = ttk.Scale(self, from_=0, to=info['maximum'],
                               variable=self.preview_value, command=self.slide)
        self.scale.pack(fill='x')
        self.scale.bind('<Escape>', self.reset)
        self.scale.bind('<ButtonPress-1>', self.begin)
        self.scale.bind('<ButtonRelease-1>', self.finish)
        self.scale.bind('<FocusOut>', self.finish)
        curves=['equal_power','linear'] if role=='Music' else ['smooth','linear','ease_in','ease_out']
        curve_row=ttk.Frame(self);curve_row.pack(fill='x')
        ttk.Label(curve_row,text='Curve').pack(side='left')
        self.curve=tk.StringVar(value=info.get('curve',curves[0]))
        self.curve_box=ttk.Combobox(curve_row,textvariable=self.curve,values=curves,state='readonly',width=13)
        self.curve_box.pack(side='left',padx=4);self.curve_box.bind('<<ComboboxSelected>>',lambda e:self.discrete())
        footer = footer_parent if footer_parent is not None else self
        self.actions = actions = ttk.Frame(footer); actions.pack(side='bottom', fill='x', pady=4)
        for label, seconds in [('Cut', 0), ('Quick', .25), ('Soft', 1.)]:
            ttk.Button(actions, text=label, width=6,
                       command=lambda n=seconds: self.preset(n)).pack(side='left', padx=(0, 3))
        self.audition_button=ttk.Button(actions,text='Audition',command=self.audition)
        self.audition_button.pack(side='right')
        ttk.Button(actions,text='Cancel gesture',command=self.reset).pack(side='right',padx=3)
        if info.get('compatibility'):
            ttk.Label(self,text='Manual overlap retained until this boundary is edited.',wraplength=410).pack(fill='x')
        self.message_label = ttk.Label(footer, textvariable=self.message, wraplength=410)
        self.message_label.pack(side='bottom', fill='x', pady=(2, 0))
        footer.bind('<Configure>', lambda e: self.message_label.configure(wraplength=max(150, e.width - 8)), add='+')
        self.bind('<Configure>', self.resize)
        self.bind('<Destroy>', self.on_destroy,add='+')
        self.draw()

    def resize(self, event):
        width = max(160, event.width - 12)
        for child in self.winfo_children():
            if isinstance(child, ttk.Label):child.configure(wraplength=width)

    def choose_kind(self, event=None):
        if self.kind.get() == 'Cut':self.preset(0)
        elif self.preview_value.get() <= 0:self.preset(min(.5, self.info['maximum']))
        else:self.discrete()

    def set_seconds(self, value):
        value = max(0., min(self.info['maximum'], float(value)))
        self.seconds.set(f'{value:.3f}'); self.entry_text = self.seconds.get(); self.preview_value.set(value)
        if value == 0:self.kind.set('Cut')
        elif self.kind.get() == 'Cut':self.kind.set(self.default_kind)
        self.apply(); self.draw()

    def preset(self, value):
        self.begin();self.set_seconds(min(value,self.info['maximum']));self.finish()
    def slide(self, value):self.set_seconds(float(value))

    def preview_entry(self,event=None):
        text=self.seconds.get()
        if event is not None and (getattr(event,'keysym','') in ('Return','KP_Enter','Escape','Tab') or text==self.entry_text):return
        self.entry_text=text
        try:value = float(text)
        except ValueError:return
        if math.isfinite(value) and 0 <= value <= self.info['maximum']:
            self.preview_value.set(value)
            if value > 0 and self.kind.get() == 'Cut':self.kind.set(self.default_kind)
            elif value == 0:self.kind.set('Cut')
            self.apply();self.draw()
        else:self.message.set('Use finite seconds within the overlap range.')

    def start_drag(self, event):
        self.canvas.focus_set()
        self.begin();self.drag_start = (event.x, self.preview_value.get())

    def drag(self, event):
        if self.drag_start is None:return
        x, value = self.drag_start
        self.set_seconds(value + (x - event.x) / max(1, self.canvas.winfo_width() * .38) * self.info['maximum'])

    def nudge(self, direction):
        self.begin();self.set_seconds(self.preview_value.get() + direction / self.app.project.fps);self.finish()
        return 'break'

    def draw(self):
        c = self.app.ui_chrome; cv = self.canvas
        width = max(180, cv.winfo_width()); cv.delete('all'); cv.configure(bg=c['field_bg'])
        value = self.preview_value.get() if self.kind.get() != 'Cut' else 0
        if self.is_seam:
            middle=width/2
            cv.create_rectangle(8,12,middle-5,48,fill=c['selection_bg'],outline=c['accent'])
            cv.create_rectangle(middle+5,12,width-8,48,fill=c['selection_bg'],outline=c['accent'])
            if value:
                cv.create_line(12,16,middle-8,46,fill=c['accent'],width=2);cv.create_line(middle+8,46,width-12,16,fill=c['accent'],width=2)
            cv.create_text(width/4,31,text='LAST',fill=c['foreground']);cv.create_text(width*3/4,31,text='FIRST',fill=c['foreground'])
            cv.create_text(middle,61,text=f'{value/2:.3f}s out + {value/2:.3f}s in' if value else 'Loop · Cut',fill=c['muted_fg'])
            return
        overlap = min(1., value / max(.001, self.info['maximum'])) * width * .38
        join = width * .52; incoming = join - overlap
        cv.create_rectangle(8, 10, join, 32, fill=c['selection_bg'], outline=c['accent'])
        cv.create_rectangle(incoming, 37, width - 8, 59, fill=c['selection_bg'], outline=c['accent'])
        cv.create_text(14, 21, text='OUT', anchor='w', fill=c['foreground'])
        cv.create_text(width - 14, 48, text='IN', anchor='e', fill=c['foreground'])
        cv.create_line(incoming, 5, incoming, 59, fill=c['accent'], width=3)
        cv.create_line(join, 5, join, 59, fill=c['muted_fg'], dash=(2, 3))
        if overlap > 20:
            cv.create_line(incoming, 11, join, 31, fill=c['accent'], width=2)
            cv.create_line(incoming, 58, join, 38, fill=c['accent'], width=2)
        cv.create_text(width / 2, 64, text=f'{value:.3f}s overlap' if value else 'Cut · no overlap',
                       fill=c['muted_fg'], font=('TkFixedFont', 8))

    def begin(self,event=None):
        if self.app.project is not self.project:return False
        if self.gesture_token is not None and getattr(self.app,'gesture',None) is self.gesture_token:return True
        if hasattr(self.app,'begin_gesture'):
            if getattr(self.app,'gesture',None) is not None:self.app.end_gesture()
            self.app.begin_gesture('queue-boundary');self.gesture_token=self.app.gesture
        return True

    def finish(self,event=None):
        refresh=self.analysis_dirty and self.app.project is self.project
        self.analysis_dirty=False
        self.drag_start=None
        if self.gesture_token is not None and getattr(self.app,'gesture',None) is self.gesture_token:
            self.app.end_gesture()
        self.gesture_token=None
        if refresh and hasattr(self.app,'prepare_sound_analysis'):self.app.prepare_sound_analysis()
        if self.app.project is self.project:
            try:self.info=boundary(self.project,self.role,self.info['from_id'],self.info['to_id'])
            except ValueError:pass
        return 'break' if event and getattr(event,'keysym','') in ('Return','KP_Enter') else None

    def discrete(self):
        self.begin();self.apply();self.finish();self.draw()

    def reset(self,event=None):
        self.analysis_dirty=False
        self.drag_start=None
        if self.app.project is self.project and self.gesture_token is not None and getattr(self.app,'gesture',None) is self.gesture_token:
            self.app.cancel_gesture();self.project=self.app.project
        self.gesture_token=None
        if self.app.project is not self.project:return 'break'
        try:self.info=boundary(self.project,self.role,self.info['from_id'],self.info['to_id'])
        except ValueError:return 'break'
        self.kind.set(self.choices.get(self.info['kind'],'Cut'));self.curve.set(self.info.get('curve',self.curve.get()))
        self.seconds.set(f"{self.info['seconds']:.3f}");self.entry_text=self.seconds.get();self.preview_value.set(self.info['seconds'])
        self.message.set('Gesture cancelled.');self.draw();return 'break'

    def apply(self):
        # Compatibility entry point: changes are already live; no Apply button.
        if self.app.project is not self.project:
            self.message.set('The project changed. Reopen this boundary before editing.');return
        try:
            seconds=float(self.seconds.get())
            if not math.isfinite(seconds):raise ValueError('Use finite seconds.')
            kind=next(k for k,label in self.choices.items() if label==self.kind.get())
            now=self.app.programme_time() if self.app.playing and not self.app.reviewing else None
            self.begin()
            # Setters validate all geometry and locks before mutating. No full
            # project copy, transaction, widget rebuild or analysis per pointer.
            result=set_boundary(self.project,self.role,self.info['from_id'],self.info['to_id'],kind,seconds,now=now,curve=self.curve.get())
        except (ValueError,StopIteration) as exc:
            self.message.set(str(exc) or 'Choose a transition.');return
        self.analysis_dirty=True
        if hasattr(self.app,'changed'):self.app.changed(redraw=False)
        from instrument_model import voice
        history=self.project.extra.get('music_queue_history',[]) if self.role=='Music' else voice(self.project,self.role).extra.get('queue_history',[])
        pending=now is not None and history and history[-1]['end']>now+1e-7
        self.message.set('Next repeat · current overlap retained.' if pending else 'Future boundary · live.' if now is not None else 'Live boundary · Undo restores the gesture.')
        return result

    def on_destroy(self,event):
        if event.widget is not self:return
        self.finish()
        if self.audition_window is not None:
            try:self.audition_window.destroy()
            except tk.TclError:pass

    def audition(self):
        """Separate finite preview, with its own renderer/audio and clock."""
        import time
        from PIL import ImageTk
        from instrument_model import voice
        from music_queue import items
        from programme_renderer import ProgrammeRenderer
        from audio_bus import AudioTransport
        self.finish()
        if self.app.project is not self.project:return
        if self.audition_window is not None:self.audition_window.destroy()
        p=copy.deepcopy(self.project)
        if self.role=='Music':
            incoming=next(e for e in items(p) if e['id']==self.info['to_id']);start=max(0.,incoming['start']-.5);end=incoming['start']+self.preview_value.get()+.5
            p.extra['music_queue_policy']='finish';p.extra.pop('music_queue_history',None);p.extra.pop('music_queue_origins',None)
            p.extra['sound_events']=[e for e in p.extra.get('sound_events',[]) if e.get('route_id','soundtrack')=='soundtrack']
            p.extra.pop('sound_route_history',None)
            for rid,route in p.extra.get('sound_routes',{}).items():
                if rid!='soundtrack':route['enabled']=False
        else:
            layer=voice(p,self.role);incoming=next(c for c in layer.clips if c.id==self.info['to_id']);start=max(0.,incoming.start-.5);end=incoming.start+self.preview_value.get()+.5
            for l in p.layers:l.enabled=l is layer;l.extra['queue_policy']='finish';l.extra.pop('queue_history',None);l.extra.pop('source_switches',None)
        if self.is_seam:
            if self.role=='Music':
                cycle=max(e['start']+e['duration'] for e in items(p));p.extra['music_queue_policy']='repeat'
            else:
                cycle=max(c.end for c in voice(p,self.role).clips);voice(p,self.role).extra['queue_policy']='repeat'
            start=max(0.,cycle-max(.5,self.preview_value.get()/2));end=cycle+max(.5,self.preview_value.get()/2)
        win=tk.Toplevel(self);self.audition_window=win;win.title('Independent boundary audition')
        label=ttk.Label(win,text='Independent audition');label.pack(fill='both',expand=True)
        renderer=ProgrammeRenderer(missing_policy='transparent');audio=AudioTransport();job=[None];closed=[False]
        if self.role=='Music':audio.start(p,start)
        def stop(event=None):
            if event is not None and event.widget is not win:return
            if closed[0]:return
            closed[0]=True
            if job[0]:
                try:win.after_cancel(job[0])
                except tk.TclError:pass
            audio.stop();renderer.close();self.audition_window=None
        def close():stop();win.destroy()
        ttk.Button(win,text='Stop audition',command=close).pack(fill='x');win.protocol('WM_DELETE_WINDOW',close);win.bind('<Destroy>',stop,add='+')
        origin=time.monotonic()
        def tick():
            if closed[0]:return
            t=start+time.monotonic()-origin
            if t>=end:audio.stop();label.configure(text='Audition finished');return
            try:
                if self.role!='Music':
                    photo=ImageTk.PhotoImage(renderer.render(p,t,(320,180)),master=win);label.configure(image=photo);label.image=photo
                else:label.configure(text=f'Independent Music audition · {t-start:.1f}s')
                job[0]=win.after(40,tick)
            except Exception as exc:label.configure(text=str(exc));audio.stop()
        tick()
