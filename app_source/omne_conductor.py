"""One modeless Conductor. Policy gestures invalidate no playback widgets."""
from __future__ import annotations
from conductor_targets import DEFAULTS
import copy, random
import tkinter as tk
from tkinter import ttk, messagebox
from conductor_view import ConductorView, TITLES
from conductor import TRANSITIONS
from effects_engine import EFFECTS
from performance_dials import PerformanceDial
from responsive_controls import FlowRow, PriorityToolbar
from ui_chrome import CollapsibleSection, tk_scale_theme_options
from input_gestures import claim_input, release_input

HELP = {
    'pace':'Steers the next generated clip lengths and treatment interval. Does not retime existing clips.',
    'intensity':'Strength of the next generated treatment. Use the rack to change the current treatment.',
    'reaction':'Audio modulation chosen for the next generated treatment. Current audio reaction continues when Conductor is off.',
    'layering':'Chance of adding another eligible visual channel to future generated combinations.',
    'transition_usage':'Share of eligible future boundaries with transitions. Does not change transition length.',
    'variation':'Variation of the starting point within each chosen source.',
}

def _current_policy(panel,state,token=None):
    project=panel.app.project
    return (state is not None and state.get('kind')=='conductor-policy' and
        state.get('project_ref') is project and state.get('project_id')==project.id and
        state.get('conductor_ref') is project.conductor and
        (token is None or state.get('input_token') is token))

