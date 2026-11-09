"""An inline group chain whose edits always resolve through the live outer rack."""
from __future__ import annotations
import copy
import tkinter as tk
from tkinter import ttk
import module_engine as modules
from sequencer_model import _encode
from omne_rack import ParameterFader, RACK_FACES


def promote_internal_parameter(top, displayed_path, path, key):
    """Expose a direct member on this group's face without rebuilding its macros."""
    displayed_path, path = tuple(displayed_path), tuple(path)
    if path[:-1] != displayed_path:
        raise ValueError('Choose a parameter in the displayed group')
    trial = copy.deepcopy(top)
    def change(node, remaining):
        if node.extra.get('locked'):
            raise ValueError('Unlock this group before editing it')
        subs = modules.children(node)
        if remaining:
            child = next((c for c in subs if c.id == remaining[0]), None)
            if child is None:raise ValueError('Internal group no longer exists')
            result = change(child, remaining[1:])
            node.extra['children'] = _encode(subs)
            return result
        child = next((c for c in subs if c.id == path[-1]), None)
        if child is None or key not in child.params:raise ValueError('Internal parameter no longer exists')
        if child.extra.get('locked'):raise ValueError('Unlock the internal module before editing it')
        mappings = node.extra.setdefault('mappings', {})
        for macro, targets in mappings.items():
            if any(t.get('effect') == child.id and t.get('parameter') == key for t in targets):
                return macro
        _, _, param = modules.internal_parameter_target(top, path, key)
        index = 1
        while 'macro_'+str(index) in node.params:index += 1
        macro = 'macro_'+str(index)
        node.params[macro] = copy.deepcopy(param)
        node.extra.setdefault('labels', {})[macro] = modules.label(child)+' · '+modules.parameter_descriptions(child)[key]['label']
        mappings[macro] = [{'effect': child.id, 'parameter': key, 'low':param.minimum, 'high':param.maximum}]
        return macro
    result = change(trial, displayed_path)
    modules.compile_rack([trial])
    top.params = trial.params
    top.extra = trial.extra
    return result


def edit_group_members(top,path,mutate):
    """Persist a structure edit atomically through all encoded group ancestors."""
    trial=copy.deepcopy(top)
    def visit(node,remaining):
        if node.kind!='module':raise ValueError('Choose a group')
        if node.extra.get('locked'):raise ValueError('Unlock this group before editing it')
        members=modules.children(node)
        if remaining:
            child=next((c for c in members if c.id==remaining[0]),None)
            if child is None:raise ValueError('Internal group no longer exists')
            result=visit(child,remaining[1:])
        else:
            result=mutate(members)
            ids=[c.id for c in members]
            if len(ids)!=len(set(ids)):raise ValueError('This module is already in the group')
            for targets in node.extra.get('mappings',{}).values():
                if any(t.get('effect') not in ids for t in targets):
                    raise ValueError('This module has controls on the Group Front; keep it or remove those mappings first')
        node.extra['children']=_encode(members)
        return result
    result=visit(trial,tuple(path));modules.compile_rack([trial])
    top.extra=trial.extra
    return result


class GroupParameterMotion:
    """A retained trial parameter gives automation one identity for the whole drag."""
    def __init__(self,group,path,key,owner):
        self.group=group;self.owner=owner;self.trial=copy.deepcopy(group)
        # Validate every requested ancestor, including locks hidden by promotion.
        modules.edit_internal_parameter(self.trial,path,key,{})
        owner_path,owner_key=modules.internal_parameter_owner(self.trial,tuple(path),key)
        self.chain=[];node=self.trial
        for child_id in owner_path:
            siblings=modules.children(node);child=next(c for c in siblings if c.id==child_id)
            self.chain.append((node,siblings));node=child
        self.param=node.params[owner_key]
    def write(self,app,value):
        app.write_parameter(self.param,float(value),self.owner)
        for node,siblings in reversed(self.chain):node.extra['children']=_encode(siblings)
        modules.compile_rack([self.trial])
        for name,param in self.trial.params.items():
            if name in self.group.params:self.group.params[name].__dict__.update(copy.deepcopy(param.__dict__))
            else:self.group.params[name]=copy.deepcopy(param)
        self.group.extra=copy.deepcopy(self.trial.extra)


