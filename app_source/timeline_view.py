"""Fixed layer headers, true whole-song fit, and non-destructive timeline gestures."""
from __future__ import annotations
import math
import tkinter as tk
from tkinter import ttk
from sequence_edit import move_clip,trim_clip,slip_clip,set_transition_duration,snap_time
from conductor_view import TITLES

class TimelineView(ttk.Frame):
    HEADER=164
    RULER=26
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;self.pps=38.;self.layout=[];self.hits=[];self.drag=None;self.redraw_id=None;self.photos=[]
        self.columnconfigure(1,weight=1);self.rowconfigure(2,weight=1)
        self.overview=tk.Canvas(self,height=38,highlightthickness=0);self.overview.grid(row=0,column=0,columnspan=2,sticky='ew')
        self.overview.bind('<Button-1>',self.overview_seek);self.overview.bind('<B1-Motion>',self.overview_seek)
        tools=ttk.Frame(self,padding=(4,2));tools.grid(row=1,column=0,columnspan=3,sticky='ew')
        for text,cmd in [('+ Layer',app.add_layer),('Split',app.split_current),('Duplicate',app.duplicate_current),('Replace',app.replace_current),('Transition',app.transition_current)]:ttk.Button(tools,text=text,width=max(5,len(text)+1),command=cmd).pack(side='left',padx=1)
        ttk.Label(tools,text='Snap').pack(side='left',padx=(8,2));self.snap=tk.StringVar(value='frames');ttk.Combobox(tools,textvariable=self.snap,values=['frames','beats','edges','markers','off'],state='readonly',width=8).pack(side='left')
        self.ripple=tk.BooleanVar(value=False);ttk.Checkbutton(tools,text='Ripple',variable=self.ripple).pack(side='left',padx=4)
        ttk.Button(tools,text='−',width=3,command=lambda:self.zoom_by(.75)).pack(side='right');ttk.Button(tools,text='+',width=3,command=lambda:self.zoom_by(1.33)).pack(side='right');ttk.Button(tools,text='Fit',width=4,command=self.zoom_fit).pack(side='right',padx=3)
        self.headers=tk.Canvas(self,width=self.HEADER,highlightthickness=0);self.headers.grid(row=2,column=0,sticky='ns')
        self.canvas=tk.Canvas(self,highlightthickness=0);self.canvas.grid(row=2,column=1,sticky='nsew')
        self.vbar=ttk.Scrollbar(self,orient='vertical',command=self.yview);self.vbar.grid(row=2,column=2,sticky='ns');self.canvas.configure(yscrollcommand=self.vbar.set)
        self.hbar=ttk.Scrollbar(self,orient='horizontal',command=self.xview);self.hbar.grid(row=3,column=1,sticky='ew');self.canvas.configure(xscrollcommand=self.hbar.set)
        for canvas in (self.canvas,self.headers,self.overview):canvas.bind('<Configure>',lambda e:self.schedule())
        self.canvas.bind('<Button-1>',self.press);self.canvas.bind('<B1-Motion>',self.motion);self.canvas.bind('<ButtonRelease-1>',self.release)
        self.canvas.bind('<Button-3>',self.context);self.headers.bind('<Button-1>',self.header_press);self.headers.bind('<Button-3>',self.header_context)
        self.canvas.bind('<Control-MouseWheel>',lambda e:self.zoom_by(1.2 if e.delta>0 else .83));self.canvas.bind('<MouseWheel>',lambda e:self.yview('scroll',-int(e.delta/120),'units'))
        for cv in (self.canvas,self.headers):
            cv.bind('<Button-4>',lambda e:self.yview('scroll',-2,'units'));cv.bind('<Button-5>',lambda e:self.yview('scroll',2,'units'))
        self.canvas.bind('<Escape>',self.cancel_drag)
        app.add_tip(self.canvas,'Drag a clip to move it; drag its edge to trim. Alt-drag slips the source. Drag the end of a transition bridge to change its duration. Shift-drag the ruler marks a range.')
        self.redraw()
    def xview(self,*args):self.canvas.xview(*args);self.schedule()
    def yview(self,*args):self.canvas.yview(*args);self.headers.yview_moveto(self.canvas.yview()[0]);self.schedule()
    def schedule(self):
        if self.redraw_id is None:self.redraw_id=self.after_idle(self.redraw)
    def zoom_fit(self):
        self.app.update_idletasks();self.pps=max(.02,(max(80,self.canvas.winfo_width())-16)/max(.1,self.app.project.max_end()));self.canvas.xview_moveto(0);self.redraw()
    def zoom_by(self,factor):
        width=max(1,self.canvas.winfo_width());center=self.canvas.canvasx(width/2)/self.pps
        self.pps=max(.02,min(1200,self.pps*factor));self.redraw();total=max(width,self.app.project.max_end()*self.pps+60);self.canvas.xview_moveto(max(0,(center*self.pps-width/2)/total));self.redraw()
    def overview_seek(self,event):self.app.set_playhead(max(0,event.x)/max(1,self.overview.winfo_width())*self.app.project.max_end())
    def position(self,event):return self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
    def row_at(self,y):
        for row in self.layout:
            if row['top']<=y<row['bottom']:
                channel='B' if row['b'] is not None and y>=row['b'][0] else 'A'
                return row,channel
        return None,'A'
    def hit(self,x,y):return next((h for h in reversed(self.hits) if h['rect'][0]<=x<=h['rect'][2] and h['rect'][1]<=y<=h['rect'][3]),None)
    def redraw(self):
        self.redraw_id=None;c=self.app.ui_chrome;p=self.app.project
        for cv in (self.canvas,self.headers,self.overview):cv.configure(bg=c['field_bg']);cv.delete('all')
        self.hits=[];self.layout=[];self.photos=[];y=self.RULER
        for layer in p.layers:
            has_b=any(clip.channel=='B' for clip in layer.clips)
            if layer.expanded and has_b:height=94;a=(y+7,y+36);b=(y+49,y+78)
            else:height=62;a=(y+8,y+39);b=None
            self.layout.append({'layer':layer,'top':y,'bottom':y+height,'a':a,'b':b});y+=height
        width=max(1,self.canvas.winfo_width());total=max(width,p.max_end()*self.pps+40);height=max(y+15,self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0,0,total,height));self.headers.configure(scrollregion=(0,0,self.HEADER,height))
        left=self.canvas.canvasx(0);right=self.canvas.canvasx(width);font=(c['font_family'],9)
        step=next((s for s in [.1,.25,.5,1,2,5,10,15,30,60,120,300,600,1800,3600] if s*self.pps>=70),3600)
        for i in range(max(0,int(left/self.pps/step)),int(right/self.pps/step)+2):
            t=i*step;x=t*self.pps;self.canvas.create_line(x,self.RULER,x,height,fill=c['panel_edge']);self.canvas.create_text(x+4,12,text=self.app.format_time(t),anchor='w',fill=c['muted_fg'],font=font)
        if self.app.range_in is not None and self.app.range_out is not None:
            a,b=sorted((self.app.range_in,self.app.range_out));self.canvas.create_rectangle(a*self.pps,0,b*self.pps,height,fill=c['selection_bg'],stipple='gray25',outline='')
        for m in p.markers:
            x=float(m.get('time',0))*self.pps;self.canvas.create_line(x,0,x,self.RULER,fill=c['accent'],width=2);self.canvas.create_text(x+3,2,text=m.get('name',''),anchor='nw',fill=c['accent'],font=font)
        for row in self.layout:
            layer=row['layer'];selected=layer.id==self.app.selected_layer_id;top=row['top'];bottom=row['bottom']
            self.headers.create_rectangle(0,top,self.HEADER,bottom,fill=c['selection_bg'] if selected else c['panel_bg'],outline=c['panel_edge'])
            self.headers.create_text(9,top+16,text=('▾ ' if layer.expanded else '▸ ')+layer.name,anchor='w',width=145,fill=c['foreground'],font=font)
            flags=('On' if layer.enabled else 'Off')+' · '+('SOLO' if layer.solo else 'Mix')+' · '+('LOCK' if layer.locked else 'Edit')
            self.headers.create_text(12,top+43,text=flags,anchor='w',fill=c['muted_fg'],font=(c['font_family'],8))
            self.canvas.create_line(left,bottom,right,bottom,fill=c['panel_edge'])
            for channel in ('A','B'):
                limits=row['a'] if channel=='A' else row['b']
                if limits is not None:self.canvas.create_text(left+4,limits[0]+5,text=channel,anchor='nw',fill=c['muted_fg'],font=font)
            for clip in sorted(layer.clips,key=lambda cl:(cl.start,cl.channel)):
                x1=clip.start*self.pps;x2=clip.end*self.pps
                if x2<left or x1>right:continue
                bounds=row['b'] if clip.channel=='B' and row['b'] else row['a'];y1,y2=bounds
                fill=c['active_bg'] if clip.channel=='A' else c['button_bg'];outline=c['accent'] if clip.id==self.app.selected_clip_id else c['secondary_accent'] if clip.channel=='B' else c['panel_edge']
                self.canvas.create_rectangle(x1,y1,max(x1+3,x2),y2,fill=fill,outline=outline,width=2 if clip.id==self.app.selected_clip_id else 1)
                asset=p.asset(clip.asset_id);text=(asset.name if asset else 'Missing source')
                text=('L ' if clip.locked else '• ' if clip.manual else '')+text
                thumb=getattr(self.app,'small_thumbnails',self.app.thumbnails).get(clip.asset_id)
                start=max(x1+5,left+5)
                if thumb and x2-start>85:self.canvas.create_image(start,y1+3,image=thumb,anchor='nw');start+=45
                if x2-start>12:self.canvas.create_text(start,y1+8,text=text,anchor='nw',width=max(12,x2-start-6),fill=c['foreground'],font=font)
                self.hits.append({'kind':'clip','id':clip.id,'rect':(x1,y1,x2,y2),'layer':layer.id})
            for tr in layer.transitions:
                x1=tr.start*self.pps;x2=tr.end*self.pps;y1=top+37 if row['b'] else top+43;y2=y1+10
                if x2<left or x1>right:continue
                self.canvas.create_rectangle(x1,y1,max(x1+5,x2),y2,fill=c['accent'],outline=c['foreground'] if tr.id==self.app.selected_transition_id else c['accent'])
                if x2-x1>75:self.canvas.create_text(x1+3,y1+5,text=TITLES.get(tr.kind,tr.kind),anchor='w',font=(c['font_family'],7),fill=c['background'])
                self.hits.append({'kind':'transition','id':tr.id,'rect':(x1,y1,x2,y2),'layer':layer.id})
        self.headers.create_rectangle(0,0,self.HEADER,self.RULER,fill=c['panel_bg'],outline='');self.headers.create_text(10,13,text='LAYERS  ·  A / B',anchor='w',fill=c['muted_fg'],font=font)
        self.draw_overview();self.draw_playhead()
    def draw_overview(self):
        cv=self.overview;c=self.app.ui_chrome;p=self.app.project;w=max(1,cv.winfo_width());h=38;cv.delete('all')
        cv.create_text(8,3,text='SONG MAP',anchor='nw',fill=c['muted_fg'],font=(c['font_family'],8))
        wave=p.analysis.get('waveform',[]) or p.waveform
        if wave:
            step=max(1,len(wave)//max(1,w))
            for i in range(0,len(wave),step):
                x=i/len(wave)*w;v=max(wave[i:i+step]);cv.create_line(x,22-v*12,x,22+v*12,fill=c['secondary_accent'])
        duration=p.max_end()
        if self.app.range_in is not None and self.app.range_out is not None:
            a,b=sorted((self.app.range_in,self.app.range_out));cv.create_rectangle(a/duration*w,0,b/duration*w,h,fill=c['selection_bg'],stipple='gray25',outline=c['accent'])
        left=self.canvas.canvasx(0)/self.pps;right=self.canvas.canvasx(self.canvas.winfo_width())/self.pps;cv.create_rectangle(left/duration*w,0,min(w,right/duration*w),h-1,outline=c['panel_edge'],width=2)
        self.draw_playhead()
    def draw_playhead(self):
        c=self.app.ui_chrome;x=self.app.playhead*self.pps;self.canvas.delete('playhead');self.canvas.create_line(x,0,x,max(100,self.canvas.canvasy(self.canvas.winfo_height())),fill=c['accent'],width=2,tags='playhead')
        self.overview.delete('playhead');w=self.overview.winfo_width();self.overview.create_line(self.app.playhead/max(.01,self.app.project.max_end())*w,0,self.app.playhead/max(.01,self.app.project.max_end())*w,38,fill=c['foreground'],width=2,tags='playhead')
    def press(self,event):
        self.canvas.focus_set();x,y=self.position(event);hit=self.hit(x,y)
        if not hit:
            self.app.set_playhead(x/self.pps);row,channel=self.row_at(y)
            if row:self.app.select_layer(row['layer'].id,channel)
            self.drag={'op':'range' if event.state&1 else 'seek','time':x/self.pps};return
        self.app.pause();self.app.selected_layer_id=hit['layer']
        if hit['kind']=='transition':
            self.app.selected_transition_id=hit['id'];self.app.deck.scope.set('Transition');self.app.set_playhead(x/self.pps);self.app.deck.refresh(force=True)
            self.drag={'op':'transition','hit':hit,'x':x,'y':y};return
        found=self.app.project.clip(hit['id']);layer,clip=found
        self.app.selected_clip_id=clip.id;self.app.selected_transition_id=None;self.app.selected_channel.set(clip.channel);self.app.deck.scope.set('Clip');self.app.set_playhead(min(clip.end-1/self.app.project.fps,max(clip.start,x/self.pps)))
        op='slip' if event.state&8 else 'left' if x-hit['rect'][0]<7 else 'right' if hit['rect'][2]-x<7 else 'move'
        if not (layer.locked or clip.locked or (clip.timing_locked and op!='slip')):self.drag={'op':op,'hit':hit,'x':x,'y':y,'start':clip.start,'end':clip.end,'in':clip.in_point,'channel':clip.channel}
        else:self.app.update_status('This clip is locked. Unlock it in the Control Deck to edit.')
        self.redraw();self.app.deck.refresh(force=True)
    def motion(self,event):
        if not self.drag:return
        x,y=self.position(event);d=self.drag
        if d['op'] in {'seek','range'}:
            self.app.set_playhead(x/self.pps)
            if d['op']=='range':self.app.range_in=min(d['time'],x/self.pps);self.app.range_out=max(d['time'],x/self.pps);self.schedule()
            return
        delta=(x-d['x'])/self.pps;d['delta']=delta;row,channel=self.row_at(y);d['dest']=row['layer'].id if row else d['hit']['layer'];d['dest_channel']=channel if row else d.get('channel','A')
        self.canvas.delete('ghost')
        r=d['hit']['rect'];left=r[0]+(delta*self.pps if d['op'] in {'move','left'} else 0);right=r[2]+(delta*self.pps if d['op'] in {'move','right','transition'} else 0)
        dy=(row['top']-next(v['top'] for v in self.layout if v['layer'].id==d['hit']['layer'])) if row and d['op']=='move' else 0
        self.canvas.create_rectangle(left,r[1]+dy,right,r[3]+dy,outline=self.app.ui_chrome['foreground'],width=2,dash=(3,2),tags='ghost');self.app.update_status(f'{d["op"].title()} · {delta:+.3f}s · release to commit, Esc to cancel')
    def release(self,event):
        d=self.drag;self.drag=None;self.canvas.delete('ghost')
        if not d or 'delta' not in d:return
        delta=d['delta'];cid=d['hit']['id'];p=self.app.project
        def snapped(t):return snap_time(p,t,self.snap.get(),pixel_tolerance=8/self.pps,exclude_id=cid)
        def edit():
            if d['op']=='move':move_clip(p,cid,snapped(d['start']+delta),d['dest'],d['dest_channel'])
            elif d['op']=='left':trim_clip(p,cid,snapped(d['start']+delta),d['end'])
            elif d['op']=='right':trim_clip(p,cid,d['start'],snapped(d['end']+delta),ripple=self.ripple.get())
            elif d['op']=='slip':slip_clip(p,cid,delta)
            elif d['op']=='transition':set_transition_duration(p,cid,p.transition(cid)[1].duration+delta)
        self.app.transaction(d['op'].title(),edit)
    def cancel_drag(self,event=None):self.drag=None;self.canvas.delete('ghost');self.app.update_status('Gesture cancelled')
    def header_press(self,event):
        y=self.headers.canvasy(event.y);row,_=self.row_at(y)
        if not row:return
        l=row['layer']
        if event.x<28:self.app.transaction('Expand layer',lambda:setattr(l,'expanded',not l.expanded))
        else:self.app.select_layer(l.id,self.app.selected_channel.get());self.app.deck.scope.set('Layer');self.app.deck.refresh(force=True)
    def header_context(self,event):
        y=self.headers.canvasy(event.y);row,_=self.row_at(y)
        if not row:return
        l=row['layer'];menu=tk.Menu(self,tearoff=False)
        for attr,label in [('enabled','Enable / disable'),('solo','Solo / unsolo'),('locked','Lock / unlock')]:menu.add_command(label=label,command=lambda a=attr:self.app.transaction(label,lambda:setattr(l,a,not getattr(l,a))))
        menu.add_command(label='Move layer up',command=lambda:self.app.reorder_layer(l.id,-1));menu.add_command(label='Move layer down',command=lambda:self.app.reorder_layer(l.id,1));menu.add_command(label='Rename',command=lambda:self.app.rename_layer(l.id));menu.add_command(label='Delete layer',command=lambda:self.app.delete_layer(l.id))
        from contextual_surface import post_native_menu
        post_native_menu(self.app,menu,self.headers,event)
    def context(self,event):
        x,y=self.position(event);h=self.hit(x,y)
        if h and h['kind']=='clip':
            l,c=self.app.project.clip(h['id']);self.app.selected_layer_id=l.id;self.app.selected_clip_id=c.id;self.app.selected_channel.set(c.channel);self.app.set_playhead(min(c.end-1/self.app.project.fps,max(c.start,x/self.pps)))
        menu=tk.Menu(self,tearoff=False)
        for label,cmd in [('Split here',self.app.split_current),('Duplicate',self.app.duplicate_current),('Replace with pool selection',self.app.replace_current),('Add transition from preceding clip',self.app.transition_current),('Delete',self.app.delete_current)]:menu.add_command(label=label,command=cmd)
        from contextual_surface import post_native_menu
        post_native_menu(self.app,menu,self.canvas,event)
