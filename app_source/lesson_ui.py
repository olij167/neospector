"""One nonmodal guided-task controller; never simulates a user action."""
from __future__ import annotations
import copy
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from guided_lessons import BY_ID, LessonSession


class LessonCoach:
    def __init__(self, app):
        self.app=app;self.session=None;self.win=None;self.timer=None;self.practice=None
        self.progress=dict(app.read_preferences().get('ux7_lesson_progress', {}));self.saved_sessions={}

    def open(self,lesson_id):
        if lesson_id not in BY_ID:raise KeyError(lesson_id)
        if self.win and self.win.winfo_exists():
            if self.session:
                self.saved_sessions[self.session.lesson.id]=self.session
                self._save(self.session.index==len(self.session.lesson.steps))
            if self.timer:
                try:self.win.after_cancel(self.timer)
                except tk.TclError:pass
            self.win.destroy();self.win=None;self.timer=None
        previous=self.saved_sessions.get(lesson_id)
        if previous and previous.project_id==self.app.project.id:self.session=previous
        else:
            self.session=LessonSession(lesson_id,self.app)
            saved=self.progress.get(lesson_id,{})
            if saved.get('project_id')==self.app.project.id:
                self.session.index=min(len(self.session.lesson.steps),int(saved.get('index',0)))
                self.session.skipped=set(saved.get('skipped',()))
        self.win=tk.Toplevel(self.app);w=self.win;w.title('Guide · '+self.session.lesson.title)
        w.geometry('390x275');w.minsize(335,245);w.transient(self.app)
        # Standard window decoration makes this card movable, resizable and
        # independently dismissible without a private pointer-grab.
        frame=ttk.Frame(w,padding=14);frame.pack(fill='both',expand=True)
        frame.columnconfigure(0,weight=1)
        ttk.Label(frame,text=self.session.lesson.title,style='Title.TLabel').grid(row=0,column=0,sticky='w')
        self.position=tk.StringVar();ttk.Label(frame,textvariable=self.position,style='Muted.TLabel').grid(row=1,column=0,sticky='w',pady=(5,7))
        self.instruction=tk.StringVar();ttk.Label(frame,textvariable=self.instruction,wraplength=350,justify='left').grid(row=2,column=0,sticky='ew')
        self.hint=tk.StringVar();ttk.Label(frame,textvariable=self.hint,wraplength=350,justify='left',style='Muted.TLabel').grid(row=3,column=0,sticky='ew',pady=(7,8))
        actions=ttk.Frame(frame);actions.grid(row=4,column=0,sticky='ew',pady=3)
        self.show_button=ttk.Button(actions,text='Show control',command=self.show_control);self.show_button.pack(side='left')
        self.pause_button=ttk.Button(actions,text='Pause',command=self.toggle_pause);self.pause_button.pack(side='left',padx=3)
        ttk.Button(actions,text='Skip step',command=self.skip).pack(side='left',padx=3)
        more=ttk.Frame(frame);more.grid(row=5,column=0,sticky='ew',pady=(6,0))
        ttk.Button(more,text='Restart',command=self.restart).pack(side='left')
        ttk.Button(more,text='Exit guide',command=self.close).pack(side='right')
        if self.practice is None:ttk.Button(more,text='Practice project…',command=self.enter_practice).pack(side='left',padx=5)
        else:ttk.Button(more,text='Return to my project',command=self.leave_practice).pack(side='left',padx=5)
        w.protocol('WM_DELETE_WINDOW',self.close)
        w.bind('<Escape>',lambda _event:self.close())
        self._tick();return w

    def _save(self,complete=False):
        if not self.session:return
        state={'project_id':self.session.project_id,'index':self.session.index,
               'complete':bool(complete),'skipped':sorted(self.session.skipped)}
        self.progress[self.session.lesson.id]=state
        self.app.ux7_lesson_progress=self.progress
        self.app.save_preferences()

    def _tick(self):
        self.timer=None
        if not self.win or not self.win.winfo_exists() or not self.session:return
        previous=self.session.index
        try:state=self.session.poll(self.app)
        except Exception as exc:
            self.hint.set('Could not inspect this step: '+str(exc));self.session.paused=True;state='paused'
        if self.session.index!=previous:self._save(state=='done')
        total=len(self.session.lesson.steps)
        self.position.set(f'{min(total,self.session.index+1)} of {total}'+('  ·  complete' if state=='done' else '  ·  paused' if self.session.paused else ''))
        if state=='project-changed':
            self.instruction.set('The project changed. Restart this lesson in the current project.')
            self.hint.set('A lesson never changes a project for you.')
        elif state=='done':
            self.instruction.set('You did it. Your real project and Undo history contain the work.')
            self.hint.set('You can open another short task from Help whenever you need it.')
        else:
            step=self.session.lesson.steps[self.session.index]
            self.instruction.set(step.instruction);self.hint.set(step.hint)
        self.show_button.configure(state='normal' if state=='active' else 'disabled')
        self.pause_button.configure(text='Resume' if self.session.paused else 'Pause')
        self.timer=self.win.after(550,self._tick)

    def show_control(self):
        if not self.session or self.session.index>=len(self.session.lesson.steps):return
        command=self.app.commands.get(self.session.lesson.steps[self.session.index].target)
        from help_browser import focus_command
        if not focus_command(self.app,command):
            self.hint.set('Find “'+command.label+'” in the '+command.scope+' controls. '+self.session.lesson.steps[self.session.index].hint)

    def toggle_pause(self):
        if not self.session:return
        self.session.paused=not self.session.paused
        if not self.session.paused and self.app.project.id!=self.session.project_id:self.session=LessonSession(self.session.lesson.id,self.app)
        self._save()

    def skip(self):
        if not self.session:return
        self.session.skip();self._save(self.session.index==len(self.session.lesson.steps))

    def restart(self):
        if not self.session:return
        self.session=LessonSession(self.session.lesson.id,self.app);self._save()

    def close(self):
        if self.practice is not None:
            self.leave_practice()
            if self.practice is not None:return
        if self.session:
            self.saved_sessions[self.session.lesson.id]=self.session
            self._save(self.session.index==len(self.session.lesson.steps))
        if self.timer and self.win:
            try:self.win.after_cancel(self.timer)
            except tk.TclError:pass
        self.timer=None
        if self.win and self.win.winfo_exists():self.win.destroy()
        self.win=None;self.session=None

    def enter_practice(self):
        app=self.app
        if self.practice is not None:return
        if app.playing or app.output_recording or app.output_busy or app.capture_busy or app.live.recording or app.live.camera_sources or app.live.sources:
            self.hint.set('Stop the performance, sharing and recordings before entering a separate practice session.');return
        if not app.confirm_discard():return
        from instrument_model import new_instrument
        from sequencer_model import load_project
        source=Path(__file__).resolve().parents[1]/'examples'/'First Light.omne-sequence.json'
        try:
            example=load_project(source)
            project=new_instrument();project.name='Practice · temporary'
            project.assets=copy.deepcopy(example.assets)
            project.audio_asset_id=example.audio_asset_id
            project.analysis=copy.deepcopy(example.analysis)
            project.waveform=copy.deepcopy(example.waveform)
            previous=(app.project,app.history,app.project_path,app.dirty,app.playhead,app.workspace_name.get())
            app.restore_project(project)
            if app.project is not project:return self.hint.set('Finish the current session before opening practice.')
            self.practice=previous
            self.session=LessonSession(self.session.lesson.id,app)
            self.hint.set('Temporary example media is ready. Return to restore your original project and Undo history.')
        except Exception as exc:self.hint.set('Practice could not open: '+str(exc))

    def leave_practice(self):
        if self.practice is None:return
        app=self.app
        if app.output_recording or app.output_busy or app.capture_busy or app.live.recording:
            self.hint.set('Finish recording or capture before leaving practice.');return
        original,history,path,dirty,playhead,workspace=self.practice
        app.history=history
        app.restore_project(original,path,new_history=False)
        if app.project is not original:return self.hint.set('The practice session is still busy.')
        app.history=history;app.dirty=dirty;app.set_playhead(playhead)
        app.switch_workspace(workspace);app.update_title();self.practice=None
        if self.session:self.session=LessonSession(self.session.lesson.id,app)
        self.hint.set('Your original project and Undo history are restored.')
