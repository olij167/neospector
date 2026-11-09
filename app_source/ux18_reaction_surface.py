"""Reaction is a property of a *visible fader*, never an alternate module view.

One strip is attached to each parameter. All edits pass through the existing
RackContext/ProjectHistory transaction path. Reading reaction state does not
start audio capture or change a routing source.
"""
from __future__ import annotations
import tkinter as tk
from rack_editing import RackContext,update_parameter
from live_parameter_controls import initial_reaction_changes

SOURCES=(('reaction_mix','MIX'),('song','SONG'),('microphone','MIC'))
BANDS=(('full','ALL'),('bass','BASS'),('mid','MID'),('high','HIGH'),('onset','HITS'))

def depth_label(value):
    """Expose the signed fraction of parameter travel, not an opaque slider."""
    percent=int(round(max(-1.,min(1.,float(value)))*100))
    return ('+' if percent>0 else '−' if percent<0 else '')+str(abs(percent))+'%'


def begin_depth(cell,row,fxid):
    if not row.winfo_exists() or not cell.parameter_guard(RackContext.capture(cell),fxid,
            next((k for k,p in cell.effect(fxid).params.items() if p is row.param),''),row.param):
        return 'break'
    row._react_depth_dragging=True
    return None

def preview_depth(row,value):
    if hasattr(row,'reaction_depth_label'):
        label=depth_label(value)
        if row.reaction_depth_label.cget('text')!=label:
            row.reaction_depth_label.configure(text=label)

def next_choice(current, choices):
    names=[name for name,_ in choices]
    return names[(names.index(current)+1)%len(names)] if current in names else names[0]


def install(cell,row,fxid):
    """Create one tiny source/band/depth strip under the existing value fader."""
    if hasattr(row,'reaction_source'):return
    bg,fg,accent=row.face
    strip=tk.Frame(row,bg=bg,highlightthickness=0,bd=0)
    strip.grid(row=1,column=0,columnspan=4,sticky='ew')
    strip.columnconfigure(2,weight=1)
    row._react_depth_dragging=False
    face=dict(bg=bg,fg=fg,activebackground=accent,activeforeground=bg,relief='flat',bd=0,
              font=('TkFixedFont',7,'bold'),padx=2,pady=0,highlightthickness=0)
    row.reaction_source=tk.Button(strip,width=5,command=lambda:change_source(cell,row,fxid),**face)
    row.reaction_source.grid(row=0,column=0,sticky='w',padx=(1,1))
    row.reaction_band=tk.Button(strip,width=5,command=lambda:change_band(cell,row,fxid),**face)
    row.reaction_band.grid(row=0,column=1,sticky='w',padx=(0,2))
    row.reaction_value=tk.DoubleVar(value=row.param.react_amount)
    row.reaction_amount=tk.Scale(strip,from_=-1,to=1,variable=row.reaction_value,resolution=.05,
         orient='horizontal',showvalue=False,bd=0,highlightthickness=0,sliderlength=7,width=5,length=55,
         bg=bg,fg=fg,troughcolor=cell.app.ui_chrome['field_bg'],activebackground=accent,
         command=lambda value:preview_depth(row,value))
    row.reaction_amount.grid(row=0,column=2,sticky='ew',padx=1)
    row.reaction_depth_label=tk.Label(strip,text=depth_label(row.param.react_amount),
        bg=bg,fg=fg,font=('TkFixedFont',7,'bold'),width=5,anchor='e')
    row.reaction_depth_label.grid(row=0,column=3,sticky='e',padx=(1,1))
    row.reaction_amount.bind('<ButtonPress-1>',lambda e:begin_depth(cell,row,fxid))
    row.reaction_amount.bind('<ButtonRelease-1>',lambda e:change_depth(cell,row,fxid))
    row.reaction_amount.bind('<KeyRelease>',lambda e:change_depth(cell,row,fxid))
    row.reaction_amount.bind('<Escape>',lambda e:(setattr(row,'_react_depth_dragging',False),refresh(row),'break')[-1])
    row._refresh_reaction=lambda:refresh(row)
    row.reaction_bar=strip
    cell.app.add_tip(row.reaction_source,'Audio source · cycle Mix, Music, Mic. Tap ∿ on the fader to react.')
    cell.app.add_tip(row.reaction_band,'Reactive frequency · cycle Level, Bass, Mid, High, Hits.')
    cell.app.add_tip(row.reaction_amount,'Audio response amount: 0% is neutral. +100% moves the parameter upwards by up to its full range at maximum signal; −100% moves it downwards. This is independent for each parameter.')
    refresh(row)


def mutate(cell,row,fxid,changes,label):
    param=row.param
    if not cell.parameter_guard(RackContext.capture(cell),fxid,next((k for k,p in cell.effect(fxid).params.items() if p is param),''),param):return False
    context=RackContext.capture(cell)
    if param.mode!='react':
        changes={**initial_reaction_changes(param),**changes}
    success=cell.run_edit(context,label,lambda rack,fx,owner:update_parameter(param,changes),fxid)
    if success:refresh(row)
    return success


def change_source(cell,row,fxid):
    name=next_choice(row.param.source,SOURCES)
    return mutate(cell,row,fxid,{'source':name},'Choose reaction source')

def change_band(cell,row,fxid):
    name=next_choice(row.param.react_band,BANDS)
    return mutate(cell,row,fxid,{'react_band':name},'Choose reaction band')

def change_depth(cell,row,fxid):
    # Tk can deliver the final Scale command after ButtonRelease. Scale.get()
    # is the authoritative final thumb position, whereas DoubleVar may be old.
    val=max(-1.,min(1.,float(row.reaction_amount.get())))
    row._react_depth_dragging=False
    success=mutate(cell,row,fxid,{'react_amount':val},'Adjust reaction depth')
    if success:preview_depth(row,val)
    else:refresh(row)
    return success

def refresh(row):
    par=row.param
    active=par.mode=='react'
    bg,fg,accent=row.face
    sources=dict(SOURCES);bands=dict(BANDS)
    state=(par.source,par.react_band,active)
    if state!=getattr(row,'_ux39_reaction_state',None):
        row.reaction_source.configure(text=sources.get(par.source,'MIX'),fg=accent if active else row.app.ui_chrome['muted_fg'])
        row.reaction_band.configure(text=bands.get(par.react_band,'ALL'),fg=accent if active else row.app.ui_chrome['muted_fg'])
        row.mode_button.configure(text='∿●' if active else '∿',width=3,
            style='UX18.ReactionOn.TButton' if active else 'UX18.Reaction.TButton')
        row._ux39_reaction_state=state
    # Never move the thumb under an active pointer: periodic rack paint and
    # history callbacks can occur while the user is still dragging it.
    if not getattr(row,'_react_depth_dragging',False):
        if abs(float(row.reaction_amount.get())-float(par.react_amount))>.001:
            row.reaction_amount.set(float(par.react_amount))
        preview_depth(row,par.react_amount)
