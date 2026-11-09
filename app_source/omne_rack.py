"""Compact pedal shelf, with precision retained in each module's own editor."""
from __future__ import annotations
import copy
import math
import tkinter as tk
from tkinter import ttk
from neospector_pedals import PedalDeck, FACES
from neospector_catalog import PRIMARY_LABELS
from performance_dials import PerformanceDial
from module_engine import label as module_label, reset_effect, ungroup, compile_rack, group_selected as group_selected_now, priority_keys, parameter_descriptions
from effects_engine import EFFECTS
from editor_widgets import ParameterDialog
from rack_editing import RackContext, move_module, update_parameter

# Rack faceplates use the family colours as hardware accents over a dark common
# chassis.  This keeps the signal path readable like a Eurorack/pedalboard while
# avoiding the large flat theme-colour cards used by the earlier prototype.
RACK_FACES={
    'Adjust':('#1D242B','#F0ECE0','#D2B94F'),
    'Colour':('#172936','#EEF7FA','#49B9E6'),
    'Texture':('#2A2618','#F5ECC7','#D8B84E'),
    'Spatial':('#16302D','#EAF5EB','#6EC6AC'),
    'Time':('#24223A','#F4EDFC','#AD9AE5'),
    'Light':('#34231D','#FFF0DA','#E29469'),
    'Custom':('#22272C','#F1EEE2','#BBB172'),
}

class ParameterDial(PerformanceDial):
    def __init__(self,parent,app,title,param,owner,locked=False,guard=None,open_controls=None,select_owner=None,face=None):
        self.param=param;self.owner=owner;self.locked=locked;self.syncing=False;self.guard=guard;self.select_owner=select_owner;self.face=face
        self.open_controls=open_controls or (lambda:ParameterDialog(app,title,param,owner))
        self.normal=tk.DoubleVar(value=self.to_normal(param.value))
        super().__init__(parent,app,title,self.normal,self.start_edit,self.write,self.finish_edit,
                         'Controls the current treatment. Double-click or type a precise value; right-click opens reaction, limits and keyframes.',units='native')
        self.entry.configure(width=6)
        if face:
            bg,fg,accent=face;style='RackDial'+bg[1:].upper()
            st=ttk.Style(self);st.configure(style+'.TFrame',background=bg);st.configure(style+'.TLabel',background=bg,foreground=fg,font=('TkDefaultFont',8,'bold'))
            self.configure(style=style+'.TFrame');self.title.configure(style=style+'.TLabel')
            self.canvas.configure(bg=bg,highlightbackground=bg,highlightcolor=accent)
            for tag,colour in (('tick',accent),('ring',app.ui_chrome['field_bg']),('sweep',accent),('pointer',fg)):
                self.canvas.itemconfigure(tag,fill=colour) if tag in ('tick','pointer') else self.canvas.itemconfigure(tag,outline=colour)
            self.canvas.itemconfigure('body',fill=app.ui_chrome['button_bg'],outline=accent);self.canvas.itemconfigure('inner',fill=app.ui_chrome['button_bg'],outline=app.ui_chrome['field_bg']);self.canvas.itemconfigure('custom',fill=accent)
        self.canvas.bind('<Button-3>',lambda e:self.open_controls())
        self.entry.bind('<Button-3>',lambda e:self.open_controls())
        if locked:self.entry.configure(state='disabled');self.canvas.configure(takefocus=False)
    def retheme(self):
        super().retheme()
        face=getattr(self,'face',None)
        if not face:return
        bg,fg,accent=face;style='RackDial'+bg[1:].upper();st=ttk.Style(self)
        st.configure(style+'.TFrame',background=bg);st.configure(style+'.TLabel',background=bg,foreground=fg,font=('TkDefaultFont',8,'bold'))
        self.configure(style=style+'.TFrame');self.title.configure(style=style+'.TLabel')
        self.canvas.configure(bg=bg,highlightbackground=bg,highlightcolor=accent)
        for tag,colour in (('tick',accent),('ring',self.app.ui_chrome['field_bg']),('sweep',accent),('pointer',fg)):
            self.canvas.itemconfigure(tag,fill=colour) if tag in ('tick','pointer') else self.canvas.itemconfigure(tag,outline=colour)
        self.canvas.itemconfigure('body',fill=self.app.ui_chrome['button_bg'],outline=accent);self.canvas.itemconfigure('inner',fill=self.app.ui_chrome['button_bg'],outline=self.app.ui_chrome['field_bg']);self.canvas.itemconfigure('custom',fill=accent)
    def editable(self):return not self.locked and (self.guard is None or self.guard()) and self.app.can_edit(self.owner)
    def to_normal(self,value):return (value-self.param.minimum)/max(.000001,self.param.maximum-self.param.minimum)
    def start_edit(self):
        if self.editable():
            if self.select_owner:self.select_owner()
            self.app.begin_gesture('program')
    def write(self,value):
        if not self.editable():return
        self.app.write_parameter(self.param,self.param.minimum+float(value)*(self.param.maximum-self.param.minimum),self.owner)
    def finish_edit(self):
        if not self.locked:self.app.end_gesture()
    def apply(self,value):
        if self.editable():super().apply(value)
    def show_value(self,*args,force=False):
        super().show_value(*args,force=force)
        if force or self.app.focus_get() is not self.entry:
            value=self.param.minimum+self.normal.get()*(self.param.maximum-self.param.minimum)
            self.text.set(f'{value:.3f}'.rstrip('0').rstrip('.') or '0')
    def enter(self,event=None):
        try:
            value=float(self.text.get())
            if not self.param.minimum<=value<=self.param.maximum:raise ValueError(f'Enter {self.param.minimum:g}–{self.param.maximum:g}.')
            self.apply(self.to_normal(value));self.release();self.canvas.focus_set();self.show_value(force=True)
        except ValueError as exc:self.app.update_status(str(exc))
        return 'break'
    def refresh(self):
        if not self.active:self.normal.set(self.to_normal(self.param.value))


class ParameterFader(tk.Frame):
    """Compact hardware fader used on a module face.

    The precision/reaction model remains the same as ParameterDial, but the rack
    surface uses the small horizontal controls from the approved hardware mock-up.
    A drag is one semantic programme gesture and refreshes never replace the widget.
    """
    def __init__(self,parent,app,title,param,owner,locked=False,guard=None,open_controls=None,select_owner=None,face=None):
        self.param=param;self.owner=owner;self.locked=locked;self.guard=guard;self.open_controls=open_controls or (lambda:ParameterDialog(app,title,param,owner));self.select_owner=select_owner;self._committing_entry=False
        from ux16_layout import parameter_kind
        self.semantic_kind=parameter_kind(title,param.minimum,param.maximum)
        self.face=face or RACK_FACES['Custom'];bg,fg,accent=self.face;self.app=app;self.active=False;self.syncing=False
        super().__init__(parent,bg=bg,bd=0,highlightthickness=0,padx=2,pady=0)
        # A single instrument-strip row. Width belongs to the fader, not
        # an oversized secondary toolbar. All parameters use the same anatomy.
        self.columnconfigure(0,weight=0);self.columnconfigure(1,weight=1)
        self.columnconfigure(2,weight=0);self.columnconfigure(3,weight=0)
        self.title=tk.Label(self,text=('± '+title[:7] if self.semantic_kind=='bipolar' else title.upper()[:9]),bg=bg,fg=fg,anchor='w',width=8,font=('TkFixedFont',7,'bold'))
        self.title.grid(row=0,column=0,sticky='w')
        self.text=tk.StringVar();self.entry=ttk.Entry(self,textvariable=self.text,width=4,justify='right')
        self.entry.grid(row=0,column=2,sticky='e',padx=(2,1))
        self.mode_button=ttk.Button(self,text='∿',width=4)
        self.mode_button.grid(row=0,column=3,sticky='e')
        self.normal=tk.DoubleVar(value=self.to_normal(self.display_value()))
        self.scale=tk.Scale(self,variable=self.normal,from_=0,to=1,resolution=(1/max(1.,param.maximum-param.minimum) if self.semantic_kind in ('steps','switch') else .001),orient='horizontal',showvalue=False,command=self.write,
            bg=bg,fg=fg,troughcolor=app.ui_chrome['field_bg'],activebackground=accent,highlightthickness=0,bd=0,sliderlength=10,width=7,length=40,takefocus=True)
        self.scale.grid(row=0,column=1,sticky='ew',padx=(2,1));self.canvas=self.scale
        app.add_tip(self.title,title+' · '+ ('Edit the value with the fader or number field.'))
        for widget in (self.scale,self.entry):app.add_tip(widget,'Drag the front-panel fader for immediate control. Type a precise value on the right. React opens the attached response device.')
        self.scale.bind('<ButtonPress-1>',self.begin);self.scale.bind('<ButtonRelease-1>',self.finish);self.scale.bind('<KeyPress>',self.begin,add='+');self.scale.bind('<KeyRelease>',self.finish,add='+')
        # UX13 removes hidden right-click editors from the pedal surface.
        self.entry.bind('<Return>',self.enter);self.entry.bind('<KP_Enter>',self.enter);self.entry.bind('<Escape>',self.cancel_entry);self.entry.bind('<FocusOut>',self.entry_blur)
        self.scale.bind('<Escape>',lambda e:(self.finish_input(cancel=True),'break')[1])
        if locked:self._set_locked(True)
        self.show_value()
    def make_dial(self):
        if hasattr(self,'dial'):return
        from instrument_dial import InstrumentDial
        self.scale.grid_remove();self.dial=InstrumentDial(self,self);self.dial.grid(row=2,column=0,columnspan=3,pady=3)
    def editable(self):return not self.locked and (self.guard is None or self.guard()) and self.app.can_edit(self.owner)
    def to_normal(self,value):return (float(value)-self.param.minimum)/max(.000001,self.param.maximum-self.param.minimum)
    def from_normal(self,value):return self.param.minimum+float(value)*(self.param.maximum-self.param.minimum)
    def display_value(self):
        """Show the value being edited, not an older base beneath keyframes."""
        p=self.param
        if p.mode=='animate' or (p.mode=='react' and p.combine_animation and p.keyframes):
            t=self.app.gesture_time if getattr(self.app,'gesture',None) else getattr(self.app,'playhead',0.)
            if hasattr(self.app,'parameter_edit_clock') and self.owner is not None:
                from sequencer_model import Clip
                if isinstance(self.owner,Clip):t=self.app.parameter_edit_clock(self.owner,t)
            return p.animated_value(t)
        return p.value
    def begin(self,event=None):
        if self.active:return None
        if not self.editable():return 'break'
        from input_gestures import claim_input
        claim_input(self.app,self)
        self.scale.focus_set()
        if self.select_owner:self.select_owner()
        self.active=True;self.app.begin_gesture('program');return None
    def write(self,value):
        if self.syncing or not self.active:return
        if not self.editable():return
        native=self.from_normal(value)
        if self.semantic_kind in ('steps','switch'):native=round(native)
        self.app.write_parameter(self.param,native,self.owner);self.text.set(f'{native:.3f}'.rstrip('0').rstrip('.') or '0')
        if hasattr(self,'dial'):self.dial.draw()
    def apply(self,value):
        value=max(0.,min(1.,float(value)))
        if not self.active and self.begin()=='break':return
        self.syncing=True;self.normal.set(value);self.syncing=False;self.write(value)
    def finish_input(self,*,cancel=False,commit_latest=True):
        if not self.active:return
        # Tk Scale commands may be queued until idle; commit the final thumb
        # position *before* ending the semantic gesture. Never quantise a typed
        # numeric value back through the scale's 0.001 resolution.
        if not cancel and commit_latest:self.write(self.normal.get())
        from input_gestures import release_input
        self.active=False;release_input(self.app,self)
        if cancel:self.app.cancel_gesture()
        else:self.app.end_gesture()
        if self.winfo_exists():self.refresh()
    def finish(self,event=None):
        self.finish_input();return None
    def release(self,event=None):return self.finish(event)
    def enter(self,event=None,*,focus_scale=True):
        if self._committing_entry:return 'break'
        self._committing_entry=True
        try:
            value=float(self.text.get())
            if self.semantic_kind in ('steps','switch') and math.isfinite(value):
                value=float(round(value))
            if not math.isfinite(value) or not self.param.minimum<=value<=self.param.maximum:
                raise ValueError(f'Enter {self.param.minimum:g}–{self.param.maximum:g}.')
            if self.begin()=='break':return 'break'
            self.syncing=True
            try:self.normal.set(self.to_normal(value))
            finally:self.syncing=False
            self.app.write_parameter(self.param,value,self.owner)
            self.finish_input(commit_latest=False)
            if focus_scale:self.scale.focus_set()
            self.refresh()
        except ValueError as exc:
            self.app.update_status(str(exc));self.show_value()
        finally:self._committing_entry=False
        return 'break'
    def entry_blur(self,event=None):
        # Focus leaves an entry when a slider gesture starts. That blur must
        # not finish or supersede the gesture the user just began.
        if self._committing_entry or self.active:return
        # Clicking elsewhere commits a valid precise number instead of
        # overwriting it with the previous model value.
        self.enter(focus_scale=False)
    def cancel_entry(self,event=None):self.show_value();self.scale.focus_set();return 'break'
    def _set_locked(self,value):
        self.locked=bool(value);self.entry.configure(state='disabled' if self.locked else 'normal');self.scale.configure(state='disabled' if self.locked else 'normal')
    def refresh(self):
        if self.active:return
        normal=self.to_normal(self.display_value())
        if abs(float(self.normal.get())-normal)>1e-6:
            self.syncing=True
            try:self.normal.set(normal)
            finally:self.syncing=False
            if hasattr(self,'dial'):self.dial.draw()
        self.show_value()
        if hasattr(self,'_refresh_reaction'):self._refresh_reaction()
    def show_value(self):
        if self.app.focus_get() is not self.entry:
            displayed=self.display_value()
            label=str(round(displayed)) if self.semantic_kind in ('steps','switch') else (f'{displayed:.3f}'.rstrip('0').rstrip('.') or '0')
            if label!=self.text.get():self.text.set(label)
    def retheme(self):
        # Rack faceplates deliberately remain hardware-coloured while shared field
        # chrome follows the active Neospector theme.
        bg,fg,accent=self.face;self.configure(bg=bg);self.title.configure(bg=bg,fg=fg);self.scale.configure(bg=bg,fg=fg,troughcolor=self.app.ui_chrome['field_bg'],activebackground=accent)


