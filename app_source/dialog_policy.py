"""Consistent owned-dialog escape, focus return and screen bounds.

Keep each dialog's existing save/cancel/worker cleanup as its close authority.
No global replacement of native dialogs or of existing Escape bindings.
"""
import tkinter as tk


def install(app):
    def mapped(event):
        win=event.widget
        if not isinstance(win,tk.Toplevel) or getattr(win,'_omne_dialog_policy',False):return
        if win.winfo_toplevel() is app or win.overrideredirect():return
        # Detached Programme/output windows deliberately follow their own geometry.
        if 'output' in win.title().casefold() and 'settings' not in win.title().casefold():return
        win._omne_dialog_policy=True
        previous=app.focus_get()
        def settle():
            if not win.winfo_exists():return
            sw,sh=win.winfo_screenwidth(),win.winfo_screenheight()
            maxw,maxh=max(320,sw-32),max(240,sh-64)
            minw,minh=win.minsize();win.minsize(min(minw,maxw),min(minh,maxh))
            w,h=min(win.winfo_width(),maxw),min(win.winfo_height(),maxh)
            x=max(0,min(win.winfo_x(),sw-w));y=max(0,min(win.winfo_y(),sh-h-32))
            if (w,h,x,y)!=(win.winfo_width(),win.winfo_height(),win.winfo_x(),win.winfo_y()):win.geometry(f'{w}x{h}+{x}+{y}')
            if not win.bind('<Escape>'):
                def escape(e):
                    # A native dropdown consumes Escape before closing its dialog.
                    widget=e.widget
                    if widget.winfo_class()=='TCombobox':
                        try:
                            pop=widget.tk.call('ttk::combobox::PopdownWindow',widget._w)
                            if int(widget.tk.call('winfo','ismapped',pop)):
                                widget.tk.call('ttk::combobox::Unpost',widget._w);return 'break'
                        except tk.TclError:pass
                    command=win.protocol('WM_DELETE_WINDOW')
                    if command:win.tk.eval(command)
                    else:win.destroy()
                    return 'break'
                win.bind('<Escape>',escape)
        win.after_idle(settle)
        def destroyed(e):
            if e.widget is win and previous is not None:
                try:
                    if previous.winfo_exists():previous.focus_set()
                except tk.TclError:pass
        win.bind('<Destroy>',destroyed,add='+')
    app.bind_all('<Map>',mapped,add='+')
