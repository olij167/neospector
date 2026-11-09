"""Playable module front panels over the accepted contextual editor controls."""
from __future__ import annotations
import copy,math
import tkinter as tk
from tkinter import ttk,simpledialog,messagebox
from instrument_widgets import EffectsDeck
from editor_widgets import ParameterRow,ParameterDialog,ScrollFrame
from ui_chrome import CollapsibleSection
from module_engine import label as module_label,reset_effect,group_effects,ungroup,compile_rack,edit_group,baked_group_children
from sequencer_model import new_id,_encode
from effects_engine import EFFECTS,LOOKS,make_effect,make_look
from instrument_model import style_from
from rack_editing import RackContext

class PlayableParameter(ParameterRow):
    def __init__(self,parent,app,label,param,owner=None):
        super().__init__(parent,app,label,param,owner)
        self.scale.configure(width=15,sliderlength=24,borderwidth=0,highlightthickness=0)
        self.mode.configure(width=5);self.scale.bind('<MouseWheel>',lambda e:'break');self.scale.bind('<Button-4>',lambda e:'break');self.scale.bind('<Button-5>',lambda e:'break')
        self.scale.bind('<Double-Button-1>',lambda e:self.precise())
        self.app.add_tip(self.scale,'Drag to play. Enter a precise value on the right. React opens the response controls. Scroll does not alter this fader.')
    def precise(self):self.entry.focus_set();self.entry.selection_range(0,'end');return 'break'
    def refresh(self):
        super().refresh();self.mode.configure(text={'static':'React','animate':'Keys','react':'React ●'}.get(self.param.mode,'React'))
    def program(self):
        # One press on a static control yields real reaction. Details retain the
        # familiar full editor; the operation is reversible and never changes input.
        if not self.app.can_edit(self.owner):return
        if self.param.mode=='static':
            def do():
                self.param.mode='react';self.param.source='reaction_mix';self.param.react_band='full';self.param.react_amount=1.0;self.param.attack=.018;self.param.release=.14;self.param.threshold=.01;self.param.extra['react_full_range']=True
            self.app.transaction('React '+self.label,do);self.refresh()
        else:ParameterDialog(self.app,self.label,self.param,self.owner)

