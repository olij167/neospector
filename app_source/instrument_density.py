"""Compact chrome for performance surfaces, without reducing type or dial size.

Named styles inherit semantic colours/fonts from the selected family theme. Only
repeated frame/border/padding costs shrink; dialogs keep their normal density.
"""
from tkinter import ttk


def compact_tree(root):
    style=ttk.Style(root)
    def visit(widget):
        kind=widget.winfo_class()
        if kind in ('TLabel','TButton','TCheckbutton','TRadiobutton','TEntry','TCombobox','TSpinbox','TProgressbar'):
            current=str(widget.cget('style') or ((str(widget.cget('orient')).title()+'.TProgressbar') if kind=='TProgressbar' else kind))
            if current not in ('TransportPlay.TButton','TransportStop.TButton','Knob.TEntry'):
                name=current if current.startswith('Compact.') else 'Compact.'+current
                options={'borderwidth':1,'padding':(3,2)}
                if kind=='TLabel':options={'borderwidth':0,'padding':0}
                elif kind in ('TCheckbutton','TRadiobutton'):options={'borderwidth':1,'padding':(1,0)}
                elif kind=='TProgressbar':options={'borderwidth':1,'thickness':4}
                style.configure(name,**options)
                if current!=name:widget.configure(style=name)
        for child in widget.winfo_children():visit(child)
    visit(root)
