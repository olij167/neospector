"""Effects-first instrument surfaces built on the accepted family controls."""
from __future__ import annotations
from conductor_targets import DEFAULTS
import copy,math,time
import tkinter as tk
from tkinter import ttk,simpledialog,messagebox,colorchooser
from PIL import Image,ImageTk
from ui_chrome import CollapsibleSection,tk_scale_theme_options
from editor_widgets import ParameterRow,ScrollFrame
from control_deck import ControlDeck
from conductor_view import ConductorView,ConductorPreferences,TITLES
from effects_engine import EFFECTS,LOOKS,BLEND_MODES,make_effect,make_look
from conductor import TRANSITIONS,SCOPES
from sequencer_model import new_id
from sequence_edit import trim_clip,slip_clip,move_clip,set_transition_duration

class EffectsDeck(ControlDeck):
    """One editing grammar; persistent voice racks are the default target."""
    def __init__(self,parent,app):
        ttk.Frame.__init__(self,parent,padding=(4,3));self.app=app;self.key=None;self.rows=[];self.owner=None;self.history_layer=None;self.history_proxy=None;self.history_span=None;self.scope=tk.StringVar(value='Layer');self.summary=tk.StringVar();self.expanded=set()
        self.columnconfigure(0,weight=1);self.rowconfigure(1,weight=1)
        top=ttk.Frame(self);top.grid(row=0,column=0,sticky='ew',pady=(1,5))
        ttk.Label(top,text='EFFECTS  /  INSTRUMENT',style='Title.TLabel').pack(side='left',padx=(0,12))
        for label,value in [('Voice','Layer'),('This clip','Clip'),('Mix','Mix'),('Master','Master'),('Transition','Transition')]:ttk.Radiobutton(top,text=label,variable=self.scope,value=value,command=lambda:self.refresh(force=True)).pack(side='left',padx=3)
        ttk.Button(top,text='Keep…',width=7,command=app.keep_ingredient).pack(side='right',padx=3)
        ttk.Checkbutton(top,text='Follow playhead',variable=app.follow_playhead,command=lambda:self.refresh(force=True)).pack(side='right',padx=8)
        self.scroll=ScrollFrame(self,app);self.scroll.grid(row=1,column=0,sticky='nsew');self.body=self.scroll.body
        ttk.Label(self,textvariable=self.summary,style='Muted.TLabel').grid(row=2,column=0,sticky='ew',pady=2)
    def flush_history(self):
        if self.history_layer is not None and self.history_proxy is not None and self.history_span is not None:
            from instrument_model import style_dict
            self.history_span['style']=style_dict(self.history_proxy)
    def refresh(self,force=False):
        if self.app.gesture and not force:return
        l,c=self.app.get_edit_target();scope=self.scope.get();p=self.app.project;tr=p.transition(self.app.selected_transition_id)
        original_layer=l;span=None
        if l is not None and scope=='Layer' and self.app.reviewing:
            span=next((e for e in reversed(l.extra.get('treatment_history',[])) if e['start']<=self.app.playhead<e['end']),None)
        if span is not None:
            if force or self.history_span is not span:
                from instrument_model import style_from
                self.history_layer=l;self.history_span=span;self.history_proxy=style_from(span['style'],l)
            l=self.history_proxy
        else:self.history_layer=self.history_proxy=self.history_span=None
        owner=c if scope=='Clip' else tr[1] if scope=='Transition' and tr else p if scope in ('Mix','Master') else l
        key=(scope,getattr(owner,'id',None),id(owner))
        if key==self.key and not force:
            for row in self.rows:
                if row.winfo_exists():row.refresh()
            return
        self.key=key;self.owner=owner;self.rows=[]
        for w in self.body.winfo_children():w.destroy()
        grid=ttk.Frame(self.body);grid.pack(fill='both',expand=True);grid.columnconfigure(1,weight=1)
        primary=ttk.LabelFrame(grid,text='PLAYABLE CONTROLS',padding=8,width=330);primary.grid(row=0,column=0,sticky='ns',padx=(0,9));primary.columnconfigure(0,weight=1)
        effects=ttk.Frame(grid);effects.grid(row=0,column=1,sticky='nsew')
        if scope=='Mix' and p.instrument_mode:
            self.summary.set('A + B → mixer → additional channels → Master · empty channels are bypassed')
            self.parameter(primary,'A ↔ B',p.voice_mix,p)
            self.choice(primary,'Mix behaviour',p.voice_mixer_mode,['blend','crossfade'],lambda v:setattr(p,'voice_mixer_mode',v))
            self.choice(primary,'Blend',p.voice_blend,BLEND_MODES,lambda v:setattr(p,'voice_blend',v))
            ttk.Label(effects,text='Blend keeps A present and layers B over it. Crossfade travels fully from A to B.\nAdditional visual channels remain independent layers above the A/B mixer.',wraplength=600,justify='left',style='Muted.TLabel').pack(anchor='nw',padx=15,pady=20)
            return
        if scope=='Master':
            self.summary.set('Master · persistent final processing of the complete Programme')
            ttk.Label(primary,text='The master rack processes all voices.\n\nEach effect keeps its own Static, Animate or React settings.',wraplength=280,justify='left',style='Muted.TLabel').pack(anchor='w')
            self.rack(effects,p.master_rack,None);self.app.compact_widgets(self.body);return
        if scope=='Transition':
            if not tr:
                self.summary.set('Select a transition bridge or create one at a clip boundary.')
                ttk.Button(primary,text='+ Transition at current clip',command=self.app.transition_current).pack(fill='x');return
            l,t=tr;self.summary.set(f'{l.name} · {TITLES.get(t.kind,t.kind)} · {t.start:.2f} → {t.end:.2f}s')
            self.choice(primary,'Type',t.kind,TRANSITIONS,lambda v:setattr(t,'kind',v))
            self.number(primary,'Duration (s)',t.duration,lambda v:set_transition_duration(p,t.id,v))
            self.number(primary,'Edge softness',t.softness,lambda v:setattr(t,'softness',max(0,min(.5,v))))
            self.choice(primary,'Easing',t.easing,['linear','smooth','ease_in','ease_out'],lambda v:setattr(t,'easing',v))
            self.flag(primary,t,'locked','Lock transition')
            ttk.Label(effects,text='Drag the bridge edges to reshape its time span. Drag its top edge for softness.\nTransfer always completes; treatment does not leave the blend stuck halfway.',wraplength=590,justify='left',style='Muted.TLabel').pack(anchor='nw',pady=12)
            ttk.Button(effects,text='Fade-through colour…',command=lambda:self.pick_colour(t,'colour')).pack(anchor='w')
            return
        if not l:return
        if scope=='Clip' and c is None:
            self.summary.set(f'{l.name} · no clip at {self.app.format_time(self.app.playhead)}')
            ttk.Label(primary,text='Choose a clip in the strip, or assign a source to this voice.',wraplength=270).pack();return
        target=c if scope=='Clip' else l
        asset=p.asset(c.asset_id) if c else None
        self.summary.set((f'{l.name} / {asset.name if asset else "clip"} · local treatment' if scope=='Clip' else f'{l.name} · persistent treatment survives source replacement')+'   |   ● Static   ◆ Animate   ≈ React')
        flags=ttk.Frame(primary);flags.pack(fill='x',pady=(0,4));self.flag(flags,target,'locked','Lock')
        if scope=='Clip':self.flag(flags,target,'manual','Protect')
        else:self.flag(flags,target,'enabled','On');self.flag(flags,target,'solo','Solo')
        self.parameter(primary,'Opacity',target.opacity,target)
        if scope=='Clip':
            for key,label in [('scale','Scale'),('x','Position X'),('y','Position Y'),('rotation','Rotation')]:self.parameter(primary,label,getattr(c,key),c)
            timing=CollapsibleSection(primary,'Timing & source',expanded=False);timing.pack(fill='x',pady=3)
            self.number(timing.body,'Duration (s)',c.duration,lambda v:trim_clip(p,c.id,c.start,c.start+v,ripple=self.app.timeline.ripple.get()))
            self.number(timing.body,'Source in (s)',c.in_point,lambda v:slip_clip(p,c.id,v-c.in_point))
            self.choice(timing.body,'Source end',c.source_policy,['hold','loop'],lambda v:setattr(c,'source_policy',v))
        else:
            if not p.instrument_mode:self.choice(primary,'Blend below',l.blend_mode,BLEND_MODES,lambda v:setattr(l,'blend_mode',v))
        # Neospector's adjustment effects are modules now. Legacy native adjustment
        # dictionaries are migrated on project load, and must not be editable from a
        # second hidden path that can make Programme treatment invisible to the rack.
        detail=CollapsibleSection(primary,'Mask / placement',expanded=False);detail.pack(fill='x',pady=3)
        self.choice(detail.body,'Mask',target.mask.kind,['none','rectangle','ellipse','alpha','luma'],lambda v:setattr(target.mask,'kind',v))
        self.number(detail.body,'Mask width',target.mask.width,lambda v:setattr(target.mask,'width',max(.01,min(2,v))))
        self.number(detail.body,'Mask height',target.mask.height,lambda v:setattr(target.mask,'height',max(.01,min(2,v))))
        self.number(detail.body,'Feather',target.mask.feather,lambda v:setattr(target.mask,'feather',max(0,min(.3,v))))
        earlier=p.layers[:p.layers.index(original_layer)]
        if target.mask.kind in ('alpha','luma'):self.choice(detail.body,'Matte source',target.mask.layer_id,{x.name:x.id for x in earlier},lambda v:setattr(target.mask,'layer_id',v))
        self.flag(detail.body,target.mask,'invert','Invert')
        self.rack(effects,target.rack,target)
        for row in self.rows:row.refresh()
        self.app.compact_widgets(self.body)
    def rack(self,parent,rack,owner):
        bar=ttk.Frame(parent);bar.pack(fill='x',pady=(1,7));labels={s.label:k for k,s in EFFECTS.items()};ev=tk.StringVar(value='Saturation' if 'Saturation' in labels else next(iter(labels)))
        ttk.Combobox(bar,textvariable=ev,values=list(labels),state='readonly',width=16).pack(side='left');ttk.Button(bar,text='+ Effect',width=9,command=lambda:self.commit('Add effect',lambda:rack.append(make_effect(labels[ev.get()])))).pack(side='left',padx=3)
        lv=tk.StringVar(value='River Memory');ttk.Combobox(bar,textvariable=lv,values=list(LOOKS),state='readonly',width=16).pack(side='left',padx=(8,2));ttk.Button(bar,text='+ Look',width=8,command=lambda:self.commit('Add editable look',lambda:rack.extend(make_look(lv.get())))).pack(side='left',padx=3)
        ttk.Button(bar,text='Clear rack',command=lambda:self.commit('Clear rack',lambda:rack.clear())).pack(side='right')
        cards=ttk.Frame(parent);cards.pack(fill='both',expand=True)
        columns=2 if self.app.winfo_width()<1550 else 3
        for col in range(columns):cards.columnconfigure(col,weight=1,uniform='fx')
        if not rack:
            ttk.Label(cards,text='Choose a look. Then make it yours.\n\nEffects stay with this voice as its footage changes.\nUse ≈ to map any control to the soundtrack or live audio.\nKeep a rack to reuse it with different sources.',justify='left',wraplength=650,style='Muted.TLabel').pack(anchor='w',padx=14,pady=15)
        for i,fx in enumerate(rack):
            spec=EFFECTS.get(fx.kind)
            if not spec:continue
            card=ttk.LabelFrame(cards,text=f'{i+1:02d}  {spec.label}',padding=6);card.grid(row=i//columns,column=i%columns,sticky='new',padx=3,pady=4)
            controls=ttk.Frame(card);controls.pack(fill='x');enabled=tk.BooleanVar(value=fx.enabled)
            ttk.Checkbutton(controls,text='On',variable=enabled,command=lambda fx=fx,v=enabled:self.commit('Bypass effect',lambda:setattr(fx,'enabled',v.get()))).pack(side='left')
            for text,fn in [('×',lambda fx=fx:self.commit('Remove effect',lambda:rack.remove(fx))),('Copy',lambda fx=fx:self.copy_effect(rack,fx)),('→',lambda i=i:self.move_effect(rack,i,1)),('←',lambda i=i:self.move_effect(rack,i,-1)),('↺',lambda fx=fx:self.reset_effect(fx))]:ttk.Button(controls,text=text,width=4,command=fn).pack(side='right',padx=1)
            for n,(key,param) in enumerate(fx.params.items()):
                if n==0:self.parameter(card,key.replace('_',' ').title(),param,owner)
                else:
                    if n==1:details=CollapsibleSection(card,'Details',expanded=False);details.pack(fill='x')
                    self.parameter(details.body,key.replace('_',' ').title(),param,owner)
            if spec.note:self.app.add_tip(card,spec.note)

class ConductorStrip(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(4,3));self.app=app;self.seed=tk.StringVar(value=str(app.project.mutation_seed));self.scope=tk.StringVar(value='sequence');self.expand=tk.BooleanVar(value=False)
        ttk.Label(self,text='CONDUCTOR',style='Title.TLabel').pack(side='left',padx=(0,7))
        ttk.Entry(self,textvariable=self.seed,width=10).pack(side='left');ttk.Button(self,text='Randomise',width=10,command=self.randomise).pack(side='left',padx=2)
        ttk.Combobox(self,textvariable=self.scope,values=SCOPES,state='readonly',width=10).pack(side='left',padx=3)
        self.mutate_button=ttk.Button(self,text='MUTATE',style='Accent.TButton',command=app.mutate,width=9);self.mutate_button.pack(side='left',padx=2)
        ttk.Checkbutton(self,text='Evolve',variable=app.evolve,command=app.toggle_evolve).pack(side='left',padx=4)
        ttk.Button(self,text='Recipe…',width=9,command=self.recipe).pack(side='left',padx=2)
        self.summary=tk.StringVar();ttk.Label(self,textvariable=self.summary,style='Muted.TLabel').pack(side='right',padx=6)
    def randomise(self):
        import random
        seed=random.SystemRandom().randrange(1,2**31);self.seed.set(str(seed));self.app.transaction('New seed · current output unchanged',lambda:setattr(self.app.project,'mutation_seed',seed))
    def refresh(self):
        if self.app.focus_get() and str(self.app.focus_get()).startswith(str(self)):return
        self.seed.set(str(self.app.project.mutation_seed));r=self.app.project.conductor;self.summary.set(f'{r.clip_min:g}–{r.clip_max:g}s · FX {r.intensity:.0%} · React {r.reaction:.0%}')
    def recipe(self):
        w=tk.Toplevel(self.app);w.title('Conductor · direction and recipe');w.geometry('1000x570');w.minsize(850,340);w.transient(self.app)
        ttk.Label(w,text='Shape the next generation. The current performance keeps playing.',style='Title.TLabel',padding=12).pack(anchor='w')
        ConductorView(w,self.app).pack(fill='x',padx=10,pady=5)
        ttk.Label(w,text='Preferences opens transition / effect / reaction weights and exact timing. Manual edits remain protected.\nEvolve schedules future material; it never silently replaces the already-played interval.',padding=12,style='Muted.TLabel',justify='left').pack(anchor='w')
        evolution=ttk.LabelFrame(w,text='When Evolve is enabled',padding=8);evolution.pack(fill='x',padx=12,pady=4)
        for key,label,default in [('evolve_treatment','Evolve unlocked rack values',True),('evolve_sources','Change future footage',False),('evolve_sound','Continue through soundtrack library',False)]:
            value=tk.BooleanVar(value=bool(self.app.project.conductor.extra.get(key,default)))
            ttk.Checkbutton(evolution,text=label,variable=value,command=lambda k=key,v=value:self.app.transaction('Conductor evolution policy',lambda:self.app.project.conductor.extra.__setitem__(k,v.get()))).pack(side='left',padx=5)
        row=ttk.Frame(w,padding=10);row.pack(fill='x');ttk.Button(row,text='Use selected album as pool',command=self.app.use_album_pool).pack(side='left');ttk.Button(row,text='Use all media',command=lambda:self.app.transaction('All media pool',lambda:self.app.project.conductor.extra.pop('pool_ids',None))).pack(side='left',padx=7);ttk.Button(row,text='Close',command=w.destroy).pack(side='right')
