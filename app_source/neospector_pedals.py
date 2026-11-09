"""Distinct pedal faces; existing property/mapping machinery remains authoritative."""
from __future__ import annotations
import copy,random,tkinter as tk
from pedal_layout import geometry,expanded
from tkinter import ttk
from playable_rack import PlayableDeck,PlayableParameter,ModuleBuilder
from instrument_widgets import EffectsDeck
from effects_engine import EFFECTS
from module_engine import label as module_label,reset_effect

# Local faceplates are intentionally separate from the editor theme. All controls
# retain theme-derived fields, focus and numerical editing; no bundled fonts.
FACES={
 'Adjust':('#D9D4C2','#232830','#857954'),
 'Colour':('#24465E','#F0F3F5','#83C9E8'),
 'Texture':('#CFB65B','#272319','#806C35'),
 'Spatial':('#23524C','#E6F3E5','#92CDB7'),
 'Time':('#453E64','#F6EDFF','#C3ADEA'),
 'Light':('#9A4D38','#FFF3D8','#F3B082'),
 'Custom':('#4B4E53','#F5F0DC','#D8CE85'),
}

class PedalParameter(PlayableParameter):
    def __init__(self,parent,app,title,param,owner,face):
        super().__init__(parent,app,title,param,owner)
        bg,fg,accent=face
        key='Pedal'+bg[1:];style=ttk.Style(self)
        style.configure(key+'.TFrame',background=bg)
        style.configure(key+'.TLabel',background=bg,foreground=fg,font=('TkDefaultFont',10))
        self.configure(style=key+'.TFrame')
        label=self.grid_slaves(row=0,column=0)[0]
        label.configure(style=key+'.TLabel',width=0)
        label.grid(row=0,column=0,columnspan=2,sticky='w',pady=(3,1))
        self.columnconfigure(0,weight=1);self.columnconfigure(1,weight=0)
        self.scale.grid(row=1,column=0,sticky='ew',padx=(0,7));self.scale.configure(bg=bg,troughcolor=app.ui_chrome['field_bg'],activebackground=accent,length=100,sliderlength=24,width=17)
        self.entry.grid(row=1,column=1,sticky='e');self.entry.configure(width=6)
        self.mode.grid(row=0,column=2,rowspan=2,padx=(7,0));self.mode.configure(width=5)
        self.evaluated.grid(row=2,column=0,columnspan=3,sticky='e');self.evaluated.configure(style=key+'.TLabel')
        if param.mode=='static':self.evaluated.grid_remove()

