"""Contextual rack trays, sharing the catalogue and parameter model with the instrument."""
from __future__ import annotations
import copy
import math
import tkinter as tk
from tkinter import ttk
from module_engine import label as module_label, children
from rack_editing import RackContext, PARAMETER_CHOICES, PARAMETER_NUMBERS, update_parameter
from responsive_controls import FlowRow
from ui_chrome import CollapsibleSection
from ui_chrome import tk_scale_theme_options
from module_engine import internal_parameters, internal_parameter_target, internal_parameter_owner, edit_internal_parameter, parameter_descriptions
from live_parameter_controls import (ParameterGesture, REACTION_BANDS,
    REACTION_SOURCES, RESPONSE_PRESETS, available_reaction_sources,
    initial_reaction_changes, response_name, should_debounce_key, source_status)


class RackParameterTray(ttk.Frame):
    def __init__(self,parent,deck,fx,key):
        super().__init__(parent,padding=5)
        self.deck=deck;self.app=deck.app;self.context=RackContext.capture(deck);self.fx_id=fx.id;self.key=key
        self.param=fx.params[key];self.vars={};self.entries={};self.title=module_label(fx);self._after={};self._syncing=False
        self.gesture=ParameterGesture(self.app,self._gesture_target,self._set_message,self.refresh_indicator)
        head=ttk.Frame(self);head.pack(fill='x')
        self.title_label=ttk.Label(head,text=self.title,style='PlayerName.TLabel');self.title_label.pack(side='left',fill='x',expand=True)
        self.pinned=tk.BooleanVar(value=False)
        ttk.Button(head,text='×',width=3,command=self.close).pack(side='right')
        self.parameter_name=tk.StringVar(value=key)
        labels={k:fx.extra.get('labels',{}).get(k,k.replace('_',' ').title()) for k in fx.params}
        label_to_key={label:name for name,label in labels.items()};self.parameter_label=tk.StringVar(value=labels[key])
        if len(labels)>1:
            selector=ttk.Frame(self);selector.pack(fill='x',pady=(1,2));ttk.Label(selector,text='Parameter',style='Muted.TLabel').pack(side='left')
            parameter_box=ttk.Combobox(selector,textvariable=self.parameter_label,values=list(label_to_key),state='readonly',width=11);parameter_box.pack(side='right',fill='x',expand=True,padx=(4,0))
            parameter_box.bind('<<ComboboxSelected>>',lambda e:deck.open_parameter(fx.id,label_to_key[self.parameter_label.get()]))
            selector.pack_forget()
        self.title_label.configure(text=labels[key]+' · Reaction')

        self.vars.update({name:tk.StringVar(value=getattr(self.param,name)) for name in PARAMETER_CHOICES})
        self.vars.update({name:tk.StringVar(value=f'{getattr(self.param,name):g}') for name in PARAMETER_NUMBERS})
        self.react_enabled=tk.BooleanVar(value=self.param.mode=='react')
        self.combine=tk.BooleanVar(value=self.param.combine_animation);self.protected=tk.BooleanVar(value=bool(self.param.extra.get('conductor_locked',False)))

        power=ttk.Frame(self);power.pack(fill='x',pady=(2,2))
        self.react_power=ttk.Checkbutton(power,text='REACT',variable=self.react_enabled,command=self.toggle_reaction)
        self.react_power.pack(side='left')
        self.effective=tk.StringVar();ttk.Label(power,textvariable=self.effective,style='Muted.TLabel').pack(side='right')

        routing=ttk.Frame(self);routing.pack(fill='x',pady=2);routing.columnconfigure(1,weight=1)
        ttk.Label(routing,text='Source').grid(row=0,column=0,sticky='w')
        self.source_labels={value:label for value,label in REACTION_SOURCES};self.source_values={label:value for value,label in REACTION_SOURCES}
        self.source_label=tk.StringVar(value=self.source_labels.get(self.param.source,self.param.source))
        self.source_box=source_box=ttk.Combobox(routing,textvariable=self.source_label,values=[label for _,label in REACTION_SOURCES],state='readonly',width=9)
        source_box.grid(row=0,column=1,sticky='ew',padx=3);source_box.bind('<<ComboboxSelected>>',lambda e:self.activate_source(self.source_values[self.source_label.get()]))
        self.source_buttons={}
        self.prepare_button=ttk.Button(routing,text='Audio…',width=6,command=self.prepare_source);self.prepare_button.grid(row=0,column=2,padx=(1,0))
        ttk.Label(routing,text='Range').grid(row=1,column=0,sticky='w')
        self.band_labels={value:('Full range' if value=='full' else label) for value,label in REACTION_BANDS};self.band_values={label:value for value,label in self.band_labels.items()}
        self.band_label=tk.StringVar(value=self.band_labels.get(self.param.react_band,self.param.react_band))
        self.band_box=band_box=ttk.Combobox(routing,textvariable=self.band_label,values=list(self.band_values),state='readonly',width=9)
        band_box.grid(row=1,column=1,sticky='ew',padx=3);band_box.bind('<<ComboboxSelected>>',lambda e:self.activate_band(self.band_values[self.band_label.get()]))
        self.band_buttons={}
        self.source_meter=ttk.Progressbar(routing,maximum=1,length=34);self.source_meter.grid(row=1,column=2,sticky='ew',padx=(1,0))
        self.source_note=tk.StringVar()

        tactile=ttk.Frame(self);tactile.pack(fill='x',pady=(3,1));tactile.columnconfigure(1,weight=1)
        ttk.Label(tactile,text='Travel').grid(row=0,column=0,sticky='w')
        self.depth_value=tk.DoubleVar(value=self.param.react_amount)
        self.depth_scale=tk.Scale(tactile,variable=self.depth_value,from_=-1,to=1,resolution=.01,orient='horizontal',showvalue=False,length=70,command=self.depth_changed,**tk_scale_theme_options(self.app.ui_chrome))
        self.depth_scale.grid(row=0,column=1,sticky='ew',padx=4);self._bind_scale(self.depth_scale)
        depth=self._entry(tactile,'react_amount',0,2);depth.configure(width=4)
        ttk.Button(tactile,text='↔',width=1,command=self.reverse_direction).grid(row=0,column=3,padx=(2,0))
        ttk.Label(tactile,text='Base').grid(row=1,column=0,sticky='w')
        self.base_value=tk.DoubleVar(value=self.param.value)
        span=max(1e-9,self.param.maximum-self.param.minimum)
        self.base_scale=tk.Scale(tactile,variable=self.base_value,from_=self.param.minimum,to=self.param.maximum,resolution=span/500,orient='horizontal',showvalue=False,length=70,command=self.base_changed,**tk_scale_theme_options(self.app.ui_chrome))
        self.base_scale.grid(row=1,column=1,sticky='ew',padx=4);self._bind_scale(self.base_scale)
        self._entry(tactile,'value',1,2).configure(width=4)

        # Base is already the tactile face control; avoid duplicating it here.
        self.base_scale.grid_remove();self.entries['value'].grid_remove()
        for widget in tactile.grid_slaves(row=1):widget.grid_remove()
        ttk.Label(power,text='Base').pack(side='left',padx=(5,2))
        entry=ttk.Entry(power,textvariable=self.vars['value'],width=5);entry.pack(side='left');self.entries['value']=entry
        entry.bind('<KeyRelease>',lambda e:self.queue_text('value',e));entry.bind('<Return>',lambda e:self.finish_text('value'))
        entry.bind('<KP_Enter>',lambda e:self.finish_text('value'));entry.bind('<FocusOut>',lambda e:self.finish_text('value'));entry.bind('<Escape>',self.escape)

        response=ttk.Frame(self);response.pack(fill='x',pady=2);response.columnconfigure(1,weight=1)
        ttk.Label(response,text='Shape').grid(row=0,column=0,sticky='w')
        self.response_choice=tk.StringVar(value=response_name(self.param))
        self.response_box=response_box=ttk.Combobox(response,textvariable=self.response_choice,values=list(RESPONSE_PRESETS),state='readonly',width=8)
        response_box.grid(row=0,column=1,sticky='ew',padx=3);response_box.bind('<<ComboboxSelected>>',lambda e:self.activate_response(self.response_choice.get()))
        self.response_buttons={}
        self.response_note=tk.StringVar()

        self.advanced=CollapsibleSection(self,'More · range / keys',expanded=bool(getattr(deck,'parameter_advanced',False)),on_toggle=lambda value:setattr(deck,'parameter_advanced',value))
        self.advanced.pack(fill='x',pady=(3,0));deep=self.advanced.body
        deep.columnconfigure(1,weight=1);deep.columnconfigure(3,weight=1)
        ttk.Label(deep,text='Interpolation').grid(row=0,column=0,sticky='w',pady=2)
        interpolation=ttk.Combobox(deep,textvariable=self.vars['interpolation'],values=PARAMETER_CHOICES['interpolation'],state='readonly',width=11)
        interpolation.grid(row=0,column=1,sticky='ew',padx=(0,7));interpolation.bind('<<ComboboxSelected>>',lambda e:self.activate_choice('interpolation'))
        for name,label,row,col in (('minimum','Minimum',1,0),('maximum','Maximum',1,2),('attack','Attack (s)',2,0),('release','Release (s)',2,2),('threshold','Threshold',3,0)):
            ttk.Label(deep,text=label).grid(row=row,column=col,sticky='w',pady=2,padx=(0,4));self._entry(deep,name,row,col+1,sticky='ew')
        self.combine=tk.BooleanVar(value=self.param.combine_animation);self.protected=tk.BooleanVar(value=bool(self.param.extra.get('conductor_locked',False)))
        flags=ttk.Frame(deep);flags.grid(row=4,column=0,columnspan=4,sticky='ew',pady=3)
        ttk.Checkbutton(flags,text='React over authored keys',variable=self.combine,command=lambda:self.activate_flag('combine_animation',self.combine.get())).pack(anchor='w')
        ttk.Checkbutton(flags,text='Protect this parameter from Conductor',variable=self.protected,command=lambda:self.activate_flag('conductor_locked',self.protected.get())).pack(anchor='w')
        self.message=tk.StringVar(value='Locked · unlock the card to edit' if fx.extra.get('locked') else '')
        self.note=ttk.Label(self,textvariable=self.message,style='Muted.TLabel',wraplength=190)
        def message_visibility(*_):
            # StringVar traces can outlive a destroyed companion by one Tcl turn
            # during project replacement. Never let stale contextual feedback
            # become an application callback error.
            try:
                if not self.winfo_exists() or not self.note.winfo_exists():return
                if self.message.get().strip():
                    if not self.note.winfo_manager():self.note.pack(fill='x')
                elif self.note.winfo_manager():self.note.pack_forget()
            except tk.TclError:return
        self.message.trace_add('write',message_visibility);message_visibility()
        self.key_section=ttk.LabelFrame(deep,text='Authored keyframes · project seconds',padding=5);self.key_section.grid(row=5,column=0,columnspan=4,sticky='ew',pady=5)
        self.tree=ttk.Treeview(self.key_section,columns=('time','value'),show='headings',height=3,selectmode='browse')
        self.tree.heading('time',text='Time (s)');self.tree.heading('value',text='Value');self.tree.column('time',width=90);self.tree.column('value',width=90);self.tree.pack(fill='x')
        self.kt=tk.StringVar(value=f'{self.app.playhead:.4f}');self.kv=tk.StringVar(value=f'{self.param.evaluate(self.app.playhead):.4f}')
        bar=FlowRow(self.key_section,gap=3);bar.pack(fill='x',pady=4)
        for var in (self.kt,self.kv):bar.add(ttk.Entry(bar,textvariable=var,width=8))
        bar.add(ttk.Button(bar,text='Add / replace',command=self.add_key));bar.add(ttk.Button(bar,text='Delete',command=self.delete_key))
        self.tree.bind('<<TreeviewSelect>>',self.choose_key);self.refresh_keys()
        if fx.kind=='module':
            ttk.Label(deep,text='Inside: '+' → '.join(module_label(f) for f in children(fx)),style='Muted.TLabel',wraplength=330).grid(row=7,column=0,columnspan=4,sticky='ew')
            if hasattr(deck,'ungroup_module'):ttk.Button(deep,text='Ungroup · keep motion',command=lambda:deck.ungroup_module(self.context,fx.id)).grid(row=8,column=0,columnspan=4,sticky='w')
        if fx.extra.get('locked'):
            def disable(w):
                for child in w.winfo_children():
                    if isinstance(child,(ttk.Entry,ttk.Combobox,ttk.Checkbutton,ttk.Button)):child.configure(state='disabled')
                    elif isinstance(child,tk.Scale):child.configure(state='disabled')
                    disable(child)
                disable(self)
        self.bind('<Escape>',self.escape);self.bind('<Destroy>',self.destroyed,add='+')
        self._meter_job=None;self.field_baseline=self.model_fields();self.refresh_indicator();self._poll_indicator()

    def _entry(self,host,name,row,column,sticky=''):
        entry=ttk.Entry(host,textvariable=self.vars[name],width=5);entry.grid(row=row,column=column,sticky=sticky,padx=(0,5))
        entry.bind('<KeyRelease>',lambda e,n=name:self.queue_text(n,e));entry.bind('<Return>',lambda e,n=name:self.finish_text(n))
        entry.bind('<KP_Enter>',lambda e,n=name:self.finish_text(n))
        entry.bind('<FocusOut>',lambda e,n=name:self.finish_text(n));entry.bind('<Escape>',self.escape)
        self.entries[name]=entry;return entry

    def _bind_scale(self,scale):
        scale.bind('<ButtonPress-1>',self.begin_continuous);scale.bind('<ButtonRelease-1>',self.end_continuous)
        scale.bind('<KeyPress>',self.begin_continuous,add='+');scale.bind('<KeyRelease>',self.end_continuous,add='+')

    def _set_message(self,text):
        try:self.message.set(text)
        except (AttributeError,tk.TclError):pass

    def _target(self,allow_locked=False):
        try:target=self.context.resolve(self.deck,self.fx_id)
        except (tk.TclError,AttributeError):target=None
        if target is None:return None
        rack,fx,owner=target
        if fx.params.get(self.key) is not self.param:return None
        if fx.extra.get('locked') and not allow_locked:return None
        return rack,fx,owner

    def _gesture_target(self):
        target=self._target()
        return (target[1].params[self.key],target[2]) if target else None

    def _apply_changes(self,label,changes,*,protect=True,allow_locked=False):
        target=self._target(allow_locked)
        if target is None:
            self._set_message('Locked or stale · reopen the current module to edit.')
            return False
        values=dict(changes)
        if protect and 'conductor_locked' not in values:values['conductor_locked']=True
        try:update_parameter(copy.deepcopy(target[1].params[self.key]),values)
        except (ValueError,TypeError) as exc:self._set_message(str(exc));return False
        return self.deck.run_edit(self.context,label,lambda rack,fx,owner:update_parameter(fx.params[self.key],values),self.fx_id,allow_locked)

    def toggle_reaction(self):
        if self.react_enabled.get():return self.activate_reaction()
        mode='animate' if self.param.keyframes else 'static'
        return self._apply_changes('Bypass reaction on '+self.title,{'mode':mode})

    def activate_reaction(self):
        target=self._target()
        if target is None:return self._apply_changes('Enable reaction on '+self.title,{})
        return self._apply_changes('Enable reaction on '+self.title,initial_reaction_changes(target[1].params[self.key],available=available_reaction_sources(self.app)))

    def activate_source(self,value):
        target=self._target()
        if target is None:return self._apply_changes('Choose reaction source',{})
        changed=self._apply_changes('React to '+dict(REACTION_SOURCES).get(value,value),initial_reaction_changes(target[1].params[self.key],value))
        if changed and value=='microphone' and value not in available_reaction_sources(self.app):self.after_idle(self.prepare_source)
        return changed

    def prepare_source(self):
        source=self.param.source
        if source in ('microphone','reaction_mix') and hasattr(self.app,'open_live'):
            self._set_message('Choose and start a local input; Sound and Monitor remain unchanged.')
            return self.app.open_live()
        self._set_message('Add Music to its queue, then React will follow its analysed signal.')
        self.app.update_status(self.message.get())

    def activate_band(self,value):return self._apply_changes('Choose reaction band',{'react_band':value})
    def activate_response(self,name):return self._apply_changes('Choose '+name+' response',RESPONSE_PRESETS[name])
    def reverse_direction(self):return self._apply_changes('Reverse reaction direction',{'react_amount':-self.param.react_amount})
    def activate_choice(self,name):return self._apply_changes('Edit '+name.replace('_',' '),{name:self.vars[name].get()})
    def activate_flag(self,name,value):return self._apply_changes('Edit '+name.replace('_',' '),{name:value},protect=name!='conductor_locked')

    def begin_continuous(self,event=None):
        if not self.gesture.begin():return 'break'

    def depth_changed(self,value):
        if self._syncing or not self.gesture.active:return
        try:
            if self.gesture.write_field('react_amount',float(value)):
                self.vars['react_amount'].set(f'{float(value):g}');self.field_baseline['react_amount']=self.vars['react_amount'].get()
        except ValueError as exc:self._set_message(str(exc))

    def base_changed(self,value):
        if self._syncing or not self.gesture.active:return
        try:
            if self.gesture.write_base(float(value)):
                self.vars['value'].set(f'{float(value):g}');self.field_baseline['value']=self.vars['value'].get()
        except ValueError as exc:self._set_message(str(exc))

    def end_continuous(self,event=None):self.gesture.finish()

    def queue_text(self,name,event=None):
        if self._syncing:return
        if event is not None and not should_debounce_key(event):return
        job=self._after.pop(name,None)
        if job:
            try:self.after_cancel(job)
            except tk.TclError:pass
        self._after[name]=self.after(280,lambda n=name:self.flush_text(n))

    def flush_text(self,name,finish=False):
        job=self._after.pop(name,None)
        if job:
            try:self.after_cancel(job)
            except tk.TclError:pass
        try:
            value=float(self.vars[name].get())
            if not math.isfinite(value):raise ValueError
        except (ValueError,tk.TclError):
            self._set_message('Enter a finite number; incomplete text has not changed the parameter.')
            if finish:self.gesture.finish()
            return False
        try:
            if name=='value':
                if not self.param.minimum<=value<=self.param.maximum:raise ValueError(f'Enter {self.param.minimum:g}–{self.param.maximum:g}.')
                changed=self.gesture.write_base(value)
                if changed:self.base_value.set(value);self.field_baseline[name]=f'{value:g}'
            else:
                changed=self.gesture.write_field(name,value)
                if changed:
                    self.field_baseline[name]=f'{value:g}'
                    if name=='react_amount':self.depth_value.set(value)
        except ValueError as exc:self._set_message(str(exc));changed=False
        if finish:self.gesture.finish()
        return changed

    def finish_text(self,name):self.flush_text(name,True);return 'break'

    def escape(self,event=None):
        for name,job in tuple(self._after.items()):
            try:self.after_cancel(job)
            except tk.TclError:pass
        self._after.clear()
        if self.gesture.active:self.gesture.cancel()
        else:self.sync_fields({})
        return 'break'

    def close(self):
        if self.gesture.active:self.gesture.finish()
        try:self.deck.close_tray(self.fx_id,self.key)
        except TypeError:self.deck.close_tray()

    def toggle_pin(self):
        if hasattr(self.deck,'pin_parameter'):self.deck.pin_parameter(self.fx_id,self.key,self.pinned.get())

    def destroyed(self,event):
        if event.widget is not self:return
        for job in self._after.values():
            try:self.after_cancel(job)
            except tk.TclError:pass
        self._after.clear()
        if self._meter_job:
            try:self.after_cancel(self._meter_job)
            except tk.TclError:pass
            self._meter_job=None

    def _poll_indicator(self):
        try:
            if not self.winfo_exists():return
            self.refresh_indicator();self._meter_job=self.after(160,self._poll_indicator)
        except tk.TclError:self._meter_job=None

    def refresh_indicator(self):
        try:
            available=available_reaction_sources(self.app)
            text,level=source_status(self.app,self.param.source,available);self.source_note.set(text);self.source_meter['value']=level
            ready=self.param.source in available
            self.prepare_button.configure(text='Ready' if ready else ('Mic…' if self.param.source=='microphone' else 'Audio…'),state='disabled' if ready else 'normal')
            self.response_note.set(response_name(self.param))
            value=self.app.signal_evaluator().value(self.param,self.app.playhead)
            self.effective.set(f'Now {value:.3g}')
        except (tk.TclError,AttributeError,ValueError):pass

    def model_fields(self):
        values={key:(f'{getattr(self.param,key):g}' if key in PARAMETER_NUMBERS else getattr(self.param,key)) for key in self.vars}
        values.update(combine_animation=self.param.combine_animation,conductor_locked=bool(self.param.extra.get('conductor_locked',False)))
        return values
    def pending_fields(self):
        values={key:var.get() for key,var in self.vars.items()}
        values.update(combine_animation=self.combine.get(),conductor_locked=self.protected.get())
        pending={}
        for key,value in values.items():
            baseline=self.field_baseline[key]
            if key in PARAMETER_NUMBERS:
                try:
                    if float(value)==float(baseline):continue
                except (TypeError,ValueError):pass
            if value!=baseline:pending[key]=value
        return pending
    def sync_fields(self,pending):
        self.field_baseline=self.model_fields();values={**self.field_baseline,**pending};self._syncing=True
        try:
            for key,var in self.vars.items():
                if var.get()!=values[key]:var.set(values[key])
            if hasattr(self,'source_label'):self.source_label.set(self.source_labels.get(values['source'],values['source']))
            if hasattr(self,'band_label'):self.band_label.set(self.band_labels.get(values['react_band'],values['react_band']))
            self.combine.set(values['combine_animation']);self.protected.set(values['conductor_locked'])
            self.react_enabled.set(self.param.mode=='react');self.base_value.set(self.param.value);self.depth_value.set(self.param.react_amount)
            self.refresh_indicator()
        finally:self._syncing=False
    def apply(self,event=None):
        # Compatibility for older callers which set vars then request one batch.
        if not self.winfo_exists() or self._target() is None:return 'break'
        try:
            values=self.pending_fields()
            if not values:return 'break'
            trial=copy.deepcopy(self.param);update_parameter(trial,values)
        except (ValueError,tk.TclError) as exc:self.message.set(str(exc));return 'break'
        self._apply_changes('Edit '+self.title,values)
        return 'break'
    def refresh_keys(self):
        self.tree.delete(*self.tree.get_children())
        for i,key in enumerate(self.param.keyframes):self.tree.insert('','end',iid=str(i),values=(f'{key.time:.4f}',f'{key.value:.4f}'))
    def choose_key(self,event=None):
        selected=self.tree.selection()
        if selected:
            key=self.param.keyframes[int(selected[0])];self.kt.set(str(key.time));self.kv.set(str(key.value))
    def add_key(self):
        if not self.winfo_exists():return
        try:
            t=float(self.kt.get());v=float(self.kv.get())
            if not math.isfinite(t) or not math.isfinite(v) or t<0:raise ValueError('Use a finite, non-negative project time and value.')
            if not self.param.minimum<=v<=self.param.maximum:raise ValueError('Key value must be inside the parameter range.')
        except (ValueError,tk.TclError) as exc:self.message.set(str(exc));return
        def add(rack,fx,owner):
            param=fx.params[self.key];mode=param.mode;param.add_keyframe(t,v)
            if mode=='react':param.mode='react';param.combine_animation=True
            param.extra['conductor_locked']=True
        self.deck.run_edit(self.context,'Add parameter keyframe',add,self.fx_id)
    def delete_key(self):
        if not self.winfo_exists():return
        selected=self.tree.selection()
        if not selected:return
        when=self.param.keyframes[int(selected[0])].time
        def remove(rack,fx,owner):
            param=fx.params[self.key];param.keyframes[:]=[key for key in param.keyframes if key.time!=when];param.extra['conductor_locked']=True
        self.deck.run_edit(self.context,'Delete parameter keyframe',remove,self.fx_id)


