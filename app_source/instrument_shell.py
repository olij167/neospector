"""UX10: persistent media desk, output/rack, and an optional right module drawer.

The retained WorkspaceState stores media width in ``left``, its split in
``left_fraction`` and the rack share of the right column in ``rack_fraction``.
Only Audio and Conductor can become separate task windows.
"""
import tkinter as tk
from tkinter import ttk
from workspace_shell import WorkspaceShell
from workspace_system import WorkspaceState, panel_id


class InstrumentShell(WorkspaceShell):
    MAIN = ('panel.queues', 'panel.library', 'panel.programme', 'panel.rack')
    ADVANCED = ('panel.audio', 'panel.conductor')

    def __init__(self, parent, app, state):
        self.shelf_open=True
        self.left_open=False
        self.rack_open=False
        self.rack_overlay_side='left'
        super().__init__(parent, app, state)
        for rail in (self.left_rail, self.right_rail, self.bottom_rail):
            rail.grid_remove()
        self.stage.grid_configure(column=0, columnspan=3)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        for pid in self.frames:
            for widget in (self.headers[pid], self.titles[pid]):
                for event in ('<ButtonPress-1>', '<B1-Motion>', '<ButtonRelease-1>', '<Button-3>'):
                    widget.unbind(event)
                widget.configure(cursor='')
            self.menus[pid].configure(text='Focus' if pid in ('panel.rack','panel.programme') else 'Hide',
                width=7, command=lambda p=pid: self.maximize(p) if p in ('panel.rack','panel.programme') else self.collapse(p))
        self.titles['panel.programme'].configure(text='Output')
        self.titles['panel.queues'].configure(text='Media desk')
        self.left_restore=ttk.Button(self.stage,text='A ▸',width=3,command=lambda:self.show('Queues'))
        self.right_restore=ttk.Button(self.stage,text='◂ B',width=3,command=lambda:self.show('Library'))
        self.state.sizes['left']=0
        self.state.sizes['rack_fraction']=.57
        self.schedule()

    def resolve(self, pid):
        pid = panel_id(pid)
        if pid not in self.frames:
            raise KeyError('Unknown panel')
        return pid

    def apply(self, state):
        for pid in list(self._managed):
            self._unmanage(pid)
        self.state = WorkspaceState.from_dict(state.name, state.to_dict())
        s = self.state
        s.tabs.clear()
        for pid in self.MAIN:
            s.panels[pid].update(presentation='collapsed' if (pid == 'panel.library' and not self.shelf_open) or (pid == 'panel.queues' and not self.left_open) else 'docked',
                                 zone='right' if pid=='panel.library' else 'left' if pid=='panel.queues' else 'centre',
                                 last_presentation='docked', restore_on_show=True, tab_peers=[])
        for pid in self.ADVANCED:
            if s.panels[pid]['presentation']!='floating':s.panels[pid]['presentation']='collapsed'
        if s.maximized not in ('panel.programme','panel.rack'):s.maximized=''
        s.sizes['left']=0
        self.left_open=False
        s.sizes['rack_fraction']=min(.78,max(.48,s.sizes.get('rack_fraction',.58)))
        s.sizes['right']=min(360,max(235,s.sizes.get('right',295)))
        self._rects.clear();self.sync();self.schedule()

    def sync(self):
        super().sync()
        for pid in ('panel.rack', 'panel.programme'):
            if pid in self.menus:
                self.menus[pid].configure(
                    text='Restore' if self.state.maximized == pid else 'Focus')

    def visible_ids(self):
        if self.state.maximized:
            return {self.state.maximized}
        return {p for p, s in self.state.panels.items() if s['presentation'] != 'collapsed'}

    def flip_rack_overlay(self):
        self.rack_overlay_side='left' if self.rack_overlay_side=='right' else 'right'
        self.schedule()

    def toggle_media(self):
        # The right edge rail always remains discoverable.
        if hasattr(self.app,'sidebar'):
            opened=self.app.sidebar.open_roles()
            for role in opened:self.app.sidebar.set_open(role,False)
            if not opened:self.app.sidebar.set_open('B',True)
            return True
        return self.show('Library')

    def show(self,pid):
        pid=self.resolve(pid);self.state.maximized=''
        if pid=='panel.rack':
            self.rack_open=True
            if hasattr(self.app,'sidebar'):
                self.app.sidebar._browser_open=False
                self.app.sidebar._sync()
        if pid=='panel.library':self.shelf_open=True
        if pid=='panel.queues':self.left_open=False
        self.state.panels[pid]['presentation']='floating' if pid in self.ADVANCED else 'docked'
        self.changed();return True

    def collapse(self,pid):
        pid=self.resolve(pid)
        if pid=='panel.library':
            if hasattr(self.app,'sidebar'):
                for role in self.app.sidebar.open_roles():self.app.sidebar.set_open(role,False)
            self.shelf_open=True;self.state.panels[pid]['presentation']='docked';self.changed();return True
        if pid=='panel.queues':
            self.left_open=False;self.state.panels[pid]['presentation']='collapsed';self.changed();return True
        if pid=='panel.rack':
            self.rack_open=False;self.state.maximized='';self.changed();return True
        if pid in self.MAIN:return False
        return super().collapse(pid)

    def dock(self, pid, zone=None):
        pid = self.resolve(pid)
        if pid in self.ADVANCED:
            return self.show(pid)
        return self.show(pid)

    def float_panel(self, pid):
        pid = self.resolve(pid)
        return self.show(pid) if pid in self.ADVANCED else False

    def maximize(self, pid):
        pid = self.resolve(pid)
        if pid not in ('panel.rack', 'panel.programme'):
            return False
        return super().maximize(pid)

    def tab_with(self, pid, target):
        return False

    def drag_begin(self, event, pid):
        return None

    def panel_menu(self, pid, event=None):
        # All panel actions are represented by the visible Focus/Hide controls.
        # Right-clicking the workspace no longer opens a redundant native menu.
        self.resolve(pid)
        return 'break'

    def mount_panel_controls(self, pid, host):
        pid = self.resolve(pid)
        self.headers[pid].pack_forget()
        self.menus[pid].destroy()
        self.pins[pid].destroy()
        self.menus[pid] = ttk.Button(host, text='Focus' if pid in ('panel.rack','panel.programme') else 'Hide', width=7,
            command=lambda: self.maximize(pid) if pid in ('panel.rack','panel.programme') else self.collapse(pid))
        self.menus[pid].pack(side='right')
        # Compatibility placeholder; never displayed as a docking action.
        self.pins[pid] = ttk.Button(host)

    def layout(self):
        self._pending=None
        if self._closed:return
        w,h=self.stage.winfo_width(),self.stage.winfo_height()
        if w<10 or h<10:return
        for grip in self.grips.values():self._hide(grip)
        self._hide(self.drawer_grip)
        self.left_restore.place_forget();self.right_restore.place_forget()
        for pid in self.ADVANCED:
            if self.state.panels[pid]['presentation']=='floating':self._manage(pid)
            elif pid in self._managed:self.tk.call('wm','withdraw',self.frames[pid]._w)
            else:self._hide(self.frames[pid])
        if self.state.maximized:
            for pid in self.MAIN:
                if pid==self.state.maximized:self._place(self.frames[pid],(0,0,w,h))
                else:self._hide(self.frames[pid])
            return
        gap=self.GAP
        self.left_open=False
        stack=self.app.sidebar
        roles=stack.stack_roles()
        # UX25: queue geometry is always bottom-anchored. Opening a third
        # queue never switches to a sidebar or moves existing queues upward.
        dw=0
        browser_open=bool(stack._browser_open)
        media_width=min(405,max(300,int(w*.285))) if browser_open else 0
        work_width=0
        if self.rack_open:
            work_width=min(500,max(305,int(w*.33)))
            work_width=min(work_width,max(260,w-dw-365-2*gap))
        left_width=max(media_width,work_width)
        px=left_width+gap if left_width else 0
        pw=max(260,w-dw-px-gap*int(bool(dw)))
        self._zone_rects={'left':(0,0,left_width,h),
                          'centre':(px,0,pw,h),'right':(w-dw,0,dw,h) if dw else (w,0,0,h)}
        self._hide(self.frames['panel.queues'])
        self._place(self.frames['panel.programme'],(px,0,pw,h))
        if browser_open and self.rack_open:
            browser_height=max(240,min(int(h*.57),stack.source_shelf.requested_height()+90))
            rack_height=max(180,h-browser_height-gap)
            self._place(self.frames['panel.rack'],(0,0,left_width,rack_height))
            self._place(stack.browser_frame,(0,rack_height+gap,left_width,h-rack_height-gap))
        elif browser_open:
            # A useful full-height media/source shelf with a flexible file list;
            # unlike a popup it never covers the output preview.
            self._hide(self.frames['panel.rack'])
            self._place(stack.browser_frame,(0,0,left_width,h))
        elif self.rack_open:
            self._hide(stack.browser_frame)
            self._place(self.frames['panel.rack'],(0,0,left_width,h))
        else:
            self._hide(stack.browser_frame);self._hide(self.frames['panel.rack'])
        self._hide(self.grips['rack_fraction'])
        # One anchored right stack; A, B and Music have identical placement
        # semantics. The entire preview becomes free when trays are closed.
        stack.dock_bar.place_forget();stack.music_dock_bar.place_forget()
        if roles:
            aw=min(380,max(304,int(w*.305)))
            visual_top=max(0,self.app.viewport.canvas.winfo_rooty()-self.stage.winfo_rooty()) if hasattr(self.app,'viewport') else 95
            visual_top=min(max(98,visual_top+28),int(h*.65))
            available=max(245,h-visual_top-2*gap-4)
            height=stack.fit_heights(available)
            top=max(2,h-gap-height)
            self._place(self.frames['panel.library'],(w-aw-gap,top,aw,height))
            self._hide(self.grips['right'])
            self.frames['panel.library'].lift()
            stack.request_fit()
        else:
            self._hide(self.frames['panel.library'])
            self._hide(self.grips['right'])
        self.sync()