class GroupFader(ParameterFader):
    def __init__(self, parent, workspace, path, key, title, param, owner, locked=False):
        self.workspace, self.path, self.key = workspace, path, key;self.motion=None
        super().__init__(parent,workspace.app,title,param,owner,locked=locked,
                         guard=lambda:workspace.resolve_parameter(path,key) is not None,
                         open_controls=lambda:workspace.open_controls(path,key))
        self.mode_button.configure(command=self.open_controls)
        self.scale.bind('<Escape>',lambda e:(self.finish_input(cancel=True),'break')[1])
    def begin(self,event=None):
        if self.active:return None
        resolved=self.workspace.root_rack.resolve_group()
        if resolved is None or not self.editable():return 'break'
        _,owner=self.workspace.root_rack.target()
        try:motion=GroupParameterMotion(resolved[0],self.path,self.key,owner)
        except ValueError as exc:self.app.update_status(str(exc));return 'break'
        result=super().begin(event)
        if result!='break':self.motion=motion
        return result
    def finish_input(self,*,cancel=False):
        if not self.active:return
        from input_gestures import release_input
        self.active=False;self.motion=None;release_input(self.app,self)
        if self.app.gesture:
            if cancel:self.app.cancel_gesture()
            else:self.app.end_gesture()
    def finish(self,event=None):self.finish_input()
    def cancel_entry(self,event=None):
        self.finish_input(cancel=True)
        if self.winfo_exists():self.show_value();self.scale.focus_set()
        return 'break'
    def write(self,value):
        if self.syncing or not self.active or not self.editable():return
        native=self.from_normal(value)
        resolved=self.workspace.root_rack.resolve_group()
        if not self.app.gesture or resolved is None or self.motion is None or resolved[0] is not self.motion.group:
            self.finish_input();return
        try:self.motion.write(self.app,native)
        except ValueError as exc:self.app.update_status(str(exc));return
        self.text.set(f'{native:.3f}'.rstrip('0').rstrip('.') or '0')
    def enter(self,event=None):
        try:
            value=float(self.text.get())
            if not self.param.minimum <= value <= self.param.maximum:raise ValueError('Value is outside the parameter range')
            if self.begin()=='break':return 'break'
            self.write(self.to_normal(value));self.finish_input()
        except ValueError as exc:self.app.update_status(str(exc))
        return 'break'


