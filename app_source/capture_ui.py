"""One docked capture surface over the existing Programme and export services.

The panel owns disposable UI state only. Recording, reservations, saved Drafts,
decoder isolation, validation and atomic output replacement remain in the runtime.
"""
from __future__ import annotations

import copy
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from export_scope import export_visual_project, resolve_export_range, seconds
from media_engine import EXPORT_PROFILES
from music_queue import items
from responsive_controls import FlowRow, PriorityToolbar, OverflowAdapter


class CaptureActions:
    """Place before OmneWorkspace and PlayableLifecycle in the application MRO."""

    def open_capture(self, mode='record'):
        panel = getattr(self, '_capture_panel', None)
        if panel is not None and panel.winfo_exists():
            panel.select(mode)
            return panel

        def build(parent):
            self._capture_panel = CapturePanel(parent, self)
            self._capture_panel.pack(fill='both', expand=True)
            self._capture_panel.select(mode)

        self.open_context_tray('capture', 'Record / Export', build)
        return self._capture_panel

    def export_video(self):
        return self.open_capture('export')

    def show_drafts(self):
        return self.open_capture('drafts')

    def capture_record_action(self):
        # Programme recording is now a direct transport action. Configuration
        # lives in the persistent Record Settings window, not a transient tray.
        if hasattr(self,'record_programme'):return self.record_programme()
        return self.toggle_output_record()

    def capture_draft_ready(self, take, path):
        panel = self.open_capture('drafts')
        panel.refresh_drafts()
        panel.draft_tree.selection_set(take.id)
        panel.draft_tree.see(take.id)

    def update_status(self, text):
        result = super().update_status(text)
        value = str(text)
        if value.startswith(('Export', 'Pinned · exporting', 'Rendering', 'Encoding',
                             'Recording', 'Programme recording', 'Finishing output',
                             'Pinning recent', 'Captured ', 'Capture:')):
            self._capture_feedback = value
        return result