class RackGroupTray(ttk.Frame):
    """One attached group inspector; edits resolve stable IDs into stored children."""
    def __init__(self,parent,deck,fx,key):
        super().__init__(parent,padding=5)
        self.deck=deck;self.app=deck.app;self.context=RackContext.capture(deck);self.fx_id=fx.id;self.key=key
        head=ttk.Frame(self);head.pack(fill='x')
        ttk.Label(head,text='CONTROLS',style='Title.TLabel').pack(side='left',expand=True,fill='x')
        ttk.Button(head,text='×',width=3,command=self.close).pack(side='right')
        self.count=tk.StringVar(value='');ttk.Label(head,textvariable=self.count,style='Muted.TLabel').pack(side='right',padx=3)
        self.app.add_tip(head,'Choose a control below. Internal edits persist in the group; promoted controls are edited at their owner.')
        chrome=self.app.ui_chrome
        self.list=tk.Listbox(self,height=4,exportselection=False,width=22,relief='flat',borderwidth=0,
                             background=chrome['field_bg'],foreground=chrome['field_fg'],
                             selectbackground=chrome['accent'],selectforeground=chrome['background'],
                             highlightthickness=1,highlightbackground=chrome['panel_edge'],
                             activestyle='none',font=('TkDefaultFont',9))
        self.list.pack(fill='x',pady=4)
        self.app.add_tip(self.list,'Choose a face or internal control. Arrow keys scroll the complete group, including nested modules.')
        self.targets=[]
        tactile=ttk.Frame(self);tactile.pack(fill='x',pady=(1,3))
        ttk.Label(tactile,text='VALUE',style='Muted.TLabel').pack(side='left')
        self.tactile_value=tk.DoubleVar(value=0)
        self.tactile_scale=tk.Scale(tactile,variable=self.tactile_value,from_=0,to=1,
                                    orient='horizontal',showvalue=False,resolution=.01,length=110,
                                    command=self.drag_tactile,**tk_scale_theme_options(chrome))
        self.tactile_scale.pack(side='left',fill='x',expand=True,padx=(3,0))
        self.tactile_scale.bind('<ButtonPress-1>',self.begin_tactile)
        self.tactile_scale.bind('<ButtonRelease-1>',self.end_tactile)
        self.tactile_scale.bind('<KeyPress>',self.begin_tactile,add='+')
        self.tactile_scale.bind('<KeyRelease>',self.end_tactile,add='+')
        self.tactile_scale.bind('<Escape>',lambda event:(self.finish_input(cancel=True),'break')[1])
        self.app.add_tip(self.tactile_scale,'Turn this value to change the picture now. One turn makes one Undo step; the precise value is editable below.')
        self._gesture=None;self._syncing=False
        detail_host=ttk.Frame(self);detail_host.pack(fill='both',expand=True)
        canvas=tk.Canvas(detail_host,highlightthickness=0,width=185,height=95,background=chrome['panel_bg'])
        scrollbar=ttk.Scrollbar(detail_host,orient='vertical',command=canvas.yview)
        scrollbar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        self.detail=ttk.Frame(canvas);window=canvas.create_window((0,0),window=self.detail,anchor='nw')
        self.detail.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
        canvas.bind('<MouseWheel>',lambda e:(canvas.yview_scroll(-int(e.delta/120),'units'),'break')[1])
        self.list.bind('<<ListboxSelect>>',self.select)
        self.populate()
        self.bind('<Escape>',lambda e:self.close())

    def current(self):
        resolved=self.context.resolve(self.deck,self.fx_id)
        return resolved[1] if resolved else None

    def refresh_view(self):
        """Follow current data without replacing a focused edit or the device."""
        fx=self.current()
        if fx is None:return
        selected=self.list.curselection()
        if not selected:return
        path,key=self.targets[selected[0]]
        try:
            _,_,param=internal_parameter_target(fx,path,key) if path else ((),key,fx.params[key])
        except (ValueError,KeyError,StopIteration):
            self.populate();return
        if self._gesture:return
        self._syncing=True
        try:
            if self.tactile_value.get()!=param.value:self.tactile_value.set(param.value)
        finally:self._syncing=False
        if self.focus_get() in (self.input,self.option):return
        value=param.extra.get('conductor_locked',False) if self.field.get()=='conductor_locked' else getattr(param,self.field.get())
        value=str(value)
        if self.value.get()!=value:self.value.set(value)

    def populate(self):
        fx=self.current();self.list.delete(0,'end');self.targets=[]
        if fx is None:return
        for key,desc in parameter_descriptions(fx).items():
            self.targets.append(((),key));self.list.insert('end','● '+desc['label'])
        def visit(group,path=(),depth=0):
            for child in children(group):
                child_path=(*path,child.id)
                for key,desc in parameter_descriptions(child).items():
                    self.targets.append((child_path,key))
                    origin='Group' if child.kind=='module' else module_label(child)
                    self.list.insert('end','  '*min(depth,2)+'↳ '+origin+' · '+desc['label'])
                if child.kind=='module':visit(child,child_path,depth+1)
        visit(fx)
        if self.targets:self.list.selection_set(0);self.select()

    def select(self,event=None):
        if self._gesture:self.end_tactile()
        selected=self.list.curselection()
        if not selected:return
        self.count.set(f'{selected[0]+1}/{len(self.targets)}')
        path,key=self.targets[selected[0]];fx=self.current()
        for child in self.detail.winfo_children():child.destroy()
        if fx is None:return
        if path:
            try:owner_path,owner_key,param=internal_parameter_target(fx,path,key)
            except (ValueError,KeyError):return
        else:owner_path,owner_key,param=(),key,fx.params[key]
        owner=fx
        owner_names=[]
        for child_id in owner_path:
            owner=next(child for child in children(owner) if child.id==child_id)
            owner_names.append(module_label(owner))
        label=owner.extra.get('labels',{}).get(owner_key,owner_key.replace('_',' ').title())
        selected_module=fx
        for child_id in path:selected_module=next(child for child in children(selected_module) if child.id==child_id)
        selected_description=parameter_descriptions(selected_module)[key]
        title=ttk.Label(self.detail,text=selected_description['label'],wraplength=185,style='Title.TLabel');title.pack(anchor='w')
        self.app.add_tip(title,selected_description['help'])
        if path:
            authority='Group face · '+label if not owner_path else 'Inside '+ ' › '.join(owner_names)+' · '+label
            ttk.Label(self.detail,text='Controlled by: '+authority,style='Muted.TLabel',wraplength=185).pack(anchor='w')
        self._syncing=True
        try:
            self.tactile_scale.configure(from_=param.minimum,to=param.maximum,
                                          resolution=max(.001,(param.maximum-param.minimum)/500))
            self.tactile_value.set(param.value)
        finally:self._syncing=False
        self.field=tk.StringVar(value='value');self.value=tk.StringVar(value=f'{param.value:g}')
        self.field_names={'value':'Base value','mode':'Motion · Static/React/Keys','source':'React source',
                          'react_band':'React band','react_amount':'React travel','attack':'Attack (s)',
                          'release':'Release (s)','threshold':'Threshold','minimum':'Range minimum',
                          'maximum':'Range maximum','interpolation':'Keys interpolation',
                          'combine_animation':'React over keys','conductor_locked':'Protect from Conductor'}
        self.field_label=tk.StringVar(value=self.field_names['value'])
        pick=ttk.Combobox(self.detail,textvariable=self.field_label,values=list(self.field_names.values()),state='readonly',width=20);pick.pack(fill='x',pady=(4,1))
        self.field_box=pick
        self.input=ttk.Entry(self.detail,textvariable=self.value);self.input.pack(fill='x')
        self.option=ttk.Combobox(self.detail,textvariable=self.value,state='readonly',width=18)
        pick.bind('<<ComboboxSelected>>',self.show_field)
        self.app.add_tip(pick,'Base is a precise number. Motion chooses fixed, audio reaction or timed keys; the other fields tune the selected mode.')
        self.input.bind('<Return>',lambda e:self.save(path,key));self.input.bind('<KP_Enter>',lambda e:self.save(path,key))
        save=ttk.Button(self.detail,text='Apply',command=lambda:self.save(path,key));save.pack(anchor='w',pady=3);self.save_button=save
        self.app.add_tip(save,'Apply to the owning parameter with Undo. Modes: static, react, animate. A mapped child follows its promoted control.')
        self.feedback=tk.StringVar(value='');ttk.Label(self.detail,textvariable=self.feedback,wraplength=185).pack(anchor='w')
        keys=ttk.Frame(self.detail);keys.pack(fill='x',pady=(4,0))
        ttk.Label(keys,text=f'Keys: {len(param.keyframes)}',style='Muted.TLabel').pack(anchor='w')
        self.key_time=tk.StringVar(value=f'{self.app.playhead:.3f}');self.key_value=tk.StringVar(value=f'{param.value:g}')
        ttk.Entry(keys,textvariable=self.key_time,width=7).pack(side='left')
        ttk.Entry(keys,textvariable=self.key_value,width=7).pack(side='left')
        ttk.Button(keys,text='+ Key',command=lambda:self.change_key(path,key,True)).pack(side='left')
        ttk.Button(self.detail,text='Remove key at time',command=lambda:self.change_key(path,key,False)).pack(anchor='w')
        if fx.extra.get('locked') or any(self._locked_at(fx,path[:n]) for n in range(1,len(path)+1)):
            for widget in (pick,self.input,save):widget.configure(state='disabled')
            self.feedback.set('Locked · unlock the card or internal module to edit.')
        self.input.focus_set()

    def begin_tactile(self,event=None):
        if self._gesture:return
        selected=self.list.curselection()
        if not selected:return 'break'
        path,key=self.targets[selected[0]]
        resolved=self.context.resolve(self.deck,self.fx_id)
        if resolved is None:return 'break'
        _,group,owner=resolved
        if group.extra.get('locked') or any(self._locked_at(group,path[:n]) for n in range(1,len(path)+1)) or not self.app.can_edit(owner):
            self.app.update_status('Unlock the module before turning this control.');return 'break'
        trial=copy.deepcopy(group)
        owner_path,owner_key=internal_parameter_owner(trial,path,key) if path else ((),key)
        chain=[];node=trial
        for child_id in owner_path:
            siblings=children(node);child=next(fx for fx in siblings if fx.id==child_id)
            chain.append((node,siblings));node=child
        from input_gestures import claim_input
        claim_input(self.app,self)
        self.app.begin_gesture('program')
        self._gesture=(group,owner,trial,node.params[owner_key],chain,key)

    def drag_tactile(self,value):
        if self._syncing or not self._gesture:return
        if not self.app.gesture:
            # Escape/Undo may have restored a different project while the pointer
            # is still held. A late motion must never reapply the old trial state.
            self._gesture=None
            from input_gestures import release_input
            release_input(self.app,self)
            return
        from sequencer_model import _encode
        from module_engine import compile_rack
        group,owner,trial,param,chain,key=self._gesture
        current=self.context.resolve(self.deck,self.fx_id)
        if current is None or current[1] is not group:return self.end_tactile()
        try:
            number=max(param.minimum,min(param.maximum,float(value)))
            if key in ('taps','rows','columns','waves','spacing'):number=round(number)
            self.app.write_parameter(param,number,owner)
            for parent,siblings in reversed(chain):parent.extra['children']=_encode(siblings)
            compile_rack([trial])
            for name,updated in trial.params.items():
                if name in group.params:group.params[name].__dict__.update(copy.deepcopy(updated.__dict__))
                else:group.params[name]=copy.deepcopy(updated)
            group.extra=copy.deepcopy(trial.extra)
            if self.field.get()=='value' and self.focus_get() is not self.input:self.value.set(f'{number:g}')
        except (TypeError,ValueError) as exc:self.app.update_status(str(exc))

    def end_tactile(self,event=None):
        if not self._gesture:return
        self._gesture=None
        from input_gestures import release_input
        release_input(self.app,self)
        if self.app.gesture:self.app.end_gesture()

    def finish_input(self,*,cancel=False):
        if not self._gesture:return
        self._gesture=None
        from input_gestures import release_input
        release_input(self.app,self)
        if self.app.gesture:
            if cancel:self.app.cancel_gesture()
            else:self.app.end_gesture()

    def _locked_at(self,fx,path):
        for child_id in path:fx=next(child for child in children(fx) if child.id==child_id)
        return bool(fx.extra.get('locked'))

    def show_field(self,event=None):
        name=next(key for key,label in self.field_names.items() if label==self.field_label.get())
        self.field.set(name)
        selected=self.list.curselection()
        if not selected:return
        path,key=self.targets[selected[0]];fx=self.current()
        if fx is None:return
        _,_,param=internal_parameter_target(fx,path,key) if path else ((),key,fx.params[key])
        choices=PARAMETER_CHOICES.get(name)
        if name in ('conductor_locked','combine_animation'):choices=('True','False')
        if choices:
            self.input.pack_forget();self.option.configure(values=choices)
            if not self.option.winfo_manager():self.option.pack(fill='x',before=self.save_button)
        else:
            self.option.pack_forget()
            if not self.input.winfo_manager():self.input.pack(fill='x',before=self.save_button)
        value=param.extra.get(name,False) if name=='conductor_locked' else getattr(param,name)
        self.value.set(str(value))

    def save(self,path,key):
        name=self.field.get();value=self.value.get()
        if name in ('conductor_locked','combine_animation'):
            if value.lower() not in ('true','false','1','0','yes','no'):self.feedback.set('Use true or false.');return
            value=value.lower() in ('true','1','yes')
        elif name in PARAMETER_NUMBERS:
            try:value=float(value)
            except ValueError:self.feedback.set('Enter a number.');return
        fx=self.current()
        if fx is None:return
        try:
            trial=copy.deepcopy(fx)
            if path:edit_internal_parameter(trial,path,key,{name:value})
            else:update_parameter(trial.params[key],{name:value})
        except (ValueError,TypeError) as exc:self.feedback.set(str(exc));return
        def apply(rack,group,owner):
            if path:edit_internal_parameter(group,path,key,{name:value})
            else:update_parameter(group.params[key],{name:value})
        if self.deck.run_edit(self.context,'Edit group control',apply,self.fx_id):
            self.feedback.set('Applied · Undo available')
            self.select()

    def change_key(self,path,key,add):
        try:
            time=float(self.key_time.get());value=float(self.key_value.get())
            if not math.isfinite(time) or time<0:raise ValueError('Use a non-negative time.')
            fx=self.current()
            if fx is None or fx.extra.get('locked') or any(self._locked_at(fx,path[:n]) for n in range(1,len(path)+1)):
                raise ValueError('Unlock the card or internal module before editing keys.')
            owner_path,owner_key,param=internal_parameter_target(fx,path,key) if path else ((),key,fx.params[key])
            if add and (not math.isfinite(value) or not param.minimum<=value<=param.maximum):raise ValueError('Key value outside range.')
            trial=copy.deepcopy(fx)
            def change(group):
                from sequencer_model import _encode
                if owner_path:
                    subs=children(group);child=next(e for e in subs if e.id==owner_path[0]);change_child(child,owner_path[1:]);group.extra['children']=_encode(subs)
                else:change_param(group.params[owner_key])
            def change_child(node,remaining):
                from sequencer_model import _encode
                if remaining:
                    subs=children(node);child=next(e for e in subs if e.id==remaining[0]);change_child(child,remaining[1:]);node.extra['children']=_encode(subs)
                else:change_param(node.params[owner_key])
            def change_param(p):
                if add:p.add_keyframe(time,value);p.mode='animate' if p.mode=='static' else p.mode
                else:p.keyframes[:]=[k for k in p.keyframes if k.time!=time]
                p.extra['conductor_locked']=True
            change(trial)
            from module_engine import compile_rack
            compile_rack([trial])
        except (ValueError,TypeError,AttributeError) as exc:self.feedback.set(str(exc));return
        if self.deck.run_edit(self.context,'Edit group keyframe',lambda rack,group,owner:change(group),self.fx_id):self.select()

    def close(self):
        self.finish_input()
        self.deck.close_tray(self.fx_id,self.key)
