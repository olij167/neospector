"""UX12 compact reaction strip attached to a pedal, with precise editor on demand.

This is a presentation projection: existing Parameter, RackContext, and transactions
remain the authority. Choosing a source never opens a recording device.
"""
import tkinter as tk
from tkinter import ttk
from rack_editing import RackContext, update_parameter
from live_parameter_controls import initial_reaction_changes, available_reaction_sources


class QuickReactionStrip(tk.Frame):
    def __init__(self,parent,cell,fxid,param_key,param,face):
        bg,fg,accent=face
        super().__init__(parent,bg=bg,padx=2,pady=0)
        st=ttk.Style(self);st.configure('UX14.PedalMini.TButton',padding=(1,0),font=('TkDefaultFont',8))
        self.cell=cell;self.app=cell.app;self.fxid=fxid;self.param=param;self.key=param_key
        self.columnconfigure(0,weight=1)
        top=tk.Frame(self,bg=bg);top.grid(row=0,column=0,sticky='ew')
        self.back=ttk.Button(top,text='‹ Faders',width=7,style='UX14.PedalMini.TButton',command=lambda:cell.toggle_tune(fxid,param_key))
        self.back.pack(side='left')
        tk.Label(top,text=param_key.upper()[:9]+' ∿',fg=accent,bg=bg,font=('TkDefaultFont',7,'bold')).pack(side='left',padx=2)
        # One directly editable control surface: no fine-tuning popup or dropdown.
        self.power=ttk.Button(top,text='∿ ON' if param.mode=='react' else '∿ OFF',width=5,style='UX14.PedalMini.TButton',command=self.toggle_power);self.power.pack(side='right',padx=2)
        self.options={};self.buttons={}
        for title,options,selected,method in (
            ('FROM',(('Σ','reaction_mix'),('♫','song'),('◉','microphone')),param.source,self.set_source),
            ('BAND',(('All','full'),('Low','bass'),('Mid','mid'),('High','high'),('Hit','onset')),param.react_band,self.set_band),
        ):
            row=tk.Frame(self,bg=bg);row.grid(sticky='ew',row=1 if title=='FROM' else 2,column=0,pady=0);self.buttons[title]={}
            tk.Label(row,text=title,width=5,anchor='w',fg=fg,bg=bg,font=('TkFixedFont',8)).pack(side='left')
            for caption,value in options:
                button=ttk.Button(row,text=caption,width=3 if title=='FROM' else 4,style='UX14.PedalMini.TButton',command=lambda v=value,fn=method:fn(v))
                button.pack(side='left',padx=1)
                self.buttons[title][value]=button
                if value==selected:button.configure(style='Accent.TButton')
        travel=tk.Frame(self,bg=bg);travel.grid(row=3,column=0,sticky='ew',pady=(0,0))
        tk.Label(travel,text='MOVE',width=5,anchor='w',bg=bg,fg=fg,font=('TkFixedFont',8)).pack(side='left')
        self.depth=tk.DoubleVar(value=param.react_amount)
        slider=ttk.Scale(travel,from_=-1,to=1,variable=self.depth,length=110)
        slider.pack(side='left',fill='x',expand=True)
        slider.bind('<ButtonRelease-1>',self.apply_depth)
        slider.bind('<KeyRelease>',self.apply_depth)
        ttk.Button(travel,text='↔',width=2,style='UX14.PedalMini.TButton',command=lambda:self.set_depth(-self.param.react_amount)).pack(side='right')
        self.app.add_tip(slider,'Reaction movement: left reduces or reverses; right increases. One undoable edit per release.')

    def current(self):
        return self.cell.effect(self.fxid)

    def mutate(self,title,changes):
        fx=self.current()
        if fx is None or fx.params.get(self.key) is not self.param:return False
        ctx=RackContext.capture(self.cell)
        return self.cell.run_edit(ctx,title,lambda rack,found,owner:update_parameter(self.param,changes),self.fxid)

    def set_source(self,value):
        self.mutate('Reaction audio source',{'source':value});self.refresh_buttons()

    def set_band(self,value):
        self.mutate('Reaction frequency band',{'react_band':value});self.refresh_buttons()

    def set_depth(self,value):
        self.depth.set(float(value));self.apply_depth()

    def apply_depth(self,event=None):
        self.mutate('Reaction movement',{'react_amount':max(-1.,min(1.,float(self.depth.get())))})

    def toggle_power(self):
        if self.param.mode=='react':changes={'mode':'static'}
        else:changes=initial_reaction_changes(self.param,available=available_reaction_sources(self.app))
        self.mutate('Reaction power',changes);self.refresh_buttons()

    def refresh_buttons(self):
        self.power.configure(text='∿ ON' if self.param.mode=='react' else '∿ OFF')
        for group,value in (('FROM',self.param.source),('BAND',self.param.react_band)):
            for key,button in self.buttons[group].items():
                button.configure(style='Accent.TButton' if key==value else 'TButton')