class CapturePanel(ttk.Frame):
    SCOPES = {'Whole sequence': 'sequence', 'Music queue': 'music',
              'Visual queue': 'visual', 'Current song': 'song',
              'Specific clip': 'clip', 'Specific track': 'track', 'Duration': 'duration'}
    STARTS = {'Beginning': 'beginning', 'Playhead': 'playhead', 'Recent history': 'recent'}

    def __init__(self, parent, app):
        super().__init__(parent, padding=(4, 2))
        self.app = app
        self._timer = None
        self._draft_key = None
        self.resolved = None
        self.snapshot = None
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True)
        self.pages = {}
        for key, label in (('record', 'Record'), ('export', 'Export'), ('drafts', 'Drafts')):
            page = ttk.Frame(self.tabs, padding=4)
            self.tabs.add(page, text=label)
            self.pages[key] = page
        self.feedback = tk.StringVar(value=getattr(app, '_capture_feedback', ''))
        self.feedback_label = ttk.Label(self, textvariable=self.feedback, style='Muted.TLabel', wraplength=330)
        self.feedback_label.pack(fill='x', pady=(3, 0))
        self.build_record(self.pages['record'])
        self.build_export(self.pages['export'])
        self.build_drafts(self.pages['drafts'])
        self.bind('<Configure>', self.resize, add='+')
        self.bind('<Destroy>', self.destroyed, add='+')
        self.refresh_snapshot()
        self.tick()

    def select(self, mode):
        self.tabs.select(self.pages.get(mode, self.pages['record']))
        if mode == 'drafts':
            self.refresh_drafts()

    def resize(self, event):
        if event.widget is not self:
            return
        for label in (self.feedback_label, self.record_help, self.source_label, self.range_label):
            label.configure(wraplength=max(180, event.width - 28))

    def destroyed(self, event):
        if event.widget is self and self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None

    def build_record(self, body):
        self.record_help = ttk.Label(body, text='Programme recording uses the saved Record Settings. Start/Stop is immediate; late rendered frames are held.',
                                     wraplength=330, style='Muted.TLabel')
        self.record_help.pack(fill='x', pady=(0, 5))
        row = PriorityToolbar(body, gap=4)
        row.pack(fill='x')
        self.record = ttk.Button(row, text='● Record Programme', style='Accent.TButton', command=self.record_action)
        row.add(self.record, priority=0, pinned=True)
        self.record_state = tk.StringVar()
        row.add(ttk.Label(row, textvariable=self.record_state), priority=0, pinned=True)
        if hasattr(self.app,'open_record_settings'):row.add(ttk.Button(row,text='Settings…',command=self.app.open_record_settings),priority=30)
        row = PriorityToolbar(body, gap=4)
        row.pack(fill='x', pady=(6, 0))
        row.add(ttk.Checkbutton(row, text='Retain live inputs', variable=self.app.retain_armed,
                                command=self.app.toggle_retention), priority=10)
        row.add(ttk.Button(row, text='History / coverage…', command=self.app.history_settings), priority=80)
        row.add(ttk.Checkbutton(row, text='Record control motion', variable=self.app.record_automation), priority=60)

    def record_action(self):
        self.app.toggle_output_record()
        if self.winfo_exists():
            self.refresh_state()

    def build_export(self, body):
        # Delivery actions remain reachable while the small centre tray scrolls.
        row = PriorityToolbar(body, gap=4)
        row.pack(side='bottom', fill='x', pady=(4, 0))
        self.export_button = ttk.Button(row, text='Export snapshot…', style='Accent.TButton', command=self.start_export)
        row.add(self.export_button, priority=0, pinned=True)
        self.cancel_export = ttk.Button(row, text='Cancel export', command=self.cancel)
        row.add(self.cancel_export, priority=0, pinned=True)
        self.export_progress = ttk.Progressbar(body, maximum=100)
        self.export_progress.pack(side='bottom', fill='x', pady=(3, 0))
        self.range_value = tk.StringVar()
        self.range_label = ttk.Label(body, textvariable=self.range_value, wraplength=320)
        self.range_label.pack(side='bottom', fill='x', pady=2)
        scope_row = ttk.Frame(body)
        scope_row.pack(fill='x', pady=(0, 3))
        ttk.Label(scope_row, text='Scope').pack(side='left', padx=(0, 5))
        self.scope = tk.StringVar(value='Whole sequence')
        self.scope_box = ttk.Combobox(scope_row, textvariable=self.scope, values=list(self.SCOPES), state='readonly')
        self.scope_box.pack(side='left', fill='x', expand=True)
        self.scope_box.bind('<<ComboboxSelected>>', lambda e: self.scope_changed())
        scroll = ttk.Frame(body)
        scroll.pack(fill='both', expand=True)
        canvas = tk.Canvas(scroll, highlightthickness=0, height=180,
                           background=self.app.ui_chrome['background'])
        bar = ttk.Scrollbar(scroll, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        form = ttk.Frame(canvas)
        item = canvas.create_window((0, 0), anchor='nw', window=form)
        form.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(item, width=max(1, e.width)))
        self.export_canvas = canvas
        self.source = tk.StringVar()
        self.source_label = ttk.Label(form, textvariable=self.source, style='Muted.TLabel', wraplength=320)
        self.source_label.pack(fill='x')
        ttk.Button(form, text='Refresh from current view', command=self.refresh_snapshot).pack(anchor='w', pady=3)
        self.target = tk.StringVar()
        self.target_box = ttk.Combobox(form, textvariable=self.target, state='readonly')
        self.target_box.pack(fill='x', pady=3)
        self.target_box.bind('<<ComboboxSelected>>', lambda e: self.resolve())
        self.duration_row = FlowRow(form, gap=4)
        self.duration_row.pack(fill='x', pady=3)
        self.duration_row.add(ttk.Label(self.duration_row, text='Seconds / m:ss'))
        self.duration = tk.StringVar(value='30')
        self.duration_entry = ttk.Entry(self.duration_row, textvariable=self.duration, width=8)
        self.duration_row.add(self.duration_entry)
        self.start_mode = tk.StringVar(value='Beginning')
        self.start_box = ttk.Combobox(self.duration_row, textvariable=self.start_mode,
                                     values=list(self.STARTS), state='readonly', width=14)
        self.duration_row.add(self.start_box)
        self.start_box.bind('<<ComboboxSelected>>', lambda e: self.resolve())
        self.duration.trace_add('write', lambda *_: self.resolve())
        ttk.Label(form, text='Scope sets the interval; all picture and Sound routes remain in the mix. Retained live coverage is checked before rendering.',
                  style='Muted.TLabel', wraplength=285).pack(fill='x', pady=3)
        self.profiles = {v['label']: k for k, v in EXPORT_PROFILES.items()}
        self.profile = tk.StringVar(value=EXPORT_PROFILES['web']['label'])
        ttk.Combobox(form, textvariable=self.profile, values=list(self.profiles), state='readonly').pack(fill='x', pady=3)
        self.size = tk.StringVar(value='Project size')
        ttk.Combobox(form, textvariable=self.size, values=['Project size', 'Long edge 1920', 'Long edge 1280', 'Long edge 640'],
                     state='readonly').pack(fill='x', pady=3)
        # Wheel handling is local to this panel; do not steal the instrument's bindings.
        def wheel(event):
            direction = -1 if getattr(event, 'num', None) == 4 or getattr(event, 'delta', 0) > 0 else 1
            canvas.yview_scroll(direction * 3, 'units')
            return 'break'
        def bind_wheel(widget):
            if not isinstance(widget, ttk.Combobox):
                for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                    widget.bind(event, wheel, add='+')
            for child in widget.winfo_children():
                bind_wheel(child)
        bind_wheel(form)
        bind_wheel(canvas)

    def build_drafts(self, body):
        keep = PriorityToolbar(body, gap=4)
        keep.pack(fill='x')
        self.keep_duration_group = ttk.Frame(keep)
        ttk.Label(self.keep_duration_group, text='Recent seconds').pack(side='left')
        self.keep_duration = tk.StringVar(value=self.app.capture_seconds.get())
        ttk.Entry(self.keep_duration_group, textvariable=self.keep_duration, width=7).pack(side='left', padx=(4, 0))
        keep.add(self.keep_duration_group, priority=10, overflow=OverflowAdapter.mirror())
        self.keep_button = ttk.Button(keep, text='Keep Draft', command=self.keep)
        keep.add(self.keep_button, priority=0, pinned=True)
        row = PriorityToolbar(body, gap=4)
        row.pack(side='bottom', fill='x', pady=(3, 0))
        row.add(ttk.Button(row, text='Open…', command=self.open_draft), priority=70)
        row.add(ttk.Button(row, text='Review', command=self.review_selected), priority=10)
        row.add(ttk.Button(row, text='Export', command=lambda: self.review_selected(True)), priority=20)
        row.add(ttk.Button(row, text='Return to Programme', command=self.go_live), priority=0, pinned=True)
        self.draft_tree = ttk.Treeview(body, show='tree', height=3, selectmode='browse')
        self.draft_tree.pack(fill='both', expand=True, pady=3)
        self.draft_tree.bind('<Double-1>', lambda e: self.review_selected())
        self.draft_tree.bind('<Return>', lambda e: self.review_selected())

    def refresh_snapshot(self):
        self.snapshot = copy.deepcopy(self.app.project)
        self.now = float(self.app.playhead)
        self.context = 'take' if self.app.reviewing else 'finite'
        self.identity = (self.app.project.id, bool(self.app.reviewing))
        self.current_id = getattr(getattr(getattr(self.app, 'queue_deck', None), 'sound', None), 'selected', None)
        self.source.set(('Draft' if self.app.reviewing else 'Programme') + ': ' + self.snapshot.name + ' · frozen at ' + f'{self.now:.2f}s')
        visual = export_visual_project(self.snapshot, self.context)
        bounds = self.snapshot.extra.get('capture_range') if self.context == 'take' else None
        self.targets = {'visual': {}, 'clip': {}, 'track': {}}
        for layer in visual.layers:
            if not layer.enabled:
                continue
            label = layer.extra.get('voice', layer.name)
            self.targets['visual'][label + ' · ' + layer.id[-5:]] = layer.id
            for i, clip in enumerate(layer.clips):
                if bounds and (clip.end <= bounds[0] or clip.start >= bounds[1]):
                    continue
                asset = visual.asset(clip.asset_id)
                name = asset.name if asset else 'Missing source'
                self.targets['clip'][f'{label} · {i+1}. {name} · {clip.start:.2f}–{clip.end:.2f}s'] = clip.id
        for i, event in enumerate(items(self.snapshot)):
            if bounds and (event['start'] + event['duration'] <= bounds[0] or event['start'] >= bounds[1]):
                continue
            asset = self.snapshot.asset(event['asset_id'])
            name = asset.name if asset else 'Missing source'
            self.targets['track'][f'{i+1}. {name} · {event["start"]:.2f}–{event["start"]+event["duration"]:.2f}s'] = event['id']
        self.scope_changed()

    def scope_changed(self):
        scope = self.SCOPES[self.scope.get()]
        choices = self.targets.get(scope, {})
        self.target_box.configure(values=list(choices), state='readonly' if scope in self.targets else 'disabled')
        self.target.set(next(iter(choices), ''))
        if scope in self.targets:
            self.target_box.pack(before=self.source_label, fill='x', pady=3)
        else:
            self.target_box.pack_forget()
        duration = scope == 'duration'
        self.duration_entry.configure(state='normal' if duration else 'disabled')
        self.start_box.configure(state='readonly' if duration else 'disabled')
        if duration:
            self.duration_row.pack(before=self.source_label, fill='x', pady=3)
        else:
            self.duration_row.pack_forget()
        self.export_canvas.yview_moveto(0)
        self.resolve()

    def stale(self):
        return self.identity != (self.app.project.id, bool(self.app.reviewing))

    def resolve(self):
        if self.snapshot is None:
            return
        try:
            if self.stale():
                raise ValueError('The current view changed. Refresh the source before exporting.')
            scope = self.SCOPES[self.scope.get()]
            target = self.targets.get(scope, {}).get(self.target.get())
            result = resolve_export_range(self.snapshot, scope, now=self.now, context=self.context,
                                          current_event_id=self.current_id, layer_id=target if scope == 'visual' else None,
                                          occurrence_id=target, duration=self.duration.get(),
                                          start_mode=self.STARTS[self.start_mode.get()])
            self.resolved = result
            if result['action'] == 'unavailable':
                self.range_value.set(result['label'])
            else:
                self.range_value.set(f'{result["start"]:.3f} → {result["end"]:.3f}s · {result["duration"]:.3f}s')
        except (ValueError, TypeError, KeyError) as exc:
            self.resolved = None
            self.range_value.set(str(exc))
        self.export_button.configure(state='normal' if self.resolved and self.resolved['action'] == 'render' and not self.app.rendering else 'disabled')

    def start_export(self):
        if self.app.rendering:
            return
        self.resolve()
        if not self.resolved or self.resolved['action'] != 'render':
            return
        key = self.profiles[self.profile.get()]
        extension = EXPORT_PROFILES[key]['extension']
        name = self.snapshot.name.replace('/', '-').replace('\\', '-')
        path = filedialog.asksaveasfilename(parent=self, title='Export frozen ' + ('Draft' if self.context == 'take' else 'Programme'),
                                           initialfile=name + extension, defaultextension=extension,
                                           filetypes=[('Video', '*' + extension)], confirmoverwrite=False)
        if not path:
            return
        # Native choosers can run Tk callbacks. Revalidate the view and busy state.
        if not self.winfo_exists():
            return
        if self.app.rendering or self.stale():
            self.resolve()
            return
        try:
            output = Path(path)
            if output.suffix.lower() != extension:
                raise ValueError('This profile needs a ' + extension + ' filename.')
            overwrite = output.exists()
            if overwrite and not messagebox.askyesno('Replace existing output?', 'Replace ' + output.name + '? The previous file stays intact until validation.', parent=self):
                return
            if not self.winfo_exists() or self.app.rendering or self.stale():
                return
            size = None
            if self.size.get() != 'Project size':
                limit = int(self.size.get().split()[-1])
                scale = min(1., limit / max(self.snapshot.width, self.snapshot.height))
                size = tuple(max(16, round(value * scale / 2) * 2) for value in (self.snapshot.width, self.snapshot.height))
            descriptor = copy.deepcopy(self.resolved)
            self.app.start_export(path, key, size, descriptor['start'], descriptor['end'], overwrite,
                                  snapshot=self.snapshot, descriptor=descriptor)
            self.refresh_state()
        except (ValueError, OSError) as exc:
            self.app.update_status('Export: ' + str(exc))
            self.feedback.set(str(exc))

    def cancel(self):
        if self.app.rendering:
            self.app.render_cancel.set()
            self.app.update_status('Export cancellation requested · Programme continues')
            self.cancel_export.configure(state='disabled')

    def keep(self):
        try:
            length = seconds(self.keep_duration.get())
        except ValueError as exc:
            self.app.update_status('Capture: ' + str(exc))
            return
        self.app.capture_seconds.set(f'{length:g}')
        self.app.capture_recent()
        self.refresh_state()

    def refresh_drafts(self):
        # Undo/Redo replaces the reviewed project object. Its catalogue entry can
        # still refer to the preceding state until the Draft is remembered again.
        # The active review owns the displayed name/range for that stable ID.
        active = self.app.project if self.app.reviewing else None
        projects = [active if active is not None and active.id == item['project'].id
                    else item['project'] for item in self.app.takes]
        key = tuple((p.id, p.name, tuple(p.extra.get('capture_range', ()))) for p in projects)
        if key == self._draft_key:
            return
        self._draft_key = key
        selected = self.draft_tree.selection()
        self.draft_tree.delete(*self.draft_tree.get_children())
        for p in projects:
            bounds = p.extra.get('capture_range')
            label = p.name + (f' · {bounds[1]-bounds[0]:.1f}s' if bounds else '')
            self.draft_tree.insert('', 'end', iid=p.id, text=label)
        if selected and self.draft_tree.exists(selected[0]):
            self.draft_tree.selection_set(selected)

    def review_selected(self, export=False):
        selected = self.draft_tree.selection()
        item = next((item for item in self.app.takes if selected and item['project'].id == selected[0]), None)
        if item is None:
            return
        self.app.review_take(item['project'], item.get('path'))
        # Review/Return may replace the centre tray with the project context.
        panel = self.app.open_capture('export' if export else 'drafts')
        panel.refresh_snapshot()

    def open_draft(self):
        self.app.open_take_file()
        self.app.open_capture('drafts').refresh_snapshot()

    def go_live(self):
        self.app.go_live()
        self.app.open_capture('drafts').refresh_snapshot()

    def refresh_state(self):
        recording = self.app.output_recording
        finalising = self.app.output_busy
        self.record.configure(text='■ Stop recording' if recording else 'Finalising…' if finalising else '● Start recording…',
                              state='disabled' if finalising else 'normal')
        width, height = recording.size if recording else self.app.programme_size()
        format_text = f'{width}×{height} · {recording.fps if recording else 20:g} fps'
        if recording:
            self.record_state.set(f'{max(0., self.app.programme_time()-recording.start):.1f}s · ' + format_text)
        else:
            self.record_state.set('Programme continues' if finalising else format_text)
        self.keep_button.configure(state='disabled' if self.app.capture_busy else 'normal')
        self.cancel_export.configure(state='normal' if self.app.rendering and not self.app.render_cancel.is_set() else 'disabled')
        self.export_progress['value'] = float(self.app.progress['value'])
        self.feedback.set(getattr(self.app, '_capture_feedback', ''))
        valid = self.resolved and self.resolved['action'] == 'render' and not self.stale()
        self.export_button.configure(state='normal' if valid and not self.app.rendering else 'disabled')
        if self.stale():
            self.range_value.set('The current view changed. Refresh the source before exporting.')

    def tick(self):
        self.refresh_state()
        self.refresh_drafts()
        if not self.app.closing:
            self._timer = self.after(200, self.tick)