class PlayableDeck(EffectsDeck):
    def __init__(self,parent,app):
        super().__init__(parent,app);self.selected_fx=set();self.layout_job=None;self.card_columns=0
        # Replace only the header; legacy precision scopes use their tested body.
        top=self.grid_slaves(row=0,column=0)[0]
        for w in top.winfo_children():w.destroy()
        self.heading=tk.StringVar(value='A  /  MODULE RACK');ttk.Label(top,textvariable=self.heading,style='Title.TLabel').pack(side='left',padx=(0,12))
        for title,scope in [('Voice','Layer'),('Clip','Clip'),('Mix','Mix'),('Output','Master')]:ttk.Radiobutton(top,text=title,variable=self.scope,value=scope,command=lambda:self.refresh(True)).pack(side='left',padx=2)
        self.randomise_button=ttk.Button(top,text='Randomise rack',style='Accent.TButton',command=app.randomise_current_rack);self.randomise_button.pack(side='right',padx=4)
        ttk.Button(top,text='Keep…',width=7,command=app.keep_ingredient).pack(side='right',padx=3);ttk.Button(top,text='Undo',width=6,command=app.undo).pack(side='right',padx=2)
        self.bind('<Configure>',self.resized,add='+');self.bind('<Destroy>',self.cleanup,add='+')
    def cleanup(self,event):
        if event.widget is self and self.layout_job:
            try:self.after_cancel(self.layout_job)
            except tk.TclError:pass
    def resized(self,event):
        columns=max(1,int(max(300,self.winfo_width()-30)//340))
        if columns==self.card_columns:return
        if self.layout_job:
            try:self.after_cancel(self.layout_job)
            except tk.TclError:pass
        def finish():
            self.layout_job=None
            if self.app.closing or columns==self.card_columns:return
            focus=self.app.focus_get()
            if self.app.gesture or (isinstance(focus,(ttk.Entry,tk.Entry)) and str(focus).startswith(str(self))):
                # A delayed geometry adjustment must not destroy an actively
                # edited value. Retry after editing without changing its text.
                self.layout_job=self.after(140,finish);return
            self.card_columns=columns;self.refresh(True)
        self.layout_job=self.after(140,finish)
    def parameter(self,parent,label,param,owner):
        row=PlayableParameter(parent,self.app,label,param,owner);row.pack(fill='x',pady=2);self.rows.append(row);return row
    def refresh(self,force=False):
        if self.app.gesture and not force:return
        scope=self.scope.get();l,c=self.app.get_edit_target();p=self.app.project
        if scope not in ('Layer','Master'):
            self.heading.set(('MIX' if scope=='Mix' else 'CLIP' if scope=='Clip' else 'TRANSITION')+'  /  CONTROLS')
            return super().refresh(force)
        if l is None:return
        span=next((e for e in reversed(l.extra.get('treatment_history',[])) if e['start']<=self.app.playhead<e['end']),None) if scope=='Layer' and self.app.reviewing else None
        if span:
            if force or self.history_span is not span:self.history_layer=l;self.history_span=span;self.history_proxy=style_from(span['style'],l)
            l=self.history_proxy
        else:self.history_layer=self.history_proxy=self.history_span=None
        owner=p if scope=='Master' else l;rack=p.master_rack if scope=='Master' else l.rack
        key=(scope,getattr(owner,'id',None),id(owner),tuple(e.id for e in rack))
        self.heading.set(('OUTPUT' if scope=='Master' else l.name)+'  /  MODULE RACK')
        if self.key==key:
            # A forced programme refresh must not tear down an unchanged rack.
            # _OwnerRack.rack() reconciles controls/signatures in place, which
            # preserves pointer gestures and removes the visible pedalboard flash.
            try:self.rack(self.body,rack,None if scope=='Master' else l)
            except (AttributeError,tk.TclError):
                if force:pass
                else:raise
            else:
                for row in self.rows:
                    if row.winfo_exists():row.refresh()
                return
        self.selected_fx.intersection_update(e.id for e in rack);self.key=key;self.owner=owner;self.rows=[]
        for w in self.body.winfo_children():w.destroy()
        strip=ttk.Frame(self.body);strip.pack(fill='x',pady=(0,2))
        if scope=='Layer':
            level=ttk.Frame(strip);level.pack(side='left',fill='x',expand=True,padx=(0,20));self.parameter(level,'Voice level',l.opacity,l)
            self.flag(strip,l,'enabled','On');self.flag(strip,l,'locked','Lock voice')
        ttk.Button(strip,text='Voice details…' if scope=='Layer' else 'Output settings…',command=self.owner_details).pack(side='right',padx=4)
        self.rack(self.body,rack,None if scope=='Master' else l)
        self.summary.set('Persistent treatment · footage can change without rebuilding this rack.  Select adjacent modules to group.' if scope=='Layer' else 'Final Programme processing · source and voice racks remain independent.')
        for row in self.rows:row.refresh()
    def owner_details(self):
        if self.scope.get()=='Master':return self.app.sequence_settings()
        original=self.scope.get();w=tk.Toplevel(self.app);w.title(self.app.selected_layer().name+' · precise treatment');w.geometry('940x610');w.transient(self.app)
        editor=EffectsDeck(w,self.app);editor.pack(fill='both',expand=True);editor.scope.set(original);editor.refresh(True)
        ttk.Button(w,text='Done',command=lambda:(editor.flush_history(),w.destroy(),self.refresh(True))).pack(pady=5)
    def rack(self,parent,rack,owner):
        bar=ttk.Frame(parent);bar.pack(fill='x',pady=(0,3))
        ttk.Button(bar,text='+ Module',command=lambda:self.add_menu(rack,owner,bar)).pack(side='left');ttk.Button(bar,text='Group as module…',command=lambda:ModuleBuilder(self.app,self,rack)).pack(side='left',padx=5)
        ttk.Button(bar,text='Rack options ▾',command=lambda:self.rack_menu(rack,bar)).pack(side='right')
        if not rack:
            empty=ttk.Frame(parent,padding=20);empty.pack(fill='both',expand=True)
            ttk.Label(empty,text='Play the picture.',style='Title.TLabel').pack(anchor='w')
            ttk.Label(empty,text='Randomise builds a small reactive treatment.\nKeep the parts you like, or add a module of your own.',style='Muted.TLabel',justify='left').pack(anchor='w',pady=7)
            ttk.Button(empty,text='Randomise this rack',style='Accent.TButton',command=self.app.randomise_current_rack).pack(anchor='w',pady=5);return
        cards=ttk.Frame(parent);cards.pack(fill='both',expand=True);columns=max(1,min(len(rack),int(max(300,self.winfo_width()-30)//340)));self.card_columns=max(1,int(max(300,self.winfo_width()-30)//340))
        for col in range(columns):cards.columnconfigure(col,weight=1,uniform='modules')
        for i,fx in enumerate(rack):
            card=ttk.LabelFrame(cards,text=f'{i+1:02d}  {module_label(fx)}',padding=(9,5));card.grid(row=i//columns,column=i%columns,sticky='nsew',padx=4,pady=4)
            head=ttk.Frame(card);head.pack(fill='x');selected=tk.BooleanVar(value=fx.id in self.selected_fx)
            def selection(fx=fx,v=selected):self.selected_fx.add(fx.id) if v.get() else self.selected_fx.discard(fx.id)
            ttk.Checkbutton(head,text='Select',variable=selected,command=selection).pack(side='left')
            enabled=tk.BooleanVar(value=fx.enabled);ttk.Checkbutton(head,text='On',variable=enabled,command=lambda e=fx,v=enabled:self.commit('Module bypass',lambda:setattr(e,'enabled',v.get()))).pack(side='left',padx=4)
            ttk.Button(head,text='⋯',width=3,command=lambda e=fx,w=card:self.module_menu(rack,e,w)).pack(side='right')
            locked=tk.BooleanVar(value=fx.extra.get('locked',False));ttk.Checkbutton(head,text='Lock',variable=locked,command=lambda e=fx,v=locked:self.commit('Module lock',lambda:e.extra.__setitem__('locked',v.get()))).pack(side='right',padx=2)
            params=list(fx.params.items());count=min(3,len(params)) if fx.kind=='module' else min(1,len(params))
            for k,param in params[:count]:
                title=fx.extra.get('labels',{}).get(k,{'hue':'Hue','chroma_shift':'Colour split','blur':'Softness','saturation':'Saturation','contrast':'Contrast','brightness':'Brightness','gamma':'Gamma','echo':'Trail','liquid':'Warp','grain':'Grain','vignette':'Falloff','pixelate':'Block size'}.get(fx.kind,'Amount') if k=='amount' else k.replace('_',' ').title());row=self.parameter(card,title,param,owner)
                if fx.extra.get('locked'):
                    for ctrl in (row.scale,row.entry,row.mode):ctrl.configure(state='disabled')
            if not params:ttk.Label(card,text='Open to expose your own controls.',style='Muted.TLabel').pack(anchor='w',pady=8)
            footer=ttk.Frame(card);footer.pack(fill='x',pady=(4,1));ttk.Button(footer,text='Vary',width=5,command=lambda e=fx:self.app.randomise_current_rack(selected={e.id})).pack(side='left');ttk.Button(footer,text='Reset',width=6,command=lambda e=fx:self.commit('Neutral reset',lambda:reset_effect(e))).pack(side='left',padx=3);ttk.Button(footer,text='Details…',width=9,command=lambda e=fx:self.module_details(rack,e,owner)).pack(side='right')
            if fx.kind in EFFECTS and EFFECTS[fx.kind].note:self.app.add_tip(card,EFFECTS[fx.kind].note)
    def add_menu(self,rack,owner,anchor):
        menu=tk.Menu(self,tearoff=False);groups={}
        for k,spec in EFFECTS.items():
            if spec.group not in groups:groups[spec.group]=tk.Menu(menu,tearoff=False);menu.add_cascade(label=spec.group,menu=groups[spec.group])
            groups[spec.group].add_command(label=spec.label,command=lambda k=k:self.commit('Add '+k,lambda:rack.append(make_effect(k))))
        looks=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Retrospector looks',menu=looks)
        for name in LOOKS:looks.add_command(label=name,command=lambda name=name:self.commit('Add editable look',lambda:rack.extend(make_look(name))))
        from contextual_surface import post_native_menu
        post_native_menu(self.app,menu,anchor)
    def rack_menu(self,rack,anchor):
        menu=tk.Menu(self,tearoff=False);menu.add_command(label='Randomise unlocked values',command=self.app.randomise_current_rack);menu.add_command(label='Rebuild unlocked modules',command=lambda:self.app.randomise_current_rack(rebuild=True));menu.add_command(label='Keep rack / patch…',command=self.app.keep_ingredient)
        menu.add_separator();menu.add_command(label='Clear unlocked modules',command=lambda:self.commit('Clear unlocked modules',lambda:rack.__setitem__(slice(None),[e for e in rack if e.extra.get('locked')])))
        from contextual_surface import post_native_menu
        post_native_menu(self.app,menu,anchor)
    def module_menu(self,rack,fx,anchor):
        m=tk.Menu(self,tearoff=False);i=rack.index(fx)
        for title,command in [('Earlier in chain',lambda:self.move_effect(rack,i,-1)),('Later in chain',lambda:self.move_effect(rack,i,1)),('Duplicate',lambda:self.copy_effect(rack,fx)),('Keep this module…',lambda:self.keep_module(fx)),('Remove',lambda:self.remove_module(rack,fx))]:m.add_command(label=title,command=command)
        if fx.kind=='module':m.add_command(label='Ungroup (keep motion)',command=lambda:self.commit('Ungroup module',lambda:ungroup(rack,fx.id)))
        from contextual_surface import post_native_menu
        post_native_menu(self.app,m,anchor)
    def remove_module(self,rack,fx):
        if fx.extra.get('locked'):return self.app.update_status('Unlock this module before removing it.')
        self.commit('Remove module',lambda:rack.remove(fx))
    def move_effect(self,rack,index,delta):
        other=index+delta
        if not 0<=other<len(rack):return
        if rack[index].extra.get('locked') or rack[other].extra.get('locked'):return self.app.update_status('Unlock affected modules before changing their order.')
        super().move_effect(rack,index,delta)
    def keep_module(self,fx):
        name=simpledialog.askstring('Keep module','Module name:',initialvalue=module_label(fx),parent=self.app)
        if name:
            self.app.catalog.save_ingredient(name,'rack',{'rack':_encode([fx]),'scope':'module','version':1});self.app.refresh_ingredients()
            if hasattr(self.app,'refresh_module_library'):self.app.refresh_module_library()
            self.app.update_status('Module kept in the Module Library · source media not embedded')
    def module_details(self,rack,fx,owner):
        w=tk.Toplevel(self.app);w.title(module_label(fx)+' · controls');w.geometry('620x600');w.minsize(440,300);w.transient(self.app);w.bind('<Escape>',lambda e:w.destroy());scroll=ScrollFrame(w,self.app);scroll.pack(fill='both',expand=True,padx=8,pady=8)
        ttk.Label(scroll.body,text=module_label(fx),style='Title.TLabel').pack(anchor='w',pady=6)
        if fx.extra.get('locked'):ttk.Label(scroll.body,text='Module locked. Unlock it on the rack before editing.').pack();return
        for k,param in fx.params.items():
            title=fx.extra.get('labels',{}).get(k,k.replace('_',' ').title());row=ParameterRow(scroll.body,self.app,title,param,owner);row.pack(fill='x',pady=4);row.refresh()
            ttk.Button(scroll.body,text=title+' · mapping / keyframes…',command=lambda title=title,p=param:ParameterDialog(self.app,title,p,owner)).pack(anchor='e')
        if fx.kind=='module':
            from module_engine import children
            ttk.Label(scroll.body,text='Inside this module',style='Title.TLabel').pack(anchor='w',pady=(15,5))
            for sub in children(fx):ttk.Label(scroll.body,text='  '+module_label(sub)).pack(anchor='w')
            ttk.Button(scroll.body,text='Ungroup to edit individual operations',command=lambda:(self.commit('Ungroup module',lambda:ungroup(rack,fx.id)),w.destroy())).pack(fill='x',pady=10)
        ttk.Button(w,text='Done',command=lambda:(w.destroy(),self.refresh(True))).pack(pady=5)

class ModuleBuilder(ttk.Frame):
    """Advanced group front-panel editor. Group creation itself is one rack action."""
    def __init__(self,app,deck,rack,group_fx=None,*,parent=None,on_close=None):
        self.editing=group_fx is not None
        if self.editing:
            if group_fx.kind!='module':app.update_status('Choose an editable group.');return
            selected=baked_group_children(group_fx)
        else:
            # Legacy callable path retained only for migration/tests; current UX groups immediately.
            selected=[e for e in rack if e.id in deck.selected_fx]
            if not selected:app.update_status('Select adjacent modules, then Group.');return
        self._owned_window=tk.Toplevel(app) if parent is None else None
        super().__init__(parent or self._owned_window)
        self.pack(fill='both',expand=True)
        self._on_close=on_close;self._closing=False
        self.app=app;self.deck=deck;self.rack=rack;self.group_fx=group_fx;self.selected=selected;self.context=RackContext.capture(deck)
        self.bind('<Escape>',lambda e:self.destroy())
        if self._owned_window is not None:
            self._owned_window.title(('Edit group' if self.editing else 'Build a playable module')+' · Neospector')
            self._owned_window.geometry('660x630');self._owned_window.transient(app)
            self._owned_window.protocol('WM_DELETE_WINDOW',self.destroy)
        frame=ttk.Frame(self,padding=14);frame.pack(fill='both',expand=True);ttk.Label(frame,text='Edit group front panel' if self.editing else 'Give your combination a front panel.',style='Title.TLabel').pack(anchor='w');ttk.Label(frame,text='Signal order is unchanged. Choose which existing controls are promoted to the group face.',style='Muted.TLabel',wraplength=600).pack(anchor='w',pady=5)
        self.name=tk.StringVar(value=module_label(group_fx) if self.editing else 'My module');ttk.Entry(frame,textvariable=self.name).pack(fill='x',pady=6);scroll=ScrollFrame(frame,app);scroll.pack(fill='both',expand=True);self.params=[]
        mapped={};existing_order={}
        if self.editing:
            for order,(macro,targets) in enumerate(group_fx.extra.get('mappings',{}).items()):
                for target in targets:
                    identity=(target.get('effect'),target.get('parameter'))
                    mapped[identity]=group_fx.extra.get('labels',{}).get(macro,macro.replace('_',' ').title());existing_order[identity]=order
        from module_engine import priority_keys
        self.param_rows=[]
        for fx in selected:
            ttk.Label(scroll.body,text=module_label(fx),style='Title.TLabel').pack(anchor='w',pady=(8,3))
            for n,(key,param) in enumerate(fx.params.items()):
                row=ttk.Frame(scroll.body);row.pack(fill='x',pady=2);existing=mapped.get((fx.id,key));on=tk.BooleanVar(value=bool(existing) if self.editing else key in priority_keys(fx));title=tk.StringVar(value=existing or (module_label(fx) if key in priority_keys(fx) else key.replace('_',' ').title()));ttk.Checkbutton(row,text=key,variable=on,width=17).pack(side='left');ttk.Entry(row,textvariable=title).pack(side='left',fill='x',expand=True);self.params.append((fx.id,key,on,title));self.param_rows.append(row)
                ttk.Button(row,text='↑',width=2,command=lambda r=row:self.move_promotion(r,-1)).pack(side='right')
                ttk.Button(row,text='↓',width=2,command=lambda r=row:self.move_promotion(r,1)).pack(side='right')
        if existing_order:
            combined=sorted(zip(self.params,self.param_rows),key=lambda pair:existing_order.get(pair[0][:2],len(existing_order)+self.params.index(pair[0])))
            self.params[:]=[item for item,row in combined];self.param_rows[:]=[row for item,row in combined]
            for widget in self.param_rows:widget.pack_forget();widget.pack(fill='x',pady=2)
        self.error=tk.StringVar();ttk.Label(frame,textvariable=self.error,wraplength=600,style='Muted.TLabel').pack(fill='x',pady=5);self.keep=tk.BooleanVar(value=False if self.editing else True);ttk.Checkbutton(frame,text='Save reusable copy to Modules',variable=self.keep).pack(anchor='w')
        row=ttk.Frame(frame);row.pack(fill='x',pady=8);ttk.Button(row,text='Cancel',command=self.destroy).pack(side='left');ttk.Button(row,text='Save group' if self.editing else 'Create module',style='Accent.TButton',command=self.create).pack(side='right')
    def destroy(self):
        if getattr(self,'_closing',False):return
        self._closing=True
        owner=getattr(self,'_owned_window',None)
        callback=getattr(self,'_on_close',None)
        super().destroy()
        if owner is not None and owner.winfo_exists():owner.destroy()
        if callback:callback()

    def move_promotion(self,row,delta):
        index=self.param_rows.index(row);other=index+delta
        if not 0<=other<len(self.param_rows):return
        self.param_rows[index],self.param_rows[other]=self.param_rows[other],self.param_rows[index]
        self.params[index],self.params[other]=self.params[other],self.params[index]
        for widget in self.param_rows:widget.pack_forget();widget.pack(fill='x',pady=2)
    def create(self):
        current=self.context.resolve(self.deck,self.group_fx.id if self.editing else None)
        if current is None or current[0] is not self.rack:
            self.error.set('The editing target changed. Reopen Edit Group for the current rack.');return
        if not self.app.can_edit(current[2]):return
        promote=[(eid,k,title.get()) for eid,k,on,title in self.params if on.get()]
        try:
            if self.editing:
                trial=copy.deepcopy(self.group_fx);edit_group(trial,self.name.get(),promote)
                self.app.transaction('Edit group',lambda:edit_group(self.group_fx,self.name.get(),promote));result=[self.group_fx]
            else:
                trial=copy.deepcopy(self.rack);group_effects(trial,[e.id for e in self.selected],self.name.get(),promote)
                result=[];self.app.transaction('Create composed module',lambda:result.append(group_effects(self.rack,[e.id for e in self.selected],self.name.get(),promote)))
            if not result:return
            if self.keep.get():self.app.catalog.save_ingredient(self.name.get(),'rack',{'rack':_encode(result),'scope':'module','version':1});self.app.refresh_ingredients()
            self.deck.selected_fx={result[0].id};self.deck.refresh(True)
            if hasattr(self.app,'refresh_module_library'):self.app.refresh_module_library()
            self.destroy()
        except (ValueError,StopIteration) as exc:self.error.set(str(exc))