class CompactDial(PerformanceDial):
    """The same keyboard/numeric/relative-gesture control, vertically composed."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.configure(padding=(2,0))
        style=ttk.Style(self);style.configure('Knob.TEntry',font=('TkFixedFont',9),padding=0,borderwidth=1)
        self.title.grid(row=0,column=0,columnspan=1,sticky='ew')
        self.title.configure(anchor='center')
        self.canvas.grid(row=1,column=0,sticky='')
        self.entry.grid(row=2,column=0,sticky='',padx=0,pady=(0,2))
        self.entry.configure(justify='center',width=6,style='Knob.TEntry')


class RecipeScaleControl:
    """Claim one immediate recipe gesture and reject callbacks for stale state."""
    NAVIGATION={'Up','Down','Left','Right','Home','End','Prior','Next'}
    def __init__(self,panel,parent,key,variable,value_label,lo,hi,resolution):
        self.panel=panel;self.app=panel.app;self.key=key;self.variable=variable;self.value_label=value_label
        self.active=False;self.token=None;self.project=None;self.conductor=None
        self.scale=tk.Scale(parent,variable=variable,from_=lo,to=hi,resolution=resolution,orient='horizontal',showvalue=False,
            command=self.changed,**tk_scale_theme_options(self.app.ui_chrome))
        self.scale.bind('<ButtonPress-1>',self.begin);self.scale.bind('<ButtonRelease-1>',self.release)
        self.scale.bind('<B1-Motion>',lambda event:None if self.active else 'break')
        self.scale.bind('<KeyPress>',self.key_press);self.scale.bind('<KeyRelease>',self.key_release)
        self.scale.bind('<Escape>',lambda event:self.finish_input(cancel=True))
        self.scale.bind('<FocusOut>',self.release);self.scale.bind('<Unmap>',self.release)

    def begin(self,event=None):
        # Mouse events report the placeholder keysym ``??`` on Tk 9.  Treat
        # only real key events as navigation; otherwise a native scale press
        # would be discarded before it could claim the gesture.
        keysym=(getattr(event,'keysym','') if event is not None and
                getattr(event,'type',None)==tk.EventType.KeyPress else '')
        if keysym and keysym not in self.NAVIGATION:return None
        if self.active:return None
        claim_input(self.app,self)
        if not keysym:self.scale.focus_set()
        self.project=self.app.project;self.conductor=self.project.conductor;self.token=object();self.active=True
        if not self.panel.begin_recipe(self.key,self.token,self.project,self.conductor):
            self._clear();return 'break'
        return None

    def current(self):
        return (self.active and self.app.project is self.project and
                self.app.project.conductor is self.conductor and
                self.panel.owns_recipe(self.key,self.token,self.project,self.conductor))

    def changed(self,raw):
        if not self.active:return
        if not self.current():return self._clear(abandon=True)
        self.panel.slide_recipe(self.key,float(raw),self.value_label,self.token)

    def key_press(self,event):
        if event.keysym in self.NAVIGATION:self.begin(event)

    def key_release(self,event):
        if event.keysym in self.NAVIGATION:return self.release(event)

    def release(self,event=None):
        if not self.active:return None
        native_release=(event is not None and getattr(event,'type',None)==tk.EventType.ButtonRelease)
        self.finish_input(_native_release=native_release)
        # A real ButtonRelease must continue to Scale's class binding, which
        # cancels trough repeat and ends the native slider drag.
        return None

    def _stop_native_pointer(self):
        try:self.scale.event_generate('<ButtonRelease-1>',x=-1,y=-1)
        except tk.TclError:pass

    def finish_input(self,*,cancel=False,_native_release=False):
        if not self.active:return 'break'
        token=self.token;valid=self.current();self.active=False;release_input(self.app,self)
        if not _native_release:self._stop_native_pointer()
        if cancel and valid:
            self.panel.cancel(token)
        elif valid:self.panel.end(token)
        else:self.panel.abandon_recipe(token)
        self.token=None;self.project=None;self.conductor=None
        return 'break'

    def _clear(self,abandon=False):
        token=self.token;self.active=False;release_input(self.app,self)
        self._stop_native_pointer()
        if abandon:self.panel.abandon_recipe(token)
        self.token=None;self.project=None;self.conductor=None

    def destroy(self):
        self.finish_input();self.scale.destroy()

class ConductorPanel(ConductorView):
    def __init__(self,parent,app):
        ttk.Frame.__init__(self,parent,padding=6)
        self.app=app;self.loading=False;self.active=None;self.values={};self.dials=[]
        self.scope=tk.StringVar(value='sequence');self.seed=tk.StringVar();self.c=self
        self.values['energy']=tk.DoubleVar(value=app.project.conductor.energy)
        self.minimum=tk.StringVar();self.maximum=tk.StringVar();self.summary=tk.StringVar()
        self.expand=tk.BooleanVar(value=False);self.sections={};self.recipe_vars={};self.recipe_controls={};self.choice_vars={}
        # Mode switching must never disappear behind overflow in the narrow right
        # dock. The panel itself already identifies this as Conductor, so spend the
        # header width on the two actions that matter: power and Simple/Advanced.
        header=app.shell.headers['panel.conductor']
        self.advanced_button=ttk.Button(header,text='Steer ↓',width=6,command=self.toggle_details);self.advanced_button.pack(side='right',padx=2)
        app.add_tip(self.advanced_button,'Show precise Conductor steering in place of the composition queue. Cues returns to the same prepared changes.')
        self.power=ttk.Button(header,text='OFF',width=5,command=self.toggle_power);self.power.pack(side='right',padx=2)
        self.simple_frame=ttk.Frame(self,padding=(4,2),relief='ridge',borderwidth=1);self.simple_frame.pack(fill='x',pady=(1,2))
        self.details_frame=ttk.LabelFrame(self,text='Steering',padding=(5,4));self.details=None
        from composition_queue_view import CompositionQueueView
        self.queue_view=CompositionQueueView(self.simple_frame,app);self.queue_view.pack(fill='x')
        randomrow=FlowRow(self.details_frame,gap=4);randomrow.pack(fill='x',pady=(2,0))
        self.random_button=ttk.Button(randomrow,text='Vary',width=5,command=self.random_now);randomrow.add(self.random_button)
        self.random_variation=tk.StringVar(value=f"{app.settings()['conductor_variation']*100:g}")
        randomrow.add(ttk.Spinbox(randomrow,from_=0,to=100,increment=5,textvariable=self.random_variation,width=4));randomrow.add(ttk.Label(randomrow,text='%'))
        app.add_tip(self.random_button,'Vary the future policy immediately by the adjacent amount. Power and device state remain unchanged.')
        app.add_tip(self.power,'Allow autonomous future decisions. Off leaves music, queue progression and existing audio reaction running.')
        self.queue_fill_button=ttk.Button(randomrow,text='Fill queues',width=10,command=self.generate_once);randomrow.add(self.queue_fill_button)
        self.mutate_button=self.queue_view.generate_button
        app.add_tip(self.queue_fill_button,'Prepare future visual and music queue material for the checked targets. Rack compositions use the visible composition queue; power stays unchanged.')
        targets=FlowRow(self.simple_frame,gap=3);targets.pack(fill='x',pady=(5,2));self.targets={}
        targets.add(ttk.Label(targets,text='Evolve:',style='Muted.TLabel'))
        for key,title,default in [('evolve_treatment','Rack · effects',True),('evolve_sources','Visuals +',False),('evolve_sound','Music +',False)]:
            var=tk.BooleanVar(value=default);self.targets[key]=var
            button=ttk.Checkbutton(targets,text=title,variable=var,command=lambda k=key,v=var:self.set_target(k,v.get()));targets.add(button)
        self.timing_label=tk.StringVar(value='Next choices · 4–8 s clips')
        ttk.Label(self.details_frame,textvariable=self.timing_label,style='Muted.TLabel',wraplength=290).pack(fill='x',pady=(0,3))
        self.controls=ttk.Frame(self.details_frame);self.controls.pack(fill='x');self.grid_columns=3
        for n,(key,label) in enumerate([('reaction','Reaction'),('intensity','FX strength'),('pace','Pace'),('variation','Variation'),('transition_usage','Transitions'),('layering','Layering')]):
            variable=tk.DoubleVar(value=.5);self.values[key]=variable
            dial=CompactDial(self.controls,app,label,variable,lambda k=key:self.begin(k),lambda value,k=key:self.changed(k,value),self.end,HELP[key])
            dial.grid(row=n//3,column=n%3,sticky='ew',padx=1,pady=1);self.dials.append(dial)
        for col in range(3):self.controls.columnconfigure(col,weight=1,uniform='conductor')
        self.controls.pack_configure(before=randomrow)
        self.back_to_cues=ttk.Button(self.details_frame,text='← Compositions',command=self.toggle_details)
        # The persistent header owns the single return action while steering.
        self.bind('<Configure>',self.reflow,add='+')
        self.next_area=ttk.LabelFrame(self.details_frame,text='Media next choice',padding=5)
        self.next_text=tk.StringVar(value='Drop media for its Conductor preferences.')
        ttk.Label(self.next_area,textvariable=self.next_text,style='Muted.TLabel',wraplength=270).pack(fill='x')
        nextrow=FlowRow(self.next_area,gap=4);nextrow.pack(fill='x',pady=(5,0))
        self.next_role=tk.StringVar(value='A')
        nextrow.add(ttk.Combobox(nextrow,textvariable=self.next_role,values=['A','B','C','D','Music'],state='readonly',width=10))
        nextrow.add(ttk.Button(nextrow,text='Use selected',command=lambda:app.place_media(list(app.library.selection()),self.next_role.get(),'next')))
        self.state_text=tk.StringVar()
        self.state_label=None
        self.refresh()
    def generate_once(self):
        if self.app.reviewing:return self.app.update_status('Return to Programme before generating; this review is kept unchanged.')
        if self.app.mutating:return self.app.update_status('Preparing a choice · current output continues')
        if not any(self.app.project.conductor.extra.get(key,DEFAULTS[key]) for key in ('evolve_sources','evolve_sound')):
            return self.app.update_status('Choose Visuals or Music before filling media queues.')
        if self.app.gesture:self.app.end_gesture()
        # The Conductor target switches own scope. A global Randomise menu choice
        # such as “modules” must not silently narrow this explicit one-shot action.
        result=self.app.randomise_playable('queues',automatic=True)
        self.refresh()
        return result
    def random_now(self):
        from omne_randomise import normalise_settings,vary_conductor
        try:setting=normalise_settings({**self.app.settings(),'conductor_variation':float(self.random_variation.get())/100})
        except (ValueError,tk.TclError) as exc:return self.app.update_status(str(exc))
        def apply():
            p=self.app.project;p.mutation_seed+=1;vary_conductor(p.conductor,seed=p.mutation_seed,variation=setting['conductor_variation']);p.extra['randomise_settings']=setting
        return self.app.transaction('Vary Conductor policy',apply)
    def recipe(self):
        if not self.expand.get():self.toggle_details()
    def reflow(self,event=None):
        if event is not None and event.widget is not self:return
        width=max(1,self.winfo_width()-30)
        minimum=max(80,max(d.title.winfo_reqwidth()+8 for d in self.dials))
        columns=max(1,min(3,width//minimum))
        for widget in (self.simple_frame, self.next_area):
            for label in widget.winfo_children():
                if isinstance(label,ttk.Label) and int(label.cget('wraplength') or 0):label.configure(wraplength=max(150,self.winfo_width()-26))
        if columns==self.grid_columns:return
        self.grid_columns=columns
        for col in range(3):self.controls.columnconfigure(col,weight=1 if col<columns else 0,uniform='conductor' if col<columns else '',minsize=0)
        for n,dial in enumerate(self.dials):dial.grid(row=n//columns,column=n%columns,sticky='ew')
    def toggle_power(self):
        self.app.evolve.set(not self.app.evolve.get());self.app.toggle_evolve();self.refresh()
    def set_target(self,key,value):
        self.app.transaction('Conductor target',lambda:self.app.project.conductor.extra.__setitem__(key,bool(value)))
    def toggle_details(self):
        self.expand.set(not self.expand.get())
        if self.expand.get():
            self.simple_frame.pack_forget()
            if self.details is None:self.build_details()
            for kind in getattr(self,'pool_status',{}):self.refresh_pool(kind)
            if not self.next_area.winfo_manager():self.next_area.pack(fill='x',pady=(0,4))
            self.details_frame.pack(fill='x',pady=(0,3))
        else:
            self.details_frame.pack_forget()
            self.simple_frame.pack(fill='x',pady=(1,2))
        self.advanced_button.configure(text='← Cues' if self.expand.get() else 'Steer ↓')
        # The companion is in the same retained scroll surface. Opening it must
        # reveal its controls even in Conduct's shallow right dock.
        self.after_idle(self.reveal_steering)

    def reveal_steering(self):
        surface=getattr(self.app,'conductor_tab',None)
        if surface is None or not self.winfo_exists():return
        self.update_idletasks()
        if self.expand.get():
            top=self.details_frame.winfo_y()+self.winfo_y()
            height=max(1,surface.body.winfo_reqheight())
            surface.canvas.yview_moveto(top/height)
        else:surface.canvas.yview_moveto(0)

    def state_text_widget(self):
        return None
    def build_details(self):
        self.details=True
        for title,builder,expanded in [('Sources',self._build_sources,True),('Timing',self._build_timing,False),('Choices',self._build_choices,False),('Energy links',self._build_links,False)]:
            section=CollapsibleSection(self.details_frame,title,expanded=expanded);section.pack(fill='x',pady=1)
            self.sections[title]=section;builder(section.body)

    def _build_sources(self,body):
        self.pool_vars={};self.pool_status={}
        body.columnconfigure(0,weight=1)
        for index,(kind,label) in enumerate((('visuals','Visuals'),('music','Music'))):
            box=ttk.LabelFrame(body,text=label,padding=4);box.grid(row=index,column=0,sticky='ew',pady=2)
            choice=self._pool_choice(kind);var=tk.StringVar(value=choice.get('mode','project'))
            self.pool_vars[kind]=var
            for mode,text in (('project','This project'),('albums','Selected albums…'),('all','All imports')):
                ttk.Radiobutton(box,text=text,value=mode,variable=var,
                    command=lambda k=kind,m=mode:self.set_pool(k,m)).pack(anchor='w')
            status=tk.StringVar();self.pool_status[kind]=status
            ttk.Label(box,textvariable=status,style='Muted.TLabel',wraplength=250).pack(fill='x')
            self.refresh_pool(kind)

    def _range_control(self,body,key,label,lo,hi,resolution):
        row=ttk.Frame(body);row.pack(fill='x',pady=2);row.columnconfigure(1,weight=1)
        ttk.Label(row,text=label).grid(row=0,column=0,sticky='w')
        var=tk.DoubleVar(value=getattr(self.app.project.conductor,key));self.recipe_vars[key]=var
        value=tk.StringVar(value=f'{var.get():g}');self.recipe_vars[key+'_label']=value
        control=RecipeScaleControl(self,row,key,var,value,lo,hi,resolution);self.recipe_controls[key]=control
        control.scale.grid(row=0,column=1,sticky='ew',padx=4);ttk.Label(row,textvariable=value,width=6).grid(row=0,column=2)

    def _build_timing(self,body):
        for args in [('clip_min','Clip minimum',.15,120,.05),('clip_max','Clip maximum',.15,240,.05),
                     ('transition_min','Transition minimum',.04,8,.01),('transition_max','Transition maximum',.04,12,.01)]:
            self._range_control(body,*args)
        for key,label,lo,hi in [('max_layers','Layer count',1,8),('repeat_gap','Repeat distance',0,50)]:
            row=FlowRow(body,gap=3);row.pack(fill='x',pady=2);row.add(ttk.Label(row,text=label))
            var=tk.StringVar(value=str(getattr(self.app.project.conductor,key)));self.recipe_vars[key]=var
            step=ttk.Spinbox(row,textvariable=var,from_=lo,to=hi,increment=1,width=6,
                command=lambda k=key,v=var:self.update_recipe_value(k,v.get()))
            step.bind('<Return>',lambda event,k=key,v=var:self.update_recipe_value(k,v.get()))
            step.bind('<FocusOut>',lambda event,k=key,v=var:self.update_recipe_value(k,v.get()));row.add(step)
        row=FlowRow(body,gap=3);row.pack(fill='x',pady=2);row.add(ttk.Label(row,text='Seed'))
        self.seed_entry=ttk.Entry(row,textvariable=self.seed,width=10);self.seed_entry.bind('<Return>',self.apply_seed)
        self.seed_entry.bind('<FocusOut>',self.apply_seed);row.add(self.seed_entry)
        row.add(ttk.Button(row,text='⚄ Dice',command=self.random_seed))

    def _build_choices(self,body):
        self.queue_view.build_choices(body)
        groups=(('transition_preferences','Transitions',list(TRANSITIONS)),
                ('effect_preferences','Effects',list(self.app.project.conductor.effect_preferences)),
                ('reaction_preferences','Reaction',list(self.app.project.conductor.reaction_preferences)))
        for attr,title,keys in groups:
            group=CollapsibleSection(body,title,expanded=False);group.pack(fill='x',pady=1)
            data=getattr(self.app.project.conductor,attr)
            for key in keys:
                row=ttk.Frame(group.body);row.pack(fill='x',pady=1)
                label=TITLES.get(key,EFFECTS[key].label if key in EFFECTS else key.replace('_',' ').title())
                ttk.Label(row,text=label,width=18).pack(side='left')
                var=tk.StringVar(value=data.get(key,'allow'));self.choice_vars[(attr,key)]=var
                pick=ttk.Combobox(row,textvariable=var,values=('prefer','allow','avoid','exclude'),state='readonly',width=9)
                pick.pack(side='right',fill='x',expand=True);pick.bind('<<ComboboxSelected>>',lambda event,a=attr,k=key,v=var:self.set_choice(a,k,v.get()))

    def _build_links(self,body):
        self.link_vars={}
        for key,label in [('intensity','FX strength'),('reaction','Reaction'),('layering','Layering')]:
            var=tk.BooleanVar(value=key in self.app.project.conductor.energy_links);self.link_vars[key]=var
            ttk.Checkbutton(body,text='Link '+label+' to Energy',variable=var,
                command=lambda k=key,v=var:self.set_link(k,v.get())).pack(anchor='w')
        self.energy_dial=PerformanceDial(body,self.app,'Linked Energy',self.values['energy'],lambda:self.begin('energy'),lambda v:self.changed('energy',v),self.end,'Steers linked values for the next treatment.')
        self.energy_dial.pack(fill='x')

    def _pool_choice(self,kind):
        if hasattr(self.app,'source_pool_choice'):
            try:return self.app.source_pool_choice(kind)
            except (KeyError,ValueError):pass
        return self.app.project.conductor.extra.get('source_pools',{}).get(kind,{'mode':'project','albums':[]})

    def set_pool(self,kind,mode):
        if mode=='albums' and hasattr(self.app,'choose_source_pool'):
            self.app.choose_source_pool(kind)
            # Opening the picker is not itself a policy edit.  Its explicit
            # selection transaction will refresh this control.
            self.pool_vars[kind].set(self._pool_choice(kind).get('mode','project'))
        elif hasattr(self.app,'set_source_pool'):self.app.set_source_pool(kind,{'mode':mode,'albums':[]})
        else:
            def apply():self.app.project.conductor.extra.setdefault('source_pools',{})[kind]={'mode':mode,'albums':[]}
            self.app.transaction(kind.title()+' source pool',apply)
        self.refresh_pool(kind)

    def refresh_pool(self,kind):
        if kind not in getattr(self,'pool_status',{}):return
        choice=self._pool_choice(kind);self.pool_vars[kind].set(choice.get('mode','project'))
        if hasattr(self.app,'resolve_source_pool'):
            try:
                result=self.app.resolve_source_pool(self.app.project,choice,kind)
                text=f"{result.get('eligible',len(result.get('ids',[])))} eligible"
                extra=[f"{result.get(k)} {k}" for k in ('excluded','unavailable') if result.get(k)]
                if extra:text+=' · '+' · '.join(extra)
                if result.get('reason'):text+=' · '+str(result['reason'])
            except (KeyError,ValueError,TypeError) as exc:text=str(exc)
        else:text='Pool applies to the next choice.'
        self.pool_status[kind].set(text)

    def begin_recipe(self,key,token,project,conductor):
        if self.active:return False
        if self.app.gesture:self.app.end_gesture()
        if self.app.project is not project or self.app.project.conductor is not conductor:return False
        self.active='recipe:'+key;self._policy_token=token
        self.app.gesture={'kind':'conductor-policy','before_recipe':copy.deepcopy(conductor),
            'project_ref':project,'project_id':project.id,'conductor_ref':conductor,'input_token':token}
        self.app.gesture_time=self.app.programme_time()
        return True

    def owns_recipe(self,key,token,project,conductor):
        state=self.app.gesture
        return (self.active=='recipe:'+key and getattr(self,'_policy_token',None) is token and
            state is not None and state.get('kind')=='conductor-policy' and state.get('input_token') is token and
            state.get('project_ref') is project and state.get('project_id')==project.id and
            state.get('conductor_ref') is conductor)

    def slide_recipe(self,key,value,label,token):
        if self.loading:return
        state=self.app.gesture
        if not state or not self.owns_recipe(key,token,self.app.project,self.app.project.conductor):return
        self._assign_recipe(key,value);label.set(f'{getattr(self.app.project.conductor,key):g}')

    def abandon_recipe(self,token):
        if getattr(self,'_policy_token',None) is not token:return
        state=self.app.gesture
        if state and state.get('kind')=='conductor-policy' and state.get('input_token') is token:self.app.gesture=None
        self._policy_token=None;self.active=None;self.refresh()

    def _assign_recipe(self,key,value):
        r=self.app.project.conductor
        value=int(float(value)) if key in ('max_layers','repeat_gap') else float(value)
        setattr(r,key,value)
        if key=='clip_min' and r.clip_max<value:r.clip_max=value
        elif key=='clip_max' and r.clip_min>value:r.clip_min=value
        elif key=='transition_min' and r.transition_max<value:r.transition_max=value
        elif key=='transition_max' and r.transition_min>value:r.transition_min=value
        r.normalized()

    def update_recipe_value(self,key,value):
        try:
            number=float(value)
            if key in ('max_layers','repeat_gap') and number!=int(number):raise ValueError('Use a whole number')
            before=getattr(self.app.project.conductor,key)
            if before==number:return
            self.app.transaction('Conductor '+key.replace('_',' '),lambda:self._assign_recipe(key,number));self.refresh()
        except (ValueError,tk.TclError) as exc:self.app.update_status(str(exc))

    def set_choice(self,attr,key,choice):
        current=getattr(self.app.project.conductor,attr).get(key)
        if current==choice:return
        self.app.transaction('Conductor choice · '+key,lambda:getattr(self.app.project.conductor,attr).__setitem__(key,choice))

    def set_link(self,key,enabled):
        def apply():
            links=self.app.project.conductor.energy_links
            if enabled and key not in links:links.append(key)
            elif not enabled and key in links:links.remove(key)
        self.app.transaction('Conductor Energy link',apply)

    def random_seed(self):
        self.seed.set(str(random.SystemRandom().randrange(1,2**31)));self.apply_seed()

    def apply_seed(self,event=None):
        try:
            seed=int(self.seed.get())
            if seed!=self.app.project.mutation_seed:self.app.transaction('Set Conductor seed',lambda:setattr(self.app.project,'mutation_seed',seed))
        except (ValueError,tk.TclError):self.app.update_status('Seed must be an integer')
        return 'break' if event is not None and getattr(event,'keysym','')=='Return' else None
    def refresh(self,refresh_pools=False):
        r=self.app.project.conductor
        busy=bool(getattr(self.app,'mutating',False));reviewing=bool(getattr(self.app,'reviewing',False))
        power=self.app.evolve.get()
        targets=any(r.extra.get(key,DEFAULTS[key]) for key in self.targets)
        state=('Preparing next choice · output continues' if busy else 'Review · Return to Programme before generating' if reviewing else
               'No targets · choose Visuals, Effects or Music' if not targets else
               'Waiting for the next eligible choice' if power and self.app.playing else
               'Play to begin autonomous choices' if power else '')
        can_generate=not busy and not reviewing
        if getattr(self,'_can_generate',None)!=can_generate:
            self._can_generate=can_generate;self.mutate_button.configure(state='normal' if can_generate else 'disabled')
        if getattr(self,'_power_state',None)!=power:
            self._power_state=power;self.power.configure(text='ON' if power else 'OFF',style='Accent.TButton' if power else 'TButton')
        def put(variable,value):
            if variable.get()!=value:variable.set(value)
        put(self.state_text,state)
        state_widget=self.state_text_widget()
        if state:
            if state_widget is not None and not state_widget.winfo_manager():state_widget.pack(fill='x',before=self.controls,pady=(0,3))
        elif state_widget is not None:state_widget.pack_forget()
        if self.active:return
        focus=self.app.focus_get()
        if isinstance(focus,ttk.Entry) and str(focus.cget('textvariable')) in [str(v) for v in (self.seed,self.minimum,self.maximum)]:return
        self.loading=True
        for key in ('energy','intensity','reaction','layering','transition_usage','variation'):put(self.values[key],getattr(r,key))
        pace=r.extra.get('playable_pace',{})
        linked=bool(pace and abs(r.clip_min-pace.get('clip_min',-1))<1e-6 and abs(r.clip_max-pace.get('clip_max',-1))<1e-6)
        put(self.values['pace'],pace['value'] if linked else max(0,min(1,(24-r.clip_max)/21)))
        put(self.timing_label,f'Future policy · {r.clip_min:g}–{r.clip_max:g} s'+(' · linked' if linked else ' · custom'))
        put(self.seed,str(self.app.project.mutation_seed));put(self.minimum,f'{r.clip_min:g}');put(self.maximum,f'{r.clip_max:g}')
        for key,var in self.targets.items():put(var,r.extra.get(key,DEFAULTS[key]))
        for key in ('clip_min','clip_max','transition_min','transition_max'):
            if key in self.recipe_vars:
                put(self.recipe_vars[key],getattr(r,key));put(self.recipe_vars[key+'_label'],f'{getattr(r,key):g}')
        for key in ('max_layers','repeat_gap'):
            if key in self.recipe_vars:put(self.recipe_vars[key],str(getattr(r,key)))
        for (attr,key),var in self.choice_vars.items():put(var,getattr(r,attr).get(key,'allow'))
        for key,var in getattr(self,'link_vars',{}).items():put(var,key in r.energy_links)
        if refresh_pools:
            for kind in getattr(self,'pool_status',{}):self.refresh_pool(kind)
        self.loading=False
        self.queue_view.refresh()
    def begin(self,key):
        if self.active:return
        if self.app.gesture:self.app.end_gesture()
        project=self.app.project;conductor=project.conductor;token=getattr(self.app,'_active_input_control',None)
        self.active=key;self._policy_token=token
        self.app.gesture={'kind':'conductor-policy','before_recipe':copy.deepcopy(conductor),
            'project_ref':project,'project_id':project.id,'conductor_ref':conductor,'input_token':token}
        self.app.gesture_time=self.app.programme_time()

    def changed(self,key,value):
        if self.loading or self.active!=key:return
        if not _current_policy(self,self.app.gesture):return
        v=max(0.,min(1.,float(value)));r=self.app.project.conductor
        self.values[key].set(v)
        if key=='pace':
            r.clip_min=12-11*v;r.clip_max=24-21*v;r.extra['treatment_interval']=24-21*v
            r.extra['playable_pace']={'value':v,'clip_min':r.clip_min,'clip_max':r.clip_max}
            self.timing_label.set(f'Next choices · {r.clip_min:.1f}–{r.clip_max:.1f} s clips · linked pace')
        elif key=='energy':
            r.set_energy(v)
            for linked in r.energy_links:
                if linked in self.values:self.values[linked].set(getattr(r,linked))
        else:
            setattr(r,key,v)
            if key in r.energy_links:r.energy_links.remove(key)
        # No serialization, queue, renderer, rack, audio or widget reconstruction here.
    def end(self,token=None):
        if self.active is None:return
        if token is not None and getattr(self,'_policy_token',None) is not token:return
        state=self.app.gesture;current=_current_policy(self,state,token)
        self.active=None;self._policy_token=None
        if current:self.app.gesture=None
        if current:
            before=state['before_recipe'];after=self.app.project.conductor
            if before!=after:
                # One policy-sized semantic checkpoint, not a full-project
                # serialization at either end of every knob gesture.
                self.app.history.checkpoint_conductor(before)
                self.app.policy_changed()
        self.refresh()
    def cancel(self,token=None):
        if token is not None and getattr(self,'_policy_token',None) is not token:return
        state=self.app.gesture
        current=_current_policy(self,state,token)
        if current:
            self.app.project.conductor=state['before_recipe'];self.app.gesture=None
        self._policy_token=None;self.active=None;self.refresh()
    def retheme(self):
        for dial in self.dials:dial.retheme()
        if hasattr(self,'energy_dial'):self.energy_dial.retheme()
