"""A compact sequence strip with independent, view-only lenses."""
from __future__ import annotations
import math
import tkinter as tk
from tkinter import ttk
from timeline_view import TimelineView
from responsive_controls import FlowRow
from sequence_edit import set_transition_duration,snap_time,editable
from conductor_view import TITLES

class InstrumentTimeline(TimelineView):
    HEADER=114
    RULER=22
    def __init__(self,parent,app):
        self.lenses={k:tk.BooleanVar(master=app,value=k in ('sequence','transitions')) for k in ('sequence','transitions','effects','reaction')}
        super().__init__(parent,app)
        self.overview.configure(height=18)
        tools=next(w for w in self.winfo_children() if isinstance(w,ttk.Frame))
        for w in tools.winfo_children():w.destroy()
        row=FlowRow(tools,gap=3);row.pack(fill='x')
        self.tool_row=row
        row.add(ttk.Label(row,text='FINE TUNE',style='Muted.TLabel'))
        lenses=ttk.Frame(row)
        for key,var in self.lenses.items():ttk.Checkbutton(lenses,text=key.title(),variable=var,command=self.schedule).pack(side='left',padx=1)
        ttk.Button(lenses,text='Full',width=4,command=self.full).pack(side='left');row.add(lenses)
        actions=ttk.Frame(row)
        for text,fn in [('Replace',app.replace_current),('Before',lambda:app.insert_near(False)),('After',lambda:app.insert_near(True)),('Split',app.split_current)]:ttk.Button(actions,text=text,width=6,command=fn).pack(side='left',padx=1)
        row.add(actions)
        zoom=ttk.Frame(row)
        ttk.Button(zoom,text='Fit',width=4,command=self.zoom_fit).pack(side='left');ttk.Button(zoom,text='+',width=3,command=lambda:self.zoom_by(1.4)).pack(side='left');ttk.Button(zoom,text='−',width=3,command=lambda:self.zoom_by(.7)).pack(side='left')
        ttk.Combobox(zoom,textvariable=self.snap,values=['frames','beats','edges','markers','off'],width=7,state='readonly').pack(side='left',padx=5);row.add(zoom)
        self.redraw()
    def full(self):
        value=not all(v.get() for v in self.lenses.values())
        for v in self.lenses.values():v.set(value)
        self.schedule()
    def redraw(self):
        if not self.app.project.instrument_mode:return super().redraw()
        self.redraw_id=None;p=self.app.project;theme=self.app.ui_chrome
        for cv in (self.canvas,self.headers,self.overview):cv.configure(bg=theme['field_bg']);cv.delete('all')
        self.layout=[];self.hits=[];self.photos=[];y=self.RULER;width=max(100,self.canvas.winfo_width());total=max(width,p.max_end()*self.pps+30)
        visible=(self.canvas.canvasx(0)/self.pps,self.canvas.canvasx(width)/self.pps)
        for layer in p.layers:
            h=44 if self.lenses['reaction'].get() or self.lenses['effects'].get() else 29
            row={'layer':layer,'top':y,'bottom':y+h,'a':(y+5,y+h-5),'b':None};self.layout.append(row)
            selected=layer.id==self.app.selected_layer_id
            self.headers.create_rectangle(0,y,self.HEADER,y+h,fill=theme['selection_bg'] if selected else theme['panel_bg'],outline=theme['panel_edge'])
            self.headers.create_text(9,y+h/2,text=('■ ' if layer.locked else '● ' if layer.enabled else '○ ')+layer.name,fill=theme['foreground'],anchor='w',font=('TkDefaultFont',10,'bold'))
            self.canvas.create_line(0,y+h,total,y+h,fill=theme['panel_edge'])
            for clip in layer.clips:
                if clip.end<visible[0] or clip.start>visible[1]:continue
                x1=clip.start*self.pps;x2=clip.end*self.pps;top=y+6;bot=y+h-5
                if self.lenses['sequence'].get():
                    color=theme['accent'] if clip.channel=='A' else theme.get('secondary_accent',theme['muted_fg'])
                    self.canvas.create_rectangle(x1,top,x2,bot,fill=color,stipple='gray50' if clip.id!=self.app.selected_clip_id else '',outline=theme['foreground'] if clip.id==self.app.selected_clip_id else theme['panel_edge'])
                    a=p.asset(clip.asset_id);text=a.name if a else 'Missing';available=x2-x1
                    if available>34:self.canvas.create_text(x1+6,(top+bot)/2,text=text[:max(3,int(available/7)-1)],fill=theme['foreground'],anchor='w')
                    self.hits.append({'kind':'clip','id':clip.id,'layer':layer.id,'rect':(x1,top,x2,bot)})
                if self.lenses['effects'].get() and clip.rack:self.canvas.create_line(x1,top,x2,top,fill=theme['foreground'],width=3)
                if self.lenses['reaction'].get():
                    params=[clip.opacity,clip.scale,*clip.effects.values()]+[v for fx in clip.rack for v in fx.params.values()]
                    if any(v.mode=='react' for v in params):
                        self.canvas.create_line(x1,bot-2,x2,bot-2,fill=theme['foreground'],dash=(3,3));self.canvas.create_oval(x1-3,bot-5,x1+3,bot+1,outline=theme['foreground']);self.canvas.create_oval(x2-3,bot-5,x2+3,bot+1,outline=theme['foreground'])
                    for v in params:
                        for k in v.keyframes:
                            if clip.start<=k.time<clip.end and visible[0]<=k.time<=visible[1]:
                                xx=k.time*self.pps;self.canvas.create_polygon(xx,top-1,xx+3,top+2,xx,top+5,xx-3,top+2,fill=theme['foreground'])
            if self.lenses['transitions'].get():
                for tr in layer.transitions:
                    if tr.end<visible[0] or tr.start>visible[1]:continue
                    x1=tr.start*self.pps;x2=tr.end*self.pps;top=y+2;bot=y+h-2
                    self.canvas.create_rectangle(x1,top,x2,bot,outline=theme['foreground'],width=2,fill=theme['selection_bg'],stipple='gray25')
                    self.canvas.create_line(x1,bot,x2,top,fill=theme['foreground'])
                    if x2-x1>54:self.canvas.create_text((x1+x2)/2,(top+bot)/2,text=TITLES.get(tr.kind,tr.kind)[:14],fill=theme['foreground'])
                    self.hits.append({'kind':'transition','id':tr.id,'layer':layer.id,'rect':(x1,top,x2,bot)})
            y+=h
        self.canvas.configure(scrollregion=(0,0,total,max(y,self.canvas.winfo_height())));self.headers.configure(scrollregion=(0,0,self.HEADER,max(y,self.canvas.winfo_height())))
        step=next((s for s in (.1,.25,.5,1,2,5,10,20,30,60,120,300) if s*self.pps>=55),300)
        for i in range(max(0,int(visible[0]/step)),int(visible[1]/step)+2):
            xx=i*step*self.pps;self.canvas.create_text(xx+3,4,text=self.app.format_time(i*step),fill=theme['muted_fg'],anchor='nw');self.canvas.create_line(xx,18,xx,y,fill=theme['panel_edge'])
        for marker in p.markers:
            xx=marker.get('time',0)*self.pps;self.canvas.create_polygon(xx,18,xx+4,14,xx-4,14,fill=theme['accent'])
        self.draw_overview();self.draw_playhead()
        if self.winfo_manager()=='grid':self.configure(height=202 if self.lenses['reaction'].get() or self.lenses['effects'].get() else 163)
    def press(self,event):
        if not self.app.project.instrument_mode:return super().press(event)
        self.canvas.focus_set();x,y=self.position(event);hit=self.hit(x,y);self.drag=None
        if not hit:
            if self.app.playing and not self.app.reviewing:
                self.app.update_status('Programme keeps playing. Hold playback or open a captured take to scrub.');return
            return super().press(event)
        self.app.selected_layer_id=hit['layer'];self.app.follow_playhead.set(False)
        if hit['kind']=='transition':
            self.app.selected_transition_id=hit['id'];self.app.deck.scope.set('Transition');t=self.app.project.transition(hit['id'])[1]
            op='transition_left' if x-hit['rect'][0]<7 else 'transition' if hit['rect'][2]-x<7 else 'softness' if y-hit['rect'][1]<8 else 'transition'
            if not t.locked:self.drag={'op':op,'hit':hit,'x':x,'y':y,'old_start':t.start,'old_end':t.end,'softness':t.softness}
        else:
            l,c=self.app.project.clip(hit['id']);self.app.selected_clip_id=c.id;self.app.selected_transition_id=None;self.app.selected_channel.set(c.channel);self.app.deck.scope.set('Clip')
            op='slip' if event.state&8 else 'left' if x-hit['rect'][0]<7 else 'right' if hit['rect'][2]-x<7 else 'move'
            if not(l.locked or c.locked or c.timing_locked):self.drag={'op':op,'hit':hit,'x':x,'y':y,'start':c.start,'end':c.end,'in':c.in_point,'channel':c.channel}
        if not self.app.playing or self.app.reviewing:self.app.set_playhead(x/self.pps)
        self.redraw();self.app.deck.refresh(force=True)
    def motion(self,event):
        if self.drag and self.drag['op']=='softness':
            x,y=self.position(event);self.drag['delta']=(self.drag['y']-y)/100;self.app.update_status(f'Edge softness: {max(0,min(.5,self.drag["softness"]+self.drag["delta"])):.2f} · release to commit');return
        super().motion(event)
        if self.drag and self.drag.get('op')=='move' and self.app.project.instrument_mode:self.drag['dest_channel']=self.drag['channel']
    def release(self,event):
        d=self.drag
        if d and 'delta' in d and d['op'] in ('softness','transition_left'):
            self.drag=None;self.canvas.delete('ghost');found=self.app.project.transition(d['hit']['id'])
            if not found:return
            l,t=found
            def edit():
                if l.locked or t.locked:raise ValueError('Unlock this transition first')
                if d['op']=='softness':t.softness=max(0,min(.5,d['softness']+d['delta']));t.manual=True;return
                a=self.app.project.clip(t.from_clip)[1];b=self.app.project.clip(t.to_clip)[1];editable(self.app.project,a.id,timing=True);editable(self.app.project,b.id,timing=True)
                start=max(a.start+1/self.app.project.fps,min(d['old_end']-1/self.app.project.fps,d['old_start']+d['delta']))
                if any(x.id!=t.id and x.start<d['old_end'] and x.end>start for x in l.transitions):raise ValueError('This change would overlap another transition')
                delta=start-b.start;b.in_point=max(0,b.in_point+delta*b.playback_rate);b.duration=b.end-start;b.start=start;b.manual=a.manual=True;t.start=start;t.duration=d['old_end']-start;t.manual=True
            self.app.transaction('Transition '+d['op'],edit);return
        super().release(event)
    def context(self,event):
        x,y=self.position(event);h=self.hit(x,y)
        if h and h['kind']=='clip':
            l,c=self.app.project.clip(h['id']);self.app.selected_layer_id=l.id;self.app.selected_clip_id=c.id;self.app.selected_channel.set(c.channel);self.app.follow_playhead.set(False)
        m=tk.Menu(self,tearoff=False)
        for label,fn in [('Replace media; keep treatment',self.app.replace_current),('Insert selected media before',lambda:self.app.insert_near(False)),('Insert selected media after',lambda:self.app.insert_near(True)),('Add transition',self.app.transition_current),('Split at cursor',self.app.split_current),('Duplicate',self.app.duplicate_current),('Delete',self.app.delete_current)]:m.add_command(label=label,command=fn)
        from contextual_surface import post_native_menu
        post_native_menu(self.app,m,self.canvas,event)
