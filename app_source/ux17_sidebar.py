"""UX28: all three compact, content-responsive queues share the right corner.

Presentation does not own playback or camera state. No draggable sashes, no
spacer and no mode-dependent conversion into a full-height right sidebar.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

ROLES=('A','B','Music')
VISUAL_ROLES=('A','B')
from ux26_queue_layout import requested_height as requested_queue_height, allocate as allocate_queue_heights, GAP

class RightSourceStack(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent)
        self.app=app
        self.sections={};self.selected=None
        self._radio_browsing=False;self._browser_open=False;self._browser_request='A'
        self._fit_pending=False;self._fit_signature=None;self._flash_role=None;self._flash_ticket=None
        self.rail=ttk.Frame(self)  # compatibility handle; the rail lives on the stage instead
        self.pane=ttk.Frame(self);self.pane.pack(fill='both',expand=True)
        self.spacer=ttk.Frame(self.pane)  # compatibility only; never displayed
        for role in ROLES:
            # All three queues are peers with one height allocation rule.
            parent=self.pane
            frame=tk.Frame(parent,highlightthickness=2,highlightbackground='#34374a',
                           bd=0,bg=app.ui_chrome.get('panel_bg','#20232f'))
            frame.pack_propagate(False)
            self.sections[role]={'frame':frame,'button':None,'open':False}
        self.dock_bar=tk.Frame(app.shell.stage,bg=app.ui_chrome.get('panel_bg','#20232f'),
                               highlightthickness=1,highlightbackground='#576c89')
        self.dock_buttons={}
        for role,text in (('A','QUEUE A'),('B','QUEUE B')):
            button=ttk.Button(self.dock_bar,text=text,style='UX20.SourceIdle.TButton',
                               command=lambda r=role:self.toggle(r))
            button.pack(side='left',expand=True,fill='both',padx=2,pady=3)
            self.sections[role]['button']=button;self.dock_buttons[role]=button
            app.add_tip(button,'Show or hide '+('audio' if role=='Music' else role)+' queue · bottom-right dock')
        self.music_dock_bar=tk.Frame(app.shell.stage,bg=app.ui_chrome.get('panel_bg','#20232f'),
                                     highlightthickness=1,highlightbackground='#576c89')
        music_button=ttk.Button(self.music_dock_bar,text='♫ AUDIO',style='UX20.SourceIdle.TButton',
                                command=lambda:self.toggle('Music'))
        music_button.pack(fill='both',expand=True,padx=2,pady=3)
        self.sections['Music']['button']=music_button
        self.music_button=music_button
        app.add_tip(music_button,'Show or hide soundtrack queue · bottom-right preview dock')
        self.browser_frame=tk.Frame(app.shell.stage,bg=app.ui_chrome.get('panel_bg','#20232f'),
                                    highlightthickness=1,highlightbackground='#576c89')
        from ux23_source_shelf import SourceShelf
        self.source_shelf=SourceShelf(self.browser_frame,app)
        self.shared_browser=self.source_shelf.media
        self.source_shelf.pack(fill='both',expand=True)
        self._sync()

    def open_roles(self):
        # Legacy caller: A/B only. Use stack_roles() for actual placement.
        return tuple(role for role in VISUAL_ROLES if self.sections[role]['open'])

    def stack_roles(self):
        return tuple(role for role in ROLES if self.sections[role]['open'])

    def toggle(self,role):self.set_open(role,not self.sections[role]['open'])

    def set_open(self,role,opened):
        if role not in self.sections:raise KeyError(role)
        if role=='Music':
            if hasattr(self.app,'set_audio_tray_open'):
                self.app.set_audio_tray_open(bool(opened))
            else:
                self.sections['Music']['open']=bool(opened)
                self._sync();self.app.shell.schedule()
            return
        if self.sections[role]['open']==bool(opened):return
        self.sections[role]['open']=bool(opened)
        self._sync()
        self.app.shell.schedule()

    def requested_height(self,role):
        page=getattr(getattr(self.app,'queue_deck',None),'pages',{}).get(role)
        if role=='Music' and getattr(page,'audio_view','queue')=='mixer':
            from ux26_queue_layout import AUDIO_MIXER_IDEAL
            # Empty mixer is an invitation to add a source, not an empty fader
            # canvas permanently taking a third of the programme.
            return AUDIO_MIXER_IDEAL if getattr(page.audio_mixer,'rows',{}) else 140
        return requested_queue_height(role,bool(getattr(page,'upcoming_visible',False)),len(getattr(page,'future',())))

    def desired_height(self):
        roles=self.stack_roles()
        return sum(self.requested_height(r) for r in roles)+max(0,len(roles)-1)*GAP

    def fit_heights(self,available):
        roles=self.stack_roles()
        wanted={role:self.requested_height(role) for role in roles}
        expanded={role:bool(self.app.queue_deck.pages[role].upcoming_visible or
                            (role=='Music' and getattr(self.app.queue_deck.pages[role],'audio_view','queue')=='mixer' and getattr(self.app.queue_deck.pages[role].audio_mixer,'rows',{}))) for role in roles}
        allocated=allocate_queue_heights(roles,wanted,available,expanded)
        # Mixer is a scrolling input deck. Its fixed control chrome needs room
        # even when other queues are longer: let A/B upcoming canvases shrink.
        if 'Music' in roles and getattr(self.app.queue_deck.pages['Music'],'audio_view','queue')=='mixer':
            from ux26_queue_layout import AUDIO_MIXER_MIN
            mixer_page=self.app.queue_deck.pages['Music']
            minimum=AUDIO_MIXER_MIN if getattr(mixer_page.audio_mixer,'rows',{}) else 140
            if allocated['Music']<minimum:
                need=minimum-allocated['Music']
                for role in ('A','B'):
                    if role not in allocated:continue
                    floor=114 if not expanded.get(role) else 172
                    delta=min(need,max(0,allocated[role]-floor))
                    allocated[role]-=delta;allocated['Music']+=delta;need-=delta
                    if need<=0:break
        for role,height in allocated.items():
            self.sections[role]['frame'].configure(height=height)
        return sum(allocated.values())+max(0,len(roles)-1)*GAP

    def request_fit(self):
        # This is called often during playback: schedule only on an actual
        # disclosure/item-count change, not on each render or geometry event.
        roles=self.stack_roles()
        signature=(roles,tuple(self.requested_height(r) for r in roles))
        if signature==self._fit_signature:return
        self._fit_signature=signature
        if not self._fit_pending:
            self._fit_pending=True
            def work():
                self._fit_pending=False
                if self.winfo_exists():self.app.shell.schedule()
            self.after_idle(work)

    def open_browser(self,role,mode='files'):
        if role not in ROLES:raise KeyError(role)
        self._browser_request=role;self._browser_open=True
        if hasattr(self.app,'shell'):self.app.shell.rack_open=False
        self.source_shelf.show(mode,role)
        self._sync();self.app.shell.schedule()
        if hasattr(self.app,'refresh_main_effects_button'):self.app.refresh_main_effects_button()
    def toggle_browser(self,role):
        if self._browser_open and self._browser_request==role:self.close_browser()
        else:self.open_browser(role)
    def close_browser(self):
        if not self._browser_open:return
        self._browser_open=False;self._sync();self.app.shell.schedule()
        if hasattr(self.app,'refresh_main_effects_button'):self.app.refresh_main_effects_button()

    def _sync(self):
        """Incremental queue mount: opening B must never briefly unmap A.

        Tk repaints after each geometry invalidation; wholesale pack_forget()
        made already-visible trays disappear and return in several stages.
        """
        roles=self.stack_roles()
        for role in ROLES:
            frame=self.sections[role]['frame']
            if role not in roles and frame.winfo_manager():frame.pack_forget()
        for i,role in enumerate(roles):
            frame=self.sections[role]['frame']
            height=self.requested_height(role)
            if int(frame.cget('height'))!=height:frame.configure(height=height)
            pady=(0,GAP if i<len(roles)-1 else 0)
            if frame.winfo_manager()!='pack':
                # Insert new peers at their final position without disturbing
                # any already-mounted queue, even if their order is reversed.
                next_frame=next((self.sections[r]['frame'] for r in roles[i+1:]
                                 if self.sections[r]['frame'].winfo_manager()=='pack'),None)
                options={'side':'top','fill':'x','padx':0,'pady':pady}
                if next_frame is not None:options['before']=next_frame
                frame.pack(**options)
            else:
                old_pady=frame.pack_info().get('pady',0)
                actual=(tuple(map(int,old_pady)) if isinstance(old_pady,(tuple,list))
                        else (int(old_pady),int(old_pady)))
                if actual!=(0,pady[1]):frame.pack_configure(pady=pady)
        self.refresh_rail();self.request_fit()

    def refresh_rail(self):
        for role,section in self.sections.items():
            if section['button'] is None:continue
            count=self.app.effects_count(role) if role in ('A','B') and hasattr(self.app,'queue_deck') else 0
            title={'A':'QUEUE A','B':'QUEUE B','Music':'♫ AUDIO'}[role]
            section['button'].configure(text=title+(' ▴' if section['open'] else ' ▾'),
                style='UX28.QueueFlash.TButton' if role==self._flash_role else
                      'UX28.QueueOpen.TButton' if section['open'] else 'UX28.QueueIdle.TButton')
        if hasattr(self.app,'refresh_source_tabs'):self.app.refresh_source_tabs()

    def signal(self,role):
        """A transient spatial acknowledgement, never a modal notification."""
        if role not in ROLES:return
        self._flash_role=role
        if self._flash_ticket is not None:
            try:self.after_cancel(self._flash_ticket)
            except tk.TclError:pass
        self._refresh_frame_edges();self.refresh_rail()
        self._flash_ticket=self.after(540,self._end_signal)

    def _end_signal(self):
        self._flash_ticket=None;self._flash_role=None
        self._refresh_frame_edges();self.refresh_rail()

    def _refresh_frame_edges(self):
        for role,section in self.sections.items():
            section['frame'].configure(highlightbackground='#b6cb79' if role==self._flash_role else
                                       '#85aaf0' if role==self.selected else '#34374a')

    def highlight(self,role=None):
        self.selected=role
        self._refresh_frame_edges();self.refresh_rail()
    def _fit_music_pane(self,event=None):return None
    def _fit_compact_panes(self):self.request_fit()
    def set_radio_browsing(self,enabled):
        self._radio_browsing=bool(enabled);self.request_fit()
    def expanded(self):return bool(self.open_roles())
