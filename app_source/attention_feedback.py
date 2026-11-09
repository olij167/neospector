"""Brief non-blocking visual attention for direct edits; avoids a new UI overlay."""
import tkinter as tk


def pulse(widget, color='#ead35f', flashes=2):
    if not isinstance(widget,(tk.Frame,tk.Label,tk.Canvas)):
        return False
    try:
        old_color=widget.cget('highlightbackground')
        old_width=widget.cget('highlightthickness')
        old_style=widget.cget('highlightcolor')
    except tk.TclError:
        return False
    count=0
    def phase():
        nonlocal count
        try:
            if not widget.winfo_exists():return
            on=count%2==0
            widget.configure(highlightthickness=2 if on else old_width,
                             highlightbackground=color if on else old_color,
                             highlightcolor=color if on else old_style)
            count+=1
            if count < flashes*2:widget.after(105,phase)
        except tk.TclError:
            return
    phase()
    return True
