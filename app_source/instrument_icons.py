"""Bundled line icons: no font-dependent glyphs or network assets."""
from PIL import Image,ImageDraw,ImageTk

def icon(app,name):
    cache=getattr(app,'_instrument_icons',None)
    if cache is None:cache={};app._instrument_icons=cache
    if name in cache:return cache[name]
    im=Image.new('RGBA',(40,40));d=ImageDraw.Draw(im);c='#e8e5df';line=lambda pts:d.line(pts,fill=c,width=3)
    if name=='copy':d.rectangle((8,7,25,25),outline=c,width=3);d.rectangle((15,14,32,32),outline=c,width=3)
    elif name=='reset':d.arc((9,9,32,32),25,300,fill=c,width=3);line([(8,8),(8,19),(19,19)])
    elif name=='vary':
        d.rounded_rectangle((7,7,33,33),radius=4,outline=c,width=3)
        for x,y in ((13,13),(27,13),(20,20),(13,27),(27,27)):d.ellipse((x-2,y-2,x+2,y+2),fill=c)
    elif name=='focus':
        for x,y,dx,dy in ((7,7,1,1),(33,7,-1,1),(7,33,1,-1),(33,33,-1,-1)):line([(x+dx*8,y),(x,y),(x,y+dy*8)])
    elif name=='camera':d.rectangle((6,12,27,29),outline=c,width=3);d.polygon([(28,17),(35,12),(35,29),(28,24)],outline=c,width=3)
    elif name=='mic':
        d.rounded_rectangle((15,6,25,24),radius=5,outline=c,width=3)
        d.arc((10,13,30,31),0,180,fill=c,width=3)
        line([(20,31),(20,36)]);line([(13,36),(27,36)])
    elif name=='audio':
        for x,h in ((8,14),(16,26),(24,18),(32,10)):
            line([(x,20-h//2),(x,20+h//2)])
    elif name=='app':
        d.rectangle((7,9,33,31),outline=c,width=3)
        line([(8,15),(32,15)]);d.ellipse((12,11,14,13),fill=c)
    elif name=='window':
        d.rectangle((7,8,33,32),outline=c,width=3)
        line([(8,15),(32,15)]);d.rectangle((12,19,28,27),outline=c,width=2)
    elif name=='camera-flash':
        d.rectangle((5,14,28,30),outline=c,width=3)
        d.ellipse((13,18,23,27),outline=c,width=2)
        line([(20,5),(20,10)]);line([(31,7),(28,12)]);line([(35,17),(30,17)])
    elif name=='screen':d.rectangle((5,7,35,28),outline=c,width=3);line([(20,28),(20,34)]);line([(12,34),(28,34)])
    elif name=='files':d.rectangle((7,11,33,32),outline=c,width=3);line([(7,11),(7,7),(18,7),(22,11)])
    elif name=='remove':line([(11,11),(29,29)]);line([(11,29),(29,11)])
    elif name in ('Punch','Smooth','Swell'):
        points={'Punch':[(5,33),(10,8),(17,17),(34,33)],'Smooth':[(5,33),(14,12),(23,16),(34,33)],'Swell':[(5,33),(14,28),(23,13),(28,8),(35,33)]}[name];line(points)
    elif name=='save':d.rectangle((7,7,33,33),outline=c,width=3);d.rectangle((13,7,27,17),outline=c,width=2);d.rectangle((12,24,28,33),outline=c,width=2)
    cache[name]=ImageTk.PhotoImage(im.resize((18,18),Image.Resampling.LANCZOS),master=app);return cache[name]
