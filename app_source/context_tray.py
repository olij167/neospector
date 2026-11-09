"""Contextual authoring companion over the retained workspace; never a split engine."""
import tkinter as tk
from tkinter import ttk

class ContextTrayActions:
    def open_context_tray(self,key,title,builder):
        current=getattr(self,'_context_tray',None)
        if current and current['key']==key and current['project'] is self.project:return current['body']
        self.close_context_tray()
        if self.gesture:self.end_gesture()
        frame=ttk.Frame(self.shell.stage,padding=5,relief='solid')
        head=ttk.Frame(frame);head.pack(fill='x')
        ttk.Label(head,text=title,style='Title.TLabel').pack(side='left',fill='x',expand=True)
        ttk.Button(head,text='Close',width=6,command=self.close_context_tray).pack(side='right')
        body=ttk.Frame(frame);body.pack(fill='both',expand=True)
        self._context_tray={'key':key,'frame':frame,'body':body,'project':self.project}
        try:builder(body)
        except Exception:self.close_context_tray();raise
        frame.place(relx=.03,rely=.20,relwidth=.94,relheight=.77);frame.lift()
        frame.bind('<Escape>',lambda e:(self.close_context_tray(),'break')[1])
        body.focus_set()
        return body
    def close_context_tray(self):
        current=getattr(self,'_context_tray',None)
        if not current:return
        self._context_tray=None
        if getattr(self,'gesture',None):self.end_gesture()
        try:current['frame'].destroy()
        except tk.TclError:
            if not getattr(self,'closing',False):raise
    def refresh_all(self):
        current=getattr(self,'_context_tray',None)
        if current and current['project'] is not self.project:self.close_context_tray()
        return super().refresh_all()
    def toggle_focus_output(self):
        self.close_context_tray();return super().toggle_focus_output()
    def load_layout(self,pref):
        self.close_context_tray();return super().load_layout(pref)
