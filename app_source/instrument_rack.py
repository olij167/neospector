"""UX8: one pinned instrument rack, in-place controls and group navigation.

Only presentation changes here. Owner adapters, RackContext, parameter gestures,
transactions and the module compiler remain the editing authority.
"""
import tkinter as tk
from tkinter import ttk
from omne_rack import CompactRack, OwnerCell
from rack_editing import RackContext
from rack_layout import LayoutPolicy
from rack_owners import OwnerRackAdapter
from responsive_controls import FlowRow
from module_engine import label, children, expose_group_front


class InstrumentCell(OwnerCell):
    def refresh_main(self, owner):
        # Position/opacity are available deliberately; not a permanent second rack.
        if self.adapter.scope == 'Clip':
            super().refresh_main(owner)
        if getattr(self,'placement_visible',False):self.main.grid()
        elif self.main.winfo_manager():self.main.grid_remove()

    def rack(self, parent, rack, owner):
        super().rack(parent, rack, owner)
        if not getattr(self,'_responsive_resize_bound',False):
            self._responsive_resize_bound=True
            self.scroll.canvas.bind('<Configure>',self._on_pedal_viewport_resize,add='+')
        for fx in rack:
            shell, body, expand = self.card_parts[fx.id]
            ctrl = self.card_controls[fx.id]
            if fx.kind=='module':
                # A dense group face must give the bottom hardware action strip
                # its full height instead of letting Tk's last-packed footer
                # collapse beneath the fader grid.
                style=ttk.Style(self)
                style.configure('UX15.CompactAction.TButton',padding=(2,0),font=('TkDefaultFont',8))
                style.configure('UX15.CompactValue.TEntry',padding=(1,0),font=('TkFixedFont',8))
                shell.middle.configure(height=105)
                shell.middle.pack_propagate(False)
                shell.footer.configure(height=28)
                shell.footer.pack_propagate(False)
                for fader in getattr(shell,'fader_rows',[]):
                    fader.configure(padx=1,pady=0)
                    fader.entry.configure(style='UX15.CompactValue.TEntry')
                    fader.mode_button.configure(style='UX15.CompactAction.TButton')
                for widget in shell.footer.winfo_children():
                    if isinstance(widget,ttk.Button):widget.configure(style='UX15.CompactAction.TButton')
            if not hasattr(shell, 'details_host'):
                shell.details_host = ttk.Frame(shell, padding=(4, 6))
                shell.expansion_row=tk.Frame(shell,bg=shell.face[0])
                shell.companion_host.configure(highlightthickness=0, bd=0)
                # All details live inside the same module chassis.
                # UX13: deletion, duplication, chain position and protection live
                # on the pedal. No module operation depends on a popup menu.
                for item in shell.winfo_children():
                    for control in item.winfo_children():
                        if isinstance(control,ttk.Button) and control.cget('text')=='⋯':control.destroy()
                # One consistent hardware action strip. Top row is identity,
                # power and protection; bottom row is editing and removal.
                style=ttk.Style(self)
                style.configure('UX18.Delete.TButton',padding=(2,0),foreground='#ee999b',font=('TkDefaultFont',9,'bold'))
                ctrl['delete'].configure(text='×',width=3,style='UX19.Delete.TButton')
                ctrl['earlier'].pack_forget();ctrl['later'].pack_forget()
                ctrl['lock'].configure(text='LOCK')
                ctrl['lock'].pack(side='right',padx=2)
                top=shell.winfo_children()[0]
                for widget in top.winfo_children():
                    if isinstance(widget,tk.Label) and widget.cget('text')=='⠿':widget.pack_forget()
                for widget in shell.extra_controls.winfo_children():widget.destroy()
                from instrument_icons import icon
                actions=shell.footer
                # The inherited Controls button is not a normal path any more.
                ctrl['react'].pack_forget()
                buttons=(('copy','Duplicate',lambda fid=fx.id,c=RackContext.capture(self):self.duplicate_module(c,fid)),
                    ('reset','Reset',lambda fid=fx.id,c=RackContext.capture(self):self.run_edit(c,'Reset module',lambda r,f,o:__import__('module_engine').reset_effect(f),fid)),
                    ('vary','Vary',lambda fid=fx.id,c=RackContext.capture(self):self.vary_module(c,fid)))
                for kind,tip,action in buttons:
                    control=ttk.Button(actions,text='Vary' if kind=='vary' else '',
                        image='' if kind=='vary' else icon(self.app,kind),
                        width=4 if kind=='vary' else 2,command=action,
                        style='UX19.Vary.TButton' if kind=='vary' else 'UX15.CompactAction.TButton')
                    control.pack(side='left',padx=1)
                    self.app.add_tip(control,tip)
                    if kind=='copy':ctrl['duplicate']=control
                master=ttk.Button(actions,text='∿ ALL',width=6,style='UX40.ReactAll.TButton',
                    command=lambda fid=fx.id:self.toggle_module_reaction(fid))
                master.pack(side='left',padx=(3,0))
                ctrl['react_all']=master
                self.app.add_tip(master,'Enable or disable audio reactions for the entire module. Individual parameter response amounts remain separately adjustable.')
                # Shared routing takes the unused footer space. One source and
                # one band selector set every exposed parameter in ONE history
                # transaction; these do not turn capture on or erase depths.
                source_all=ttk.Button(actions,text='MIX',width=4,style='UX40.ReactAll.TButton',
                    command=lambda fid=fx.id:self.step_module_routing(fid,'source'))
                source_all.pack(side='left',padx=(2,0));ctrl['source_all']=source_all
                band_all=ttk.Button(actions,text='ALL',width=4,style='UX40.ReactAll.TButton',
                    command=lambda fid=fx.id:self.step_module_routing(fid,'band'))
                band_all.pack(side='left',padx=(1,0));ctrl['band_all']=band_all
                self.app.add_tip(source_all,'Audio signal for all parameters. Cycle between routed Mix, Song and Microphone; does not start an input.')
                self.app.add_tip(band_all,'Audio frequency response for all parameters. Cycle Full, Bass, Mid, High and Hits. Per-parameter depths remain intact.')
                ctrl['later'].configure(width=2);ctrl['earlier'].configure(width=2)
                ctrl['later'].pack(side='right',padx=1)
                ctrl['earlier'].pack(side='right',padx=1)
                self.app.add_tip(ctrl['delete'],'Remove module · Undo restores it.')
                shell.quick_tune_host=tk.Frame(shell,bg=shell.face[0],bd=0,highlightthickness=0)
                shell.bank_bar=tk.Frame(top,bg=shell.face[0])
                shell.bank_back=ttk.Button(shell.bank_bar,text='‹',width=2,command=lambda fid=fx.id:self.change_face_bank(fid,-1))
                shell.bank_back.pack(side='left')
                shell.bank_label=tk.Label(shell.bank_bar,text='1/1',font=('TkFixedFont',8),fg=shell.face[1],bg=shell.face[0]);shell.bank_label.pack(side='left',padx=1)
                shell.bank_next=ttk.Button(shell.bank_bar,text='›',width=2,command=lambda fid=fx.id:self.change_face_bank(fid,1))
                shell.bank_next.pack(side='left')
                expand.configure(text='',command=lambda:None)
                ctrl['react'].configure(command=lambda fid=fx.id:self.open_parameter(fid))
                shell.name_label.bind('<Double-1>',lambda e,fid=fx.id:self.inline_rename_group(fid) if self.effect(fid).kind=='module' else self.select_card(fid))
                self.app.add_tip(ctrl['power'],'Bypass while preserving settings.')
            # A real pedal name belongs in the same header as the power lamp.
            # This removes a whole redundant line and preserves footer height
            # even with three parameters plus their adjacent reaction strips.
            if not hasattr(shell,'ux18_header_merged'):
                header=shell.winfo_children()[0]
                shell.name_label.pack_forget()
                shell.name_label.pack(in_=header,side='left',fill='x',expand=True,padx=(3,0))
                shell.ux18_header_merged=True
            ctrl['react'].pack_forget()  # Groups have real mapped faders; no group page.
            if fx.kind=='module' and not hasattr(shell,'ungroup_button'):
                header=shell.winfo_children()[0]
                shell.ungroup_button=ttk.Button(header,text='Split',width=5,style='UX15.CompactAction.TButton',
                    command=lambda fid=fx.id,c=RackContext.capture(self):self.ungroup_module(c,fid))
                shell.ungroup_button.pack(side='right',padx=(1,2))
                self.app.add_tip(shell.ungroup_button,'Ungroup: separate these effects while preserving their control motion.')
            ctrl['react'].unbind('<Button-3>')
            from module_reaction import reaction_summary
            overall=reaction_summary(fx)['state']
            if 'react_all' in ctrl:
                master=ctrl['react_all']
                title={'off':'∿ ALL','mixed':'∿ MIX','on':'∿ ALL ●'}[overall]
                style_name='UX40.ReactAllOn.TButton' if overall=='on' else 'UX40.ReactAll.TButton'
                if master.cget('text')!=title or master.cget('style')!=style_name:
                    master.configure(text=title,style=style_name)
                master.state(['disabled' if fx.extra.get('locked') else '!disabled'])
                from ux18_reaction_surface import SOURCES,BANDS
                source_name=dict(SOURCES).get(reaction_summary(fx)['source'],'MIXED')
                band_name=dict(BANDS).get(reaction_summary(fx)['band'],'MIXED')
                for key,text in (('source_all',source_name),('band_all',band_name)):
                    control=ctrl.get(key)
                    if control is not None:
                        if control.cget('text')!=text:control.configure(text=text)
                        control.state(['disabled' if fx.extra.get('locked') else '!disabled'])
            protected=bool(fx.extra.get('variation_locked'))
            shell.name_label.configure(text=label(fx)+(' · Protected' if protected else ''))
            self.app.add_tip(shell.name_label, 'Click to select; Ctrl-click to select several adjacent modules for grouping.')
        for row in list(self.rows):
            if not getattr(row,'winfo_exists',lambda:False)() or not hasattr(row,'mode_button'):
                continue
            # The reaction toggle is the same component as the primary fader.
            row.mode_button.configure(width=3,text='∿●' if row.param.mode=='react' else '∿',
                style='Accent.TButton' if row.param.mode=='react' else 'TButton',
                command=lambda p=row.param,fid=self._effect_id_for_parameter(row.param):self.quick_reaction(fid,p))
            row.mode_button.unbind('<Button-3>')
            # UX18: slim native metrics; the old default TButton was 34 px
            # high and silently pushed every pedal's Remove strip off-screen.
            style=ttk.Style(self)
            style.configure('UX18.Reaction.TButton',padding=(0,0),font=('TkDefaultFont',7))
            style.configure('UX18.Value.TEntry',padding=(0,0),font=('TkFixedFont',8))
            style.configure('UX18.ReactionOn.TButton',padding=(0,0),font=('TkDefaultFont',7))
            row.mode_button.configure(style='UX18.ReactionOn.TButton' if row.param.mode=='react' else 'UX18.Reaction.TButton')
            row.entry.configure(style='UX18.Value.TEntry')
            # The source, band and depth are right under this same fader.
            # Switching ∿ must NEVER replace the entire module with a tune tab.
            from ux18_reaction_surface import install
            fid=self._effect_id_for_parameter(row.param)
            if fid is not None:install(self,row,fid)
        self.relayout()

    def _on_pedal_viewport_resize(self,event):
        # Card columns must follow the CURRENT rack width, not its last width
        # before the owner shrank the whole application window.
        if event.width<8 or getattr(self,'_last_pedal_viewport_width',None)==event.width:return
        self._last_pedal_viewport_width=event.width
        self.after_idle(lambda:self.relayout() if self.winfo_exists() else None)

    def _effect_id_for_parameter(self,param):
        return next((fx.id for fx in (self.target()[0] or []) if any(p is param for p in fx.params.values())),None)

    def toggle_module_reaction(self,fxid):
        from module_reaction import reaction_summary,apply_all_reactions
        fx=self.effect(fxid)
        if fx is None or fx.extra.get('locked') or not fx.params:return False
        desired=reaction_summary(fx)['state']!='on'
        context=RackContext.capture(self)
        # run_edit already performs one committed project/rack refresh; a
        # second forced refresh here caused needless geometry work.
        return self.run_edit(context,'React all module parameters' if desired else 'Stop module reactions',
            lambda rack,module,owner:apply_all_reactions(module,desired),fxid)

    def step_module_routing(self,fxid,dimension):
        from ux18_reaction_surface import SOURCES,BANDS,next_choice
        from module_reaction import apply_all_routing,reaction_summary
        fx=self.effect(fxid)
        if fx is None or fx.extra.get('locked') or not fx.params:return False
        summary=reaction_summary(fx)
        options=SOURCES if dimension=='source' else BANDS
        current=summary['source' if dimension=='source' else 'band']
        # Mixed individual routing starts at Mix / Full instead of skipping
        # straight to a later choice when the master is first pressed.
        target=next_choice(current,options) if current!='mixed' else options[0][0]
        field={'source':target} if dimension=='source' else {'band':target}
        return self.run_edit(RackContext.capture(self),'Module '+dimension+' · '+target,
            lambda rack,module,owner:apply_all_routing(module,**field),fxid)

    def quick_reaction(self,fxid,param):
        if fxid is None:return
        from live_parameter_controls import initial_reaction_changes, available_reaction_sources
        from rack_editing import update_parameter
        context=RackContext.capture(self)
        if param.mode=='react':
            self.run_edit(context,'Turn reaction off',lambda rack,fx,owner:update_parameter(param,{'mode':'static'}),fxid)
        else:
            changes=initial_reaction_changes(param,available=available_reaction_sources(self.app))
            self.run_edit(context,'Turn reaction on',lambda rack,fx,owner:update_parameter(param,changes),fxid)
        self.refresh(True)
        # The fader, source, band and depth remain visible together.
        for row in self.rows:
            if hasattr(row,'_refresh_reaction'):row._refresh_reaction()

    def toggle_tune(self,fxid,key=None):
        # Compatibility entry point; the instrument no longer has a tune page.
        # Existing scripts can ask to focus a parameter but may not conceal it.
        self.root_rack.select_owner(self)
        for row in self.rows:
            if hasattr(row,'_refresh_reaction'):row._refresh_reaction()
        return False

    def effect(self, fxid):
        return next((f for f in self.target()[0] or [] if f.id==fxid), None)

    def toggle_details(self, fxid):
        self.root_rack.select_owner(self)
        expanded=getattr(self,'expanded_module',None)
        self.expanded_module=None if expanded==fxid else fxid
        if self.expanded_module is None:self.close_tray()
        self.relayout();self.reveal_module(fxid)

    def open_parameter(self, fxid, key=None):
        if self.frozen:return super().open_parameter(fxid,key)
        fx=self.effect(fxid)
        if fx is None:return
        if fx.kind=='module':return self.select_card(fxid)  # All group controls are already on the face.
        if not fx.params:return
        key=key or next(iter(fx.params));cache=(fxid,key)
        self.close_tray()
        self.select_card(fxid);self.expanded_module=fxid
        from rack_trays import RackParameterTray
        if cache not in self.companions:
            self.companions[cache]=RackParameterTray(self.card_parts[fxid][0].companion_host,self,fx,key)
        self.tray=self.companions[cache];self.tray_mode='parameter';self.tray_key=cache
        from immediate_choices import install
        install(self.tray)
        self.tray.pack(fill='both',expand=True)
        # Deliberately no ContextualSurfaceController registration: focus elsewhere
        # does not hide an in-place edit or expose another owner accidentally.
        self.relayout();self.root_rack._sync_selected(self)
        self.after_idle(lambda:self.reveal_module(fxid) if self.winfo_exists() else None)

    def change_face_bank(self,fxid,direction):
        parts=self.card_parts.get(fxid)
        if not parts:return
        shell=parts[0]
        pages=getattr(shell,'face_pages',1)
        shell.face_page=(getattr(shell,'face_page',0)+direction)%max(1,pages)
        self._layout_face_controls(shell,getattr(shell,'wide_face',False))

    def _layout_face_controls(self,shell,wide):
        from pedal_face_layout import face_pages
        rows=getattr(shell,'fader_rows',[])
        is_group=bool(getattr(shell,'is_group',False))
        tall=bool(getattr(shell,'tall_face',False))
        per_page=12 if is_group and wide and tall else 8 if is_group and wide else 6 if tall else 3 if not wide else 6
        pages=max(1,__import__('math').ceil(len(rows)/per_page))
        shell.face_pages=pages;shell.wide_face=wide
        shell.face_page=min(getattr(shell,'face_page',0),pages-1)
        if pages>1:
            shell.bank_label.configure(text=f'{shell.face_page+1}/{pages}')
            if not shell.bank_bar.winfo_manager():shell.bank_bar.pack(side='right',padx=1)
        elif shell.bank_bar.winfo_manager():shell.bank_bar.pack_forget()
        visible=set(range(shell.face_page*per_page,min(len(rows),(shell.face_page+1)*per_page)))
        principal=shell.principal_controls
        principal.pack_configure(fill='x',expand=True,anchor='center')
        for ri in range(8):principal.rowconfigure(ri,weight=0)
        for col in range(2):principal.columnconfigure(col,weight=1 if col==0 or wide else 0)
        for i,fader in enumerate(rows):
            if i not in visible:
                if fader.winfo_manager():fader.grid_remove()
                continue
            local=i-shell.face_page*per_page
            row,col=(local//2,local%2) if wide else (local,0)
            fader.rowconfigure(0,weight=1)
            fader.grid(row=row,column=col,sticky='nsew',padx=(2 if col else 0,0),pady=1)

    def relayout(self):
        parent=getattr(self,'cards_parent',None)
        if parent is None or not parent.winfo_exists() or getattr(self,'_instrument_layout',False):return
        self._instrument_layout=True
        try:
            from pedal_face_layout import place_faces,FACE_HEIGHT,GAP
            entries=list(self.card_parts.items())
            available=max(190,self.scroll.canvas.winfo_width()-16)
            counts=[]
            for fid,(shell,_,__) in entries:
                fx=self.effect(fid)
                count=len(getattr(shell,'fader_rows',[]))
                shell.is_group=bool(fx is not None and fx.kind=='module')
                # Groups are deliberately wide even with only a few exposed macros
                # when they have a substantial internal chain.
                if fx is not None and fx.kind=='module' and len(children(fx))>=2:count=max(4,count)
                counts.append((fid,count))
            layout=place_faces(available,counts)
            self.card_columns=layout.columns
            for col in range(max(8,layout.columns+1)):
                parent.columnconfigure(col,weight=1 if col<layout.columns else 0,minsize=0,uniform='pedal' if col<layout.columns else '')
            for fid,(shell,body,button) in entries:
                row,col,span=layout.positions[fid]
                width=layout.cell_width*span+GAP*(span-1)
                tall=(layout.rowspans or {}).get(fid,1)
                height=layout.height*tall+GAP*(tall-1)
                if shell.winfo_manager()!='grid' or getattr(shell,'_rack_slot',None)!=(row,col,span,tall):
                    shell.grid(row=row,column=col,columnspan=span,rowspan=tall,sticky='nsew',padx=GAP//2,pady=3)
                shell._rack_slot=(row,col,span,tall)
                # Do not let a fixed chassis cut into its own final parameter row.
                # Geometry is derived *after* the face-bank visibility decision;
                # the surrounding RackArea already provides vertical scrolling for
                # unusually tall modules and user-authored macro groups.
                if shell.extra_controls.winfo_manager():shell.extra_controls.pack_forget()
                if hasattr(shell,'expansion_row') and shell.expansion_row.winfo_manager():shell.expansion_row.pack_forget()
                if hasattr(shell,'details_host') and shell.details_host.winfo_manager():shell.details_host.pack_forget()
                if shell.companion_host.winfo_manager():shell.companion_host.pack_forget()
                # Response view replaces the faders *in the same chassis*, never
                # adds height or forces the surrounding pedalboard to reflow.
                if hasattr(shell,'quick_tune_host') and shell.quick_tune_host.winfo_manager():
                    if body.winfo_manager():body.pack_forget()
                    shell.quick_tune_host.pack_configure(fill='x',before=shell.footer)
                else:
                    if not body.winfo_manager():body.pack(fill='both',expand=True,before=shell.footer)
                    body.pack_configure(fill='both',expand=True)
                # A grouped pedal can be wide *inside one rack column* when
                # the Module Library is open. Use the faceplate's real width,
                # not only its outer grid columnspan, to avoid false paging.
                group_wide=bool(fx is not None and fx.kind=='module' and width>=400)
                shell.tall_face=tall>1
                self._layout_face_controls(shell,span>1 or group_wide) if hasattr(shell,'bank_bar') else None
                visible=[f for f in getattr(shell,'fader_rows',[]) if f.winfo_manager()=='grid']
                face_rows=1+max((int(f.grid_info()['row']) for f in visible),default=0)
                fader_height=max((f.winfo_reqheight() for f in visible),default=36)
                # Tk's pack and grid report requested sizes at different stages
                # of a reflow. Reserve a real baseline gap above the footer and
                # use the maximum of measured face and hardware chassis height.
                face_height=max(95+(tall-1)*layout.height,face_rows*(fader_height+2)+12)
                chrome_height=sum(w.winfo_reqheight() for w in shell.pack_slaves() if w is not body)
                full_height=max(height,face_height+chrome_height+18)
                dimensions=(width,full_height,face_height)
                if getattr(shell,'_ux35_dimensions',None)!=dimensions:
                    shell.middle.configure(height=face_height)
                    shell.configure(width=width,height=full_height)
                    shell._ux35_dimensions=dimensions
                button.configure(text='')
            self.scroll.set_policy(LayoutPolicy('Grid','Wrap','Principal controls','Auto'))
            self.scroll.allow_vertical=True  # only entire *rack*, never a pedal
            if hasattr(self,'remaining_label'):self.remaining_label.grid_remove()
            if hasattr(self,'add_tile') and self.add_tile.winfo_exists():self.add_tile.grid_remove()
            self.scroll.region()
        finally:self._instrument_layout=False

    def module_menu(self, rack, fx, anchor):
        # Obsolete compatibility method: use the permanent controls on the pedal.
        return self.select_card(fx.id)


class InstrumentRack(CompactRack):
    def __init__(self,parent,app):
        self.group_path=();self.group_context=None;self.group_view=None;self._pin=None
        super().__init__(parent,app)
        self.module_grid.set(False);self.module_layout=LayoutPolicy('Grid','Wrap','Principal controls','Auto')
        self.group_host=ttk.Frame(self);self.group_host.rowconfigure(0,weight=1);self.group_host.columnconfigure(0,weight=1)
        self.group_host.grid(row=2,column=0,sticky='nsew');self.group_host.grid_remove()
        self.scope.set('Master')
        self.app.follow_playhead.set(False)
        self.scroll.canvas.bind('<Configure>',self.fit_owner_height,add='+')
        # UX32: a second, optional instrument toolbar rather than a transient
        # settings window. It remains attached to the active rack and its Undo.
        self.variation_open=False
        self.variation_seed=tk.StringVar(value='')
        self.variation_selected_only=tk.BooleanVar(value=False)
        self.variation_status=tk.StringVar(value='')
        host=self.action_toolbar.master
        self.variation_options=FlowRow(host,gap=4,padding=(5,3))
        def spin(label,var,low,high,width=4):
            part=ttk.Frame(self.variation_options)
            ttk.Label(part,text=label).pack(side='left',padx=(0,2))
            ttk.Spinbox(part,from_=low,to=high,increment=1 if label in ('Count','Seed') else 5,
                        textvariable=var,width=width).pack(side='left')
            self.variation_options.add(part)
        spin('Count',self.random_count,1,12,3)
        spin('Range %',self.random_variation,0,100,3)
        spin('Mutate %',self.mutation_variation,0,100,3)
        spin('Seed',self.variation_seed,0,2147483647,9)
        self.variation_options.add(ttk.Checkbutton(self.variation_options,text='Selected',variable=self.variation_selected_only))
        self.variation_options.add(ttk.Button(self.variation_options,text='Save',width=5,command=self.save_variation_options))
        self.variation_status_label=ttk.Label(host,textvariable=self.variation_status,style='Muted.TLabel')
        def show_feedback(*_):
            if self.variation_status.get():
                if not self.variation_status_label.winfo_manager():self.variation_status_label.pack(fill='x')
            else:self.variation_status_label.pack_forget()
        self.variation_status.trace_add('write',show_feedback)

        self.variation_button=ttk.Button(self.action_toolbar,text='⚙ Options ▾',width=11,command=self.toggle_variation_options)
        self.variation_button.pack(side='left',padx=2)
        self.app.add_tip(self.variation_button,'Show module-count, variation, mutation, seed and selected-only controls below this rack toolbar.')


    def toggle_variation_options(self,opened=None):
        wanted=not self.variation_open if opened is None else bool(opened)
        self.variation_open=wanted
        if wanted:
            self.variation_options.pack(fill='x')
            self.variation_button.configure(text='⚙ Options ▴')
        else:
            self.variation_options.pack_forget();self.variation_button.configure(text='⚙ Options ▾')
        return wanted

    def variation_settings(self):
        from omne_randomise import normalise_settings
        values=normalise_settings({**self.app.settings(),
            'module_count':self.random_count.get(),
            'variation':float(self.random_variation.get())/100,
            'mutation_variation':float(self.mutation_variation.get())/100})
        value=self.variation_seed.get().strip()
        if value:
            seed=int(value)
            if seed<0 or seed>2147483647:raise ValueError('Seed must be 0–2147483647')
        else:seed=None
        return values,seed

    def save_variation_options(self):
        try:settings,_=self.variation_settings()
        except (ValueError,TypeError) as exc:
            self.variation_status.set(str(exc));return False
        self.app.transaction('Save rack variation',lambda:self.app.project.extra.__setitem__('randomise_settings',settings))
        self.variation_status.set('Saved · current modules unchanged')
        return True

    def random_now(self,mutate=False):
        try:
            settings,seed=self.variation_settings()
            selected=None
            if mutate and self.variation_selected_only.get():
                cell=self.selected_cell()
                selected=set(cell.selected_fx) if cell else set()
                if not selected:raise ValueError('Select one or more modules before selected-only mutation')
            self.app.apply_rack_randomise(settings,mutate=mutate,selected=selected,seed=seed)
            self.variation_status.set('Mutated' if mutate else 'Randomised')
        except (ValueError,TypeError) as exc:self.variation_status.set(str(exc))

    def _make_toolbar(self):
        """One FX instrument header: current owner + five explicit actions.

        A/B/Output selection is on each source, not duplicated across this rack.
        Group appears only for a contiguous multi-selection. Save Rack moves
        into the project's File menu instead of another permanent toolbar row.
        """
        top=self.grid_slaves(row=0,column=0)[0]
        for child in top.winfo_children():child.destroy()
        top.columnconfigure(0,weight=1)
        self.breadcrumb=tk.StringVar(value='Final Output · FX')
        self.target_name=tk.StringVar(value='Final Output')
        heading=ttk.Frame(top,padding=(8,4));heading.pack(fill='x')
        self.path_label=ttk.Label(heading,textvariable=self.breadcrumb,style='PlayerName.TLabel')
        self.path_label.pack(side='left',fill='x',expand=True)
        self.rack_power_button=ttk.Button(heading,text='FX ON',width=7,command=self.direct_toggle_fx)
        self.rack_power_button.pack(side='right')
        # UX18: the workbench is an overlay that closes locally. The user can
        # swap sides to uncover whichever part of the preview they are editing.
        self.close_button=ttk.Button(heading,text='×',width=3,command=lambda:self.app.shell.collapse('Rack'))
        self.close_button.pack(side='right',padx=(0,4))
        self.flip_button=ttk.Button(heading,text='↔',width=3,command=self.app.shell.flip_rack_overlay)
        self.flip_button.pack(side='right',padx=(0,4))
        controls=ttk.Frame(top,padding=(6,0,6,4));controls.pack(fill='x')
        self.action_toolbar=controls
        from instrument_icons import icon
        self.randomise_button=ttk.Button(controls,text='Random Rack',width=12,command=lambda:self.random_now(False))
        self.randomise_button.pack(side='left',padx=1)
        self.mutate_button=ttk.Button(controls,text='Mutate',width=7,command=lambda:self.random_now(True))
        self.mutate_button.pack(side='left',padx=1)
        self.group_button=ttk.Button(controls,text='Group',width=6,command=self.group_selected)
        # Only appears with a meaningful contiguous selection.
        self.undo_button=ttk.Button(controls,text='↶',width=3,command=self.app.undo)
        self.redo_button=ttk.Button(controls,text='↷',width=3,command=self.app.redo)
        self.redo_button.pack(side='right',padx=1)
        self.undo_button.pack(side='right',padx=1)
        self.save_rack_button=ttk.Button(controls,text='Save',command=self.save_rack)
        self.more_button=ttk.Button(controls,text='⋯',command=lambda:None)
        self.add_button=ttk.Button(controls,text='+ FX',command=lambda:None)
        self.owner_buttons={r:ttk.Button(controls,text=r) for r in ('A','B','Master','Transition')}
        self.focus_button=ttk.Button(controls,text='Focus',command=lambda:self.app.shell.maximize('Rack'))
        self.back_button=ttk.Button(controls,text='Back',command=self.leave_group)
        self.scope_selector=ttk.Combobox(top,textvariable=self.target_name,state='readonly')
        self.owner_status=tk.StringVar();self.fx_enabled_var=tk.BooleanVar(value=True)
        self.primary_actions=[self.randomise_button,self.group_button]
        for button,tip in ((self.randomise_button,'Generate a different FX rack on this source.'),
                           (self.mutate_button,'Mutate unlocked settings on this source without replacing its modules.'),
                           (self.undo_button,'Undo the most recent project edit.'),
                           (self.redo_button,'Redo the most recent undone project edit.')):
            self.app.add_tip(button,tip)

    def direct_toggle_fx(self):
        self.toggle_fx_layer()
        self.rack_power_button.configure(text='FX ON' if self.fx_enabled() else 'FX OFF',
            style='TButton' if self.fx_enabled() else 'Accent.TButton')

    def fit_owner_height(self,event=None):
        if not self.winfo_exists():return
        self.scroll.canvas.itemconfigure(self.scroll.window,height=max(1,self.scroll.canvas.winfo_height()-2))
        self.relayout()

    def target(self):
        if not self._ready:return super().target()
        cell=self.selected_cell()
        return cell.target() if cell and not cell.frozen else (None,None)

    def find_clip(self,role,clip_id):
        from instrument_model import voice
        from queue_policies import visual_state_at
        layer=voice(self.app.project,role)
        if layer is None:return None
        state=layer
        clip=next((c for c in layer.clips if c.id==clip_id),None)
        if clip is None:
            state=visual_state_at(layer,self.app.playhead)
            clip=next((c for c in state.clips if c.id==clip_id),None)
        if clip is None:return None
        self._selected_clip_authority=(self.app.project,layer,state,clip)
        return layer,clip

    def refresh(self,force=False):
        if not self._ready:return
        p=self.app.project
        old=self.selected_owner_key
        retained_group=self.group_path if self._project is not None and self._project.id==p.id else ()
        replaced=self._project is not p
        if self._project is not p:
            for cell in self.owner_cells.values():cell.destroy()
            self.owner_cells={};self._project=p;self._mounted_owner=None
            self.group_path=();self.group_context=None
        adapters=[OwnerRackAdapter(self.app,p,p,'Master'),OwnerRackAdapter(self.app,p,p,'Transition')]+[OwnerRackAdapter(self.app,p,l,'Layer') for l in p.layers]
        layer,clip=self.app.get_edit_target()
        clip_state=layer
        authority=getattr(self,'_selected_clip_authority',None)
        if self.scope.get()=='Clip' and clip is None and authority:
            from queue_policies import visual_state_at
            project,source,state,chosen=authority
            if project is p and source.id==self.app.selected_layer_id and chosen.id==self.app.selected_clip_id and (state is source or visual_state_at(source,self.app.playhead) is state):
                layer,clip,clip_state=source,chosen,state
        if self.scope.get()=='Clip' and layer and clip:
            if not any(c is clip for c in layer.clips):
                from queue_policies import visual_state_at
                clip_state=visual_state_at(layer,self.app.playhead)
            adapter=OwnerRackAdapter(self.app,p,clip,'Clip',layer);adapter.queue_state=clip_state
            adapters.append(adapter)
        keys={a.key for a in adapters}
        for key,cell in list(self.owner_cells.items()):
            if key not in keys:cell.destroy();del self.owner_cells[key]
        for adapter in adapters:
            previous=self.owner_cells.get(adapter.key)
            if previous and (previous.adapter.owner is not adapter.owner or getattr(previous.adapter,'queue_state',previous.adapter.parent) is not getattr(adapter,'queue_state',adapter.parent)):
                previous.destroy();del self.owner_cells[adapter.key]
            if adapter.key not in self.owner_cells:
                self.owner_cells[adapter.key]=InstrumentCell(self.owners_host,self,adapter)
            else:self.owner_cells[adapter.key].refresh(force)
        desired=('Transition',p.id) if self.scope.get()=='Transition' else ('Master',p.id) if self.scope.get()=='Master' else ('Clip',clip.id) if self.scope.get()=='Clip' and clip else ('Layer',layer.id) if layer else ('Master',p.id)
        self.selected_owner_key=desired
        if self.scope.get()!=desired[0]:self.scope.set(desired[0])
        cell=self.selected_cell()
        if cell:
            self._sync_selected(cell)
            title=self.owner_title()
            if self.target_name.get()!=title:self.target_name.set(title)
        if replaced and retained_group and cell:
            self.group_path=retained_group;self.group_context=RackContext.capture(cell)
        if self.group_path and self.resolve_group() is None:self.group_path=();self.group_context=None
        self.refresh_toolbar_state()
        # Value/meter updates refresh the existing pedal widgets in place.
        # Only owner swaps, project restores and forced rebuilds need the
        # expensive grid/mapped-widget geometry pass.
        needs_relayout=(force or replaced or old!=desired or
                        self._mounted_owner is not cell or
                        getattr(self,'_last_layout_owner',None)!=desired)
        if needs_relayout:self.relayout()
        self._last_layout_owner=desired
        library=getattr(self.app,'module_library',None)
        if library is not None and hasattr(library,'destination_caption'):
            library.destination_caption.set('Add to '+self.owner_title())

    def select_owner(self,cell):
        changed=self.selected_owner_key!=cell.adapter.key
        # Faders select their owner on every press. With no owner change, a
        # relayout before each drag created an avoidable input-latency spike.
        if not changed:
            if self.app.follow_playhead.get():self.app.follow_playhead.set(False)
            return
        self.selected_owner_key=cell.adapter.key
        if self.scope.get()!=cell.adapter.scope:self.scope.set(cell.adapter.scope)
        if cell.adapter.scope=='Layer':self.app.selected_layer_id=cell.adapter.owner.id
        elif cell.adapter.scope=='Clip':
            self.app.selected_layer_id=cell.adapter.parent.id;self.app.selected_clip_id=cell.adapter.owner.id
        self.app.follow_playhead.set(False)
        self._sync_selected(cell)
        title=self.owner_title()
        if self.target_name.get()!=title:self.target_name.set(title)
        if changed:self.group_path=();self.group_context=None
        self.refresh_toolbar_state();self.relayout()
        library=getattr(self.app,'module_library',None)
        if library and hasattr(library,'destination_caption'):library.destination_caption.set('Add to '+self.owner_title())

    def _bypass_holder(self):
        holder,key=super()._bypass_holder()
        if self.scope.get()=='Transition' and holder is not None:
            return holder,'transition_rack_bypassed'
        return holder,key

    def toggle_fx_layer(self):
        if self.scope.get()!='Transition':return super().toggle_fx_layer()
        enable=not self.fx_enabled()
        self.app.transaction('Transition rack '+('on' if enable else 'off'),
            lambda:self.app.project.extra.__setitem__('transition_rack_bypassed',not enable))
        self.refresh_toolbar_state();self.app.refresh_all()

    def owner_title(self):
        cell=self.selected_cell()
        if not cell:return 'Choose a source'
        a=cell.adapter
        if a.scope=='Master':return 'Final Output'
        if a.scope=='Transition':return 'A/B Transition'
        if a.scope=='Layer':return 'Visual '+a.title
        asset=self.app.project.asset(a.owner.asset_id)
        return 'Visual '+a.parent.extra.get('voice',a.parent.name)+' → '+(asset.name if asset else 'Missing source')

    def refresh_toolbar_state(self):
        super().refresh_toolbar_state()
        if not hasattr(self,'breadcrumb'):return
        title=self.owner_title() if self._ready else 'Final Output'
        names=[]
        resolved=self.resolve_group() if self.group_path else None
        if resolved:
            top,node,path=resolved;names=[label(top)];cursor=top
            for fid in path:
                cursor=next(c for c in children(cursor) if c.id==fid);names.append(label(cursor))
        self.breadcrumb.set(' → '.join([title,*names] if names else [title,'Effects']))
        if hasattr(self,'back_button'):
            if self.group_path:self.back_button.pack(side='left',before=next(w for w in self.back_button.master.winfo_children() if isinstance(w,ttk.Frame)),padx=(0,6))
            else:self.back_button.pack_forget()
        for role,b in self.owner_buttons.items():
            cell=self.selected_cell() if self._ready else None
            active=bool(cell and (cell.adapter.scope==role if role in ('Master','Transition') else cell.adapter.scope in ('Layer','Clip') and role==getattr(cell.adapter.parent if cell.adapter.scope=='Clip' else cell.adapter.owner,'extra',{}).get('voice')))
            b.configure(style='Accent.TButton' if active else 'TButton')
        cell=self.selected_cell() if self._ready else None
        status=''
        if cell and cell.adapter.scope=='Transition':status='A/B bridge · active only between endpoints'
        elif cell and cell.adapter.scope!='Master':
            layer=cell.adapter.parent if cell.adapter.scope=='Clip' else cell.adapter.owner
            if not layer.enabled:status='Not in output'
            elif not self.app.playing:status='Ready · playback stopped'
            else:status='Editing live'
        elif cell:status='Final picture'
        if hasattr(self,'owner_status') and self.owner_status.get()!=status:self.owner_status.set(status)
        if hasattr(self,'group_button'):
            rack,_=self.target();ids=[i for i,f in enumerate(rack or []) if f.id in getattr(self,'selected_fx',set())]
            allowed=len(ids)>1 and ids==list(range(min(ids),max(ids)+1)) and not self.group_path
            self.group_button.configure(state='normal' if allowed else 'disabled')
            if allowed and not self.group_button.winfo_manager():self.group_button.pack(side='left',padx=1)
            elif not allowed and self.group_button.winfo_manager():self.group_button.pack_forget()
        if hasattr(self,'add_button'):self.add_button.configure(state='normal')
        if hasattr(self,'save_rack_button'):self.save_rack_button.configure(state='disabled' if self.group_path else 'normal')
        if hasattr(self,'randomise_button'):self.randomise_button.configure(state='disabled' if self.group_path else 'normal')

    def relayout(self):
        if not self._ready:return
        # No group navigation workspace: group parameters use the ordinary
        # mapped faders directly on the group pedal.
        self.group_path=();self.group_context=None
        if hasattr(self,'group_host'):self.group_host.grid_remove()
        self.scroll.grid();cell=self.selected_cell()
        for other in self.owner_cells.values():
            if other is not cell and other.winfo_manager():other.grid_remove()
        if cell:
            cell.grid(row=0,column=0,sticky='nsew');self._mounted_owner=cell
            self.owners_host.columnconfigure(0,weight=1);self.owners_host.rowconfigure(0,weight=1)
            cell.header.grid_remove();cell.state_label.grid_remove()
            if getattr(cell,'placement_visible',False):cell.main.grid()
            else:cell.main.grid_remove()
            cell.configure(width=max(400,self.scroll.canvas.winfo_width()-12))
            cell.relayout()
        self.scroll.set_policy(LayoutPolicy())

    def open_parameter(self,fxid,key=None):
        cell=self.selected_cell()
        if cell:cell.open_parameter(fxid,key);self._sync_selected(cell)

    def open_catalogue(self):
        self.app.show_module_library()
        if self.group_path:self.app.module_library.destination_caption.set('Add to '+self.breadcrumb.get())

    def group_selected(self):
        cell=self.selected_cell()
        if not cell or self.group_path:return False
        # Grouping is useful without mandatory macros. Promote deliberately later.
        from module_engine import group_effects
        rack,_=cell.target();ids=[f.id for f in rack if f.id in cell.selected_fx]
        if len(ids)<2:return False
        context=RackContext.capture(cell);created=[]
        ok=cell.run_edit(context,'Group modules',lambda r,f,o:created.append(expose_group_front(group_effects(r,ids,'New Group'))))
        if ok and created:
            cell.selected_fx={created[0].id};self._sync_selected(cell)
        return bool(ok)

    def enter_group(self,fxid):
        cell=self.selected_cell()
        if cell and cell.effect(fxid) is not None:cell.select_card(fxid)
        return False  # Legacy callers must not open a second group page.

    def leave_group(self):
        self.group_path=();self.group_context=None
        return False

    def resolve_group(self):
        if not self.group_path or self.group_context is None:return None
        cell=self.selected_cell()
        if cell is None:return None
        target=self.group_context.resolve(cell,self.group_path[0])
        if target is None:return None
        top=target[1];node=top
        for fid in self.group_path[1:]:
            node=next((f for f in children(node) if f.id==fid and f.kind=='module'),None)
            if node is None:return None
        return top,node,self.group_path[1:]

    def edit_group_parameter(self,path,key,changes):
        if self.group_view:return self.group_view.edit_parameter(path,key,changes)
        return False

    def promote_group_parameter(self,path,key):
        if self.group_view:return self.group_view.promote_parameter(path,key)
        return False

    def toggle_variation_protection(self,fxid):
        cell=self.selected_cell()
        if cell:
            context=RackContext.capture(cell)
            return cell.run_edit(context,'Protect from variation',lambda r,f,o:f.extra.__setitem__('variation_locked',not f.extra.get('variation_locked')),fxid,True)

    def integrated_menu(self):
        # Deprecated entry point retained for callers; the rack no longer
        # offers a separate menu. Editing actions live on the rack surface.
        return self.app.update_status('Rack actions are available on the surface.')

    def show_placement(self):
        cell=self.selected_cell()
        if cell:
            cell.placement_visible=not getattr(cell,'placement_visible',False)
            self.relayout()

    def refresh_navigation(self):pass
    def serialize_layout(self):return {'instrument':True,'grid':False}

    def save_named_rack(self,name,context=None):
        name=' '.join(str(name).split())
        if not name or len(name)>80:raise ValueError('Give this rack a name of 1–80 characters.')
        if context:
            cell,authority=context;target=authority.resolve(cell)
            if target is None:raise ValueError('The source project changed. Close and save the current rack again.')
            rack=target[0]
        else:rack,_=self.target()
        if rack is None:raise ValueError('Choose a rack to save.')
        from sequencer_model import _encode
        result=self.app.catalog.save_ingredient(name,'rack',{'rack':_encode(rack)})
        self.app.refresh_ingredients();self.app.update_status('Saved '+name+' to Library → Racks')
        return result

    def save_rack(self):
        cell=self.selected_cell()
        if cell is None:return
        existing=getattr(self,'save_window',None)
        if existing and existing.winfo_exists():existing.lift();return existing
        context=(cell,RackContext.capture(cell))
        w=tk.Toplevel(self.app);self.save_window=w;w.title('Save Rack');w.transient(self.app)
        body=ttk.Frame(w,padding=18);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Save',style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,text=self.owner_title()+' → Library / Racks',style='Muted.TLabel').pack(anchor='w',pady=(4,12))
        name=tk.StringVar(value='My Treatment');entry=ttk.Entry(body,textvariable=name,width=36);entry.pack(fill='x');entry.focus_set();entry.selection_range(0,'end')
        error=tk.StringVar();ttk.Label(body,textvariable=error,wraplength=340).pack(fill='x',pady=6)
        actions=ttk.Frame(body);actions.pack(fill='x',pady=(6,0))
        def save(event=None):
            try:self.save_named_rack(name.get(),context)
            except (ValueError,OSError) as exc:error.set(str(exc));return 'break'
            w.destroy();return 'break'
        ttk.Button(actions,text='Cancel',command=w.destroy).pack(side='left')
        ttk.Button(actions,text='Save',style='Accent.TButton',command=save).pack(side='right')
        w.bind('<Escape>',lambda e:w.destroy());entry.bind('<Return>',save)
        return w
