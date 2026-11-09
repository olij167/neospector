"""Playhead-following controls with one authority: the rendered project model."""
from __future__ import annotations
import copy
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from sequencer_model import Clip,Layer,Mask,new_id
from effects_engine import EFFECTS,LOOKS,BLEND_MODES,make_effect,make_look
from conductor import TRANSITIONS
from conductor_view import TITLES
from sequence_edit import trim_clip,slip_clip,move_clip,set_transition_duration
from ui_chrome import CollapsibleSection
from editor_widgets import ParameterRow,ScrollFrame


class ControlDeck(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=(5,2));self.app=app;self.key=None;self.rows=[];self.owner=None;self.columnconfigure(0,weight=1);self.rowconfigure(4,weight=1)
        top=ttk.Frame(self);top.grid(row=0,column=0,sticky='ew');ttk.Label(top,text='CONTROL DECK',style='Title.TLabel').pack(side='left')
        self.scope=tk.StringVar(value='Clip');box=ttk.Combobox(top,textvariable=self.scope,values=['Clip','Layer','Mix','Master','Transition'],state='readonly',width=11);box.pack(side='right');box.bind('<<ComboboxSelected>>',lambda e:self.refresh(force=True))
        row=ttk.Frame(self);row.grid(row=1,column=0,sticky='ew',pady=(4,0));ttk.Checkbutton(row,text='Follow playhead',variable=app.follow_playhead,command=lambda:self.refresh(force=True)).pack(side='left');ttk.Label(row,text='Off = pin selection',style='Muted.TLabel').pack(side='right')
        channel=ttk.Frame(self);channel.grid(row=2,column=0,sticky='ew',pady=3)
        for ch in ('A','B'):ttk.Radiobutton(channel,text='Channel '+ch,variable=app.selected_channel,value=ch,command=lambda:self.refresh(force=True)).pack(side='left',padx=(0,8))
        ttk.Button(channel,text='Mix',width=5,command=lambda:(self.scope.set('Mix'),self.refresh(force=True))).pack(side='right')
        self.summary=tk.StringVar();ttk.Label(self,textvariable=self.summary,style='Muted.TLabel',wraplength=310,justify='left').grid(row=3,column=0,sticky='ew',pady=(3,6))
        self.scroll=ScrollFrame(self,app);self.scroll.grid(row=4,column=0,sticky='nsew');self.body=self.scroll.body
        self.note=ttk.Label(self,text='● Static   ◆ Animate   ≈ React · click a symbol for programming',style='Muted.TLabel',wraplength=310,justify='left');self.note.grid(row=5,column=0,sticky='ew',pady=3)
    def refresh(self,force=False):
        if self.app.gesture and not force:return
        layer,clip=self.app.get_edit_target();scope=self.scope.get();tr=self.app.project.transition(self.app.selected_transition_id)
        if scope=='Transition' and not tr:
            active=[t for t in (layer.transitions if layer else []) if t.start<=self.app.playhead<t.end]
            if active:tr=(layer,active[-1])
        owner=clip if scope=='Clip' else tr[1] if scope=='Transition' and tr else layer if scope in ('Layer','Mix') else self.app.project if scope=='Master' else None
        key=(scope,getattr(layer,'id',None),getattr(owner,'id',None),id(owner))
        if key==self.key and not force:
            for row in self.rows:
                if row.winfo_exists():row.refresh()
            return
        focus=self.app.focus_get()
        if not force and focus and str(focus).startswith(str(self)) and focus.winfo_class() in ('TEntry','Entry','TCombobox','Text'):return
        self.key=key;self.rows=[];self.owner=owner
        for w in self.body.winfo_children():w.destroy()
        if scope=='Master':self.summary.set('Master output · all layers → effects');self.rack(self.body,self.app.project.master_rack,None);return
        if not layer:self.summary.set('No layer');return
        if scope=='Clip':
            if not clip:
                self.summary.set(f'{layer.name} → {self.app.selected_channel.get()} → gap at {self.app.format_time(self.app.playhead)}')
                ttk.Label(self.body,text='No clip under the playhead in this channel.',wraplength=280,justify='left').pack(anchor='w',pady=10)
                ttk.Button(self.body,text='Place selected media here',command=self.app.place_selected_asset).pack(fill='x')
                return
            asset=self.app.project.asset(clip.asset_id);self.summary.set(f'{layer.name} → {clip.channel} → {asset.name if asset else "Missing media"}')
            flags=ttk.Frame(self.body);flags.pack(fill='x');self.flag(flags,clip,'locked','Lock');self.flag(flags,clip,'timing_locked','Lock timing');self.flag(flags,clip,'manual','Protect from Mutate')
            sec=self.section('Transform',True)
            for key,label in [('opacity','Opacity'),('scale','Scale'),('x','Position X'),('y','Position Y'),('rotation','Rotation')]:self.parameter(sec,label,getattr(clip,key),clip)
            sec=self.section('Timing & source',False)
            self.number(sec,'Start (s)',clip.start,lambda v:trim_clip(self.app.project,clip.id,v,v+clip.duration))
            self.number(sec,'Duration (s)',clip.duration,lambda v:trim_clip(self.app.project,clip.id,clip.start,clip.start+v,ripple=self.app.timeline.ripple.get()))
            self.number(sec,'Source in (s)',clip.in_point,lambda v:slip_clip(self.app.project,clip.id,v-clip.in_point))
            self.number(sec,'Playback rate',clip.playback_rate,lambda v:setattr(clip,'playback_rate',max(.1,min(4,v))))
            self.choice(sec,'End of source',clip.source_policy,['hold','loop'],lambda v:setattr(clip,'source_policy',v))
            self.choice(sec,'Framing',clip.fit,['contain','cover','stretch'],lambda v:setattr(clip,'fit',v))
            self.choice(sec,'Channel',clip.channel,['A','B'],lambda v:move_clip(self.app.project,clip.id,clip.start,layer.id,v))
            self.number(sec,'Fade in (s)',clip.fade_in,lambda v:setattr(clip,'fade_in',max(0,v)))
            self.number(sec,'Fade out (s)',clip.fade_out,lambda v:setattr(clip,'fade_out',max(0,v)))
            if asset and asset.kind in ('text','shape','colour'):
                b=self.section('Text / shape source',True);ttk.Label(b,text='Source edits affect every use of this asset.',style='Muted.TLabel',wraplength=265).pack(anchor='w')
                ttk.Button(b,text='Edit source…',command=lambda:self.app.edit_asset(asset.id)).pack(fill='x')
            sec=self.section('Adjust',False)
            for key,p in clip.effects.items():self.parameter(sec,key.title(),p,clip)
            self.rack(self.body,clip.rack,clip);self.mask(clip,layer)
        elif scope in ('Layer','Mix'):
            self.summary.set(f'{layer.name} → A / B → {layer.blend_mode.replace("_"," ")} → lower layers')
            flags=ttk.Frame(self.body);flags.pack(fill='x');self.flag(flags,layer,'enabled','On');self.flag(flags,layer,'solo','Solo');self.flag(flags,layer,'locked','Lock')
            self.parameter(self.body,'Opacity',layer.opacity,layer);self.parameter(self.body,'A ↔ B',layer.mix,layer)
            self.choice(self.body,'Mixer',layer.mixer_mode,['auto','crossfade','over','matte'],lambda v:setattr(layer,'mixer_mode',v))
            ttk.Label(self.body,text='Auto follows transition bridges; Crossfade uses the A/B fader. Empty B is bypassed.',style='Muted.TLabel',wraplength=280,justify='left').pack(anchor='w',pady=3)
            self.choice(self.body,'Blend below',layer.blend_mode,BLEND_MODES,lambda v:setattr(layer,'blend_mode',v))
            sec=self.section('Adjust',True)
            for key,p in layer.effects.items():self.parameter(sec,key.title(),p,layer)
            self.rack(self.body,layer.rack,layer);self.mask(layer,layer)
        elif scope=='Transition':
            if not tr:self.summary.set('No transition here. Select a bridge or add one to a clip.');ttk.Button(self.body,text='Add transition',command=self.app.transition_current).pack(fill='x');return
            layer,transition=tr;self.summary.set(f'{layer.name} → {TITLES.get(transition.kind,transition.kind)} · {transition.duration:.3f}s')
            flag=ttk.Frame(self.body);flag.pack(fill='x');self.flag(flag,transition,'locked','Lock transition')
            self.choice(self.body,'Transition',transition.kind,TRANSITIONS,lambda v:setattr(transition,'kind',v))
            self.number(self.body,'Duration (s)',transition.duration,lambda v:set_transition_duration(self.app.project,transition.id,v))
            self.number(self.body,'Soft edge',transition.softness,lambda v:setattr(transition,'softness',max(0,min(.5,v))))
            self.choice(self.body,'Easing',transition.easing,['linear','smooth','ease_in','ease_out'],lambda v:setattr(transition,'easing',v))
            ttk.Button(self.body,text='Fade-through colour…',command=lambda:self.pick_colour(transition,'colour')).pack(fill='x',pady=5)
            ttk.Label(self.body,text='Duration extends the outgoing clip. Its Hold / Loop source rule supplies any extra source handles.',style='Muted.TLabel',wraplength=280,justify='left').pack(anchor='w',pady=6)
            ttk.Button(self.body,text='Remove transition bridge',command=lambda:self.commit('Remove transition',lambda:layer.transitions.remove(transition))).pack(fill='x',pady=8)
        for row in self.rows:row.refresh()
    def commit(self,label,fn):
        owner=self.owner
        if not self.app.can_edit(owner):return
        def do():
            fn()
            if hasattr(owner,'manual'):owner.manual=True
        self.app.transaction(label,do)
    def section(self,title,expanded):
        section=CollapsibleSection(self.body,title,expanded=expanded);section.pack(fill='x',pady=(6,0));return section.body
    def parameter(self,parent,label,param,owner):
        row=ParameterRow(parent,self.app,label,param,owner);row.pack(fill='x',pady=1);self.rows.append(row);return row
    def number(self,parent,label,value,setter):
        row=ttk.Frame(parent);row.pack(fill='x',pady=3);ttk.Label(row,text=label,width=17).pack(side='left');v=tk.StringVar(value=f'{value:.5g}');e=ttk.Entry(row,textvariable=v,width=12);e.pack(side='right',fill='x',expand=True)
        def change(event=None):
            try:
                value=float(v.get())
                import math
                if not math.isfinite(value):raise ValueError('Value must be finite')
                self.commit(label,lambda:setter(value))
            except Exception as exc:messagebox.showerror(label,str(exc),parent=self)
            return 'break'
        e.bind('<Return>',change);self.app.add_tip(e,'Press Enter to apply this value. Nothing is changed while you are typing.');return e
    def choice(self,parent,label,value,choices,setter):
        mapping=choices if isinstance(choices,dict) else {TITLES.get(v,str(v).replace('_',' ').title()):v for v in choices}
        display=next((k for k,v in mapping.items() if v==value),'Choose…' if value is None else str(value))
        row=ttk.Frame(parent);row.pack(fill='x',pady=3);ttk.Label(row,text=label,width=13).pack(side='left');v=tk.StringVar(value=display)
        box=ttk.Combobox(row,values=list(mapping),textvariable=v,state='readonly',width=14);box.pack(side='right',fill='x',expand=True)
        box.bind('<<ComboboxSelected>>',lambda e:self.commit(label,lambda:setter(mapping[v.get()])))
    def flag(self,parent,owner,attr,label):
        v=tk.BooleanVar(value=getattr(owner,attr))
        def change():
            if attr!='locked' and not self.app.can_edit(self.owner):v.set(getattr(owner,attr));return
            self.app.transaction(label,lambda:setattr(owner,attr,v.get()))
        ttk.Checkbutton(parent,text=label,variable=v,command=change).pack(side='left',padx=(0,5))
    def pick_colour(self,owner,attr):
        value=colorchooser.askcolor(getattr(owner,attr),parent=self.app,title='Choose colour')[1]
        if value:self.commit('Set colour',lambda:setattr(owner,attr,value))
    def rack(self,parent,rack,owner):
        area=CollapsibleSection(parent,'Effects rack',expanded=True);area.pack(fill='x',pady=(7,0));body=area.body
        bar=ttk.Frame(body);bar.pack(fill='x',pady=4);effect_labels={spec.label:kind for kind,spec in EFFECTS.items()};choice=tk.StringVar(value=next(iter(effect_labels)));box=ttk.Combobox(bar,textvariable=choice,values=list(effect_labels),state='readonly',width=15);box.pack(side='left',fill='x',expand=True)
        ttk.Button(bar,text='+ Effect',command=lambda:self.commit('Add effect',lambda:rack.append(make_effect(effect_labels[choice.get()])))).pack(side='right',padx=(4,0))
        looks=ttk.Frame(body);looks.pack(fill='x',pady=3);look=tk.StringVar(value=next(iter(LOOKS)));ttk.Combobox(looks,textvariable=look,values=list(LOOKS),state='readonly',width=15).pack(side='left',fill='x',expand=True)
        ttk.Button(looks,text='+ Look',command=lambda:self.commit('Add look',lambda:rack.extend(make_look(look.get())))).pack(side='right',padx=(4,0))
        if not rack:ttk.Label(body,text='Add a treatment or start from an editable Retrospector-derived look.',style='Muted.TLabel',wraplength=275,justify='left').pack(anchor='w',pady=4)
        for i,fx in enumerate(rack):
            spec=EFFECTS.get(fx.kind)
            if spec is None:
                ttk.Label(body,text=f'Unsupported effect: {fx.kind}',wraplength=260).pack();continue
            card=ttk.LabelFrame(body,text=f'{i+1}. {spec.label}',padding=(5,3));card.pack(fill='x',pady=4)
            row=ttk.Frame(card);row.pack(fill='x');enabled=tk.BooleanVar(value=fx.enabled)
            ttk.Checkbutton(row,text='On',variable=enabled,command=lambda fx=fx,v=enabled:self.commit('Bypass effect',lambda:setattr(fx,'enabled',v.get()))).pack(side='left')
            for label,cmd in [('↺',lambda fx=fx:self.reset_effect(fx)),('↑',lambda i=i:self.move_effect(rack,i,-1)),('↓',lambda i=i:self.move_effect(rack,i,1)),('Copy',lambda fx=fx:self.copy_effect(rack,fx)),('×',lambda fx=fx:self.commit('Remove effect',lambda:rack.remove(fx)))]:ttk.Button(row,text=label,width=3 if len(label)==1 else 5,command=cmd).pack(side='right',padx=1)
            for j,(key,p) in enumerate(fx.params.items()):
                if j==0:self.parameter(card,key.replace('_',' ').title(),p,owner)
                else:
                    if j==1:more=CollapsibleSection(card,'Details',expanded=False);more.pack(fill='x')
                    self.parameter(more.body,key.replace('_',' ').title(),p,owner)
            if spec.note:self.app.add_tip(card,spec.note)
    def reset_effect(self,fx):
        # Bypass preserves settings; Reset deliberately restores factory controls.
        self.commit('Reset effect',lambda:setattr(fx,'params',make_effect(fx.kind).params))
    def move_effect(self,rack,i,direction):
        j=max(0,min(len(rack)-1,i+direction))
        self.commit('Reorder effect',lambda:rack.insert(j,rack.pop(i)))
    def copy_effect(self,rack,fx):
        new=copy.deepcopy(fx);new.id=new_id('fx');self.commit('Duplicate effect',lambda:rack.insert(rack.index(fx)+1,new))
    def mask(self,owner,layer):
        section=self.section('Mask / clipping',False);m=owner.mask
        self.choice(section,'Mask',m.kind,['none','rectangle','ellipse','alpha','luma'],lambda v:setattr(m,'kind',v))
        prior=self.app.project.layers[:self.app.project.layers.index(layer)]
        if m.kind in ('alpha','luma'):
            self.choice(section,'Source layer',m.layer_id,{f'{i+1}. {l.name}':l.id for i,l in enumerate(prior)},lambda v:setattr(m,'layer_id',v))
            ttk.Label(section,text='Uses the alpha or brightness of an earlier layer without consuming channel B.',style='Muted.TLabel',wraplength=265,justify='left').pack()
        elif m.kind in ('rectangle','ellipse'):
            for key in ('width','height','x','y'):self.number(section,key.title(),getattr(m,key),lambda v,k=key:setattr(m,k,max(-2,min(2,v))))
        self.number(section,'Feather',m.feather,lambda v:setattr(m,'feather',max(0,min(.3,v))))
        row=ttk.Frame(section);row.pack(fill='x');self.flag(row,m,'invert','Invert mask')
