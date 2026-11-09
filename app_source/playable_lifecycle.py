"""Scoped snapshot export and reservation-safe temporary input retention."""
from conductor_targets import DEFAULTS as CONDUCTOR_DEFAULTS
import copy,json,math,shutil,threading,time,traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from history_retention import DEFAULTS,Reservations,segment_units,retire_segments,metadata_count,owned_file
from sequencer_model import new_id,project_to_dict
from performance_capture import capture_with_recordings
from media_engine import render_project
from process_tools import Cancelled

def prepare_export_snapshot(snapshot,start,end,segments):
    bounds=snapshot.extra.get('capture_range')
    if bounds and snapshot.extra.get('session_mode')=='review':
        if not float(bounds[0])<=start<end<=float(bounds[1]):raise ValueError('Export must stay inside the saved Take range.')
        # Captured Takes already contain frozen source mappings, retained audio
        # and analysis. Re-capturing would consult unrelated current inputs.
        return copy.deepcopy(snapshot)
    return capture_with_recordings(snapshot,start,end,segments)

class PlayableLifecycle:
    def retention_state(self):
        if not hasattr(self,'history_reservations'):self.history_reservations=Reservations()
        return self.history_reservations
    def retention_limits(self):return {**DEFAULTS,**self.programme_project().extra.get('retention_limits',{})}
    def reserve_history(self,start,end):
        with self.retention_lock:return self.retention_state().reserve(max(0.,start-5),end)
    def release_history(self,token):
        with self.retention_lock:self.retention_state().release(token)
    def retention_cutoff(self,now):
        cutoff=now-self.retention_limits()['seconds']
        return min(cutoff,self.output_retention_start) if self.output_retention_start is not None else cutoff
    def rotate_retention(self,restart=True):
        if self.retention_busy:return
        self.retention_busy=True;limits=self.retention_limits();now=self.programme_time();root=self.cache/'input-history'
        def work():
            try:
                self._roll_inputs(restart)
                with self.retention_lock:
                    units=segment_units(self.recorded_segments,root);pins=self.retention_state().pinned(units)
                    if self.output_retention_start is not None:pins.update(u['id'] for u in units if u['end']>self.output_retention_start)
                    result=retire_segments(self.recorded_segments,root,now=now,window_seconds=limits['seconds'],byte_budget=limits['bytes'],pinned_ids=pins)
                    self.recorded_segments=result['segments'];self._history_coverage=result['coverage_intervals']
                free=shutil.disk_usage(self.cache).free
                if result['unmet_budget'] or free<limits['free_reserve']:
                    # Stop recording growth, never sacrifice pins. Programme remains live.
                    self.retention_enabled=False
                    if self.live.recording:self._roll_inputs(False)
                    self.events.put(('call',lambda:self.retain_armed.set(False)))
                    self.events.put(('status','History recording stopped: protected storage or free-space limit. Saved work and Programme are preserved.'))
                else:self.events.put(('status',f"Input history · {len(result['segments'])} retained segments · {result['retained_bytes']/1024**2:.1f} MiB"))
            except Exception as exc:self.events.put(('status','Input history: '+str(exc)))
            finally:self.retention_busy=False
        threading.Thread(target=work,name='Bounded input retention',daemon=True).start()
    def toggle_retention(self):
        if self.retain_armed.get() and shutil.disk_usage(self.cache).free<self.retention_limits()['free_reserve']:
            self.retain_armed.set(False);return self.update_status('Input history needs the configured free-space reserve. Free space or lower the reserve explicitly.')
        return super().toggle_retention()
    def history_settings(self):
        existing=getattr(self,'history_window',None)
        if existing and existing.winfo_exists():existing.lift();return
        w=tk.Toplevel(self);self.history_window=w;w.title('Recent history · limits and coverage');w.geometry('510x420');body=ttk.Frame(w,padding=16);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Temporary input history',style='Title.TLabel').pack(anchor='w')
        limits=self.retention_limits();values={}
        for key,label,scale in [('seconds','Keep recent minutes',60),('bytes','Temporary media budget · GiB',1024**3),('free_reserve','Keep free on disk · GiB',1024**3)]:
            row=ttk.Frame(body);row.pack(fill='x',pady=5);ttk.Label(row,text=label).pack(side='left');v=tk.StringVar(value=f'{limits[key]/scale:g}');values[key]=(v,scale);ttk.Entry(row,textvariable=v,width=9).pack(side='right')
        spans=getattr(self,'_history_coverage',[])
        coverage='; '.join(f'{a:.1f}–{b:.1f}s' for a,b in spans) or 'No completed recorded segments'
        ttk.Label(body,text='Recorded input coverage: '+coverage+'\nEditable file decisions are separate. Unrecorded live input cannot be reconstructed. Saved takes and original files are never retired.',wraplength=465,style='Muted.TLabel').pack(fill='x',pady=10)
        ttk.Label(body,text='When history fills, automatic changes pause to keep the instrument responsive. Save a Take to preserve the result, then start a fresh session. Pinned input history is kept.',wraplength=465,style='Muted.TLabel').pack(fill='x',pady=6)
        def save():
            try:
                setting={key:float(v.get())*scale for key,(v,scale) in values.items()}
                if not all(math.isfinite(x) for x in setting.values()) or not 30<=setting['seconds']<=21600 or setting['bytes']<16*1024**2 or setting['free_reserve']<16*1024**2:raise ValueError('Use 0.5–360 minutes and budgets / free reserve of at least 16 MiB.')
                if setting['bytes']>limits['bytes'] and shutil.disk_usage(self.cache).free<setting['bytes']-limits['bytes']+setting['free_reserve']:raise ValueError('Not enough free storage for that budget increase and reserve.')
                self.transaction('History limits',lambda:self.project.extra.__setitem__('retention_limits',{**limits,**setting}));w.destroy()
            except ValueError as exc:messagebox.showerror('History limits',str(exc),parent=w)
        ttk.Button(body,text='Save limits',command=save).pack(side='bottom',anchor='e');w.bind('<Escape>',lambda e:w.destroy())
    def measure_history_budget(self):
        # Histories include source switches, treatment/master/mixer/camera/route
        # histories, parameter keyframes, clips, transitions and sound events.
        # Their replay boundaries are not guessed. Explicit growth cap instead.
        if not getattr(self,'_history_measure_busy',False) and time.monotonic()-getattr(self,'_history_measured_at',0)>10:
            snapshot=self.programme_snapshot();context=id(self.programme_project());self._history_measure_busy=True;self._history_measured_at=time.monotonic();limits=self.retention_limits()
            def measure():
                try:
                    count=metadata_count(snapshot);size=len(json.dumps(project_to_dict(snapshot)))
                    if count>=limits['metadata_events'] or size>=limits['metadata_bytes']:
                        def stop():
                            if id(self.programme_project())!=context:return
                            self.evolve.set(False);self.record_automation.set(False);self.update_status('Autonomy / control-motion recording held at the history metadata limit. Capture a Take and start a new session; Programme continues.')
                        self.events.put(('call',stop))
                finally:self._history_measure_busy=False
            threading.Thread(target=measure,name='History metadata budget',daemon=True).start()
    def evolve_next(self):
        self.measure_history_budget()
        if getattr(self,'_playable_running',False):return
        # Keep the existing treatment evolution engine. Source preparation uses
        # the same bounded source-intent adapter as the front-panel action.
        p=self.programme_project();options=p.conductor.extra;prior={k:options.get(k) for k in ('evolve_sources','evolve_sound')};present=set(options)
        try:
            options['evolve_sources']=False;options['evolve_sound']=False
            super().evolve_next()
        finally:
            for k,v in prior.items():
                if k in present:options[k]=v
                else:options.pop(k,None)
        from music_queue import items
        from queue_model import queue_position,mode_at
        intent=self.source_intent(p);now=self.programme_time();due=False
        if options.get('evolve_sources',CONDUCTOR_DEFAULTS['evolve_sources']) and intent['visuals']['mode'] not in ('off','live'):
            due=any(l.enabled and not l.locked and not l.extra.get('playable_empty') and l.extra.get('voice') in intent['enabled_roles'] and mode_at(l,now)['mode']=='queue' and l.extra.get('queue_generation_at',0)<=now and max((c.end for c in l.clips),default=0)-queue_position(l,now)<20 for l in p.layers)
        if options.get('evolve_sound',CONDUCTOR_DEFAULTS['evolve_sound']) and intent['music']['mode']=='auto':
            from queue_policies import music_position
            due=due or (p.extra.get('music_generation_at',0)<=now and max((e['start']+e['duration'] for e in items(p)),default=0)-music_position(p,now)<3)
        if due:self.randomise_playable('queues',automatic=True)
    def start_export(self,path,profile='web',size=None,start=0.,end=None,overwrite=False,*,snapshot=None,descriptor=None):
        if self.rendering:return
        snapshot=copy.deepcopy(snapshot if snapshot is not None else self.project)
        from export_scope import snapshot_for_descriptor
        try:snapshot=snapshot_for_descriptor(snapshot,descriptor)
        except ValueError as exc:return self.update_status('Export: '+str(exc))
        end=float(end if end is not None else snapshot.max_end());saved_take=bool(snapshot.extra.get('capture_range') and snapshot.extra.get('session_mode')=='review')
        token=self.reserve_history(start,end);self.rendering=True;self.render_cancel=threading.Event();self.cancel_button.configure(state='normal');self.progress['value']=0
        report=self.cache/'exports'/new_id('job');report.mkdir(parents=True);self.last_diagnostics=report
        def work():
            try:
                with self.retention_lock:
                    segments=[] if saved_take else self._roll_inputs(True) if self.live.recording else list(self.recorded_segments)
                prepared=prepare_export_snapshot(snapshot,start,end,segments)
                (report/'scope.json').write_text(json.dumps(descriptor or {'start':start,'end':end,'source_context':'take' if snapshot.extra.get('capture_range') else 'Programme'},indent=2))
                (report/'project.omne-sequence.json').write_text(json.dumps(project_to_dict(prepared),indent=2))
                result=render_project(prepared,path,start=start,end=end,profile=profile,size=size,overwrite=overwrite,cancel=self.render_cancel,diagnostics_dir=report,progress=lambda text:self.events.put(('export_progress',text)))
                self.events.put(('export_done',str(result),str(report)))
            except Cancelled:self.events.put(('export_cancelled',str(report)))
            except Exception as exc:
                (report/'failure.txt').write_text(traceback.format_exc());self.events.put(('export_failed',str(exc),str(report)))
            finally:self.release_history(token)
        threading.Thread(target=work,name='Frozen scope export',daemon=True).start();self.update_status(f'Pinned · exporting frozen {start:.2f}–{end:.2f}s snapshot. Programme continues.')

    def toggle_output_record(self):
        if not self.output_recording and not self.output_busy:self._record_stop_at=math.inf
        return super().toggle_output_record()

    def record_next_duration(self,seconds):
        from export_scope import seconds as validate
        seconds=validate(seconds)
        if self.reviewing:return self.update_status('Return to Programme before recording future Programme.')
        if self.output_recording or self.output_busy:return self.update_status('Finish the current output recording first.')
        self.toggle_output_record()
        if not self.output_recording:return
        self._record_stop_at=self.output_recording.start+seconds
        self._duration_record=self.output_recording
        def check():
            if self.closing or self.output_recording is not self._duration_record:return
            if self.programme_time()>=self._record_stop_at:
                self.toggle_output_record();return
            self.after(80,check)
        self.after(80,check);self.update_status(f'Recording next {seconds:g}s of Programme · pause holds the session clock.')
