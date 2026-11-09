"""One Media Settings overlay, reached by context rather than duplicate editors."""
import copy
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from media_settings_model import tabs_for,validate_defaults
from sequencer_model import _encode
from responsive_controls import FlowRow

class MediaSettings(tk.Toplevel):
    def __init__(self,app,ids,tab='General'):
        super().__init__(app);self.app=app;self.pid=app.project.id;self._form_project=app.project;self.ids=[i for i in ids if app.project.asset(i)];self.asset=app.project.asset(self.ids[0]);self.values={};self.tabs={};self.preference_vars={};self.drafts={};self._building=False;self._input_project=None;self._live_before=None
        self.title('Media settings · '+self.asset.name);self.transient(app);self.geometry('650x555');self.minsize(510,450)
        self.bind('<Escape>',self.cancel_input);self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.body=ttk.Frame(self,padding=12);self.body.pack(fill='both',expand=True)
        header=FlowRow(self.body,gap=5);header.pack(fill='x')
        header.add(ttk.Label(header,text='MEDIA SETTINGS',style='Title.TLabel'))
        self.asset_choice=tk.StringVar(value=self.asset.name)
        if len(self.ids)>1:
            choices=[app.project.asset(i).name for i in self.ids];self.chooser=ttk.Combobox(header,values=choices,textvariable=self.asset_choice,state='readonly',width=26);header.add(self.chooser)
            self.chooser.bind('<<ComboboxSelected>>',self.choose_asset)
        else:header.add(ttk.Label(header,text=self.asset.name,style='Muted.TLabel'))
        ttk.Label(self.body,text='Changes apply to future uses of this source in this project.',wraplength=610,style='Muted.TLabel').pack(fill='x',pady=(4,10))
        self.error=tk.StringVar();foot=ttk.Frame(self.body);foot.pack(side='bottom',fill='x',pady=(8,0))
        ttk.Label(foot,textvariable=self.error,style='Muted.TLabel',wraplength=400).pack(side='left',fill='x',expand=True)
        ttk.Button(foot,text='Done',command=self.destroy).pack(side='right')
        self.book=ttk.Notebook(self.body);self.book.pack(fill='both',expand=True);self.build(tab)
    def choose_asset(self,event=None):
        if self.app.project is not self._form_project:
            self.error.set('Project changed. Reopen settings for this Library.');return
        index=self.chooser.current()
        if index>=0:
            self.finish_input()
            self.asset=self.app.project.asset(self.ids[index]);self.error.set('');self.build('General')
    def build(self,tab):
        self._building=True
        for widget in self.book.winfo_children():widget.destroy()
        self.values={};self.tabs={};self.preference_vars={};a=self.asset;p=a.metadata.get('sequence_preferences',{});self.rack_override=copy.deepcopy(p.get('default_rack'))
        for title in tabs_for(a):
            frame=ttk.Frame(self.book,padding=10);self.book.add(frame,text=title);self.tabs[title]=frame
        def field(parent,key,label,default='',choices=None):
            row=ttk.Frame(parent);row.pack(fill='x',pady=4);ttk.Label(row,text=label,width=27).pack(side='left')
            v=tk.StringVar(value=str(p.get(key,default)));self.values[key]=v
            control=ttk.Combobox(row,textvariable=v,values=choices,state='readonly',width=16) if choices else ttk.Entry(row,textvariable=v,width=16)
            control.pack(side='left',fill='x',expand=True);return v
        general=self.tabs['General'];self.name=tk.StringVar(value=a.name);ttk.Entry(general,textvariable=self.name).pack(fill='x',pady=5)
        facts=f'{a.kind.title()} · {a.width} × {a.height}' if a.kind!='audio' else 'Audio'
        if a.duration:facts+=f' · {a.duration:.2f} s'
        fps=a.metadata.get('fps') or a.metadata.get('frame_rate')
        if fps:facts+=' · '+str(fps)+' fps (source)'
        ttk.Label(general,text=facts,style='Muted.TLabel').pack(anchor='w',pady=8)
        ttk.Label(general,text=a.path,style='Muted.TLabel',wraplength=570).pack(fill='x',pady=8)
        ttk.Label(general,text='The original file is never changed by these settings. Frame rate and dimensions describe the source, not a conversion request.',wraplength=570,style='Muted.TLabel').pack(fill='x',pady=8)
        playback=self.tabs['Playback']
        if a.kind in ('video','audio'):
            field(playback,'source_in','Usable start · seconds',0)
            field(playback,'source_out','Usable end · seconds',a.duration or '')
            field(playback,'playback_rate','Playback speed · ×',1)
            field(playback,'source_policy','At the end of the source','loop',('loop','hold'))
        else:ttk.Label(playback,text='Still-image duration is chosen per occurrence.\nSet its default range in Conductor.',style='Muted.TLabel').pack(anchor='w',pady=6)
        if a.kind!='audio':field(playback,'fit','Picture fit','cover',('cover','contain','stretch'))
        conductor=self.tabs['Conductor'];self.enabled=tk.BooleanVar(value=p.get('enabled',True));ttk.Checkbutton(conductor,text='Eligible for automatic selection',variable=self.enabled).pack(anchor='w',pady=4)
        field(conductor,'weight','Selection weight',1)
        if a.kind!='audio':
            field(conductor,'clip_min','Minimum occurrence · seconds','')
            field(conductor,'clip_max','Maximum occurrence · seconds','')
            field(conductor,'intensity','Generated FX strength · 0–1','')
            row=FlowRow(conductor,gap=4);row.pack(fill='x',pady=7);row.add(ttk.Label(row,text='Eligible channels'))
            self.roles={r:tk.BooleanVar(value=r in p.get('roles',['A','B','C','D'])) for r in ('A','B','C','D')}
            for role,var in self.roles.items():row.add(ttk.Checkbutton(row,text=role,variable=var))
        else:self.roles={}
        ttk.Label(conductor,text='Blank values inherit the Conductor. Manual queue placement remains available even when automatic selection is off.',wraplength=565,style='Muted.TLabel').pack(fill='x',pady=7)
        if 'Effects' in self.tabs:
            fx=self.tabs['Effects'];self.rack_text=tk.StringVar();self.update_rack_text()
            row=FlowRow(fx,gap=4);row.pack(fill='x')
            row.add(ttk.Button(row,text='Use current rack',command=self.use_rack))
            row.add(ttk.Button(row,text='Inherit generated',command=self.clear_rack))
            row.add(ttk.Label(row,textvariable=self.rack_text,style='Muted.TLabel'))
            inner=ttk.Notebook(fx);inner.pack(fill='both',expand=True,pady=7)
            from editor_widgets import ScrollFrame
            for key,title in [('effect_preferences','Effects'),('reaction_preferences','Reaction')]:
                scroll=ScrollFrame(inner,self.app);inner.add(scroll,text=title);self.preference_vars[key]={}
                for i,(kind,_) in enumerate(getattr(self.app.project.conductor,key).items()):
                    ttk.Label(scroll.body,text=kind.replace('_',' ').title()).grid(row=i,column=0,sticky='w',pady=2,padx=(0,14))
                    v=tk.StringVar(value=p.get(key,{}).get(kind,'inherit'));self.preference_vars[key][kind]=v
                    ttk.Combobox(scroll.body,textvariable=v,values=['inherit','prefer','allow','avoid','exclude'],state='readonly',width=14).grid(row=i,column=1,sticky='ew',pady=2)
        if 'Audio' in self.tabs:
            field(self.tabs['Audio'],'sound_gain','Default source gain · 0–2',1)
            ttk.Label(self.tabs['Audio'],text='Applies when this source is added to Music. Video sound is not enabled merely by importing or queuing its picture. Choose Queue → Music to use its audio stream.',wraplength=565,style='Muted.TLabel').pack(fill='x',pady=10)
        draft=self.drafts.get(a.id)
        if draft:
            name,updates=draft;self.name.set(name)
            for k,v in self.values.items():v.set(updates.get(k,''))
            self.enabled.set(updates.get('enabled',True))
            for r,v in self.roles.items():v.set(r in updates.get('roles',[]))
            self.rack_override=copy.deepcopy(updates.get('default_rack'))
            if 'Effects' in self.tabs:self.update_rack_text()
            for key,values in self.preference_vars.items():
                for k,v in values.items():v.set(updates.get(key,{}).get(k,'inherit'))
        self.book.select(self.tabs.get(tab,self.tabs['General']))
        self._building=False
        variables=[self.name,self.enabled,*self.values.values(),*self.roles.values()]
        for values in self.preference_vars.values():variables.extend(values.values())
        for value in variables:value.trace_add('write',lambda *_:self.live_update())
        def bind_fields(widget):
            for child in widget.winfo_children():
                if isinstance(child,(ttk.Entry,ttk.Combobox)):
                    child.bind('<FocusOut>',lambda e:self.finish_input(),add='+')
                    child.bind('<Return>',lambda e:self.finish_input(),add='+')
                bind_fields(child)
        bind_fields(self.book)
    def update_rack_text(self):self.rack_text.set('Generated treatment' if self.rack_override is None else str(len(self.rack_override))+' saved modules')
    def use_rack(self):
        rack,owner=self.app.deck.target()
        if rack is None:return self.error.set('Select a module rack first.')
        self.rack_override=_encode(rack);self.update_rack_text();self.live_update();self.finish_input()
    def clear_rack(self):self.rack_override=None;self.update_rack_text();self.live_update();self.finish_input()
    def read_fields(self):
        updates={k:v.get() for k,v in self.values.items()};updates['enabled']=self.enabled.get()
        if self.roles:updates['roles']=[r for r,v in self.roles.items() if v.get()]
        if 'Effects' in self.tabs:updates['default_rack']=copy.deepcopy(self.rack_override)
        for key,values in self.preference_vars.items():updates[key]={k:v.get() for k,v in values.items() if v.get()!='inherit'}
        return self.name.get().strip(),updates
    def live_update(self):
        if self._building:return
        if self.app.project is not self._form_project or self.pid!=self.app.project.id:
            return self.error.set('Project changed. Reopen settings for this Library.')
        asset=self.app.project.asset(self.asset.id)
        if asset is None:return self.error.set('This source is no longer in the project.')
        if asset is not self.asset:return self.error.set('Source changed. Reopen settings for this Library.')
        try:
            name,updates=self.read_fields()
            if not name:raise ValueError('Enter a source name.')
            result=validate_defaults(asset,updates,self.app.project.conductor.clip_min,self.app.project.conductor.clip_max)
        except (ValueError,tk.TclError) as exc:return self.error.set(str(exc))
        if name==asset.name and result==asset.metadata.get('sequence_preferences',{}):return
        from input_gestures import claim_input
        if self._input_project is None:
            claim_input(self.app,self);self._input_project=self.app.project
            self.app.begin_gesture('media defaults');self._live_before=self.app.gesture['before']
        if self.app.project is not self._input_project:return
        asset.name=name;asset.metadata['sequence_preferences']=result;self.asset=asset
        self.app.dirty=True;self.app.revision+=1;self.error.set('')
        # Typing retains one gesture until focus leaves. Choice/toggle activation
        # completes at idle, after Tk has delivered the entire change.
        if not isinstance(self.focus_get(),(ttk.Entry,tk.Entry)):
            self.after_idle(self.finish_input)
    def finish_input(self,cancel=False):
        from input_gestures import release_input
        project=self._input_project;before=self._live_before
        self._input_project=None;self._live_before=None;release_input(self.app,self)
        if project is None:return
        if self.app.project is not project or self.app.project.id!=self.pid:return
        if cancel:self.app.cancel_gesture()
        else:
            self.app.end_gesture()
            if before:self.app.persist_assets(before)
        self.asset=self.app.project.asset(self.asset.id)
        self.app.refresh_library()
    def cancel_input(self,event=None):
        self.finish_input(cancel=True);self.destroy();return 'break'
    def apply(self):
        # Compatibility with automation that previously pressed Apply.
        self.live_update();self.finish_input()
    def destroy(self):
        if hasattr(self,'_input_project'):self.finish_input()
        super().destroy()
