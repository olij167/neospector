"""A playable rotary face over the existing ParameterFader gesture authority."""
import math,tkinter as tk
class InstrumentDial(tk.Canvas):
    def __init__(self,parent,row):
        self.row=row;self.point=None;self.default=row.param.value
        bg,fg,accent=row.face
        super().__init__(parent,width=100,height=84,bg=bg,highlightthickness=0,takefocus=True,cursor='hand2')
        self.bind('<ButtonPress-1>',self.press);self.bind('<B1-Motion>',self.drag);self.bind('<ButtonRelease-1>',self.release)
        self.bind('<KeyPress>',self.key);self.bind('<Escape>',self.cancel);self.bind('<FocusOut>',self.release);self.bind('<Unmap>',self.release)
        self.bind('<Double-Button-1>',self.reset);self.bind('<Button-3>',lambda e:row.open_controls())
        self.bind('<MouseWheel>',lambda e:'break')
        row.app.add_tip(self,'Drag up/down · Shift for fine control · arrows adjust · double-click resets · Escape cancels')
        self.draw()
    def press(self,e):
        if self.row.begin()=='break':return 'break'
        self.focus_set();self.point=(e.y_root,self.row.normal.get());return 'break'
    def drag(self,e):
        if self.point:
            y,v=self.point;self.row.apply(v+(y-e.y_root)/(1200 if e.state&1 else 160));self.draw()
        return 'break'
    def release(self,e=None):
        self.point=None;self.row.finish_input();return 'break'
    def cancel(self,e=None):
        self.point=None;self.row.finish_input(cancel=True);self.draw();return 'break'
    def key(self,e):
        if e.keysym in ('Up','Right','Down','Left','Home','End'):
            value=0 if e.keysym=='Home' else 1 if e.keysym=='End' else self.row.normal.get()+(1 if e.keysym in ('Up','Right') else -1)*(.001 if e.state&1 else .01)
            self.row.apply(value);self.row.finish_input();self.draw();return 'break'
    def reset(self,e=None):
        self.row.apply(self.row.to_normal(self.default));self.row.finish_input();self.draw();return 'break'
    def draw(self):
        if not self.winfo_exists():return
        row=self.row;bg,fg,accent=row.face;v=max(0,min(1,row.normal.get()));self.delete('all')
        self.create_arc(19,9,81,71,start=225,extent=-270,style='arc',outline='#071014',width=5)
        self.create_arc(19,9,81,71,start=225,extent=-max(.1,v*270),style='arc',outline=accent,width=5)
        p=row.param
        if p.mode=='react':
            end=max(0,min(1,v+p.react_amount));self.create_arc(13,3,87,77,start=225-v*270,extent=-(end-v)*270,style='arc',outline=accent,width=2,dash=(2,2))
        self.create_oval(26,16,74,64,fill='#0e1820',outline=accent,width=2)
        a=math.radians(225-v*270);self.create_line(50,40,50+20*math.cos(a),40-20*math.sin(a),fill=fg,width=4,capstyle='round')
        try:effective=row.app.signal_evaluator().value(p,row.app.programme_time() if row.app.playing else row.app.playhead);ev=max(0,min(1,row.to_normal(effective)))
        except (AttributeError,ValueError):ev=v
        if p.mode!='static':
            a=math.radians(225-ev*270);x,y=50+35*math.cos(a),40-35*math.sin(a);self.create_oval(x-3,y-3,x+3,y+3,fill=fg,outline='')
        self.create_text(50,78,text='−        +',fill=accent,font=('TkDefaultFont',8))