class PedalDeck(PlayableDeck):
    def __init__(self,parent,app):
        super().__init__(parent,app);self.browser=None;self.card_modes=dict(app.read_preferences().get('pedal_modes',{}));self.card_parts={};self.cards_parent=None
        top=self.grid_slaves(row=0,column=0)[0]
        for w in top.winfo_children():w.destroy()
        from responsive_controls import FlowRow
        row=FlowRow(top,gap=5);row.pack(fill='x')
        row.add(ttk.Label(row,text='PEDALBOARD',style='Title.TLabel'))
        self.target_name=tk.StringVar(value='Whole picture')
        box=ttk.Combobox(row,textvariable=self.target_name,values=['Whole picture','A','B','C','D','Camera','Selected clip','A/B mixer','Transition'],width=16,state='readonly');row.add(box)
        box.bind('<<ComboboxSelected>>',self.choose_target)
        self.primary_actions=[]
        for text,fn,style in [('Randomise',app.new_treatment,'Accent.TButton'),('Mutate',app.mutate_treatment,'TButton'),('Add',self.open_catalogue,'TButton')]:
            b=ttk.Button(row,text=text,command=fn,style=style,width=9);row.add(b);self.primary_actions.append(b)
        ttk.Style(self).configure('PedalAction.TButton',padding=(4,2),font=('TkDefaultFont',9))
        self.randomise_button=self.primary_actions[0]
        row.add(ttk.Button(row,text='Keep…',command=app.keep_ingredient,width=7))
        self.scope.set('Master')
        for summary_label in self.grid_slaves(row=2,column=0):summary_label.grid_remove()
        self.bind('<Map>',lambda e:self.resized(e) if e.widget is self else None,add='+')
        self.app.add_tip(self.primary_actions[0],'Choose a new editable treatment. Locked modules and controls remain. Does not change sources or sound.')
        self.app.add_tip(self.primary_actions[1],'Keep the same modules; vary unlocked settings. Undo restores the previous result.')
    def resized(self,event):
        if not hasattr(self,'card_parts'):return
        if self.layout_job:
            try:self.after_cancel(self.layout_job)
            except tk.TclError:pass
        def finish():
            self.layout_job=None
            if not self.app.closing:self.relayout()
        self.layout_job=self.after(90,finish)
    def relayout(self):
        parent=getattr(self,'cards_parent',None)
        if parent is None or not parent.winfo_exists():return
        width=max(180,parent.winfo_width());cols,w=geometry(width,len(self.card_parts));self.card_columns=cols
        # Layout changes never reconstruct controls, values or in-progress gestures.
        for i,parts in enumerate(self.card_parts.values()):
            shell,body,button=parts;mode=self.card_modes.get(shell.fx_id,'Auto');show=expanded(mode,w)
            if mode=='Auto' and self.scroll.canvas.winfo_height()<225:show=False
            if show or mode=='Auto':
                body.pack(fill='x',before=shell.footer,padx=10,pady=0)
                for n,row in enumerate(body.winfo_children()):
                    if show or n==0:row.pack(fill='x',pady=2)
                    else:row.pack_forget()
            else:body.pack_forget()
            button.configure(text='▾' if show else '▸')
            shell.configure(width=w);shell.grid(row=i//cols,column=i%cols,sticky='nw',padx=6,pady=7)
            shell.update_idletasks()
            height=sum(child.winfo_reqheight() for child in shell.pack_slaves())+9
            shell.configure(height=height)
    def set_card_mode(self,fxid,mode):
        if mode not in ('Compact','Expanded','Auto'):raise ValueError('Choose Compact, Expanded or Auto')
        self.card_modes[fxid]=mode;self.relayout();self.app.save_preferences()
    def size_menu(self,fxid,anchor):
        menu=tk.Menu(self,tearoff=False)
        for label in ('Auto','Compact','Expanded'):menu.add_command(label=label,command=lambda v=label:self.set_card_mode(fxid,v))
        from contextual_surface import post_native_menu
        post_native_menu(self.app,menu,anchor)
    def choose_target(self,event=None):
        name=self.target_name.get()
        if name in ('A','B','C','D','Camera'):self.app.focus_voice(name)
        else:self.scope.set({'Whole picture':'Master','Selected clip':'Clip','A/B mixer':'Mix','Transition':'Transition'}[name]);self.refresh(True)
    def target(self):
        l,c=self.app.get_edit_target();scope=self.scope.get()
        if scope=='Master':return self.app.project.master_rack,self.app.project
        if scope=='Clip':return (c.rack,c) if c else (None,None)
        if scope=='Layer':
            owner=self.history_proxy if self.history_proxy is not None else l
            return (owner.rack,owner) if owner else (None,None)
        return None,None
    def refresh(self,force=False):
        if not force and not self.winfo_ismapped():return
        if hasattr(self,'target_name'):
            l,c=self.app.get_edit_target();scope=self.scope.get()
            self.target_name.set({'Master':'Whole picture','Clip':'Selected clip','Mix':'A/B mixer','Transition':'Transition'}.get(scope,l.extra.get('voice',l.name) if l else 'A'))
        super().refresh(force)
        if self.scope.get() in ('Master','Layer') and self.body.winfo_children():
            strip=self.body.winfo_children()[0]
            if isinstance(strip,ttk.Frame):strip.pack_forget()
    def rack(self,parent,rack,owner):
        self.rendered_cards=[];self.card_parts={};self.cards_parent=None
        if not rack:
            box=ttk.Frame(parent,padding=24);box.pack(fill='both',expand=True)
            ttk.Label(box,text='Shape the picture.',style='Welcome.TLabel').pack(anchor='w')
            ttk.Label(box,text='Randomise for a new reactive treatment.  Add to choose your own modules.\nEvery factory group opens into editable building blocks.',style='Muted.TLabel',justify='left').pack(anchor='w',pady=8)
            return
        cards=ttk.Frame(parent);cards.pack(fill='both',expand=True);self.cards_parent=cards;cards.bind('<Configure>',self.resized,add='+')
        cols,w=geometry(max(600,self.winfo_width()-35),len(rack))
        for i,fx in enumerate(rack):
            family=fx.extra.get('family','Custom') if fx.kind=='module' else EFFECTS.get(fx.kind).group if fx.kind in EFFECTS else 'Custom'
            face=FACES.get(family,FACES['Custom']);bg,fg,accent=face
            shell=tk.Frame(cards,bg=bg,highlightthickness=2,highlightbackground=accent,bd=2,relief='raised');shell.grid(row=i//cols,column=i%cols,sticky='nw',padx=6,pady=7);shell.fx_id=fx.id;shell.configure(width=w);shell.pack_propagate(False)
            self.rendered_cards.append(shell)
            title=tk.Canvas(shell,height=38,bg=bg,highlightthickness=0);title.pack(fill='x')
            title.create_text(12,6,text=module_label(fx),anchor='nw',fill=fg,font=('TkDefaultFont',11,'bold'))
            title.create_text(12,30,text=('EDITABLE GROUP' if fx.kind=='module' else 'BASE MODULE')+'  /  '+family.upper(),anchor='w',fill=fg,font=('TkFixedFont',8))
            # Small functional motifs communicate a family, not live processing.
            def draw_pattern(event,cv=title,fam=family,ink=accent):
                cv.delete('pattern');x=max(230,event.width-65)
                for n in range(5):
                    if fam=='Time':cv.create_rectangle(x+n*5,7+n*3,x+24+n*5,24+n*3,outline=ink,tags='pattern')
                    elif fam=='Spatial':cv.create_oval(x+n*5,7+n*2,x+30+n*3,33-n*2,outline=ink,tags='pattern')
                    else:cv.create_line(x,8+n*6,x+48-(n%2)*8,8+n*6,fill=ink,width=2,tags='pattern')
            title.bind('<Configure>',draw_pattern)
            switches=tk.Frame(shell,bg=bg);switches.pack(fill='x',padx=9,pady=(0,0))
            enabled=tk.BooleanVar(value=fx.enabled);selected=tk.BooleanVar(value=fx.id in self.selected_fx)
            tk.Checkbutton(switches,text='ON',variable=enabled,bg=bg,fg=fg,selectcolor=bg,activebackground=bg,activeforeground=fg,font=('TkDefaultFont',9),pady=0,command=lambda f=fx,v=enabled:self.commit('Module bypass',lambda:setattr(f,'enabled',v.get()))).pack(side='left')
            def select(f=fx,v=selected):self.selected_fx.add(f.id) if v.get() else self.selected_fx.discard(f.id)
            size=ttk.Button(switches,text='▾',width=2,style='PedalAction.TButton');size.configure(command=lambda f=fx,b=size:self.set_card_mode(f.id,'Compact' if b.cget('text')=='▾' else 'Expanded'));size.pack(side='right');size.bind('<Button-3>',lambda e,f=fx,b=size:self.size_menu(f.id,b));self.app.add_tip(size,'Collapse / expand this pedal. Right-click for Auto sizing. This changes layout only.')
            tk.Checkbutton(switches,text='Select',variable=selected,bg=bg,fg=fg,selectcolor=bg,activebackground=bg,activeforeground=fg,font=('TkDefaultFont',9),pady=0,command=select).pack(side='right')
            body=tk.Frame(shell,bg=bg);body.pack(fill='both',expand=True,padx=12,pady=3)
            params=list(fx.params.items());count=min(2,len(params))
            for key,p in params[:count]:
                name=fx.extra.get('labels',{}).get(key,PRIMARY_LABELS.get(fx.kind,fx.kind.replace('_',' ').title()) if key=='amount' else key.replace('_',' ').title())
                row=PedalParameter(body,self.app,name,p,owner,face);row.pack(fill='x',pady=2);self.rows.append(row)
                if fx.extra.get('locked'):
                    for ctrl in (row.scale,row.entry,row.mode):ctrl.configure(state='disabled')
            foot=tk.Frame(shell,bg=bg);foot.pack(fill='x',padx=9,pady=(1,3));shell.footer=foot;self.card_parts[fx.id]=(shell,body,size)
            ttk.Button(foot,style='PedalAction.TButton',text='Vary',width=5,command=lambda f=fx:self.app.mutate_treatment(selected={f.id})).pack(side='left')
            ttk.Button(foot,style='PedalAction.TButton',text='Reset',width=6,command=lambda f=fx:self.commit('Neutral reset',lambda:reset_effect(f))).pack(side='left',padx=3)
            ttk.Button(foot,style='PedalAction.TButton',text='Details',width=7,command=lambda f=fx:self.module_details(rack,f,owner)).pack(side='right')
            ttk.Button(foot,style='PedalAction.TButton',text='⋯',width=3,command=lambda f=fx,w=shell:self.module_menu(rack,f,w)).pack(side='right',padx=3)
            if fx.extra.get('locked'):tk.Label(shell,text='LOCKED',bg=bg,fg=fg,font=('TkFixedFont',8)).pack(anchor='e',padx=9)
        self.resized(None)
        self.summary.set('Randomise = new treatment · Mutate = vary this treatment · Details = mappings and precise control')
    def open_catalogue(self):
        rack,owner=self.target()
        if rack is None:return self.app.update_status('Choose Whole picture, a voice, or a clip to add modules.')
        # Compatibility bridge only: every Add surface now opens the one stable UX4
        # Module Library. No parallel catalogue implementation is retained.
        if hasattr(self.app,'show_module_library'):return self.app.show_module_library()
        return self.app.update_status('Module Library is unavailable in this host.')
    def add_menu(self,rack,owner,anchor):self.open_catalogue()
    def toggle_module_lock(self,fx):
        self.commit('Module lock',lambda:fx.extra.__setitem__('locked',not fx.extra.get('locked',False)))
    def module_menu(self,rack,fx,anchor):
        menu=tk.Menu(self,tearoff=False);index=rack.index(fx)
        menu.add_command(label='Unlock module' if fx.extra.get('locked') else 'Lock module',command=lambda:self.toggle_module_lock(fx))
        menu.add_separator()
        for title,command in [('Earlier in chain',lambda:self.move_effect(rack,index,-1)),('Later in chain',lambda:self.move_effect(rack,index,1)),('Duplicate',lambda:self.copy_effect(rack,fx)),('Keep this module…',lambda:self.keep_module(fx)),('Remove',lambda:self.remove_module(rack,fx))]:menu.add_command(label=title,command=command)
        if fx.kind=='module':
            from module_engine import ungroup
            menu.add_command(label='Ungroup (keep motion)',command=lambda:self.commit('Ungroup module',lambda:ungroup(rack,fx.id)))
        menu.add_separator();menu.add_command(label='Voice / output settings…',command=self.owner_details)
        from contextual_surface import post_native_menu
        post_native_menu(self.app,menu,anchor)
