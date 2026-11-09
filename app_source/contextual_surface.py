"""Shared lifetime controller for transient contextual Neospector surfaces.

Transient surfaces are not task windows.  They stay open while focus/clicks are
inside the surface or its launcher and close on outside interaction or Escape.
Only one rack-context surface is active at a time, eliminating stacked stale
panels without using fragile per-widget FocusOut chains.
"""
from __future__ import annotations
import tkinter as tk


def _inside(widget, ancestor):
    if widget is None or ancestor is None:
        return False
    current=widget
    while current is not None:
        if current is ancestor:
            return True
        current=getattr(current,'master',None)
    return False


class ContextualSurfaceController:
    def __init__(self, root):
        self.root=root
        self._active=None
        self._button_bind=None
        self._focus_bind=None
        self._escape_bind=None
        self._pending=None

    def show(self, key, surface, close, *, anchors=()):
        """Register *surface* as the current transient UI surface.

        ``close`` must be idempotent.  It is called after an outside interaction,
        not synchronously inside Tk's event dispatch, so combobox/menu internals
        get a chance to finish their own selection first.
        """
        native=getattr(self.root,'_posted_native_menu',None)
        if native:native['dismiss']()
        current=self._active
        if current and current['key']!=key:
            self.dismiss()
        self._active={'key':key,'surface':surface,'close':close,'anchors':tuple(a for a in anchors if a is not None)}
        self._ensure_bindings()
        return surface

    def active(self, key=None):
        if not self._active:return False
        return key is None or self._active['key']==key

    def _ensure_bindings(self):
        if self._button_bind is None:
            self._button_bind=self.root.bind_all('<ButtonPress>',self._outside,add='+')
        if self._focus_bind is None:
            self._focus_bind=self.root.bind_all('<FocusIn>',self._outside,add='+')
        if self._escape_bind is None:
            self._escape_bind=self.root.bind_all('<Escape>',self._escape,add='+')

    def _escape(self,event=None):
        if self._active:
            self.dismiss();return 'break'

    @staticmethod
    def _path_inside(widget, surface, anchors=()):
        # Tcl-native children such as ttk Combobox popdowns may not have a Python
        # master chain, but their window path still begins with the originating
        # widget/surface path.
        path=str(widget or '')
        prefixes=[str(surface),*[str(a) for a in anchors if a is not None]]
        return bool(path and any(path==prefix or path.startswith(prefix+'.') for prefix in prefixes))

    def _outside(self,event):
        active=self._active
        if not active:return
        widget=getattr(event,'widget',None);surface=active['surface'];anchors=active['anchors']
        try:
            if widget is not None and (_inside(widget,surface) or any(_inside(widget,a) for a in anchors) or self._path_inside(widget,surface,anchors)):
                return
        except tk.TclError:
            pass
        # A pointer press outside is decisive even when the clicked Canvas/Frame
        # does not accept focus. That is the common source of contextual panels
        # lingering after the user has plainly moved on. Focus-only changes remain
        # deferred so native Combobox popdowns can settle first.
        pointer=getattr(event,'type',None)==tk.EventType.ButtonPress
        self._schedule_check(widget,pointer=pointer)

    def _schedule_check(self, event_widget=None, *, pointer=False):
        if self._pending is not None:
            try:self.root.after_cancel(self._pending)
            except tk.TclError:pass
        self._pending=self.root.after_idle(lambda:self._check(event_widget,pointer=pointer))

    def _check(self,event_widget=None,*,pointer=False):
        self._pending=None
        active=self._active
        if not active:return
        surface=active['surface'];anchors=active['anchors']
        try:
            if surface is None or not surface.winfo_exists():
                self._active=None;return
            if event_widget is not None and (_inside(event_widget,surface) or any(_inside(event_widget,a) for a in anchors) or self._path_inside(event_widget,surface,anchors)):
                return
            if pointer:
                self.dismiss();return
            focus=self.root.focus_get()
            if focus is not None and (_inside(focus,surface) or any(_inside(focus,a) for a in anchors) or self._path_inside(focus,surface,anchors)):
                return
        except tk.TclError:
            pass
        self.dismiss()

    def dismiss(self, key=None):
        active=self._active
        if not active or (key is not None and active['key']!=key):return False
        self._active=None
        close=active['close']
        try:close()
        except tk.TclError:pass
        return True

    def forget(self, key=None):
        """Forget the active registration after its owner closed it directly."""
        if not self._active or (key is not None and self._active['key']!=key):return False
        self._active=None;return True

    def destroy(self):
        if self._pending is not None:
            try:self.root.after_cancel(self._pending)
            except tk.TclError:pass
            self._pending=None
        for sequence,bid in (('<ButtonPress>',self._button_bind),('<FocusIn>',self._focus_bind),('<Escape>',self._escape_bind)):
            if bid:
                try:self.root._root()._unbind(('bind','all',sequence),bid)
                except tk.TclError:pass
        self._button_bind=self._focus_bind=self._escape_bind=None;self._active=None


