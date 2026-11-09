"""Six retained panels, four bounded zones, one presentation engine.

Panel frames keep a common ancestor for their entire life. Tk's wm manage/forget
changes their presentation without recreating a view, a decoder or a rack owner.
Drawers are overlays; docking is the only operation that consumes canvas space.
"""
from __future__ import annotations
import copy
import tkinter as tk
from tkinter import ttk
from workspace_system import PANEL_IDS, PANEL_NAMES, ZONES, WorkspaceState, panel_id


class EdgeTab(tk.Canvas):
    def __init__(self, parent, label, command, *, vertical=False, chrome=None):
        self.label=label;self.command=command;self.vertical=vertical
        self.chrome=chrome or {}
        super().__init__(parent,width=28 if vertical else 126,height=126 if vertical else 27,
                         highlightthickness=1,takefocus=True,bd=0,cursor='hand2')
        self.bind('<Button-1>',lambda e:self.command())
        self.bind('<Return>',lambda e:self.command());self.bind('<space>',lambda e:(self.command(),'break')[1])
        self.hover=False;self.focused=False
        self.bind('<Enter>',lambda e:self._state(hover=True))
        self.bind('<Leave>',lambda e:self._state(hover=False))
        self.bind('<FocusIn>',lambda e:self._state(focused=True))
        self.bind('<FocusOut>',lambda e:self._state(focused=False))
        self.active=False;self.paint(False)
    def _state(self,**changes):
        for key,value in changes.items():setattr(self,key,value)
        self.paint(self.active)
    def paint(self, active):
        self.active=active;c=self.chrome
        bg=c.get('panel_bg',c.get('background','#191923'));fg=c.get('text',c.get('foreground','#edeaf4'))
        accent=c.get('accent','#ad97db');emphasis=active or self.hover or self.focused
        self.configure(bg=bg,highlightbackground=accent if emphasis else bg)
        self.delete('all')
        if emphasis:
            if self.vertical:self.create_rectangle(1,3,4,122,fill=accent,outline='')
            else:self.create_rectangle(3,22,122,25,fill=accent,outline='')
        self.create_text(15 if self.vertical else 63,59 if self.vertical else 11,
             text=self.label,angle=90 if self.vertical else 0,fill=fg,
             font=('TkDefaultFont',9,'bold' if emphasis else 'normal'))
        self.create_text(15 if self.vertical else 63,112 if self.vertical else 21,
             text='◆' if active else '▸' if emphasis else '·',fill=accent if emphasis else fg,
             font=('TkDefaultFont',7))