class _OwnerRack(PedalDeck):
    def __init__(self,parent,app):
        self.tray_mode=None;self.tray_key=None;self.tray=None;self.tray_scope=None
        super().__init__(parent,app)
        self.randomise_button.configure(text='Randomise',command=self.random_now,width=9)
        top=self.grid_slaves(row=0,column=0)[0];row=top.winfo_children()[0]
        for widget in list(row.items):
            if isinstance(widget,ttk.Label) and widget.cget('text')=='PEDALBOARD':
                row.items.remove(widget);widget.destroy()
            if isinstance(widget,ttk.Combobox):
                widget.configure(width=17);self.scope_selector=widget
                app.add_tip(widget,'Current treatment target. Voice and clip racks process their own material; Whole picture is the final Programme rack. Conductor controls future choices.')
            if isinstance(widget,ttk.Button) and widget.cget('text')=='Keep…':
                row.items.remove(widget);widget.destroy()
        self.primary_actions[1].configure(width=6,command=lambda:self.random_now(True));self.primary_actions[2].configure(width=4)
        extra=ttk.Button(row,text='⋯',width=2,command=lambda:self.rack_menu(extra));row.add(extra)
        settings=app.settings();self.random_count=tk.StringVar(value=str(settings['module_count']));self.random_variation=tk.StringVar(value=f"{settings.get('variation',1.0)*100:g}")
        self.mutation_variation=tk.DoubleVar(value=settings.get('mutation_variation',.55)*100)
        controls=ttk.Frame(row)
        ttk.Spinbox(controls,from_=1,to=12,textvariable=self.random_count,width=3).pack(side='left')
        ttk.Label(controls,text='×').pack(side='left',padx=(2,4))
        ttk.Spinbox(controls,from_=0,to=100,increment=5,textvariable=self.random_variation,width=4).pack(side='left')
        ttk.Label(controls,text='%').pack(side='left',padx=(2,0));row.add(controls)
        mutation=ttk.Frame(row);ttk.Label(mutation,text='Δ').pack(side='left')
        self.mutation_scale=ttk.Scale(mutation,from_=0,to=100,variable=self.mutation_variation,length=55);self.mutation_scale.pack(side='left');row.add(mutation)
        for w in (controls,mutation):row.items.remove(w)
        row.items.insert(row.items.index(self.randomise_button)+1,controls)
        row.items.insert(row.items.index(self.primary_actions[1])+1,mutation)
        app.add_tip(controls,'New rack: top-level module count and parameter variation from defaults. Protected modules are retained.')
        app.add_tip(self.mutation_scale,'Mutation intensity. Mutate varies unlocked values while keeping the module chain.')
        self.scope_status=tk.StringVar()
        self.scope_label=ttk.Label(self,textvariable=self.scope_status,style='Muted.TLabel',anchor='w')
        self.scope_label.grid(row=2,column=0,sticky='ew',padx=6,pady=(1,0))
        self.card_controls={}

    def random_now(self,mutate=False):
        from omne_randomise import normalise_settings
        try:
            # Randomise means a new treatment: module count controls topology and
            # parameter generation runs at full authority. Mutate means preserve
            # the topology and use only the Vary percentage as its intensity.
            settings=normalise_settings({**self.app.settings(),'module_count':self.random_count.get(),
                'variation':float(self.random_variation.get())/100,'mutation_variation':float(self.mutation_variation.get())/100})
        except (ValueError,tk.TclError) as exc:return self.app.update_status(str(exc))
        return self.app.apply_rack_randomise(settings,mutate=mutate)

    def refresh(self,force=False):
        pending=None
        if self.tray_mode=='parameter' and self.tray is not None and self.tray.winfo_exists() and hasattr(self.tray,'pending_fields'):
            tray=self.tray
            pending=(tray.param,tray.pending_fields())
        super().refresh(force)
        if hasattr(self,'scope_status'):
            rack,owner=self.target()
            if rack is not None:
                role=self.target_name.get();state='history' if self.history_span is not None and self.scope.get()=='Layer' else 'current'
                self.scope_status.set(f'{role} · {state} · {len(rack)} modules · {sum(bool(f.enabled) for f in rack)} on')
            else:self.scope_status.set(self.summary.get())
        if pending and self.tray_mode=='parameter' and self.tray is not None and self.tray.winfo_exists():
            original,values=pending
            if self.tray.param is original:self.tray.sync_fields(values)

    def rack_menu(self,anchor):
        menu=tk.Menu(self,tearoff=False)
        patch=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Patch / group',menu=patch)
        patch.add_command(label='Keep rack as patch…',command=self.app.keep_ingredient)
        patch.add_command(label='Group selected modules…',command=self.group_selected)
        menu.add_command(label='Target / routing details…',command=self.owner_details)
        self.app.popup_menu(menu,anchor)

    def run_edit(self,context,label,operation,module_id=None,allow_locked=False):
        target=context.resolve(self,module_id)
        if target is None:
            self.app.update_status('The rack target changed. Select the current module again.');return False
        rack,fx,owner=target
        if not self.app.can_edit(owner):return False
        if fx is not None and fx.extra.get('locked') and not allow_locked:
            self.app.update_status('Unlock this module before editing it.');return False
        def apply():
            operation(rack,fx,owner)
            if hasattr(owner,'manual'):owner.manual=True
        self.app.transaction(label,apply)
        return True

    def parameter_guard(self,context,fxid,key,param):
        current=context.resolve(self,fxid)
        return bool(current and not current[1].extra.get('locked') and current[1].params.get(key) is param)

    def rack(self,parent,rack,owner):
        context=RackContext.capture(self)
        if not getattr(self,'cards_parent',None) or not self.cards_parent.winfo_exists():
            self.rendered_cards=[];self.card_parts={};self.card_controls={};self.companions={}
            # UX4 retired the transient bottom Add dock. Parameter companions remain
            # contextual; module browsing belongs to the stable Module Library panel.
            self.tray_host=None;self._local_tray_host=False
            cards=tk.Frame(parent,bg=self.app.ui_chrome['preview_bg'],bd=0,highlightthickness=0);cards.pack(fill='both',expand=True);self.cards_parent=cards
            cards.bind('<Configure>',self.resized,add='+')
        cards=self.cards_parent;c=self.app.ui_chrome
        present={f.id:f for f in rack}
        for fid,(shell,body,button) in list(self.card_parts.items()):
            fx=present.get(fid)
            signature=tuple((key,id(value)) for key,value in fx.params.items()) if fx else None
            if fx is None or shell.parameter_signature!=signature:
                shell.destroy();del self.card_parts[fid];self.card_controls.pop(fid,None)
                for key,tray in list(self.companions.items()):
                    if key[0]==fid:self.companions.pop(key)
        self.rows=[row for row in self.rows if row.winfo_exists()]
        for i,fx in enumerate(rack):
            if fx.id in self.card_parts:
                shell=self.card_parts[fx.id][0]
                if hasattr(shell,'name_label'):shell.name_label.configure(text=module_label(fx))
                continue
            family=fx.extra.get('family','Custom') if fx.kind=='module' else (EFFECTS[fx.kind].group if fx.kind in EFFECTS else 'Custom')
            bg,fg,accent=RACK_FACES.get(family,RACK_FACES['Custom'])
            shell=tk.Frame(cards,bg=bg,highlightthickness=2,highlightbackground=accent,bd=1,relief='ridge')
            shell.fx_id=fx.id;shell.accent=accent;shell.face=(bg,fg,accent);shell.parameter_signature=tuple((key,id(value)) for key,value in fx.params.items());self.rendered_cards.append(shell)
            # Two-line hardware header: controls never squeeze the module name.
            # This lets the chassis stay portrait-ish without turning labels into
            # unreadable abbreviations at normal rack widths.
            top=tk.Frame(shell,bg=bg,padx=4,pady=0);top.pack(fill='x')
            badge=tk.Label(top,text=f'{i+1:02d}',bg=accent,fg=bg,width=3,anchor='center',font=('TkFixedFont',8,'bold'),padx=2,pady=1);badge.pack(side='left',padx=(0,4));shell.number_badge=badge
            enabled=tk.BooleanVar(value=fx.enabled)
            power=tk.Checkbutton(top,text='ON',variable=enabled,indicatoron=False,bg=bg,fg=fg,selectcolor=accent,activebackground=accent,activeforeground=bg,bd=0,relief='flat',highlightthickness=0,padx=4,pady=1,command=lambda fid=fx.id,v=enabled:self.run_edit(context,'Module bypass',lambda rack,f,owner:setattr(f,'enabled',v.get()),fid,True));power.pack(side='left')
            lamp=tk.Canvas(top,width=12,height=12,bg=bg,highlightthickness=0);lamp.pack(side='left',padx=(4,3));lamp.dot=lamp.create_oval(2,2,10,10,outline=accent,fill=accent)
            self.app.add_tip(lamp,'Signal lamp: bright = processing, hollow = bypassed. A centre dot appears when a front-panel control is reacting.')
            self.app.add_tip(power,'Bypass this module while keeping its settings. Lock protects its values and chain position; bypass remains playable.')
            # Expanded is the normal instrument face. Compacting is automatic when
            # the rack truly cannot show a usable expanded card, not a mode the
            # performer has to manage. Keep the control object only for backwards
            # compatible tests/API callers; it is intentionally not packed.
            size=ttk.Button(top,text='▾',width=2,command=lambda:None)
            self.card_modes.setdefault(fx.id,'Expanded')
            more=ttk.Button(top,text='⋯',width=2,command=lambda f=fx,w=shell:self.module_menu(rack,f,w));more.pack(side='right',padx=(2,0))
            delete=ttk.Button(top,text='×',width=3,command=lambda fid=fx.id:self.delete_module(context,fid),style='UX19.Delete.TButton')
            delete.pack(side='right',padx=(2,1))
            locked=tk.BooleanVar(value=bool(fx.extra.get('locked')))
            lock=tk.Checkbutton(top,text='LOCK',variable=locked,indicatoron=False,bg=bg,fg=fg,selectcolor=accent,activebackground=accent,activeforeground=bg,bd=0,relief='flat',highlightthickness=0,padx=3,pady=1,command=lambda fid=fx.id,v=locked:self.run_edit(context,'Module lock',lambda rack,f,owner:f.extra.__setitem__('locked',v.get()),fid,True));lock.pack(side='right',padx=2)
            handle=tk.Label(top,text='⠿',cursor='fleur',bg=bg,fg=accent,font=('TkDefaultFont',11,'bold'));handle.pack(side='right',padx=(1,2));handle.bind('<ButtonPress-1>',lambda e,fid=fx.id:self.drag_start(fid,e));handle.bind('<B1-Motion>',self.drag_motion);handle.bind('<ButtonRelease-1>',self.drag_end)
            name=tk.Label(shell,text=module_label(fx),bg=bg,fg=fg,anchor='w',font=('TkDefaultFont',9,'bold'),padx=7,pady=0);name.pack(fill='x')
            name.bind('<Button-1>',lambda e,fid=fx.id:self.select_card(fid,bool(e.state&4)));name.bind('<Double-1>',lambda e,fid=fx.id,is_group=(fx.kind=='module'):self.inline_rename_group(fid) if is_group else self.open_parameter(fid));shell.name_label=name
            shell.configure(takefocus=True);shell.bind('<Alt-Left>',lambda e,fid=fx.id:self.reorder_module(context,fid,-1));shell.bind('<Alt-Right>',lambda e,fid=fx.id:self.reorder_module(context,fid,1));shell.bind('<Button-1>',lambda e,fid=fx.id:self.select_card(fid,bool(e.state&4)))
            shell.bind('<space>',lambda e,fid=fx.id:(self.select_card(fid,bool(e.state&4)),'break')[1])
            shell.bind('<Delete>',lambda e,fid=fx.id:(self.delete_module(context,fid),'break')[1])
            # The family is already communicated by the faceplate accent.  Keep
            # the card free of redundant subtitle chrome and expose the semantic
            # description as a tooltip instead.
            shell.family_tag=None
            self.app.add_tip(name,f'{family} module · '+('editable group' if fx.kind=='module' else 'signal module'))
            body=tk.Frame(shell,bg=bg,padx=4,pady=0);body.pack(fill='both',expand=True);shell.middle=body
            principal=tk.Frame(body,bg=bg);principal.pack(fill='x');shell.principal_controls=principal
            descriptions=parameter_descriptions(fx)
            face_keys=priority_keys(fx)
            params=[(key,fx.params[key]) for key in face_keys]+[(key,param) for key,param in fx.params.items() if key not in face_keys]
            # A single grid owns *every* parameter; the rack controls which
            # bank is visible at a fixed height. No second hidden detail stack.
            shell.fader_rows=[]
            extra=tk.Frame(body,bg=bg);shell.extra_controls=extra
            for key,param in params:
                description=descriptions[key]
                label='Amount' if key=='amount' and fx.kind!='module' else description['label']
                row=ParameterFader(principal,self.app,label,param,owner,bool(fx.extra.get('locked')),
                    guard=lambda fid=fx.id,k=key,p=param:self.parameter_guard(context,fid,k,p),
                    open_controls=lambda fid=fx.id,k=key:self.open_parameter(fid,k),
                    select_owner=lambda:self.root_rack.select_owner(self),face=(bg,fg,accent))
                self.app.add_tip(row.title,description['label']+' · '+description['help'])
                self.app.add_tip(row.mode_button,'Reaction on/off. The same pedal shows sound source, band and movement.')
                shell.fader_rows.append(row)
                self.rows.append(row)
                row.mode_button.configure(command=lambda fid=fx.id,k=key:self.react_parameter(fid,k))
            shell.face_page=0
            # Group internals live in the same attached Controls companion.
            # A second read-only list here displaces the playable face and
            # duplicates information without providing editing authority.
            foot=tk.Frame(shell,bg=self.app.ui_chrome['field_bg'],padx=4,pady=0);foot.pack(fill='x');shell.footer=foot
            react=tk.Button(foot,text='CONTROLS',command=lambda fid=fx.id:self.open_parameter(fid),bg=accent,fg=bg,activebackground=fg,activeforeground=bg,bd=0,relief='flat',padx=7,pady=2,font=('TkDefaultFont',8,'bold'));react.pack(side='left')
            self.app.add_tip(react,'Open the attached Controls companion for every parameter, reaction, keys and internal group controls.')
            self.app.add_tip(delete,'Remove this module from the chain. Undo restores its settings and place; unlock it first if locked.')
            later=ttk.Button(foot,text='→',width=2,command=lambda fid=fx.id:self.reorder_module(context,fid,1));later.pack(side='right',padx=(2,0))
            earlier=ttk.Button(foot,text='←',width=2,command=lambda fid=fx.id:self.reorder_module(context,fid,-1));earlier.pack(side='right')
            if i==0 or fx.extra.get('locked') or rack[i-1].extra.get('locked'):earlier.state(['disabled'])
            if i==len(rack)-1 or fx.extra.get('locked') or rack[i+1].extra.get('locked'):later.state(['disabled'])
            shell.companion_host=tk.Frame(cards,bg=bg,highlightthickness=2,highlightbackground=accent,bd=1,relief='ridge',padx=2,pady=2);shell.companion_host.grid_remove()
            self.card_controls[fx.id]={'lock':lock,'earlier':earlier,'later':later,'power':power,'lamp':lamp,'react':react,'delete':delete,'expand':size,'enabled_var':enabled,'locked_var':locked}
            shell.pack_propagate(False);self.card_parts[fx.id]=(shell,body,size)
        self.card_parts={fx.id:self.card_parts[fx.id] for fx in rack};self.rendered_cards=[parts[0] for parts in self.card_parts.values()]
        for i,fx in enumerate(rack):
            ctrl=self.card_controls[fx.id];locked=bool(fx.extra.get('locked'));ctrl['enabled_var'].set(fx.enabled);ctrl['locked_var'].set(locked)
            ctrl['earlier'].state(['disabled' if i==0 or locked or rack[i-1].extra.get('locked') else '!disabled'])
            ctrl['later'].state(['disabled' if i==len(rack)-1 or locked or rack[i+1].extra.get('locked') else '!disabled'])
            state=' · Locked' if locked else ' · Manual' if any(p.extra.get('conductor_locked') for p in fx.params.values()) else ''
            self.card_parts[fx.id][0].name_label.configure(text=module_label(fx)+state);self.card_parts[fx.id][0].number_badge.configure(text=f'{i+1:02d}')
            lamp=ctrl.get('lamp');reacting=any(p.mode=='react' for p in fx.params.values())
            if lamp is not None and lamp.winfo_exists():
                lamp.delete('react')
                lamp.itemconfigure(lamp.dot,fill=(self.card_parts[fx.id][0].accent if fx.enabled else ''),outline=self.card_parts[fx.id][0].accent)
                if reacting:lamp.create_oval(4,4,8,8,fill=self.app.ui_chrome['accent'],outline='',tags='react')
            if 'react' in ctrl:ctrl['react'].configure(text='CONTROLS ●' if reacting else 'CONTROLS')
            ctrl['delete'].state(['disabled' if locked else '!disabled'])
        for row in self.rows:
            current=next((f for f in rack if any(p is getattr(row,'param',None) for p in f.params.values())),None)
            if current:
                row.locked=bool(current.extra.get('locked'))
                if hasattr(row,'_set_locked'):row._set_locked(row.locked)
                else:row.entry.configure(state='disabled' if row.locked else 'normal')
                if hasattr(row,'mode_button'):row.mode_button.configure(text={'static':'React','react':'React ●','animate':'Keys ◆'}.get(row.param.mode,'Controls'))
        self.relayout();self.paint_selection()

    def show_empty_rack(self):
        parent=getattr(self,'cards_parent',None)
        if parent is None or not parent.winfo_exists():return
        if getattr(self,'empty',None) is not None and self.empty.winfo_exists():return
        c=self.app.ui_chrome;panel=tk.Frame(parent,bg='#11161B',highlightthickness=1,highlightbackground=c['accent'],bd=0,padx=12,pady=10)
        head=tk.Frame(panel,bg='#11161B');head.pack(fill='x')
        lamp=tk.Canvas(head,width=12,height=12,bg='#11161B',highlightthickness=0);lamp.pack(side='left',padx=(0,6));lamp.create_oval(2,2,10,10,outline=c['muted_fg'],fill='')
        tk.Label(head,text='NO MODULES',bg='#11161B',fg=c['foreground'],font=('TkFixedFont',8,'bold')).pack(side='left')
        tk.Label(panel,text='Signal passes unchanged.',bg='#11161B',fg=c['muted_fg'],anchor='w',font=('TkDefaultFont',8)).pack(fill='x',pady=(5,7))
        actions=tk.Frame(panel,bg='#11161B');actions.pack(fill='x')
        ttk.Button(actions,text='＋ Add module',command=self.open_catalogue).pack(side='left')
        ttk.Button(actions,text='Randomise',command=lambda:(self.root_rack.select_owner(self) if hasattr(self,'root_rack') else None,self.root_rack.random_now(False) if hasattr(self,'root_rack') else self.random_now(False))).pack(side='left',padx=4)
        panel.grid(row=0,column=0,sticky='nw',padx=7,pady=7);self.empty=panel

    def paint_selection(self):
        for fid,(shell,_,__) in self.card_parts.items():
            shell.configure(highlightthickness=2 if fid in self.selected_fx else 1,highlightbackground=self.app.ui_chrome['accent'] if fid in self.selected_fx else shell.accent)

    def select_card(self,fxid,multiple=False):
        if not multiple:self.selected_fx={fxid}
        elif fxid in self.selected_fx:self.selected_fx.discard(fxid)
        else:self.selected_fx.add(fxid)
        self.paint_selection()
        root=getattr(self,'root_rack',None)
        if root is not None:root.refresh_toolbar_state()

    def insertion_index_at(self,x_root,y_root):
        rack,owner=self.target()
        if rack is None:return None
        try:
            x0=self.winfo_rootx();y0=self.winfo_rooty();x1=x0+self.winfo_width();y1=y0+self.winfo_height()
            if not (x0<=x_root<=x1 and y0<=y_root<=y1):return None
        except tk.TclError:return None
        if not rack:return 0
        best=None
        for index,fx in enumerate(rack):
            parts=self.card_parts.get(fx.id)
            if not parts:continue
            shell=parts[0]
            try:
                sx=shell.winfo_rootx();sy=shell.winfo_rooty();sw=shell.winfo_width();sh=shell.winfo_height();cx=sx+sw/2;cy=sy+sh/2
            except tk.TclError:continue
            dist=(x_root-cx)**2+(y_root-cy)**2
            candidate=index if (y_root<cy or (abs(y_root-cy)<sh*.45 and x_root<cx)) else index+1
            if best is None or dist<best[0]:best=(dist,candidate)
        return len(rack) if best is None else max(0,min(len(rack),best[1]))

    def reorder_module(self,context,fxid,direction):
        current=context.resolve(self,fxid)
        if current is None:return
        rack,fx,owner=current;i=rack.index(fx);other=i+direction
        if not 0<=other<len(rack):return
        if fx.extra.get('locked') or rack[other].extra.get('locked'):
            return self.app.update_status('Unlock affected modules before changing their order.')
        self.run_edit(context,'Reorder module',lambda r,f,o:move_module(r,fxid,direction),fxid)

    def vary_module(self,context,fxid):
        from omne_randomise import vary_rack
        seed=int(self.app.project.extra.get('rack_seed',730))+1
        def vary(rack,fx,owner):
            vary_rack(rack,seed=seed,variation=float(self.mutation_variation.get())/100,selected={fxid});self.app.project.extra['rack_seed']=seed
        self.run_edit(context,'Vary module',vary,fxid)

    def module_menu(self,rack,fx,anchor):
        context=RackContext.capture(self);menu=tk.Menu(self,tearoff=False)
        menu.add_command(label='Delete',command=lambda:self.delete_module(context,fx.id))
        menu.add_command(label='Duplicate',command=lambda:self.duplicate_module(context,fx.id))
        menu.add_command(label='Unlock' if fx.extra.get('locked') else 'Lock',command=lambda:self.run_edit(context,'Module lock',lambda r,f,o:f.extra.__setitem__('locked',not f.extra.get('locked',False)),fx.id,True))
        menu.add_command(label='Save to Library…',command=lambda:self.keep_module(fx))
        indices=[i for i,f in enumerate(rack) if f.id in self.selected_fx]
        if len(indices)>=2 and indices==list(range(min(indices),max(indices)+1)):menu.add_command(label='Group selected modules',command=self.group_selected)
        if fx.kind=='module':menu.add_command(label='Ungroup · keep motion',command=lambda:self.ungroup_module(context,fx.id))
        menu.add_separator()
        menu.add_command(label='Move earlier',command=lambda:self.reorder_module(context,fx.id,-1))
        menu.add_command(label='Move later',command=lambda:self.reorder_module(context,fx.id,1))
        menu.add_command(label='Controls',command=lambda:self.open_parameter(fx.id))
        if fx.kind=='module':menu.add_command(label='Edit Group…',command=lambda:self.edit_group_details(fx.id))
        self.app.popup_menu(menu,anchor)

    def duplicate_module(self,context,fxid):
        from module_engine import reidentify
        def duplicate(rack,fx,owner):
            copied=reidentify(fx);trial=rack[:];trial.insert(rack.index(fx)+1,copied);compile_rack(trial);rack[:]=trial
        self.run_edit(context,'Duplicate module',duplicate,fxid,True)

    def delete_module(self,context,fxid):
        ok=self.run_edit(context,'Delete module',lambda rack,fx,owner:rack.remove(fx),fxid)
        if ok:
            self.selected_fx.discard(fxid)
            self.focus_set()
        return ok

    def ungroup_module(self,context,fxid):
        self.run_edit(context,'Ungroup module',lambda rack,fx,owner:ungroup(rack,fxid),fxid)

    def group_selected(self):
        rack,owner=self.target()
        if rack is None:return self.app.update_status('Choose a rack before grouping modules.')
        ids=[fx.id for fx in rack if fx.id in self.selected_fx]
        if len(ids)<2:return self.app.update_status('Select two or more adjacent modules, then Group.')
        context=RackContext.capture(self);created=[]
        def apply(r,fx,o):created.append(group_selected_now(r,ids))
        try:ok=self.run_edit(context,'Group modules',apply)
        except ValueError as exc:return self.app.update_status(str(exc))
        if ok and created:
            self.selected_fx.clear();self.selected_fx.add(created[0].id);self.refresh(True)
            self.app.update_status('Grouped '+str(len(ids))+' modules · double-click the name to rename; Edit Group… changes the front panel.')
        return bool(created)
    def edit_group_details(self,fxid):
        rack,owner=self.target();fx=next((f for f in rack or [] if f.id==fxid),None)
        if fx is None or fx.kind!='module':return
        self.app.open_module_builder(self,rack,group_fx=fx) if hasattr(self.app,'open_module_builder') else __import__('playable_rack').ModuleBuilder(self.app,self,rack,group_fx=fx)
    def inline_rename_group(self,fxid):
        rack,owner=self.target();fx=next((f for f in rack or [] if f.id==fxid),None)
        if fx is None or fx.kind!='module' or fx.extra.get('locked'):return self.app.update_status('Unlock the group before renaming it.')
        parts=self.card_parts.get(fxid)
        if not parts:return
        shell=parts[0];label=getattr(shell,'name_label',None)
        if label is None or getattr(shell,'rename_entry',None):return
        value=tk.StringVar(value=module_label(fx));entry=ttk.Entry(shell,textvariable=value);shell.rename_entry=entry;label.pack_forget();entry.pack(fill='x',padx=6,pady=1,before=shell.middle);entry.focus_set();entry.selection_range(0,'end')
        done={'value':False}
        def finish(commit=True):
            if done['value']:return 'break'
            done['value']=True;name=' '.join(value.get().strip().split())
            if commit:
                if not name or len(name)>80:
                    done['value']=False;self.app.update_status('Group names must be 1–80 characters.');entry.focus_set();return 'break'
                context=RackContext.capture(self)
                self.run_edit(context,'Rename group',lambda r,f,o:(f.extra.__setitem__('name',name),f.extra.__setitem__('generated_name',False)),fxid)
                label.configure(text=name)
            try:entry.destroy()
            except tk.TclError:pass
            shell.rename_entry=None;label.pack(fill='x',before=shell.middle);return 'break'
        entry.bind('<Return>',lambda e:finish(True));entry.bind('<KP_Enter>',lambda e:finish(True));entry.bind('<Escape>',lambda e:finish(False));entry.bind('<FocusOut>',lambda e:finish(True))

    def close_tray(self,fxid=None,key=None):
        closed_id=fxid or (self.tray_key[0] if self.tray_mode=='parameter' and self.tray_key else None)
        root=getattr(self,'root_rack',None)
        if fxid is not None:
            tray=self.companions.get((fxid,key))
            if tray is not None and tray.winfo_exists():tray.pack_forget()
            if root is not None and hasattr(root,'contextual'):root.contextual.forget(('react',self.adapter.key,fxid,key))
            if tray is not self.tray:self.relayout();return
        if self.tray is not None and self.tray.winfo_exists():
            self.tray.pack_forget()
            if root is not None and self.tray_key:
                root.contextual.forget(('react',self.adapter.key,*self.tray_key))
        self.tray_mode=None;self.tray_key=None;self.tray=None
        # Closing a contextual surface never seeks the rack. The performer's
        # current scroll position is part of their working context.
        self.relayout()

    def reveal_settled(self,widget):
        """Reveal a rack peer after Tk has settled nested canvas geometry.

        The immediate reveal keeps interaction responsive; queued reveals make the
        result deterministic after configure bursts without synchronous geometry
        flushing or unmapping the owner subtree.
        """
        def reveal():
            try:
                if widget is None or not widget.winfo_exists():return
                self.relayout();self.scroll.reveal(widget)
                root=getattr(self,'root_rack',None)
                if root is not None:
                    root.relayout();root.scroll.reveal(widget)
            except tk.TclError:pass
        reveal();self.after_idle(reveal);self.after(70,reveal)

    def reveal_module(self,fxid=None):
        parts=self.card_parts.get(fxid) or next(iter(self.card_parts.values()),None)
        if parts is None:return
        self.scroll.reveal(parts[0])
        if hasattr(self,'root_rack') and not getattr(self.app,'inline_rack_mode',False):self.root_rack.scroll.reveal(parts[0])

    def render_tray(self):
        # UX4 retired the bottom Add dock. Add now focuses the stable Module Library panel.
        if self.tray_mode=='catalogue':self.app.show_module_library()

    def open_catalogue(self):
        root=getattr(self,'root_rack',None)
        if root is not None:root.select_owner(self)
        rack,owner=self.target()
        if rack is None:return self.app.update_status('Choose Whole picture, a voice, or a clip to add modules.')
        self.tray_mode=None;self.tray_key=None;self.tray=None
        self.app.show_module_library()
        if root is not None:root._sync_selected(self)

    def react_parameter(self,fxid,key):
        rack,owner=self.target();fx=next((f for f in rack or [] if f.id==fxid),None)
        if fx is None:return
        if fx.params[key].mode!='react':
            from live_parameter_controls import initial_reaction_changes,available_reaction_sources
            context=RackContext.capture(self)
            self.run_edit(context,'React '+module_label(fx),lambda r,f,o:update_parameter(f.params[key],initial_reaction_changes(f.params[key],available=available_reaction_sources(self.app))),fxid)
        self.open_parameter(fxid,key)

    def open_parameter(self,fxid,key=None):
        rack,owner=self.target();fx=next((f for f in rack or [] if f.id==fxid),None)
        if fx is None:return
        if not fx.params and fx.kind!='module':return
        key=key or next(iter(fx.params),None);cache=(fxid,key);root=getattr(self,'root_rack',None)
        context_key=('react',self.adapter.key,fxid,key) if hasattr(self,'adapter') else ('react',id(self),fxid,key)
        if self.tray_mode=='parameter' and self.tray_key==cache and self.tray is not None and self.tray.winfo_manager():
            try:self.tray.focus_set()
            except tk.TclError:pass
            return
        if root is not None:root.contextual.dismiss()
        self.select_card(fxid);self.tray_mode='parameter';self.tray_key=cache
        if cache not in self.companions:
            from rack_trays import RackParameterTray, RackGroupTray
            self.companions[cache]=(RackGroupTray if fx.kind=='module' else RackParameterTray)(self.card_parts[fxid][0].companion_host,self,fx,key)
        self.tray=self.companions[cache];self.tray.pack(fill='both',expand=True)
        if root is not None:
            anchor=self.card_controls.get(fxid,{}).get('react')
            root.contextual.show(context_key,self.tray,lambda:self.close_tray(fxid,key),anchors=(anchor,))
        self.relayout();self.reveal_settled(self.tray)
        if root is not None:root._sync_selected(self)

    def module_details(self,rack,fx,owner):
        current,_=self.target()
        if current is rack:self.open_parameter(fx.id)

    def relayout(self):
        from rack_layout import positions,LayoutPolicy
        parent=getattr(self,'cards_parent',None)
        if parent is None or not parent.winfo_exists():return
        if getattr(self,'_rack_relayout_active',False):return
        self._rack_relayout_active=True
        policy=getattr(self,'layout_override',None) or getattr(getattr(self,'root_rack',None),'module_layout',LayoutPolicy(rows='2'))
        width=max(100,getattr(self,'scroll',parent).canvas.winfo_width() if hasattr(getattr(self,'scroll',None),'canvas') else parent.winfo_width())
        # Companions are true peer devices. Opening React inserts a neighbouring
        # bay instead of stretching/reconstructing the module itself.
        slots=[]
        for fid in self.card_parts:
            slots.append(('module',fid))
            host=self.card_parts[fid][0].companion_host
            if host.winfo_children() and any(child.winfo_manager() for child in host.winfo_children()):slots.append(('companion',fid))
        bus=getattr(self,'rack_react_frame',None)
        if bus is not None and bus.winfo_exists() and getattr(self,'rack_react_visible',False):slots.append(('bus','layer-react'))
        text_scale=max(1.,min(2.,float(self.tk.call('tk','scaling'))/1.333))
        cols,cell_width,places=positions(width,slots,policy,minimum=round(198*text_scale));self.card_columns=cols
        if getattr(self,'_rack_column_count',None)!=cols:
            previous=max(12,getattr(self,'_rack_column_count',0)+1,cols+1)
            for col in range(previous):parent.columnconfigure(col,weight=0,uniform='')
            parent.columnconfigure(cols,weight=1);self._rack_column_count=cols
        max_height=48
        slot_places={key:(row,col) for key,row,col in places}
        for fid,(shell,body,button) in self.card_parts.items():
            row,col=slot_places[('module',fid)]
            module_width=max(round(205*text_scale),min(round(232*text_scale),cell_width));slot=(row,col)
            if getattr(shell,'_rack_slot',None)!=slot or not shell.winfo_manager():
                shell.grid(row=row,column=col,sticky='nw',padx=3,pady=3);shell._rack_slot=slot
            if getattr(shell,'_rack_width',None)!=module_width:
                shell.configure(width=module_width);shell._rack_width=module_width
            root=getattr(self,'root_rack',None)
            available_h=max(1,self.scroll.canvas.winfo_height() if getattr(self.app,'inline_rack_mode',False) else getattr(root,'scroll',self.scroll).canvas.winfo_height() if root is not None else self.scroll.canvas.winfo_height())
            # Expanded is the invariant. Only an unusually shallow rack falls back
            # to the principal controls so the instrument never becomes unusable.
            normal_height=(sum(w.winfo_reqheight()+4 for w in shell.pack_slaves() if w is not body)
                           +shell.principal_controls.winfo_reqheight()+shell.extra_controls.winfo_reqheight()+12)
            auto_compact=available_h<max(235,normal_height+8)
            expanded=not auto_compact and policy.detail!='Collapsed'
            if not body.winfo_manager():body.pack(fill='both',expand=True,before=shell.footer)
            if expanded:
                if not shell.extra_controls.winfo_manager():shell.extra_controls.pack(fill='x',pady=(3,0))
            elif shell.extra_controls.winfo_manager():shell.extra_controls.pack_forget()
            # The patch strip is always present. React, Details and chain order are
            # performance controls, not an advanced panel.
            if not shell.footer.winfo_manager():shell.footer.pack(fill='x')
            button.configure(text='▾' if expanded else '▸')
            height=sum(w.winfo_reqheight()+4 for w in shell.pack_slaves())+6
            target_height=max(round(236*min(1.15,text_scale)),height)
            if getattr(shell,'_rack_height',None)!=target_height:
                shell.configure(height=target_height);shell._rack_height=target_height
            max_height=max(max_height,height)
            host=shell.companion_host
            if ('companion',fid) in slot_places:
                cr,cc=slot_places[('companion',fid)];host_slot=(cr,cc);host_width=module_width;host_height=target_height
                if getattr(host,'_rack_slot',None)!=host_slot or not host.winfo_manager():
                    host.grid(row=cr,column=cc,sticky='nw',padx=3,pady=3);host._rack_slot=host_slot
                if getattr(host,'_rack_size',None)!=(host_width,host_height):
                    host.configure(width=host_width,height=host_height);host._rack_size=(host_width,host_height)
                # Never let a large companion request widen its grid column. React
                # is physically the same chassis size as the source module.
                host.pack_propagate(False)
                max_height=max(max_height,host.winfo_reqheight())
            elif host.winfo_manager():host.grid_remove()
        if ('bus','layer-react') in slot_places:
            br,bc=slot_places[('bus','layer-react')];bus_slot=(br,bc);bus_width=max(205,min(232,cell_width))
            if getattr(bus,'_rack_slot',None)!=bus_slot or not bus.winfo_manager():bus.grid(row=br,column=bc,sticky='nw',padx=3,pady=3);bus._rack_slot=bus_slot
            if getattr(bus,'_rack_size',None)!=(bus_width,138):bus.configure(width=bus_width,height=138);bus._rack_size=(bus_width,138)
            bus.pack_propagate(False)
        if hasattr(getattr(self,'scroll',None),'set_policy'):
            rows=math.ceil(max(1,len(places))/max(1,cols));visible=rows
            companion_open=any(tray.winfo_manager() for tray in getattr(self,'companions',{}).values())
            root=getattr(self,'root_rack',None);workstation=bool(root and getattr(root,'_mounted_owner',None) is self)
            allowance=10 if workstation else 65
            available=max(190 if workstation else (180 if companion_open else 90),getattr(root,'scroll',self.scroll).canvas.winfo_height()-allowance)
            natural=max_height*visible+8
            # The selected rack is a workstation, not a content-sized strip. Keep
            # the backplane stable and use its negative space instead of repeatedly
            # shrinking/growing the native canvas as modules or trays appear.
            self.scroll.set_policy(policy,available if workstation else min(available,natural))
            if hasattr(self,'remaining'):
                self.remaining.set('')
                if self.remaining_label.winfo_manager():self.remaining_label.grid_remove()
        self.selected_fx.intersection_update(self.card_parts)
        if not hasattr(self,'add_tile') or not self.add_tile.winfo_exists():self.add_tile=ttk.Button(parent,text='＋  ADD MODULE',command=self.open_catalogue)
        next_slot=len(places)
        if self.card_parts and next_slot<cols:
            tile_slot=(0,next_slot)
            if getattr(self.add_tile,'_rack_slot',None)!=tile_slot or not self.add_tile.winfo_manager():self.add_tile.grid(row=0,column=next_slot,sticky='nw',padx=7,pady=7,ipadx=18,ipady=18);self.add_tile._rack_slot=tile_slot
        elif self.add_tile.winfo_manager():self.add_tile.grid_remove()
        self._rack_relayout_active=False
    def inspect_group(self,parent,fx):
        from ui_chrome import CollapsibleSection
        from module_engine import children
        section=CollapsibleSection(parent,'Inside group',expanded=False,on_toggle=lambda value:self.relayout());section.pack(fill='x')
        def show(host,group,depth=0):
            for child in children(group):
                label=('  '*depth)+module_label(child)+(' · bypassed' if not child.enabled else '')
                ttk.Label(host,text=label,style='Muted.TLabel').pack(anchor='w')
                if child.kind=='module':show(host,child,depth+1)
                else:
                    for key,param in child.params.items():ttk.Label(host,text=('  '*(depth+1))+f'{key}: {param.value:g} · {param.mode}',style='Muted.TLabel').pack(anchor='w')
        show(section.body,fx)
        ttk.Button(section.body,text='Ungroup · keep motion',command=lambda:self.ungroup_module(RackContext.capture(self),fx.id)).pack(anchor='w')

    def drag_start(self,fxid,event):
        from input_gestures import claim_input
        claim_input(self.app,self)
        self.dragging=(RackContext.capture(self),fxid);self.drop_id=None;self.drop_marker=None
    def drag_motion(self,event):
        if not getattr(self,'dragging',None):return
        y=event.y_root;x=event.x_root;self.drop_id=None
        if getattr(self,'drop_marker',None):self.drop_marker.destroy();self.drop_marker=None
        for fid,(shell,body,button) in self.card_parts.items():
            inside=shell.winfo_rootx()<=x<shell.winfo_rootx()+shell.winfo_width() and shell.winfo_rooty()<=y<shell.winfo_rooty()+shell.winfo_height()
            if inside:
                self.drop_id=fid;self.drop_marker=tk.Frame(shell,height=3,bg=self.app.ui_chrome['accent']);self.drop_marker.place(x=0,y=0,relwidth=1)
            shell.configure(highlightthickness=3 if inside else 1,highlightbackground=self.app.ui_chrome['accent'])
    def finish_input(self,*,cancel=False):
        from input_gestures import release_input
        release_input(self.app,self);self.dragging=None;self.drop_id=None
        if getattr(self,'drop_marker',None):
            if self.drop_marker.winfo_exists():self.drop_marker.destroy()
            self.drop_marker=None
        if self.winfo_exists():self.paint_selection()
        return 'break'
    def drag_end(self,event):
        from input_gestures import release_input
        release_input(self.app,self)
        drag=getattr(self,'dragging',None);self.dragging=None
        if getattr(self,'drop_marker',None):self.drop_marker.destroy();self.drop_marker=None
        if not drag:return
        context,fid=drag;target=getattr(self,'drop_id',None);resolved=context.resolve(self,fid)
        if resolved and target and target!=fid:
            rack,fx,owner=resolved;start=rack.index(fx);end=next((i for i,f in enumerate(rack) if f.id==target),start)
            if any(f.extra.get('locked') for f in rack[min(start,end):max(start,end)+1]):self.app.update_status('Unlock affected modules before changing their order.')
            else:self.run_edit(context,'Reorder module',lambda r,f,o:r.insert(end-(1 if start<end else 0),r.pop(r.index(f))),fid)
        self.paint_selection()