def popup_coordinates(anchor, menu_width, menu_height, event=None):
    """Keep contextual menus inside the desktop; flip above when bottom cramped."""
    vx=anchor.winfo_vrootx();vy=anchor.winfo_vrooty()
    vw=anchor.winfo_vrootwidth() or anchor.winfo_screenwidth()
    vh=anchor.winfo_vrootheight() or anchor.winfo_screenheight()
    pad=8
    x=event.x_root if event is not None else anchor.winfo_rootx()
    bottom=anchor.winfo_rooty()+anchor.winfo_height()
    y=event.y_root if event is not None else bottom
    if y+menu_height>vy+vh-pad:y=(event.y_root if event else anchor.winfo_rooty())-menu_height
    return max(vx+pad,min(x,vx+vw-pad-menu_width)),max(vy+pad,min(y,vy+vh-pad-menu_height))

def post_native_menu(root, menu, anchor, event=None, *, dispose_menu=True):
    """Post an owned native menu; dispose it only after the native selection ends.

    Tk's tk_popup returns while the menu is still posted. A finally/destroy there
    makes the menu flash and vanish. Conversely, keeping each menu indefinitely
    leaks its descendants and Tcl commands. Unmap is the lifetime boundary.
    """
    controller=getattr(root,'contextual_surfaces',None)
    if controller and controller.active():controller.dismiss()
    previous = getattr(root, '_posted_native_menu', None)
    if previous:
        same_anchor = previous['anchor'] is anchor
        previous['dismiss']()
        if same_anchor:
            if dispose_menu:menu.destroy()
            return
    bindings = []
    closed = [False]
    record = {'menu': menu, 'anchor': anchor}

    def dispose(event=None):
        if event is not None and event.widget is not menu:
            return
        if closed[0]:
            return
        closed[0] = True
        for sequence, binding in bindings:
            try:
                root._root()._unbind(('bind', 'all', sequence), binding)
                script=str(root.tk.call('bind','all',sequence))
                root.tk.call('bind','all',sequence,script.rstrip()+'\n' if script.strip() else '')
            except tk.TclError:
                pass
        if getattr(root, '_posted_native_menu', None) is record:
            root._posted_native_menu = None
        # The native command callback may still be executing on Unmap.
        if dispose_menu:
            try:
                root.after_idle(lambda: menu.destroy() if menu.winfo_exists() else None)
            except tk.TclError:
                pass

    def dismiss(event=None):
        widget = getattr(event, 'widget', None)
        if event is not None and ContextualSurfaceController._path_inside(widget, menu, (anchor,)):
            return
        try:
            menu.unpost()
            menu.grab_release()
        except tk.TclError:
            pass
        dispose()

    def escape(event=None):
        dismiss()
        return 'break'

    record['dismiss'] = dismiss
    root._posted_native_menu = record
    menu.bind('<Unmap>', dispose, add='+')
    menu.bind('<Destroy>', dispose, add='+')
    bindings.append(('<ButtonPress>', root.bind_all('<ButtonPress>', dismiss, add='+')))
    bindings.append(('<FocusIn>', root.bind_all('<FocusIn>', dismiss, add='+')))
    bindings.append(('<Escape>', root.bind_all('<Escape>', escape, add='+')))
    try:
        menu.update_idletasks()
        count=menu.index('end')
        captions=[]
        if isinstance(count,int):
            for i in range(count+1):
                try:captions.append(str(menu.entrycget(i,'label')))
                except tk.TclError:pass
        guessed_width=min(460,max(140,44+max((len(name) for name in captions),default=8)*8))
        guessed_height=max(28,26*len(captions)+8)
        x,y=popup_coordinates(anchor,max(guessed_width,menu.winfo_reqwidth()),max(guessed_height,menu.winfo_reqheight()),event)
        menu.tk_popup(x,y)
    except tk.TclError:
        dismiss()
        raise
    finally:
        try:
            menu.grab_release()
        except tk.TclError:
            pass