class WorkspaceShell(ttk.Frame):
    HEADER=27
    GAP=8
    def __init__(self,parent,app,state):
        super().__init__(parent);self.app=app;self.state=state
        self.frames={};self.headers={};self.bodies={};self.titles={};self.menus={};self.pins={}
        self._managed=set();self._rects={};self._pending=None;self._opener=None
        self._drag=None;self._drop_overlay=None;self._sizing=None;self._closed=False
        self.left_rail=ttk.Frame(self);self.left_rail.grid(row=0,column=0,sticky='ns')
        self.stage=tk.Frame(self,bg=app.ui_chrome.get('background','#15151c'),bd=0,highlightthickness=0)
        self.stage.grid(row=0,column=1,sticky='nsew')
        self.right_rail=ttk.Frame(self);self.right_rail.grid(row=0,column=2,sticky='ns')
        self.bottom_rail=ttk.Frame(self);self.bottom_rail.grid(row=1,column=0,columnspan=3,sticky='ew')
        self.rowconfigure(0,weight=1);self.columnconfigure(1,weight=1)
        self.edge_tabs={}
        for pid,rail,vert in [('panel.queues',self.bottom_rail,False),('panel.library',self.bottom_rail,False),
                              ('panel.conductor',self.bottom_rail,False),('panel.audio',self.bottom_rail,False)]:
            tab=EdgeTab(rail,'Channels + FX' if pid=='panel.queues' else PANEL_NAMES[pid],lambda p=pid:self.toggle(p),vertical=vert,chrome=app.ui_chrome)
            tab.pack(side='top' if vert else 'left',pady=1,padx=1);self.edge_tabs[pid]=tab
            if hasattr(app,'add_tip'):app.add_tip(tab,'Show or hide '+PANEL_NAMES[pid]+'. An inactive stacked panel is selected first. Placement and playback are retained.')
        for pid in PANEL_IDS:
            frame=tk.Frame(self.stage,bg=app.ui_chrome.get('background','#15151c'),bd=0,highlightthickness=1,
                           highlightbackground=app.ui_chrome.get('sash_color','#44414e'))
            header=ttk.Frame(frame,padding=(5,1));header.pack(fill='x')
            title=ttk.Label(header,text='Module Rack' if pid=='panel.rack' else PANEL_NAMES[pid],style='PlayerName.TLabel',cursor='fleur')
            title.pack(side='left')
            menu=ttk.Button(header,text='⋯',width=3,command=lambda p=pid:self.panel_menu(p));menu.pack(side='right')
            pin=ttk.Button(header,text='Pin',width=4,command=lambda p=pid:self.dock(p,self.state.panels[p]['edge']))
            body=ttk.Frame(frame);body.pack(fill='both',expand=True)
            self.frames[pid]=frame;self.headers[pid]=header;self.bodies[pid]=body;self.titles[pid]=title;self.menus[pid]=menu;self.pins[pid]=pin
            for widget in (header,title):
                widget.bind('<ButtonPress-1>',lambda e,p=pid:self.drag_begin(e,p))
                widget.bind('<B1-Motion>',self.drag_motion)
                widget.bind('<ButtonRelease-1>',self.drag_end)
                widget.bind('<Double-Button-1>',lambda e,p=pid:(self.maximize(p),'break')[1])
                widget.bind('<Button-3>',lambda e,p=pid:self.panel_menu(p,e))
        self.grips={}
        for key,cursor in [('left','sb_h_double_arrow'),('right','sb_h_double_arrow'),('bottom','sb_v_double_arrow'),
                           ('rack_fraction','sb_v_double_arrow'),('right_fraction','sb_v_double_arrow'),('left_fraction','sb_v_double_arrow'),('bottom_fraction','sb_v_double_arrow')]:
            grip=tk.Frame(self.stage,height=5,width=5,cursor=cursor,bg=app.ui_chrome.get('sash_color','#44414e'))
            grip.bind('<ButtonPress-1>',lambda e,k=key:self.resize_begin(e,k));grip.bind('<B1-Motion>',self.resize_motion)
            grip.bind('<ButtonRelease-1>',self.resize_end);self.grips[key]=grip
        self.drawer_grip=tk.Frame(self.stage,bg=app.ui_chrome.get('sash_color','#44414e'))
        self.drawer_grip.bind('<ButtonPress-1>',lambda e:self.resize_begin(e,'drawer'))
        self.drawer_grip.bind('<B1-Motion>',self.resize_motion);self.drawer_grip.bind('<ButtonRelease-1>',self.resize_end)
        self.stage.bind('<Configure>',lambda e:self.schedule())
        self.bind('<Destroy>',self._destroy,add='+')
        self._outside_id=self.app.bind_all('<ButtonPress-1>',self._outside,add='+')
        self.apply(state)

    def _destroy(self,e):
        if e.widget is not self:return
        self._closed=True
        if self._pending:
            try:self.after_cancel(self._pending)
            except tk.TclError:pass
        # unbind only our callback, never other application handlers.
        try:self.app._unbind(('bind','all','<ButtonPress-1>'),self._outside_id)
        except (tk.TclError,AttributeError):pass

    def mount_panel_controls(self,pid,host):
        """Place panel actions into its content toolbar without a second header."""
        pid=self.resolve(pid);self.headers[pid].pack_forget()
        self.menus[pid].destroy();self.pins[pid].destroy()
        self.menus[pid]=ttk.Button(host,text='⋯',width=3,command=lambda:self.panel_menu(pid))
        self.menus[pid].pack(side='right')
        self.pins[pid]=ttk.Button(host,text='Pin',width=4,command=lambda:self.dock(pid,self.state.panels[pid]['edge']))
        host.bind('<ButtonPress-1>',lambda e:self.drag_begin(e,pid))
        host.bind('<B1-Motion>',self.drag_motion);host.bind('<ButtonRelease-1>',self.drag_end)
        host.bind('<Double-Button-1>',lambda e:(self.maximize(pid),'break')[1])
        host.bind('<Button-3>',lambda e:self.panel_menu(pid,e))
        self.sync()

    def resolve(self,pid):
        pid=panel_id(pid)
        if pid=='panel.rack':pid='panel.queues'
        if pid not in self.frames:raise KeyError('Unknown panel')
        return pid
    def snapshot(self,name=None):
        for pid in self._managed:
            try:self.state.panels[pid]['geometry']=str(self.tk.call('wm','geometry',self.frames[pid]._w))
            except tk.TclError:pass
        return WorkspaceState.from_dict(name or self.state.name,self.state.to_dict())
    def apply(self,state):
        for pid in list(self._managed):self._unmanage(pid)
        self.state=WorkspaceState.from_dict(state.name,state.to_dict())
        # Present the retained rack inside Channels, including old saved layouts.
        rack=self.state.panels['panel.rack'];queues=self.state.panels['panel.queues']
        if rack['presentation']!='collapsed' and queues['presentation']=='collapsed':
            queues.update(presentation='docked',zone='bottom',edge='bottom',restore_on_show=True)
            self.state.sizes['bottom']=max(390,self.state.sizes['bottom'])
        rack['presentation']='collapsed'
        for zone,group in list(self.state.tabs.items()):
            group['members']=[p for p in group['members'] if p!='panel.rack']
            if len(group['members'])<2:
                for member in group['members']:self.state.panels[member]['presentation']='docked'
                del self.state.tabs[zone]
            elif group['active']=='panel.rack':group['active']=group['members'][0]
        if self.state.maximized=='panel.rack':self.state.maximized='panel.queues'
        self._rects.clear();self.sync();self.schedule()
    def sync(self):
        self.app.panel_states={PANEL_NAMES[p]:s['presentation']!='collapsed' for p,s in self.state.panels.items()}
        self.app.panel_floats={PANEL_NAMES[p]:self.frames[p] for p in self._managed}
        self.app.panel_tab_groups={z:PANEL_NAMES[g['active']] for z,g in self.state.tabs.items()}
        self.app._maximized_panel=PANEL_NAMES.get(self.state.maximized,'')
        if hasattr(self.app,'workspace_controller'):self.app.workspace_controller.state=self.state
        if hasattr(self.app,'workspace_locked'):self.app.workspace_locked.set(self.state.locked)
        for pid,tab in self.edge_tabs.items():tab.paint(pid in self.visible_ids())
        for pid,pin in self.pins.items():
            if self.state.panels[pid]['presentation']=='drawer':pin.pack(side='right',before=self.menus[pid],padx=2)
            else:pin.pack_forget()
    def changed(self):
        self.sync();self.schedule()
        if hasattr(self.app,'queue_deck'):self.app.save_preferences()
    def schedule(self):
        if not self._closed and self._pending is None:self._pending=self.after_idle(self.layout)
    def _place(self,w,rect):
        rect=tuple(int(max(1,n)) if i>1 else int(n) for i,n in enumerate(rect))
        if self._rects.get(w)!=rect or not w.winfo_manager():w.place(x=rect[0],y=rect[1],width=rect[2],height=rect[3]);self._rects[w]=rect
    def _hide(self,w):
        if w.winfo_manager()=='place':w.place_forget()
        self._rects.pop(w,None)
    def visible_ids(self):
        if self.state.maximized:return {self.state.maximized}
        inactive={pid for g in self.state.tabs.values() for pid in g['members'] if pid!=g['active']}
        return {pid for pid,s in self.state.panels.items() if s['presentation']!='collapsed' and pid not in inactive}
    def _unmanage(self,pid):
        if pid not in self._managed:return
        frame=self.frames[pid]
        try:
            self.state.panels[pid]['geometry']=str(self.tk.call('wm','geometry',frame._w))
            self.tk.call('wm','forget',frame._w)
        except tk.TclError:pass
        self._managed.discard(pid);self._rects.pop(frame,None)
    def _manage(self,pid):
        frame=self.frames[pid];s=self.state.panels[pid]
        if pid not in self._managed:
            self._hide(frame);self.tk.call('wm','manage',frame._w);self._managed.add(pid)
            self.tk.call('wm','title',frame._w,PANEL_NAMES[pid]+' · Neospector')
            self.tk.call('wm','minsize',frame._w,330,220)
            if not hasattr(frame,'_workspace_close'):
                frame._workspace_close=self.register(lambda p=pid:self.collapse(p))
            self.tk.call('wm','protocol',frame._w,'WM_DELETE_WINDOW',frame._workspace_close)
            geometry=s['geometry'] or ('1000x430' if pid in ('panel.queues','panel.rack') else '600x620')
            from workspace_system import clamp_float_geometry
            geometry=clamp_float_geometry(geometry,(self.app.winfo_vrootx(),self.app.winfo_vrooty(),self.app.winfo_screenwidth(),self.app.winfo_screenheight()))
            s['geometry']=geometry
            try:self.tk.call('wm','geometry',frame._w,geometry)
            except tk.TclError:self.tk.call('wm','geometry',frame._w,'600x520')
        self.tk.call('wm','deiconify',frame._w)
    def _untab(self,pid):
        for zone,g in list(self.state.tabs.items()):
            if pid not in g['members']:continue
            g['members'].remove(pid)
            if len(g['members'])<2:
                for p in g['members']:self.state.panels[p]['presentation']='docked'
                self.state.tabs.pop(zone)
            elif g['active']==pid:g['active']=g['members'][0]
    def show(self,pid):
        pid=self.resolve(pid);s=self.state.panels[pid]
        if self.state.maximized and self.state.maximized!=pid:self.state.maximized=''
        if s['presentation']=='collapsed':
            self._opener=self.app.focus_get()
            if s['last_presentation']=='floating':s['presentation']='floating'
            elif s.get('restore_on_show'):
                s['presentation']='docked'
                peers=[p for p in s.get('tab_peers',[]) if self.state.panels[p]['zone']==s['zone'] and self.state.panels[p]['presentation'] in ('docked','tabbed')]
                if peers:
                    group=self.state.tabs.setdefault(s['zone'],{'members':peers[:1],'active':pid})
                    if pid not in group['members']:group['members'].append(pid)
                    group['active']=pid
                    for p in group['members']:self.state.panels[p]['presentation']='tabbed'
            else:
                self.dismiss_drawer();s['presentation']='docked'
        if s['presentation']=='tabbed':self.state.tabs[s['zone']]['active']=pid
        if s['presentation']=='floating':self._manage(pid);self.frames[pid].lift()
        self.changed();return True
    def toggle(self,pid):
        pid=self.resolve(pid);s=self.state.panels[pid]
        if s['presentation']=='tabbed' and self.state.tabs[s['zone']]['active']!=pid:
            return self.show(pid)
        if s['presentation']!='collapsed':return self.collapse(pid)
        return self.show(pid)
    def dismiss_drawer(self):
        changed=False
        for pid,s in self.state.panels.items():
            if s['presentation']=='drawer':s['presentation']='collapsed';changed=True
        if changed:self.changed()
        return changed
    def collapse(self,pid):
        pid=self.resolve(pid)
        if pid=='panel.programme':
            if pid in self._managed:return self.dock(pid,'centre')
            return False
        s=self.state.panels[pid]
        if s['presentation'] not in ('collapsed','drawer'):
            s['last_presentation']=s['presentation'];s['restore_on_show']=True
        group=self.state.tabs.get(s['zone'])
        if group and pid in group['members']:
            for p in group['members']:self.state.panels[p]['tab_peers']=[q for q in group['members'] if q!=p]
        self._untab(pid)
        if pid in self._managed:
            s['geometry']=str(self.tk.call('wm','geometry',self.frames[pid]._w));self.tk.call('wm','withdraw',self.frames[pid]._w)
        s['presentation']='collapsed'
        if self.state.maximized==pid:self.state.maximized=''
        self.changed();self.restore_focus();return True
    def restore_focus(self):
        try:
            if self._opener and self._opener.winfo_exists():self._opener.focus_set()
        except tk.TclError:pass
        self._opener=None
    def dock(self,pid,zone=None):
        pid=self.resolve(pid)
        if self.state.locked:return False
        s=self.state.panels[pid];zone=zone or s['zone']
        if zone not in ZONES:return False
        self._untab(pid);self._unmanage(pid)
        s.update(presentation='docked',zone=zone,last_presentation='docked',restore_on_show=True,tab_peers=[])
        if zone!='centre':s['edge']=zone
        s['order']=max([p['order'] for p in self.state.panels.values() if p['zone']==zone]+[0])+1
        self.state.maximized='';self.changed();return True
    def float_panel(self,pid):
        pid=self.resolve(pid)
        if self.state.locked:return False
        self._untab(pid);s=self.state.panels[pid];s.update(presentation='floating',last_presentation='floating')
        self.state.maximized='';self._manage(pid);self.changed();return True
    def maximize(self,pid):
        pid=self.resolve(pid)
        if self.state.maximized==pid:self.state.maximized=''
        else:self.state.maximized=pid
        self.changed();return True
    def escape(self):
        if self._drag:self.cancel_drag();return True
        if self.state.maximized:self.state.maximized='';self.changed();return True
        if self.dismiss_drawer():self.restore_focus();return True
        return False
    def tab_with(self,pid,target):
        pid=self.resolve(pid);target=self.resolve(target)
        if pid==target or self.state.locked:return False
        zone=self.state.panels[target]['zone']
        if self.state.panels[target]['presentation'] not in ('docked','tabbed'):self.dock(target,zone)
        self._untab(pid);self._unmanage(pid)
        group=self.state.tabs.setdefault(zone,{'members':[target],'active':target})
        for p in (target,pid):
            if p not in group['members']:group['members'].append(p)
            self.state.panels[p].update(presentation='tabbed',zone=zone,last_presentation='tabbed')
        group['active']=pid;self.state.maximized='';self.changed();return True
    def select_tab(self,zone,pid):
        pid=self.resolve(pid);g=self.state.tabs.get(zone)
        if not g or pid not in g['members']:return False
        g['active']=pid;self.changed();return True
    def ungroup(self,zone):
        if self.state.locked:return False
        g=self.state.tabs.pop(zone,None)
        if not g:return False
        for p in g['members']:self.state.panels[p]['presentation']='docked'
        self.changed();return True
    def _outside(self,event):
        pid=next((p for p,s in self.state.panels.items() if s['presentation']=='drawer'),None)
        if not pid:return
        w=event.widget
        # A contextual popup and native menu must not cause the editor to disappear.
        try:
            if w.winfo_toplevel()!=self.app:return
        except (AttributeError,tk.TclError):return
        if any(str(w).startswith(str(x)) for x in [self.frames[pid],*self.edge_tabs.values()]):return
        self.dismiss_drawer()
    def layout(self):
        self._pending=None
        if self._closed:return
        w=max(1,self.stage.winfo_width());h=max(1,self.stage.winfo_height())
        if w<10 or h<10:return
        for grip in self.grips.values():self._hide(grip)
        self._hide(self.drawer_grip)
        if self.state.maximized:
            pid=self.state.maximized
            for p,f in self.frames.items():
                if p in self._managed:
                    if p==pid:self._unmanage(p)
                    else:self.tk.call('wm','withdraw',f._w)
                if p!=pid:self._hide(f)
            self._place(self.frames[pid],(0,0,w,h));self.frames[pid].lift();return
        zones={z:[] for z in ZONES}
        for pid,s in self.state.panels.items():
            f=self.frames[pid]
            if s['presentation']=='floating':self._manage(pid);continue
            if pid in self._managed:
                if s['presentation']=='collapsed':self.tk.call('wm','withdraw',f._w);continue
                self._unmanage(pid)
            if s['presentation'] in ('docked','tabbed'):zones[s['zone']].append(pid)
            elif s['presentation']=='collapsed':self._hide(f)
        for ids in zones.values():ids.sort(key=lambda p:self.state.panels[p]['order'])
        gap=self.GAP;sizes=self.state.sizes
        bh=min(sizes['bottom'],max(180,h*(.74 if 'panel.queues' in zones['bottom'] else .57))) if zones['bottom'] else 0
        top=h-bh-(gap if bh else 0)
        lw=min(sizes['left'],max(250,w*.38)) if zones['left'] else 0
        rw=min(sizes['right'],max(250,w*.35)) if zones['right'] else 0
        # Both side docks yield proportionally before taking away the working centre.
        allowed=max(0,w-360-gap*2)
        if lw+rw>allowed and lw+rw>0:
            scale=allowed/(lw+rw);lw*=scale;rw*=scale
        cx=lw+(gap if lw else 0);cw=w-cx-rw-(gap if rw else 0)
        rects={'left':(0,0,lw,top),'right':(w-rw,0,rw,top),'centre':(cx,0,cw,top),'bottom':(0,h-bh,w,bh)}
        self._zone_rects=rects
        for zone,ids in zones.items():
            if not ids:continue
            x,y,ww,hh=rects[zone];group=self.state.tabs.get(zone)
            if group:
                # The existing edge rail is the sole tab selector. Stacking is
                # retained in the model without a duplicate strip above content.
                for p in group['members']:
                    if p!=group['active']:self._hide(self.frames[p])
                ids=[p for p in ids if p not in group['members'] or p==group['active']]
            if len(ids)==2:
                frac_key='rack_fraction' if zone=='centre' else zone+'_fraction'
                if zone=='centre' and 'panel.rack' in ids:
                    ids.sort(key=lambda p:p=='panel.rack');fraction=1-sizes.get(frac_key,.46)
                else:fraction=sizes.get(frac_key,.58 if zone=='right' else .5)
                first=max(100,min(hh-105,(hh-gap)*fraction))
                heights=[first,max(100,hh-gap-first)]
                if frac_key in self.grips:
                    self._place(self.grips[frac_key],(x,y+first,ww,gap));self.grips[frac_key].lift()
            else:heights=[max(1,(hh-gap*(len(ids)-1))/len(ids))]*len(ids)
            for pid,height in zip(ids,heights):
                self._place(self.frames[pid],(x,y,ww,height));y+=height+gap
        for grip in self.grips.values():
            if grip.winfo_manager():grip.lift()
        for key,rect in [('left',(lw,0,gap,top)),('right',(w-rw-gap,0,gap,top)),('bottom',(0,h-bh-gap,w,gap))]:
            if zones[key]:self._place(self.grips[key],rect);self.grips[key].lift()
        for pid,s in self.state.panels.items():
            if s['presentation']!='drawer':continue
            edge=s['edge'];f=self.frames[pid]
            if edge=='bottom':
                dh=min(max(320,sizes['drawer_bottom']),max(220,h-70));rect=(0,h-dh,w,dh);grip=(0,h-dh-5,w,5)
            else:
                dw=min(max(380,sizes['drawer_'+edge]),max(280,w-60));rect=(0 if edge=='left' else w-dw,0,dw,h)
                grip=(dw if edge=='left' else w-dw-5,0,5,h)
            self._place(f,rect);f.lift();self.drawer_grip.configure(cursor='sb_v_double_arrow' if edge=='bottom' else 'sb_h_double_arrow')
            self._place(self.drawer_grip,grip);self.drawer_grip.lift()
        self.sync()
    def resize_begin(self,e,key):
        # Layout lock prevents panel relocation; resizing remains available.
        try:e.widget.grab_set()
        except (tk.TclError,AttributeError):pass
        self._sizing=(key,e.x_root,e.y_root,dict(self.state.sizes))
        return 'break'
    def resize_motion(self,e):
        if not self._sizing:return
        key,x,y,old=self._sizing;dx=e.x_root-x;dy=e.y_root-y;s=self.state.sizes
        if key=='drawer':
            pid=next((p for p,d in self.state.panels.items() if d['presentation']=='drawer'),None)
            if not pid:return
            edge=self.state.panels[pid]['edge'];k='drawer_'+edge
            s[k]=max(280,old[k]+(dx if edge=='left' else -dx if edge=='right' else -dy))
        elif key.endswith('_fraction'):
            zone='centre' if key=='rack_fraction' else key.split('_')[0];height=max(200,self._zone_rects[zone][3])
            s[key]=max(.18,min(.82,old.get(key,.5)+(-dy if key=='rack_fraction' else dy)/height))
        else:s[key]=max(180,old[key]+(dx if key=='left' else -dx if key=='right' else -dy))
        self.schedule();return 'break'
    def resize_end(self,e):
        if self._sizing:
            self._sizing=None
            try:e.widget.grab_release()
            except (tk.TclError,AttributeError):pass
            self.changed()
    def drag_begin(self,e,pid):
        if self.state.locked:return
        self._drag={'pid':pid,'x':e.x_root,'y':e.y_root,'active':False}
    def drag_motion(self,e):
        d=self._drag
        if not d:return
        if not d['active'] and abs(e.x_root-d['x'])+abs(e.y_root-d['y'])<9:return
        d['active']=True
        if self._drop_overlay is None:
            self._drop_overlay=tk.Canvas(self.stage,highlightthickness=1,bd=0,bg=self.app.ui_chrome.get('background','#15151c'))
            c=self._drop_overlay;w=self.stage.winfo_width();h=self.stage.winfo_height()
            self._drop_targets={}
            for zone,rect in {'left':(8,h//2-35,90,70),'right':(w-98,h//2-35,90,70),'bottom':(w//2-60,h-78,120,65),'centre':(w//2-60,30,120,65)}.items():
                target=ttk.Label(self.stage,text='Dock '+zone.title(),anchor='center',relief='solid',padding=8)
                target.place(x=rect[0],y=rect[1],width=rect[2],height=rect[3]);target.lift();self._drop_targets[zone]=(target,rect)
            c.destroy();self._drop_overlay=True
        return 'break'
    def drag_end(self,e):
        d=self._drag
        if not d:return
        if not d['active']:self.cancel_drag();return
        x=e.x_root-self.stage.winfo_rootx();y=e.y_root-self.stage.winfo_rooty();target=None
        for zone,(widget,(xx,yy,w,h)) in self._drop_targets.items():
            if xx<=x<=xx+w and yy<=y<=yy+h:target=zone;break
        pid=d['pid'];tab_target=None
        if target is None:
            for p,head in self.headers.items():
                if p==pid or not head.winfo_ismapped():continue
                xx=head.winfo_rootx();yy=head.winfo_rooty()
                if xx<=e.x_root<=xx+head.winfo_width() and yy<=e.y_root<=yy+head.winfo_height():tab_target=p;break
        self.cancel_drag()
        if target:self.dock(pid,target)
        elif tab_target:self.tab_with(pid,tab_target)
        else:self.float_panel(pid)
        return 'break'
    def cancel_drag(self):
        for widget,rect in getattr(self,'_drop_targets',{}).values():widget.destroy()
        self._drop_targets={};self._drop_overlay=None;self._drag=None
    def panel_menu(self,pid,event=None):
        pid=self.resolve(pid);s=self.state.panels[pid];menu=tk.Menu(self,tearoff=False)
        if pid=='panel.rack' and hasattr(self.app,'deck'):
            self.app.deck.populate_menu(menu);menu.add_separator()
        menu.add_command(label='Restore' if self.state.maximized==pid else 'Maximize',command=lambda:self.maximize(pid))
        menu.add_command(label='Float',command=lambda:self.float_panel(pid),state='disabled' if self.state.locked else 'normal')
        dock=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Dock',menu=dock,state='disabled' if self.state.locked else 'normal')
        for zone in ZONES:dock.add_command(label=zone.title(),command=lambda z=zone:self.dock(pid,z))
        tabs=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Tab with',menu=tabs,state='disabled' if self.state.locked else 'normal')
        for p in PANEL_IDS:
            if p!=pid:tabs.add_command(label=PANEL_NAMES[p],command=lambda q=p:self.tab_with(pid,q))
        if s['presentation']=='tabbed':menu.add_command(label='Separate tabs',command=lambda:self.ungroup(s['zone']))
        if pid=='panel.library' and hasattr(self.app,'populate_library_menu'):
            menu.add_separator();self.app.populate_library_menu(menu)
        if pid=='panel.programme' and hasattr(self.app,'populate_programme_menu'):
            menu.add_separator();self.app.populate_programme_menu(menu)
        if pid!='panel.programme':menu.add_separator();menu.add_command(label='Close to edge',command=lambda:self.collapse(pid))
        anchor=self.menus[pid]
        from contextual_surface import post_native_menu
        post_native_menu(self.app,menu,anchor,event)