class OwnerCell(_OwnerRack):
    """A retained deck whose edit authority is independent of global selection."""
    def __init__(self,parent,root,adapter):
        from rack_layout import RackArea
        ttk.Frame.__init__(self,parent,padding=4,relief='groove',borderwidth=1)
        self.root_rack=root;self.app=root.app;self.adapter=adapter;self.frozen=adapter.scope=='Clip' and getattr(adapter,'queue_state',adapter.parent) is not adapter.parent;self.scope=tk.StringVar(value=adapter.scope);self.target_name=tk.StringVar(value=adapter.title)
        self.rows=[];self.key=None;self.owner=adapter.owner;self.history_layer=self.history_proxy=self.history_span=None
        self.selected_fx=set();self.card_modes=root.card_modes;self.card_parts={};self.card_controls={};self.cards_parent=None;self.rendered_cards=[];self.companions={}
        self.tray_mode=self.tray_key=self.tray=None;self.layout_job=None;self.layout_override=None
        self.layout_override=root.saved_owner_layouts.get(self.preference_key())
        self.mutation_variation=root.mutation_variation;self.summary=tk.StringVar();self.remaining=tk.StringVar();self.state_text=tk.StringVar()
        self.columnconfigure(0,weight=1);self.rowconfigure(2,weight=1)
        from responsive_controls import PriorityToolbar,OverflowAdapter
        self.header=PriorityToolbar(self,gap=3);self.header.grid(row=0,column=0,sticky='ew')
        self.header.add_action(adapter.title,lambda:root.select_owner(self),priority=0,pinned=True)
        self.layout_button=None
        if adapter.scope=='Layer':self.header.add_action('React layer',self.toggle_rack_react,priority=12)
        self.collapsed=False;self.header.add_action('▾',self.toggle,priority=2)
        if hasattr(adapter.owner,'enabled'):
            self.enabled=tk.BooleanVar(value=adapter.owner.enabled)
            self.header.add(ttk.Checkbutton(self.header,text='On',variable=self.enabled,command=lambda:self.owner_edit('Owner bypass',lambda o:setattr(o,'enabled',self.enabled.get()))),priority=3)
        self.state_label=ttk.Label(self,textvariable=self.state_text,style='Muted.TLabel',wraplength=400);self.state_label.grid(row=1,column=0,sticky='ew')
        self.content=ttk.Frame(self);self.content.grid(row=2,column=0,sticky='nsew');self.content.columnconfigure(0,weight=1);self.content.rowconfigure(1,weight=1)
        self.rack_react_frame=None;self.rack_react_visible=False
        self.main=ttk.Frame(self.content);self.main.grid(row=0,column=0,sticky='ew');self.main_signature=None
        self.scroll=RackArea(self.content,self.app,height=180);self.scroll.grid(row=1,column=0,sticky='nsew');self.body=self.scroll.body
        self.scroll.canvas.bind('<Configure>',self.resized,add='+')
        self.remaining_label=ttk.Label(self.content,textvariable=self.remaining,style='Muted.TLabel');self.remaining_label.grid(row=2,column=0,sticky='ew')
        self.clip_host=ttk.Frame(self.content);self.clip_host.grid(row=3,column=0,sticky='ew');self.clip_cells={}
        self.bind('<Destroy>',self.cleanup,add='+')
        self.refresh(True)
    def preference_key(self):return '/'.join((self.adapter.project.id,self.adapter.scope,self.adapter.owner.id))
    def target(self):return self.adapter.target()
    def activate_current(self):
        if not self.frozen:return self
        if self.adapter.target()[0] is None:
            self.app.update_status('The current queue version changed. Select its clip again.');return None
        parent=self.adapter.parent;clip_id=self.adapter.owner.id;root=self.root_rack
        if not self.app.can_edit(parent) or not self.app.can_edit(self.adapter.owner):return None
        from queue_policies import activate_visual_state
        self.app.transaction('Edit current clip; cancel prepared cycle',lambda:activate_visual_state(parent,self.app.playhead))
        root.refresh(True)
        return next((cell for cell in root.all_cells() if cell.adapter.scope=='Clip' and cell.adapter.owner.id==clip_id and not cell.frozen),None)
    def open_parameter(self,fxid,key=None):
        if self.frozen:
            cell=self.activate_current()
            if cell:return cell.open_parameter(fxid,key)
            return
        return super().open_parameter(fxid,key)
    def open_catalogue(self):
        if self.frozen:
            cell=self.activate_current()
            if cell:return cell.open_catalogue()
            return
        return super().open_catalogue()
    def run_edit(self,context,label,operation,module_id=None,allow_locked=False):
        if self.frozen:
            self.app.update_status('Choose Edit current clip to replace the prepared cycle before changing this treatment.');return False
        return super().run_edit(context,label,operation,module_id,allow_locked)
    def owner_edit(self,label,operation):
        context=RackContext.capture(self)
        return self.run_edit(context,label,lambda rack,fx,owner:operation(owner))
    def local_random(self,mutate):
        if self.frozen:
            self.app.update_status('Choose Edit current clip before randomising the current treatment.');return
        self.root_rack.select_owner(self);self.root_rack.random_now(mutate)
    def select_card(self,fxid,multiple=False):
        self.root_rack.select_owner(self);super().select_card(fxid,multiple);self.relayout();self.root_rack._sync_selected(self)
    def toggle(self):
        self.collapsed=not self.collapsed
        if self.collapsed:self.content.grid_remove()
        else:self.content.grid()
        self.root_rack.relayout()
    def layout_menu(self):
        from rack_layout import policy_menu
        policy=self.layout_override or self.root_rack.module_layout
        menu=policy_menu(self,policy,self.set_layout)
        menu.add_separator();menu.add_command(label=('✓ ' if self.layout_override is None else '')+'Follow rack defaults',command=lambda:self.set_layout(None))
        self.app.popup_menu(menu,self.header)
    def set_layout(self,policy):
        # Owner-specific layout policies were retired. One Grid toggle controls the
        # whole selected rack so nested owners cannot contradict the workspace.
        self.layout_override=None;self.root_rack.saved_owner_layouts.pop(self.preference_key(),None)
        self.root_rack.module_grid.set(getattr(policy,'flow','Wrap')!='Single strip' if policy is not None else True)
        self.root_rack.apply_grid_mode()
    def pin_parameter(self,fxid,key,pinned):
        self.pinned=getattr(self,'pinned',set())
        if pinned:self.pinned.add((fxid,key))
        else:self.pinned.discard((fxid,key))
        self.root_rack.relayout()
    def rack_reaction_targets(self):
        rack,owner=self.target();out=[]
        for fx in rack or []:
            if not fx.enabled or fx.extra.get('locked'):continue
            # Principal amount/macro controls are musically useful; topology stays stable.
            for key,param in fx.params.items():
                if key=='amount' or fx.kind=='module':out.append((fx,key,param))
        return out
    def toggle_rack_react(self):
        """Show the layer reaction macro as a real rack-side bus device."""
        self.root_rack.select_owner(self)
        if self.rack_react_frame is not None and self.rack_react_frame.winfo_exists():
            self.rack_react_visible=not self.rack_react_visible
            if not self.rack_react_visible:self.rack_react_frame.grid_remove()
            self.relayout();return
        host=self.cards_parent;self.rack_react_visible=True
        c=self.app.ui_chrome;bg='#18373A';fg='#E8F4E7';accent='#72D7B8'
        box=tk.Frame(host,bg=bg,highlightthickness=2,highlightbackground=accent,bd=0);self.rack_react_frame=box
        head=tk.Frame(box,bg=bg,padx=6,pady=4);head.pack(fill='x')
        lamp=tk.Canvas(head,width=12,height=12,bg=bg,highlightthickness=0);lamp.pack(side='left');lamp.create_oval(2,2,10,10,fill=accent,outline=accent)
        tk.Label(head,text='LAYER REACT BUS',bg=bg,fg=fg,font=('TkDefaultFont',9,'bold')).pack(side='left',padx=5)
        self.rack_react_enabled=tk.BooleanVar(value=True);tk.Checkbutton(head,text='ON',variable=self.rack_react_enabled,bg=bg,fg=fg,selectcolor=bg,activebackground=bg,activeforeground=fg,command=self.apply_rack_react).pack(side='right')
        bands=tk.Frame(box,bg=bg,padx=6);bands.pack(fill='x');self.rack_react_band=tk.StringVar(value='full')
        for value,label in [('full','FULL'),('bass','BASS'),('mid','MID'),('treble','HIGH')]:tk.Radiobutton(bands,text=label,variable=self.rack_react_band,value=value,bg=bg,fg=fg,selectcolor=bg,activebackground=bg,activeforeground=fg,indicatoron=False,bd=1,command=self.apply_rack_react).pack(side='left',fill='x',expand=True,padx=1)
        row=tk.Frame(box,bg=bg,padx=7,pady=5);row.pack(fill='x');tk.Label(row,text='DEPTH',bg=bg,fg=fg).pack(side='left')
        self.rack_react_depth=tk.DoubleVar(value=1.0);scale=tk.Scale(row,from_=-1,to=1,resolution=.01,showvalue=False,orient='horizontal',variable=self.rack_react_depth,command=lambda v:self.apply_rack_react(),bg=bg,fg=fg,troughcolor=c['field_bg'],activebackground=accent,highlightthickness=0,bd=0,length=105);scale.pack(side='left',fill='x',expand=True,padx=5)
        shape=tk.Frame(box,bg=bg,padx=6,pady=0);shape.pack(fill='x',pady=(0,5));ttk.Button(shape,text='Punch',width=6,command=lambda:self.set_rack_react_shape(.04,.16)).pack(side='left');ttk.Button(shape,text='Smooth',width=7,command=lambda:self.set_rack_react_shape(.18,.65)).pack(side='left',padx=3);ttk.Button(shape,text='×',width=2,command=self.toggle_rack_react).pack(side='right')
        self.rack_react_attack=.018;self.rack_react_release=.14
        self.apply_rack_react();self.relayout()
    def set_rack_react_shape(self,attack,release):
        self.rack_react_attack=attack;self.rack_react_release=release;self.apply_rack_react()
    def apply_rack_react(self):
        targets=self.rack_reaction_targets()
        if not targets:return self.app.update_status('This layer has no unlocked principal module controls to react.')
        enabled=bool(self.rack_react_enabled.get());band=self.rack_react_band.get();depth=float(self.rack_react_depth.get())
        def apply():
            for fx,key,param in targets:
                if enabled:
                    param.mode='react';param.source='reaction_mix';param.react_band=band;param.react_amount=depth;param.attack=self.rack_react_attack;param.release=self.rack_react_release;param.threshold=.01;param.extra['react_full_range']=True
                elif param.mode=='react':param.mode='static'
            if hasattr(self.owner,'manual'):self.owner.manual=True
        self.app.transaction('Layer reaction macro',apply);self.app.update_status(f'Layer React · {len(targets)} controls · {band} · {depth:+.2f}')

    def refresh(self,force=False):
        if self.adapter.scope=='Layer':
            layer=self.adapter.owner
            span=next((span for span in reversed(layer.extra.get('treatment_history',[])) if span['start']<=self.app.playhead<span['end']),None) if self.app.reviewing else None
            if span is not self.history_span:
                self.flush_history()
                from instrument_model import style_from
                self.history_span=span;self.history_layer=layer if span else None;self.history_proxy=style_from(span['style'],layer) if span else None;self.adapter.edit_owner=self.history_proxy
        rack,owner=self.target()
        if rack is None:return
        self.owner=owner;self.state_text.set(self.adapter.state()+(' · history' if self.history_span else ''))
        if hasattr(self,'enabled'):self.enabled.set(owner.enabled)
        if self.frozen:
            if not getattr(self,'frozen_notice',None):
                self.frozen_notice=ttk.Frame(self.body,padding=5);self.frozen_notice.pack(fill='x')
                ttk.Label(self.frozen_notice,text='Current clip · next cycle prepared',style='Muted.TLabel').pack(anchor='w')
                ttk.Button(self.frozen_notice,text='Edit current clip · cancel prepared cycle',command=self.activate_current).pack(anchor='w')
                for fx in rack:
                    ttk.Button(self.frozen_notice,text=module_label(fx)+' · controls',command=lambda fid=fx.id:self.open_parameter(fid)).pack(anchor='w')
            return
        self.refresh_main(owner)
        if rack and getattr(self,'empty',None):self.empty.destroy();self.empty=None
        render_key=tuple((fx.id,fx.kind,fx.enabled,bool(fx.extra.get('locked')),tuple((key,id(param)) for key,param in fx.params.items())) for fx in rack)
        # Playback refreshes happen many times per second.  Reflowing identical Tk
        # geometry on every tick was the principal source of visible rack flicker.
        if force or render_key!=getattr(self,'_rack_render_key',None):
            self._rack_render_key=render_key
            self.rack(self.body,rack,owner)
        for row in self.rows:
            if row.winfo_exists():row.refresh()
        for tray in self.companions.values():
            if not tray.winfo_exists():continue
            if hasattr(tray,'pending_fields'):tray.sync_fields(tray.pending_fields())
            elif hasattr(tray,'refresh_view'):tray.refresh_view()
        if not rack:self.show_empty_rack()
        elif getattr(self,'empty',None):self.empty.destroy();self.empty=None
    def refresh_main(self,owner):
        from ui_chrome import CollapsibleSection
        from sequencer_model import adjustment_parameters
        if self.adapter.scope=='Master':return
        params=[('Opacity',owner.opacity)]
        if self.adapter.scope=='Clip':params.extend((key.title(),getattr(owner,key)) for key in ('scale','x','y','rotation'))
        defaults=adjustment_parameters();effects=[(key,value) for key,value in owner.effects.items() if value!=defaults.get(key)]
        mask=owner.mask
        signature=(id(owner),tuple((key,id(value)) for key,value in effects),mask.kind)
        if signature==self.main_signature:return
        self.main_signature=signature
        for w in self.main.winfo_children():w.destroy()
        section=CollapsibleSection(self.main,'Main controls'+(f' · {len(effects)} adjustments' if effects else '')+(' · mask '+mask.kind if mask.kind!='none' else ''),expanded=False,on_toggle=lambda v:self.relayout());section.pack(fill='x')
        context=RackContext.capture(self)
        for key,param in params+[(key.title(),value) for key,value in effects]:
            row=ParameterDial(section.body,self.app,key,param,owner,guard=lambda:context.resolve(self) is not None,select_owner=lambda:self.root_rack.select_owner(self));row.pack(fill='x');self.rows.append(row)
        if mask.kind!='none':
            ttk.Label(section.body,text=f'Mask: {mask.kind} · {mask.width:g} × {mask.height:g} · feather {mask.feather:g}'+(' · inverted' if mask.invert else ''),style='Muted.TLabel').pack(anchor='w')
        ttk.Button(section.body,text='Owner controls…',command=self.owner_details).pack(anchor='w')
    def owner_details(self):
        self.root_rack.select_owner(self)
        return super().owner_details()


