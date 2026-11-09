"""Visible, keyboard-focusable choices using the existing parameter transactions."""
from tkinter import ttk
class ChoiceStrip(ttk.Frame):
    def __init__(self,parent,choices,variable,labels,command):
        super().__init__(parent);self.buttons={};self.variable=variable;self.labels=labels
        for i,(key,label) in enumerate(choices):
            button=ttk.Button(self,text=label,width=0,command=lambda k=key:command(k));button.grid(row=0,column=i,sticky='ew',padx=1);self.columnconfigure(i,weight=1);self.buttons[key]=button
        self.token=variable.trace_add('write',self.refresh);self.bind('<Destroy>',self.cleanup,add='+');self.refresh()
    def refresh(self,*args):
        value=self.variable.get()
        for key,button in self.buttons.items():button.state(['pressed'] if self.labels.get(key,key)==value else ['!pressed'])
    def cleanup(self,event):
        if event.widget is self:self.variable.trace_remove('write',self.token)
def install(tray):
    if hasattr(tray,'source_strip'):return
    from live_parameter_controls import RESPONSE_PRESETS
    def replace(box,choices,var,labels,command):
        info=box.grid_info();box.grid_remove();strip=ChoiceStrip(box.master,choices,var,labels,command);strip.grid(**{k:v for k,v in info.items() if k!='in'});return strip
    sources=[(k,{'song':'♫ Music','microphone':'● Mic','reaction_mix':'∑ All'}.get(k,v)) for k,v in tray.source_labels.items()]
    tray.source_strip=replace(tray.source_box,sources,tray.source_label,tray.source_labels,tray.activate_source)
    bands=[(k,{'full':'Full','bass':'Bass','mid':'Mid','high':'High','onset':'Hits'}.get(k,v)) for k,v in tray.band_labels.items()]
    tray.band_strip=replace(tray.band_box,bands,tray.band_label,tray.band_labels,tray.activate_band)
    box=tray.response_box
    tray.response_strip=replace(box,[(k,k) for k in RESPONSE_PRESETS],tray.response_choice,{},tray.activate_response)
    from instrument_icons import icon
    for name,button in tray.response_strip.buttons.items():button.configure(image=icon(tray.app,name),compound='left')
