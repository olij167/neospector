"""Visual layout inspection only. Does not use real media/devices."""
import sys,os,tempfile,json
from pathlib import Path
from PIL import ImageGrab
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from neospector_console import NeospectorApp
with tempfile.TemporaryDirectory(prefix='ux36-view-') as home:
    os.environ['OMNE_SEQUENCER_SANDBOX']=home
    os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
    app=NeospectorApp(test_mode=True)
    app.geometry('1320x850+0+0')
    for i in range(4):app.update()
    w=app.show_startup_window(True);w.geometry('800x650+40+40');w.lift()
    for i in range(4):app.update()
    def snap(win,name):
        bbox=(win.winfo_rootx(),win.winfo_rooty(),win.winfo_rootx()+win.winfo_width(),win.winfo_rooty()+win.winfo_height())
        ImageGrab.grab(bbox=bbox).save(str(Path(__file__).resolve().parents[1]/name))
    snap(w,'UX36_WELCOME_PREVIEW.png')
    w.destroy();app.startup_window=None
    p=app.open_preferences('appearance');p.geometry('810x680+40+40')
    for i in range(5):app.update()
    ed=p.theme_editor
    details={'preferences_width':p.winfo_width(),'editor_available':ed.winfo_width(),'editor_requested':ed.winfo_reqwidth(),'palette_request':ed.body.winfo_reqwidth(),'palette_actual':ed.body.winfo_width(),'scroll_width':ed.canvas.winfo_width()}
    snap(p,'UX36_APPEARANCE_PREVIEW.png')
    p.close()
    p=app.open_preferences('devices');p.geometry('810x680+40+40')
    for i in range(4):app.update()
    snap(p,'UX36_DEVICES_PREVIEW.png')
    p.close();app.close(force=True)
    print(json.dumps(details,indent=2))