class GroupWorkspace(ttk.Frame):
    def __init__(self,parent,root_rack):
        super().__init__(parent)
        self.root_rack=root_rack;self.app=root_rack.app;self.faders={};self._signature=None
        from rack_layout import RackArea, LayoutPolicy
        self.area=RackArea(self,self.app,height=250);self.area.allow_vertical=True
        self.area.set_policy(LayoutPolicy(flow='Single strip'));self.area.pack(fill='both',expand=True)
        self.chain=self.area.body;self.expanded=None;self.cards={}
    def _structure_edit(self,label,mutate):
        expected=self.root_rack.resolve_group()
        if expected is None:return False
        top,_,path=expected;path=tuple(path)
        def apply():
            current=self.root_rack.resolve_group()
            if current is None or current[0] is not top or tuple(current[2])!=path:return False
            _,owner=self.root_rack.target()
            if not self.app.can_edit(owner):return False
            edit_group_members(top,path,mutate)
            return True
        return self.app.transaction(label,apply)
    def add_module(self,fx,index=None):
        def add(members):
            at=len(members) if index is None else max(0,min(len(members),int(index)))
            members.insert(at,copy.deepcopy(fx))
        return self._structure_edit('Add module inside group',add)
    def change_member(self,child_id,action):
        if action not in ('bypass','earlier','later','remove'):raise ValueError('Choose a valid group action')
        def change(members):
            index=next((i for i,c in enumerate(members) if c.id==child_id),None)
            if index is None:raise ValueError('Internal module no longer exists')
            child=members[index]
            if child.extra.get('locked'):raise ValueError('Unlock the internal module before editing it')
            if action=='bypass':child.enabled=not child.enabled
            elif action=='remove':members.pop(index)
            else:
                other=index+(-1 if action=='earlier' else 1)
                if not 0<=other<len(members):return
                if members[other].extra.get('locked'):raise ValueError('Unlock the neighbouring module before moving it')
                members[index],members[other]=members[other],members[index]
        return self._structure_edit('Edit group member · '+action,change)
    def resolve_parameter(self,path,key):
        resolved=self.root_rack.resolve_group()
        if not resolved:return None
        top,_,_=resolved
        try:return modules.internal_parameter_target(top,tuple(path),key)
        except (ValueError,KeyError,StopIteration):return None
    def edit_parameter(self,path,key,changes,continuous=False):
        path=tuple(path)
        def apply():
            resolved=self.root_rack.resolve_group()
            if not resolved:return False
            _,owner=self.root_rack.target()
            if not self.app.can_edit(owner):return False
            modules.edit_internal_parameter(resolved[0],path,key,changes)
            return True
        if continuous:
            result=apply()
            if result:self.app.changed(redraw=False)
        else:result=self.app.transaction('Edit group parameter',apply)
        return result
    def promote_parameter(self,path,key):
        def apply():
            resolved=self.root_rack.resolve_group()
            if not resolved:return False
            _,owner=self.root_rack.target()
            if not self.app.can_edit(owner):return False
            return promote_internal_parameter(resolved[0],resolved[2],path,key)
        return self.app.transaction('Show on Group Front',apply)
    def open_controls(self,path,key):
        fader=self.faders.get((path,key))
        if fader is None:return
        old=getattr(fader,'controls',None)
        if old is not None:
            old.destroy();fader.controls=None;return
        target=self.resolve_parameter(path,key)
        if target is None:return
        param=target[2];host=ttk.Frame(fader,padding=(0,4));host.grid(row=2,column=0,columnspan=3,sticky='ew');fader.controls=host
        host.columnconfigure(1,weight=1)
        from live_parameter_controls import REACTION_SOURCES, REACTION_BANDS
        choices=(('mode','Mode',[('static','Manual'),('animate','Keys'),('react','React')]),
                 ('source','Source',REACTION_SOURCES),('react_band','Listen',REACTION_BANDS))
        fader.control_vars={};fader.control_entries={}
        for row,(field,title,options) in enumerate(choices):
            labels=dict(options);reverse={v:k for k,v in options}
            ttk.Label(host,text=title).grid(row=row,column=0,sticky='w')
            var=tk.StringVar(value=labels.get(getattr(param,field),getattr(param,field)))
            fader.control_vars[field]=var
            from immediate_choices import ChoiceStrip
            strip=ChoiceStrip(host,options,var,labels,lambda value,f=field:self.edit_parameter(path,key,{f:value}))
            strip.grid(row=row,column=1,sticky='ew')
        for row,(field,title) in enumerate((('value','Base'),('react_amount','Travel'),('attack','Attack · s'),('release','Smoothing · s')),3):
            var=tk.StringVar(value=f'{getattr(param,field):g}');fader.control_vars[field]=var
            ttk.Label(host,text=title).grid(row=row,column=0,sticky='w')
            entry=ttk.Entry(host,textvariable=var,width=9);entry.grid(row=row,column=1,sticky='ew');fader.control_entries[field]=entry
            def save(event=None,f=field,v=var):
                try:
                    number=float(v.get())
                    if f=='value':
                        if fader.begin()!='break':fader.write(fader.to_normal(number));fader.finish_input()
                    else:self.edit_parameter(path,key,{f:number})
                except ValueError as exc:self.app.update_status(str(exc))
                return 'break'
            entry.bind('<Return>',save)
        fader.source_note=tk.StringVar();ttk.Label(host,textvariable=fader.source_note,wraplength=210).grid(row=7,column=0,columnspan=2,sticky='w')
        fader.source_meter=ttk.Progressbar(host,maximum=1,length=180);fader.source_meter.grid(row=8,column=0,columnspan=2,sticky='ew')
        ttk.Label(host,text=f'{len(param.keyframes)} saved keys retained').grid(row=9,column=0,columnspan=2)
        self.refresh_source(fader)
    def refresh_source(self,fader):
        if getattr(fader,'controls',None) is None:return
        from live_parameter_controls import source_status
        try:text,level=source_status(self.app,fader.param.source)
        except AttributeError:text,level='Source status unavailable',0
        fader.source_note.set(text);fader.source_meter['value']=level
    def toggle_more(self,child_id):
        self.expanded=None if self.expanded==child_id else child_id
        for eid,(button,extras,fronts) in self.cards.items():
            expanded=True;button.configure(text='')
            for widget in extras+fronts:
                if expanded:widget.pack(fill='x',pady=3)
                else:widget.pack_forget()
        self.area.region()
    def refresh(self,force=False):
        resolved=self.root_rack.resolve_group()
        if not resolved:
            for child in self.chain.winfo_children():child.destroy()
            self.faders={};self._signature=None;return
        top,node,prefix=resolved;prefix=tuple(prefix)
        signature=(top.id,prefix,repr(node.extra.get('mappings',{})),tuple((c.id,c.kind,c.enabled,tuple(c.params),bool(c.extra.get('locked'))) for c in modules.children(node)),bool(top.extra.get('locked')),bool(node.extra.get('locked')))
        # During a drag, retain input ownership and synchronize copied parameters.
        if signature==self._signature or any(f.active for f in self.faders.values()):
            for (path,key),fader in self.faders.items():
                current=self.resolve_parameter(path,key)
                if current:fader.param=current[2];fader.refresh();self.refresh_source(fader)
            return
        self._signature=signature
        for child in self.chain.winfo_children():child.destroy()
        self.faders={};self.cards={};_,owner=self.root_rack.target()
        for index,child in enumerate(modules.children(node)):
            card=ttk.LabelFrame(self.chain,text=f'{index+1} · {modules.label(child)}',padding=8)
            card.grid(row=0,column=index,sticky='nsew',padx=4,pady=6);self.chain.columnconfigure(index,weight=0,minsize=240)
            actions=ttk.Frame(card);actions.pack(fill='x')
            ttk.Button(actions,text='ON' if child.enabled else 'OFF',width=4,command=lambda eid=child.id:self.change_member(eid,'bypass')).pack(side='left')
            # Internal group members use the same direct actions as normal pedals.
            ttk.Button(actions,text='× Remove',width=9,command=lambda eid=child.id:self.change_member(eid,'remove')).pack(side='right')
            ttk.Button(actions,text='→',width=2,command=lambda eid=child.id:self.change_member(eid,'later')).pack(side='right',padx=2)
            ttk.Button(actions,text='←',width=2,command=lambda eid=child.id:self.change_member(eid,'earlier')).pack(side='right')
            if child.kind=='module':ttk.Button(card,text='Open group →',command=lambda eid=child.id:self.root_rack.enter_group(eid)).pack(fill='x')
            more=ttk.Button(card,text='',command=lambda:None)  # no extra disclosure
            extras=[];fronts=[];self.cards[child.id]=(more,extras,fronts)
            path=(*prefix,child.id)
            principal=modules.priority_keys(child)
            if not principal:principal=list(child.params)[:1]
            for key,desc in modules.parameter_descriptions(child).items():
                target=self.resolve_parameter(path,key)
                if target is None:continue
                fader=GroupFader(card,self,path,key,desc['label'],target[2],owner,locked=bool(top.extra.get('locked') or node.extra.get('locked') or child.extra.get('locked')))
                # UX13 retains only the compact fader on group members.
                fader.pack(fill='x',pady=2)
                self.faders[(path,key)]=fader
                for widget in (fader.scale,fader.entry):widget.unbind('<Button-3>')
                promoted=any(any(t.get('effect')==child.id and t.get('parameter')==key for t in targets) for targets in node.extra.get('mappings',{}).values())
                front=ttk.Button(card,text='Show on Group Front' if not promoted else 'On Group Front',state='disabled' if promoted or fader.locked else 'normal',command=lambda p=path,k=key:self.promote_parameter(p,k));front.pack(fill='x',pady=1)
        if self.expanded in self.cards:
            expanded=self.expanded;self.expanded=None;self.toggle_more(expanded)
        self.area.region()
        if not modules.children(node):ttk.Label(self.chain,text='This group has no modules.').grid(row=0,column=0,padx=12,pady=12)
