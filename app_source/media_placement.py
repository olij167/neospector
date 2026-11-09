"""Visible, dwell-assisted Library placement. Drag previews never mutate media."""
import time,tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from media_settings_model import queue_drop_intent
from visual_channels import strongest_channel

class MediaPlacementActions:
    def open_media_settings(self,ids,tab='General'):
        ids=[i for i in ids if self.project.asset(i)]
        if not ids:return self.update_status('Select Library media first.')
        old=getattr(self,'media_settings_window',None)
        if old and old.winfo_exists():
            if old.asset.id in ids:
                old.book.select(old.tabs.get(tab,old.tabs['General']));old.lift();return old
            old.lift();self.update_status('Close the existing Media Settings before editing another source.');return old
        from media_settings_ui import MediaSettings
        self.media_settings_window=MediaSettings(self,ids,tab);return self.media_settings_window
    def batch_personality(self):return self.open_media_settings(list(self.library.selection()),'Conductor')
    def begin_media_drag(self,event,browser):
        self.clear_media_drag()
        collection=getattr(browser,'drag_collection_ids',None)
        self._drag_media={'origin':(event.x_root,event.y_root),'browser':browser,'active':False,'target':None,'entered':time.monotonic(),'signature':None,'ids':list(collection) if collection else None}
        browser.drag_collection_ids=None
    def drop_destination(self,x,y):
        widget=self.winfo_containing(x,y)
        if widget is None:return None
        chain=str(widget)
        for role,page in self.queue_deck.pages.items():
            for surface in (page,page.editor_body):
                if chain==str(surface) or chain.startswith(str(surface)+'.'):return 'queue',role,page
        if chain==str(self.conductor) or chain.startswith(str(self.conductor)+'.'):return 'settings','Conductor',self.conductor
        if chain==str(self.deck) or chain.startswith(str(self.deck)+'.'):return 'settings','Effects',self.deck
        if chain==str(self.viewport) or chain.startswith(str(self.viewport)+'.'):return 'now','auto',self.viewport
        return None
    def queue_drop_plan(self,page,x,y,dwell):
        cy=y-page.canvas.winfo_rooty()
        if y<page.canvas.winfo_rooty():zone='next'
        elif cy>=page.canvas.winfo_height():zone='append'
        else:zone='list'
        before=None;index=None
        if zone=='list':
            pos=page.canvas.canvasy(cy);index=max(0,min(len(page.future),int((pos+26)/56)))
            if index<len(page.future):before=page.ident(page.future[index])
        intent=queue_drop_intent(zone,dwell,before)
        page.canvas.delete('media-insert')
        if intent[0]=='insert':
            line=2+index*56;page.canvas.create_line(2,line,max(10,page.canvas.winfo_width()-2),line,fill=self.ui_chrome['accent'],width=3,tags='media-insert')
        return intent
    def motion_media_drag(self,event):
        state=self._drag_media
        if not state:return
        x,y=state['origin']
        if not state['active'] and abs(x-event.x_root)+abs(y-event.y_root)<8:return
        state['active']=True;state['event']=SimpleNamespace(x_root=event.x_root,y_root=event.y_root)
        target=self.drop_destination(event.x_root,event.y_root);state['target']=target
        signature=(target[0],target[1],str(target[2])) if target else None
        if signature!=state['signature']:
            self.clear_drag_cue();state['signature']=signature;state['entered']=time.monotonic()
            timer=getattr(self,'media_drag_timer',None)
            if timer:
                try:self.after_cancel(timer)
                except tk.TclError:pass
            if target and target[0]=='queue':
                self.media_drag_timer=self.after(1020,lambda:self.motion_media_drag(state['event']) if self._drag_media is state else None)
        ids=list(state.get('ids') or state['browser'].selection())
        if target:
            action,role,widget=target
            if action=='queue':
                kind,before=self.queue_drop_plan(widget,event.x_root,event.y_root,time.monotonic()-state['entered']);state['plan']=(kind,before)
                label={'next':'Play next','append':'Append','insert':'Insert here'}[kind]+' → '+role
                if kind=='append' and time.monotonic()-state['entered']<1:label+=' · hold for position'
            elif action=='settings':label='Media settings → '+role
            else:
                try:role='Music' if ids and all(self.project.asset(i).kind=='audio' for i in ids) else strongest_channel(self.project,self.playhead,self.signal_evaluator());label='Play now → '+role
                except ValueError as exc:label=str(exc)
            cue=getattr(self,'media_drag_cue',None)
            if cue is None or not cue.winfo_exists():
                cue=ttk.Label(widget,text=label,style='Title.TLabel',padding=4);self.media_drag_cue=cue;cue.place(relx=.5,rely=1.,anchor='s')
            elif cue.cget('text')!=label:cue.configure(text=label)
        else:label='Drop into a queue, Programme, modules or Conductor'
        if self.drop_feedback.get()!=label:self.drop_feedback.set(label);self.update_status(label)
    def clear_drag_cue(self):
        cue=getattr(self,'media_drag_cue',None)
        if cue is not None:
            try:cue.destroy()
            except tk.TclError:pass
        self.media_drag_cue=None
        if hasattr(self,'queue_deck'):
            for page in self.queue_deck.pages.values():page.canvas.delete('media-insert')
    def clear_media_drag(self):
        self.clear_drag_cue();timer=getattr(self,'media_drag_timer',None)
        if timer:
            try:self.after_cancel(timer)
            except tk.TclError:pass
        self.media_drag_timer=None;self._drag_media=None
    def end_media_drag(self,event):
        state=self._drag_media
        if not state or not state['active']:self.clear_media_drag();return
        target=self.drop_destination(event.x_root,event.y_root)
        ids=list(state.get('ids') or state['browser'].selection());plan=None
        if target and target[0]=='queue':plan=self.queue_drop_plan(target[2],event.x_root,event.y_root,time.monotonic()-state['entered'])
        self.clear_media_drag();self.drop_feedback.set('Drop → strongest channel')
        if not target:return
        ids=self.ensure_project_media(ids)
        if not ids:return self.update_status('Those Library sources are unavailable. Locate the files and try again.')
        action,role,widget=target
        if action=='settings':return self.open_media_settings(ids,role)
        if action=='queue':
            kind,before=plan
            if kind=='insert':return self.place_media_before(ids,role,before)
            return self.place_media(ids,role,'next' if kind=='next' else 'queue')
        return self.place_media(ids,role,action)
    def place_media_before(self,ids,role,before):
        from queue_model import ordered,queue_position,append_assets
        from instrument_model import voice
        from music_queue import items,store,layout
        from audio_bus import add_sound
        ids=self.ensure_project_media(ids)
        if not ids:return
        now=self.programme_time() if self.playing and not self.reviewing else self.playhead
        if role!='Music':
            layer=voice(self.project,role);anchor=next((c for c in layer.clips if c.id==before),None)
            if anchor is None or anchor.start<=queue_position(layer,now):return self.update_status('That insertion point is now playing or no longer exists. Drop again at an upcoming position.')
            if any(self.project.asset(i).kind=='audio' for i in ids):return self.update_status('Audio belongs in Music, not a visual queue.')
            self.transaction('Insert media into '+role,lambda:append_assets(self.project,layer.id,ids,before=before))
        else:
            events=items(self.project);idx=next((i for i,e in enumerate(events) if e['id']==before),None)
            if idx is None or events[idx]['start']<=now:return self.update_status('That Music position is no longer upcoming. Drop again.')
            if any(e.get('locked') or e.get('timing_locked') or e.get('pinned') for e in events[idx:]):return self.update_status('Unpin/unlock the affected Music items before inserting here.')
            if any(self.project.asset(i).kind!='audio' and not self.project.asset(i).metadata.get('has_audio') for i in ids):return self.update_status('This source has no audio stream.')
            def insert():
                start=events[idx]['start'];cursor=max([now]+[e['start']+e['duration'] for e in events]);created=[]
                for aid in ids:
                    e=add_sound(self.project,aid,start=cursor);e['manual']=True;created.append(e);cursor+=e['duration']
                store(self.project,events[:idx]+layout(created+events[idx:],start))
            self.transaction('Insert media into Music',insert);self.prepare_sound_analysis();self.configure_sound_sources()
        self.queue_deck.show_role(role)
