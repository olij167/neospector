"""UX4 visual Module Library.

The Library is a stable workspace panel, not a transient Add form.  It presents
registered effects, factory groups and user-kept modules with the same family
language as the rack.  Project/rack state remains authoritative elsewhere.
"""
from __future__ import annotations
import copy, tkinter as tk
from tkinter import ttk, filedialog
from catalogue_entries import entries as factory_entries
from effects_engine import EFFECTS, make_effect
from neospector_catalog import FACTORY_GROUPS, build_group, PRIMARY_LABELS
from module_engine import compile_rack, children, label as module_label, reidentify
from sequencer_model import _effect_from
from responsive_controls import FlowRow

LIBRARY_FACES={
    'Adjust':('#1D242B','#F0ECE0','#D2B94F','◫'),
    'Colour':('#172936','#EEF7FA','#49B9E6','◉'),
    'Texture':('#2A2618','#F5ECC7','#D8B84E','▒'),
    'Spatial':('#16302D','#EAF5EB','#6EC6AC','↔'),
    'Time':('#24223A','#F4EDFC','#AD9AE5','≋'),
    'Light':('#34231D','#FFF0DA','#E29469','✦'),
    'Custom':('#22272C','#F1EEE2','#BBB172','◆'),
}


def _mine_rows(app):
    out=[]
    try:ingredients=app.catalog.ingredients()
    except Exception:return out
    for item in ingredients:
        if item.get('kind')!='rack':continue
        payload=item.get('payload') or {}
        if payload.get('scope')!='module':continue
        raw=payload.get('rack') or []
        if len(raw)!=1:continue
        try:
            fx=_effect_from(copy.deepcopy(raw[0]));compile_rack([fx])
        except Exception:continue
        family=fx.extra.get('family','Custom') if fx.kind=='module' else EFFECTS.get(fx.kind).group if fx.kind in EFFECTS else 'Custom'
        members=children(fx) if fx.kind=='module' else []
        operation_count=len(members) if members else 1
        out.append({
            'id':f"mine:{item['id']}:{item['revision']}",'name':item['name'],'type':'Mine','family':family,
            'key':item['id'],'revision':item['revision'],'effect':fx,'created':float(item.get('created',0)),
            'tags':list(fx.extra.get('tags',[])),
            'detail':('Saved group' if fx.kind=='module' else 'Saved module')+f' · {operation_count} operation'+('s' if operation_count!=1 else ''),
            'members':[module_label(x) for x in members],
            'promoted':[str(v) for _,v in sorted(fx.extra.get('labels',{}).items())],
            'operation_count':operation_count,'parameter_count':len(fx.params),
        })
    return out


def catalogue_rows(app):
    rows=[]
    transition=getattr(getattr(app,'deck',None),'scope',None)
    transition=bool(transition and transition.get()=='Transition')
    from ux16_transitions import validate_transition_rack
    for row in factory_entries():
        try:
            trial=build_group(row['key']) if row['type']=='Group' else make_effect(row['key'])
            if transition:validate_transition_rack([trial])
            elif any(op.kind.startswith('transition_') for op in compile_rack([trial])):continue
        except (ValueError,KeyError):continue
        item=dict(row);item['created']=0.0
        if row['type']=='Group':
            family,recipe=FACTORY_GROUPS[row['key']]
            item['members']=[EFFECTS[k].label for k,_ in recipe]
            item['promoted']=[PRIMARY_LABELS.get(k,EFFECTS[k].label) for k,_ in recipe[:3]]
            item['operation_count']=len(recipe);item['parameter_count']=len(item['promoted'])
            item['cue']=' → '.join(item['members'][:3])+(' → …' if len(item['members'])>3 else '')
        else:
            fx=make_effect(row['key']);item['members']=[];item['promoted']=[];item['operation_count']=1;item['parameter_count']=len(fx.params)
            item['cue']=EFFECTS[row['key']].note or 'Single processing operation'
        rows.append(item)
    for item in _mine_rows(app):
        try:
            if transition:validate_transition_rack([item['effect']])
            elif any(op.kind.startswith('transition_') for op in compile_rack([item['effect']])):continue
            rows.append(item)
        except ValueError:continue
    return rows