class CompactRack(_OwnerRack):
    """All existing owners stay visible; selection only sets action destination."""
    def __init__(self,parent,app):
        self.owner_cells={};self.selected_owner_key=None;self._project=None;self._ready=False;self._mounted_owner=None
        super().__init__(parent,app)
        from rack_layout import RackArea,LayoutPolicy
        from contextual_surface import ContextualSurfaceController
        self.contextual=getattr(app,'contextual_surfaces',None) or ContextualSurfaceController(self.winfo_toplevel())
        self.module_grid=tk.BooleanVar(value=True)
        self.owner_layout=LayoutPolicy();self.module_layout=LayoutPolicy('Grid','Wrap','Expand all','Auto');self.saved_owner_layouts={}
        self.load_layout(app.read_preferences().get('rack_layout',{}))
        self.scroll.destroy();self.scroll=RackArea(self,app);self.scroll.grid(row=2,column=0,sticky='nsew');self.body=self.scroll.body
        self.scope_label.destroy();self.rowconfigure(1,weight=0);self.rowconfigure(2,weight=1);self.rowconfigure(3,weight=0)
        # UX4: Add is a stable workspace panel; no bottom catalogue dock is created.
        from responsive_controls import FlowRow
        self.owner_remaining=ttk.Label(self,text='',style='Muted.TLabel')
        self.body.bind('<Configure>',self.resized,add='+')
        self.special_host=ttk.Frame(self.body);self.owners_host=ttk.Frame(self.body);self.owners_host.pack(fill='both',expand=True)
        self.owners_host.bind('<Configure>',self.resized,add='+');self.special_editor=None
        self._make_toolbar();self._ready=True
    def _make_toolbar(self):
        from responsive_controls import PriorityToolbar,OverflowAdapter
        top=self.grid_slaves(row=0,column=0)[0]
        for child in top.winfo_children():child.destroy()
        # The single common panel header also owns rack actions. No extra title,
        # owner strip or permanent settings row competes with the module faces.
        if hasattr(self.app,'channel_effects_host'):
            host=top
            self.more_button=ttk.Button(host,text='⋯',width=3,command=self.integrated_menu)
            self.more_button.pack(side='right')
        elif hasattr(self.app,'shell'):
            top.destroy();host=self.app.shell.headers['panel.rack']
            self.app.shell.titles['panel.rack'].configure(text='Rack')
            self.more_button=self.app.shell.menus['panel.rack']
        else:host=top
        row=PriorityToolbar(host,gap=3);row.pack(side='left',fill='x',expand=True,padx=4);self.toolbar=row
        row.more_button.configure(text='⋯',width=3)
        self.scope_selector=ttk.Combobox(row,textvariable=self.target_name,state='readonly',width=13)
        self.scope_selector.bind('<<ComboboxSelected>>',self.choose_target)
        if not hasattr(self.app,'channel_effects_host'):
            row.add(self.scope_selector,priority=0,pinned=True,overflow=OverflowAdapter.mirror('<<ComboboxSelected>>'))
        else:
            row.add_action('Mixer FX',lambda:self.app.open_channel_effects('Mix'),priority=30)
            row.add_action('Transition FX',lambda:self.app.open_channel_effects('Transition'),priority=30)
        self.randomise_button=row.add_action('Randomise',self.random_now,priority=0,pinned=True,style='Accent.TButton',width=9)
        mutate=row.add_action('Mutate',lambda:self.random_now(True),priority=0,pinned=True,width=7)
        self.add_button=row.add_action('Add',lambda:self.app.commands.invoke('rack.add-module'),priority=0,pinned=True,width=5)
        self.primary_actions=[self.randomise_button,mutate,self.add_button]
        def fit_actions(toolbar,width,dims):
            compact=sum(size[0] for size in dims.values())+toolbar.gap*max(0,len(dims)-1)>width
            for item in toolbar.items:
                widget=item['widget']
                if widget in self.primary_actions:item['pinned']=not compact
            # Keep the target visible before offering any action on that target.
            if compact:
                add_width=dims.get(self.add_button,(0,0))[0]
                scope_width=dims.get(self.scope_selector,(0,0))[0]
                if scope_width+add_width+toolbar.more_button.winfo_reqwidth()+toolbar.gap*2<=width:
                    next(item for item in toolbar.items if item['widget'] is self.add_button)['pinned']=True
        row.pin_policy=fit_actions
        self.target_name.trace_add('write',lambda *_:self.refresh_toolbar_state())
        self.app.add_tip(self.scope_selector,'Whole picture is the final Programme treatment. Channels and selected clips retain independent racks.')
        self.app.add_tip(self.randomise_button,'Replace unlocked module identities using saved Randomise options. Only explicit module locks preserve structure.')
        self.app.add_tip(mutate,'Vary the existing module parameters with saved strength. Manual values are not mutation locks.')
        self.fx_enabled_var=tk.BooleanVar(value=True)

    def integrated_menu(self):
        menu=tk.Menu(self,tearoff=False)
        self.populate_menu(menu)
        self.app.popup_menu(menu,self.more_button)

    def populate_menu(self,menu):
        menu.add_command(label='Randomise options…',command=lambda:self.app.open_randomise('rack',self.more_button))
        menu.add_command(label='Mutate strength…',command=lambda:self.app.open_randomise('mutate',self.more_button))
        menu.add_separator()
        menu.add_checkbutton(label='Effects enabled',variable=self.fx_enabled_var,command=self.toggle_fx_layer)
        menu.add_checkbutton(label='Grid / wrap modules',variable=self.module_grid,command=self.apply_grid_mode)
        cell=self.selected_cell();rack,owner=cell.target() if cell else (None,None)
        editable=bool(cell and self.app.can_edit(cell.adapter.owner))
        ids=[i for i,f in enumerate(rack or []) if f.id in self.selected_fx]
        if editable and len(ids)>=2 and ids==list(range(min(ids),max(ids)+1)):
            menu.add_command(label='Group selected modules',command=self.group_selected)
        menu.add_command(label='Save treatment to Library…',command=self.app.keep_ingredient)
        menu.add_command(label='Target / routing details…',command=self.owner_details)
        menu.add_separator();menu.add_command(label='Clear modules',command=self.clear_unlocked,state='normal' if editable else 'disabled')


    def apply_grid_mode(self):
        from rack_layout import LayoutPolicy
        self.module_layout=LayoutPolicy('Grid','Wrap' if self.module_grid.get() else 'Single strip','Expand all','Auto' if self.module_grid.get() else '1')
        for cell in self.all_cells():cell.layout_override=None
        self.saved_owner_layouts.clear();self.relayout();self.app.save_preferences()

    def quick_layout(self,name):
        # Compatibility entry point for saved commands/tests from the earlier four
        # layout buttons. The public surface is now one Grid toggle.
        self.module_grid.set(name!='strip');self.apply_grid_mode()

    def _bypass_holder(self):
        cell=self.selected_cell()
        if cell is None:return None,None
        owner=cell.adapter.owner
        return (owner.extra,'rack_bypassed') if hasattr(owner,'extra') else (None,None)

    def fx_enabled(self):
        holder,key=self._bypass_holder();return not bool(holder and holder.get(key,False))

    def toggle_fx_layer(self):
        cell=self.selected_cell()
        if cell is None:return
        owner=cell.adapter.owner;enable=not self.fx_enabled()
        def apply():owner.extra['rack_bypassed']=not enable
        self.app.transaction('Enable effects layer' if enable else 'Bypass effects layer',apply)
        self.refresh_toolbar_state();self.app.refresh_all()

    def clear_unlocked(self):
        cell=self.selected_cell()
        if cell is None:return
        rack,owner=cell.target()
        if rack is None:return
        locked=[item for item in rack if item.extra.get('locked')]
        if locked and not self.app.test_mode:
            from tkinter import messagebox
            if not messagebox.askyesno('Clear module layer',f'Clear all {len(rack)} modules, including {len(locked)} locked module(s)?',parent=self.app):return
        context=RackContext.capture(cell)
        cell.run_edit(context,'Clear module layer',lambda r,fx,o:r.clear(),allow_locked=True)
        self.refresh(True)

    def refresh_toolbar_state(self):
        if hasattr(self,'fx_enabled_var'):
            try:self.fx_enabled_var.set(self.fx_enabled())
            except tk.TclError:pass

    def target(self):
        if not self._ready:return super().target()
        if self.scope.get() not in ('Master','Layer','Clip'):return None,None
        cell=self.selected_cell()
        return cell.target() if cell and not cell.frozen else (None,None)
    def selected_cell(self):
        key=self.selected_owner_key
        if not key or key[0]!=self.scope.get():return None
        if key in self.owner_cells:return self.owner_cells[key]
        for parent in self.owner_cells.values():
            if key in parent.clip_cells:return parent.clip_cells[key]
        return None
    def select_owner(self,cell):
        changed=self.selected_owner_key!=cell.adapter.key
        self.selected_owner_key=cell.adapter.key;self.scope.set(cell.scope.get())
        if cell.scope.get()=='Layer':self.app.selected_layer_id=cell.adapter.owner.id
        elif cell.scope.get()=='Clip':
            self.app.selected_layer_id=cell.adapter.parent.id;self.app.selected_clip_id=cell.adapter.owner.id
        self.target_name.set(cell.adapter.title if cell.scope.get()!='Clip' else 'Selected clip');self._sync_selected(cell)
        if changed:
            self.refresh_navigation();self.relayout();self.scroll.reveal(cell)
    def _sync_selected(self,cell):
        self.owner=cell.owner;self.selected_fx=cell.selected_fx
        for name in ('card_parts','card_controls','rendered_cards','cards_parent','rows','tray','tray_mode','tray_key','companions','history_layer','history_span','history_proxy'):
            setattr(self,name,getattr(cell,name))
        self.scope_status.set(cell.adapter.state())
    def refresh(self,force=False):
        if not self._ready:return
        from rack_owners import OwnerRackAdapter
        p=self.app.project
        if self._project is not p:
            selections={key:set(cell.selected_fx) for key,cell in self.owner_cells.items()}
            for cell in self.owner_cells.values():cell.destroy()
            self.owner_cells={};self._project=p
        else:selections={}
        owners=[OwnerRackAdapter(self.app,p,p,'Master')]+[OwnerRackAdapter(self.app,p,l,'Layer') for l in p.layers]
        current_keys={adapter.key for adapter in owners}
        for key,cell in list(self.owner_cells.items()):
            if key not in current_keys:cell.destroy();del self.owner_cells[key]
        layer,clip=self.app.get_edit_target()
        for adapter in owners:
            cell=self.owner_cells.get(adapter.key)
            if cell is None:
                cell=OwnerCell(self.app.queue_content if getattr(self.app,'inline_rack_mode',False) else self.owners_host,self,adapter);cell.selected_fx=selections.get(adapter.key,set());self.owner_cells[adapter.key]=cell
            else:cell.refresh(force)
            if adapter.scope!='Layer':continue
            from rack_owners import current_sources
            queue_state,current_clips,mode=current_sources(adapter.owner,self.app.playhead)
            relevant=[(clip,adapter.owner)] if any(c is clip for c in adapter.owner.clips) else []
            relevant.extend((current_clip,queue_state) for current_clip in current_clips if not any(c is current_clip for c,state in relevant))
            keep=set()
            for child_clip,source_state in relevant:
                child=OwnerRackAdapter(self.app,p,child_clip,'Clip',adapter.owner);child.queue_state=source_state;keep.add(child.key)
                existing=cell.clip_cells.get(child.key)
                if existing and (existing.adapter.owner is not child_clip or getattr(existing.adapter,'queue_state',adapter.owner) is not source_state):existing.destroy();del cell.clip_cells[child.key]
                if child.key not in cell.clip_cells:
                    cell.clip_cells[child.key]=OwnerCell(cell.clip_host,self,child);cell.clip_cells[child.key].pack(fill='x',pady=(5,0))
                else:cell.clip_cells[child.key].refresh(force)
            for key,child in list(cell.clip_cells.items()):
                # An open companion and an active gesture retain their occurrence.
                if key not in keep and not self.app.gesture and not any(t.winfo_manager() for t in child.companions.values()):child.destroy();del cell.clip_cells[key]
        scope=self.scope.get()
        desired=('Master',p.id) if scope=='Master' else ('Clip',getattr(clip,'id',None)) if scope=='Clip' else ('Layer',getattr(layer,'id',None))
        if scope in ('Master','Layer','Clip'):self.selected_owner_key=desired
        if scope in ('Mix','Transition'):
            from instrument_widgets import EffectsDeck
            self.special_host.pack(fill='x',before=self.owners_host)
            if self.special_editor is None:self.special_editor=EffectsDeck(self.special_host,self.app);self.special_editor.pack(fill='x')
            self.special_editor.scope.set(scope);self.special_editor.refresh(force)
        else:self.special_host.pack_forget()
        cell=self.selected_cell()
        if cell:self.target_name.set('Whole picture' if scope=='Master' else 'Selected clip' if scope=='Clip' else cell.adapter.title);self._sync_selected(cell)
        elif scope=='Clip':self.target_name.set('Selected clip')
        self.refresh_navigation();self.refresh_toolbar_state();self.relayout()
    def refresh_navigation(self):
        # Scope is one retained selector; available owners are populated by the
        # existing owner registry rather than duplicate navigation widgets.
        values=['Whole picture']+[c.adapter.title for c in self.owner_cells.values() if c.adapter.scope=='Layer']
        if self.app.get_edit_target()[1] is not None:values.append('Selected clip')
        values+=['A/B mixer','Transition']
        if tuple(self.scope_selector.cget('values'))!=tuple(values):self.scope_selector.configure(values=values)
    def flush_history(self):
        for cell in self.owner_cells.values():cell.flush_history()
        if self.special_editor:self.special_editor.flush_history()
    def relayout(self):
        if not self._ready:return
        selected=self.selected_cell();previous=self._mounted_owner
        if selected is None:
            if previous is not None and previous.winfo_exists() and previous.winfo_manager():previous.grid_remove()
            self._mounted_owner=None;self.scroll.set_policy(self.owner_layout);self.owner_remaining.grid_remove();return
        parent=selected if selected.adapter.scope!='Clip' else next((c for c in self.owner_cells.values() if c.adapter.owner is selected.adapter.parent),selected)
        changed=previous is not parent
        if changed:
            if previous is not None and previous.winfo_exists() and previous.winfo_manager():previous.grid_remove()
            # Project restoration can leave a stale cell gridded even when the
            # remembered pointer was destroyed. Hide only those actual strays.
            for cell in self.owner_cells.values():
                if cell is not parent and cell.winfo_manager():cell.grid_remove()
            parent.grid(row=0,column=0,sticky='nsew',padx=2,pady=2);self._mounted_owner=parent
        elif not parent.winfo_manager():parent.grid(row=0,column=0,sticky='nsew',padx=2,pady=2)
        self.owners_host.columnconfigure(0,weight=1);self.owners_host.rowconfigure(0,weight=1)
        target_width=max(420,self.scroll.canvas.winfo_width()-8)
        try:current_width=int(float(parent.cget('width')))
        except (ValueError,tk.TclError):current_width=-1
        if abs(current_width-target_width)>1:parent.configure(width=target_width)
        parent.relayout()
        for child in parent.clip_cells.values():child.relayout()
        # The selected owner stays mounted. Earlier builds removed and re-gridded
        # this complete subtree on every resize/refresh, producing the flicker seen
        # in the owner screencast and clearing native Treeview paint between frames.
        if not parent.content.winfo_manager():parent.content.grid()
        if parent.header.winfo_manager():parent.header.grid_remove()
        if parent.state_label.winfo_manager():parent.state_label.grid_remove()
        self.scroll.set_policy(self.owner_layout)
        self.scroll.grid_configure(sticky='nsew');self.owner_remaining.grid_remove()
        if changed:
            try:parent.scroll.canvas.yview_moveto(0);self.scroll.reveal(parent)
            except tk.TclError:pass

    def serialize_layout(self):
        return {'grid':bool(self.module_grid.get())}

    def load_layout(self,raw):
        from rack_layout import LayoutPolicy
        grid=True
        if isinstance(raw,dict):
            if 'grid' in raw:grid=bool(raw.get('grid'))
            elif isinstance(raw.get('modules'),dict):grid=raw['modules'].get('flow')!='Single strip'
        self.module_grid.set(grid)
        self.module_layout=LayoutPolicy('Grid','Wrap' if grid else 'Single strip','Expand all','Auto' if grid else '1')
        self.saved_owner_layouts={}
        if getattr(self,'_ready',False):
            for cell in self.all_cells():cell.layout_override=None
            self.relayout()

    def layout_menu(self):
        # Kept as an internal compatibility action. Public rack layout is one Grid
        # toggle so there are no conflicting presentation policies.
        menu=tk.Menu(self,tearoff=False)
        menu.add_command(label=('✓ ' if self.module_grid.get() else '')+'Grid · vertical wrap',command=lambda:(self.module_grid.set(True),self.apply_grid_mode()))
        menu.add_command(label=('✓ ' if not self.module_grid.get() else '')+'Row · horizontal scroll',command=lambda:(self.module_grid.set(False),self.apply_grid_mode()))
        self.app.popup_menu(menu,self.scope_selector)

    def set_layout(self,level,policy):
        self.module_grid.set(getattr(policy,'flow','Wrap')!='Single strip');self.apply_grid_mode()

    def open_parameter(self,fxid,key=None):
        for cell in self.all_cells():
            rack,owner=cell.target()
            if any(f.id==fxid for f in rack or []):cell.open_parameter(fxid,key);self._sync_selected(cell);return
    def all_cells(self):
        for cell in self.owner_cells.values():
            yield cell
            yield from cell.clip_cells.values()
    def open_catalogue(self):
        cell=self.selected_cell()
        if cell:cell.open_catalogue();self._sync_selected(cell)
    def close_tray(self,fxid=None,key=None):
        cell=next((c for c in self.all_cells() if fxid in c.card_parts),None) if fxid else self.selected_cell()
        if cell:cell.close_tray(fxid,key);self._sync_selected(cell)
    def select_card(self,fxid,multiple=False):
        cell=self.selected_cell()
        if cell:cell.select_card(fxid,multiple);self._sync_selected(cell)
    def set_card_mode(self,fxid,mode):
        cell=next((c for c in self.all_cells() if fxid in c.card_parts),None)
        if cell:cell.set_card_mode(fxid,mode)