def effect_from_row(row):
    if row['type']=='Base':return make_effect(row['key'])
    if row['type']=='Group':return build_group(row['key'])
    if row['type']=='Mine':return reidentify(row['effect'])
    raise ValueError('Unknown Module Library entry')


class ModuleLibraryPanel(ttk.Frame):
    CARD_HEIGHT=84;CARD_EXPANDED=126
    def __init__(self,parent,app):
        super().__init__(parent,padding=(7,6));self.app=app;self._rows={};self._visible=[];self.cards={};self.expanded=set();self.selected_id='';self._search_job=None;self._layout_job=None;self._drag=None;self._generation=None
        self.conductor_selection=False;self._pool_project=None
        self.view=tk.StringVar(value=app.read_preferences().get('module_library_view','Grid'));self.columns=1
        self.query=tk.StringVar();self.category=tk.StringVar(value='All');self.family=tk.StringVar(value='All families');self.sort=tk.StringVar(value='Name')
        titlebar=ttk.Frame(self);titlebar.pack(fill='x',pady=(0,4))
        ttk.Label(titlebar,text='MODULE LIBRARY',style='Title.TLabel').pack(side='left')
        self.close_button=ttk.Button(titlebar,text='×',width=3,command=lambda:self.app.toggle_module_library(False))
        self.close_button.pack(side='right')
        head=FlowRow(self,gap=4);head.pack(fill='x')
        self.search=ttk.Entry(head,textvariable=self.query,width=14);head.add(self.search)
        self.category_box=ttk.Combobox(head,textvariable=self.category,values=('All','Effects','Groups','Mine'),state='readonly',width=8)
        for value,title in [('All','All'),('Effects','Single'),('Groups','Groups'),('Mine','Saved')]:
            head.add(ttk.Radiobutton(head,text=title,variable=self.category,value=value))
        # Filters that materially change the rack are always visible. Family
        # names participate in search; no second hidden filter hierarchy.
        self.filter_button=ttk.Button(head,text='',command=lambda:None)
        self.sort_button=ttk.Button(head,text='Sort: Name',command=self.cycle_sort)
        head.add(self.sort_button)
        self.import_recipe_button=ttk.Button(head,text='↧ Import',command=self.import_recipe)
        head.add(self.import_recipe_button)
        for value in ('Grid','List'):
            head.add(ttk.Radiobutton(head,text=value,variable=self.view,value=value,command=lambda v=value:self.set_view(v)))
        self.filter_menu=None;self.sort_menu=None
        # A direct family row, rather than nested filters or another menu.
        self.family_filter_row=FlowRow(self,gap=3);self.family_filter_row.pack(fill='x',pady=(3,2))
        self.family_buttons={}
        for family,label in [('All families','All'),('Transition','Motion'),('Colour','Colour'),('Texture','Texture'),('Spatial','Spatial'),('Adjust','Adjust'),('Light','Light'),('Time','Time'),('Custom','Custom')]:
            button=ttk.Radiobutton(self.family_filter_row,text=label,variable=self.family,value=family)
            self.family_buttons[family]=button;self.family_filter_row.add(button)
        self.family.trace_add('write',lambda *_:self.refresh())
        self.destination_caption=tk.StringVar(value='Choose a rack to add modules')
        ttk.Label(self,textvariable=self.destination_caption,style='PlayerName.TLabel',padding=(4,5)).pack(fill='x')
        self.group_tools=FlowRow(self,gap=3);self.group_tools.pack(fill='x',pady=(0,3))
        self.group_button=ttk.Button(self.group_tools,text='▣ Group',width=9,command=self.open_group_tools)
        self.group_tools.add(self.group_button)
        self.edit_group_button=ttk.Button(self.group_tools,text='✎ Edit group',width=12,command=self.edit_selected_group)
        self.group_tools.add(self.edit_group_button)
        self.variation_button=ttk.Button(self.group_tools,text='⚙ Random / Mutate',width=17,command=self.open_variation_tools)
        self.group_tools.add(self.variation_button)
        app.add_tip(self.group_button,'Select at least two adjacent rack modules, then group them as an editable module.')
        app.add_tip(self.edit_group_button,'Open the attached Controls companion of a selected group.')
        app.add_tip(self.variation_button,'Set random module count, variation and mutation strength without altering sources.')
        self.pool_banner=ttk.Frame(self)
        self.pool_text=tk.StringVar(value='Conductor pool')
        ttk.Label(self.pool_banner,textvariable=self.pool_text,style='PlayerName.TLabel').pack(side='left')
        ttk.Button(self.pool_banner,text='Done',command=self.finish_conductor_selection).pack(side='right')
        self.canvas=tk.Canvas(self,bg=app.ui_chrome.get('preview_bg','#11161B'),highlightthickness=0,bd=0)
        self.vbar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview);self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.pack(side='left',fill='both',expand=True,pady=(6,0));self.vbar.pack(side='right',fill='y',pady=(6,0))
        self.host=tk.Frame(self.canvas,bg=app.ui_chrome.get('preview_bg','#11161B'));self.window=self.canvas.create_window((0,0),window=self.host,anchor='nw')
        self.host.bind('<Configure>',self._host_configure);self.canvas.bind('<Configure>',self._canvas_configure)
        self._bind_wheel(self.canvas);self._bind_wheel(self.host)
        self.query.trace_add('write',self._queue_search);self.category.trace_add('write',lambda *_:self.refresh())
        self.bind('<Map>',lambda e:self.refresh(force=True) if e.widget is self else None,add='+')
        self.refresh(force=True)
    def open_group_tools(self):
        if self.app.deck.group_selected():
            self.app.update_status('Group created. Select the new group, then Edit group for internal controls.')
            return True
        self.app.update_status('Choose two or more neighbouring modules in the rack to create a group.')
        return False
    def edit_selected_group(self):
        deck=self.app.deck;cell=deck.selected_cell()
        if cell is None:return self.app.update_status('Select a group in the rack first.')
        rack,_=cell.target()
        selected=[fx for fx in rack or () if fx.id in cell.selected_fx and fx.kind=='module']
        if len(selected)!=1:return self.app.update_status('Select one group in the rack to edit its controls.')
        cell.open_parameter(selected[0].id)
        return True
    def open_variation_tools(self):
        self.app.open_effects_context(getattr(self.app,'rack_context_role','Master'))
        self.app.deck.toggle_variation_options(True)
        return True
    def import_recipe(self,path=None):
        if not path:
            path=filedialog.askopenfilename(parent=self.app,title='Import editable module recipe',
                filetypes=[('Neospector module recipe','*.json'),('JSON','*.json')])
        if not path:return False
        try:
            from module_recipe_io import read_recipe
            from sequencer_model import _encode
            fx=read_recipe(path)
            saved=self.app.catalog.save_ingredient(fx.extra.get('name','Imported module'),'rack',
                {'scope':'module','rack':_encode([fx])})
            self.refresh(force=True)
            self.app.update_status('Imported editable module: '+saved['name'])
            return True
        except (ValueError,OSError,TypeError,KeyError) as exc:
            self.app.update_status('Recipe import rejected: '+str(exc))
            return False

    def _bind_wheel(self,widget):
        widget.bind('<MouseWheel>',self._wheel,add='+');widget.bind('<Button-4>',self._wheel,add='+');widget.bind('<Button-5>',self._wheel,add='+')
    def _wheel(self,event):
        try:
            if not self.winfo_ismapped():return
            direction=-1 if getattr(event,'num',0)==4 or getattr(event,'delta',0)>0 else 1
            self.canvas.yview_scroll(direction,'units');return 'break'
        except tk.TclError:return
    def _queue_search(self,*_):
        if self._search_job:
            try:self.after_cancel(self._search_job)
            except tk.TclError:pass
        self._search_job=self.after(140,self.refresh)
    def _host_configure(self,event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
    def _canvas_configure(self,event):
        self.canvas.itemconfigure(self.window,width=max(1,event.width));self._queue_layout()
    def _queue_layout(self):
        if self._layout_job:
            try:self.after_cancel(self._layout_job)
            except tk.TclError:pass
        self._layout_job=self.after_idle(self._layout)
    def _families(self):return sorted({r['family'] for r in self._rows.values()})
    def cycle_sort(self):
        values=('Name','Family','Recent')
        next_value=values[(values.index(self.sort.get())+1)%len(values)]
        self.sort.set(next_value)
        self.sort_button.configure(text='Sort: '+next_value)
        self.refresh()
    def _rebuild_filter_menu(self):
        available={r['family'] for r in self._rows.values()}
        if self.family.get()!='All families' and self.family.get() not in available:
            self.family.set('All families')
        for key,button in self.family_buttons.items():
            # FlowRow positions its existing child controls, preserving focus.
            # Hidden unneeded families do not create vacant hit targets.
            button.configure(state='normal' if key=='All families' or key in available else 'disabled')
    def refresh(self,force=False):
        if hasattr(self.app,'deck'):
            self.destination_caption.set('Add to '+(self.app.deck.breadcrumb.get() if getattr(self.app.deck,'group_path',()) else self.app.deck.target_name.get()))
        if self.conductor_selection and self._pool_project is not self.app.project:
            if getattr(self._pool_project,'id',None)==self.app.project.id:self._pool_project=self.app.project
            else:self.finish_conductor_selection()
        if self.conductor_selection:self._refresh_pool_banner()
        self._search_job=None
        generation=(getattr(self.app.catalog,'generation',None),getattr(self.app,'project',None).id if getattr(self.app,'project',None) else None,getattr(self.app.deck.scope,'get',lambda:'' )() if hasattr(self.app,'deck') else None)
        if force or generation!=self._generation:
            self._generation=generation;self._rows={r['id']:r for r in catalogue_rows(self.app)}
            for rid in tuple(self.cards):
                if rid not in self._rows:
                    try:self.cards[rid].destroy()
                    except tk.TclError:pass
                    self.cards.pop(rid,None);self.expanded.discard(rid)
            self._rebuild_filter_menu()
        q=self.query.get().strip().casefold();category=self.category.get();family=self.family.get()
        rows=[]
        for row in self._rows.values():
            if category=='Effects' and row['type']!='Base':continue
            if category=='Groups' and row['type']!='Group':continue
            if category=='Mine' and row['type']!='Mine':continue
            if family!='All families' and row['family']!=family:continue
            hay=' '.join([row['name'],row['family'],row.get('detail','')]+list(row.get('members',[]))+list(row.get('tags',[]))).casefold()
            if q and q not in hay:continue
            rows.append(row)
        order=self.sort.get()
        if order=='Family':rows.sort(key=lambda r:(r['family'].casefold(),r['name'].casefold(),r['id']))
        elif order=='Recent':rows.sort(key=lambda r:(-float(r.get('created',0)),r['name'].casefold(),r['id']))
        else:rows.sort(key=lambda r:(r['name'].casefold(),r['family'].casefold(),r['id']))
        self._visible=[r['id'] for r in rows]
        for row in rows:
            if row['id'] not in self.cards:self.cards[row['id']]=self._make_card(row)
            else:self.cards[row['id']].row=row;self._draw_card(self.cards[row['id']])
        visible=set(self._visible)
        for rid,card in self.cards.items():
            if rid not in visible:card.grid_remove()
        self._layout()
        if self.selected_id not in visible:self.selected_id=self._visible[0] if self._visible else ''
        self._paint_selection()
    def set_view(self,value):
        if value not in ('Grid','List'):raise ValueError('Choose Grid or List')
        self.view.set(value)
        # Preference only; presentation never enters project undo or changes media.
        self.app.module_library_view=value;self.app.save_preferences()
        self._layout()
    def _layout(self):
        self._layout_job=None;width=max(220,self.canvas.winfo_width())
        cols=1 if self.view.get()=='List' else max(1,min(4,width//250))
        self.columns=cols
        for col in range(4):self.host.columnconfigure(col,weight=1 if col<cols else 0,uniform='module-library' if col<cols else '',minsize=0)
        for i,rid in enumerate(self._visible):
            card=self.cards.get(rid)
            if card:
                card.grid(row=i//cols,column=i%cols,sticky='nsew',padx=3,pady=2 if self.view.get()=='List' else 4)
                self._draw_card(card)
        self.host.update_idletasks();self.canvas.configure(scrollregion=self.canvas.bbox('all'))
    def _make_card(self,row):
        fam=row.get('family','Custom');bg,fg,accent,_=LIBRARY_FACES.get(fam,LIBRARY_FACES['Custom'])
        card=tk.Canvas(self.host,height=self.CARD_HEIGHT,bg=bg,highlightthickness=2,highlightbackground=accent,bd=0,takefocus=1,cursor='hand2');card.row=row;self._bind_wheel(card)
        card.bind('<Configure>',lambda e,c=card:self._draw_card(c));card.bind('<Button-1>',lambda e,c=card:self._press_card(c,e));card.bind('<B1-Motion>',lambda e,c=card:self._drag_card(c,e));card.bind('<ButtonRelease-1>',lambda e,c=card:self._release_card(c,e));card.bind('<Double-1>',lambda e,c=card:self.activate_row(c.row));card.bind('<Return>',lambda e,c=card:self.activate_row(c.row));card.bind('<space>',lambda e,c=card:self.add_row(c.row));card.bind('<Button-3>',lambda e,c=card:self.add_row(c.row));card.bind('<Key-Up>',lambda e:self._key_move(-1));card.bind('<Key-Down>',lambda e:self._key_move(1));card.bind('<Key-Left>',lambda e:self._key_move(-1));card.bind('<Key-Right>',lambda e:self._key_move(1))
        self._draw_card(card);return card
    def _draw_card(self,card):
        row=card.row;fam=row.get('family','Custom');bg,fg,accent,icon=LIBRARY_FACES.get(fam,LIBRARY_FACES['Custom']);w=max(210,card.winfo_width());expanded=row['id'] in self.expanded and bool(row.get('members'))
        if self.view.get()=='List':
            card.configure(height=100 if expanded else 54,bg=bg);card.delete('all')
            card.create_rectangle(0,0,5,120,fill=accent,outline='')
            card.create_text(14,17,text=row['name'],anchor='w',fill=fg,font=('TkDefaultFont',10,'bold'),width=max(100,w-75))
            card.create_text(14,38,text=fam+' · '+('Effect' if row['type']=='Base' else row['type'])+(' · '+str(row.get('operation_count',1))+' ops' if row.get('members') else ''),anchor='w',fill=accent,font=('TkDefaultFont',8))
            card.create_text(w-24,16,text=self._add_glyph(row),fill=fg,font=('TkDefaultFont',15,'bold'))
            if row.get('members'):
                card.create_text(w-24,40,text='▾' if expanded else '▸',fill=accent,font=('TkDefaultFont',11,'bold'))
                if expanded:card.create_text(14,64,text=' → '.join(row['members']),anchor='nw',fill=fg,font=('TkDefaultFont',8),width=max(100,w-28))
            return
        card.configure(height=self.CARD_EXPANDED if expanded else self.CARD_HEIGHT,bg=bg);card.delete('all')
        card.create_rectangle(0,0,w,24,fill=accent,outline='');card.create_text(8,12,text=icon,fill=bg,font=('TkDefaultFont',11,'bold'))
        type_label='EFFECT' if row['type']=='Base' else 'MINE' if row['type']=='Mine' else 'GROUP'
        card.create_text(28,12,text=type_label+' · '+fam.upper(),anchor='w',fill=bg,font=('TkFixedFont',8,'bold'))
        self._draw_motif(card,row,w-72,28,accent)
        name_item=card.create_text(9,29,text=row['name'],anchor='nw',fill=fg,font=('TkDefaultFont',10,'bold'),width=max(90,w-100))
        name_bottom=max(49,card.bbox(name_item)[3])
        count=int(row.get('operation_count',len(row.get('members',[])) or 1));cue=row.get('cue') or row.get('detail','');cue=cue.split(' · ',1)[-1] if ' · ' in cue and not row.get('cue') else cue
        if len(cue)>62:cue=cue[:59]+'…'
        cue_item=card.create_text(9,name_bottom+4,text=cue,anchor='nw',fill=fg,font=('TkDefaultFont',8),width=max(90,w-100))
        detail_bottom=max(74,card.bbox(cue_item)[3]);card_height=max(self.CARD_HEIGHT,detail_bottom+10)
        card.configure(height=card_height)
        card.create_text(w-15,12,text=self._add_glyph(row),fill=bg,font=('TkDefaultFont',15,'bold'),tags='plus')
        if row.get('members'):
            card.create_text(w-25,card_height-15,text=('▾' if expanded else '▸'),fill=accent,font=('TkDefaultFont',11,'bold'),tags='fold')
            card.create_text(w-45,card_height-15,text=f'{count} op'+('s' if count!=1 else ''),anchor='e',fill=fg,font=('TkFixedFont',7))
        else:
            params=int(row.get('parameter_count',0));label=f'{params} param'+('s' if params!=1 else '') if params else '1 op'
            card.create_text(w-9,card_height-15,text=label,anchor='e',fill=accent,font=('TkFixedFont',7,'bold'))
        if expanded:
            raw_members=list(row.get('members',[]));members='  →  '.join(raw_members[:8])+('  →  +'+str(len(raw_members)-8)+' more' if len(raw_members)>8 else '');promoted=', '.join(row.get('promoted',[]))
            divider=card_height;card.configure(height=max(self.CARD_EXPANDED,divider+72))
            card.create_line(8,divider,w-8,divider,fill=accent)
            card.create_text(9,divider+9,text=members,anchor='nw',fill=fg,font=('TkDefaultFont',8),width=max(110,w-18))
            if promoted:card.create_text(9,divider+36,text='Front: '+promoted,anchor='nw',fill=accent,font=('TkDefaultFont',8,'bold'),width=max(110,w-18))
    def _draw_motif(self,card,row,x,y,colour):
        import math
        kind=str(row.get('key',row.get('id',''))).lower();family=row.get('family','')
        if 'tile' in kind or 'pixel' in kind or family=='Texture':
            for i in range(3):
                for j in range(3):card.create_rectangle(x+i*15,y+j*13,x+i*15+11,y+j*13+9,outline=colour)
        elif family=='Time':
            for i in range(4):card.create_oval(x+i*7,y+i*4,x+29+i*7,y+25+i*4,outline=colour)
        elif family=='Colour':
            for i in range(4):card.create_rectangle(x+i*12,y,x+i*12+9,y+36,fill=['#a1d8d1','#bd99dc','#d4669b','#e6ca73'][i],outline='')
        else:
            points=[]
            for i in range(25):points.extend((x+i*2,y+20+math.sin(i*.4)*14))
            card.create_line(*points,fill=colour,width=2,smooth=True)

    def _select(self,card,focus=True):
        self.selected_id=card.row['id'];self._paint_selection()
        if focus:
            try:card.focus_set()
            except tk.TclError:pass
    def _paint_selection(self):
        accent=self.app.ui_chrome.get('accent','#D8CE85')
        for rid,card in self.cards.items():
            if not card.winfo_exists():continue
            fam=card.row.get('family','Custom');normal=LIBRARY_FACES.get(fam,LIBRARY_FACES['Custom'])[2]
            card.configure(highlightthickness=3 if rid==self.selected_id else 2,highlightbackground=accent if rid==self.selected_id else normal)
    def _press_card(self,card,event):
        self._select(card);self._drag={'card':card,'x':event.x_root,'y':event.y_root,'active':False}
        if event.x>=card.winfo_width()-48 and event.y>(28 if self.view.get()=='List' else 48) and card.row.get('members'):
            rid=card.row['id'];self.expanded.discard(rid) if rid in self.expanded else self.expanded.add(rid);self._draw_card(card);self._layout();self._drag=None;return 'break'
        if event.x>=card.winfo_width()-48 and event.y<(28 if self.view.get()=='List' else 52):
            self._drag=None;self.add_row(card.row);return 'break'
    def _drag_card(self,card,event):
        if not self._drag:return
        if abs(event.x_root-self._drag['x'])+abs(event.y_root-self._drag['y'])>8:
            self._drag['active']=True
            try:index=self.app.module_library_drop_index(event.x_root,event.y_root)
            except Exception:index=None
            self.app.update_status(('Insert '+card.row['name']+' at rack position '+str(index+1)+'.') if index is not None else 'Drag to the selected rack to insert '+card.row['name']+' at an exact position.')
    def _release_card(self,card,event):
        drag=self._drag;self._drag=None
        if not drag or not drag.get('active'):return
        try:index=self.app.module_library_drop_index(event.x_root,event.y_root)
        except Exception:index=None
        if index is None:self.app.update_status('Drop over the selected rack to insert the module.');return
        self.add_row(card.row,index=index)
    def _key_move(self,delta):
        if not self._visible:return 'break'
        try:i=self._visible.index(self.selected_id)
        except ValueError:i=0
        rid=self._visible[max(0,min(len(self._visible)-1,i+delta))];card=self.cards[rid];self._select(card);self.canvas.yview_moveto(max(0,card.winfo_y()/max(1,self.host.winfo_height())));return 'break'
    def _context(self,card,event):
        self._select(card)
        return self.add_row(card.row)
    def _toggle_expand(self,rid):
        self.expanded.discard(rid) if rid in self.expanded else self.expanded.add(rid);self._draw_card(self.cards[rid]);self._layout()
    def _export_mine(self,row):
        path=filedialog.asksaveasfilename(parent=self.app,title='Export saved module',defaultextension='.omne-ingredient.json')
        if path:self.app.catalog.export_ingredient(row['key'],path,row['revision']);self.app.update_status('Module exported.')
    def activate_row(self,row):
        if self.conductor_selection:
            from composition_queue import state
            if row['id'] in state(self.app.project).get('pool_ids',[]):return 'break'
        self.add_row(row)
        return 'break'
    def add_row(self,row,index=None):
        if self.conductor_selection and index is None:return self.toggle_pool_row(row)
        try:fx=effect_from_row(row);compile_rack([fx])
        except Exception as exc:return self.app.update_status(str(exc))
        return self.app.insert_module_from_library(fx,row['name'],index=index,entry_type=row.get('type','Base'))
    def _add_glyph(self,row):
        if not self.conductor_selection:return '+'
        from composition_queue import state
        return '☑' if row['id'] in state(self.app.project).get('pool_ids',[]) else '☐'
    def begin_conductor_selection(self):
        self.conductor_selection=True;self._pool_project=self.app.project
        self.pool_banner.pack(fill='x',pady=3,before=self.canvas);self._refresh_pool_banner();self.refresh()
    def finish_conductor_selection(self):
        if not self.conductor_selection:return
        self.conductor_selection=False;self._pool_project=None;self.pool_banner.pack_forget()
        for card in self.cards.values():self._draw_card(card)
    def _refresh_pool_banner(self):
        from composition_queue import state
        s=state(self.app.project)
        self.pool_text.set('Conductor · '+('All groups' if s.get('pool_mode','all')=='all' else str(len(s.get('pool_ids',[])))+' selected'))
    def toggle_pool_row(self,row):
        if self.conductor_selection and self._pool_project is not self.app.project:return self.finish_conductor_selection()
        from composition_queue import configure,state
        if self.app.reviewing:return self.app.update_status('Return to Programme before choosing its module pool.')
        ids=list(state(self.app.project).get('pool_ids',[]))
        if row['id'] in ids:ids.remove(row['id'])
        else:ids.append(row['id'])
        self.app.transaction('Conductor module pool',lambda:configure(self.app.project,{'pool_mode':'selected','pool_ids':ids}))
        self._refresh_pool_banner()
        for card in self.cards.values():self._draw_card(card)
    def focus_library(self):
        self.refresh(force=True);self.search.focus_set();return self
