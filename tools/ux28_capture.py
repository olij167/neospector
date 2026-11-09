import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from PIL import ImageGrab
from neospector_console import NeospectorApp
import tkinter as tk
out=Path(__file__).resolve().parents[1]/'evidence'/'ux28'
out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='ux28screen-') as home:
    os.environ['OMNE_SEQUENCER_SANDBOX']=home
    os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
    a=NeospectorApp(test_mode=True)
    a.geometry('1600x910+0+0')
    for _ in range(9):a.update()
    a.sidebar.set_open('A',True);a.sidebar.set_open('B',True);a.set_audio_tray_open(True)
    for _ in range(10):a.update()
    ImageGrab.grab(bbox=(0,0,1600,910)).save(out/'ux28_three_queues.png')
    for role in ('A','B','Music'):a.queue_deck.pages[role].set_future(True)
    for _ in range(10):a.update()
    ImageGrab.grab(bbox=(0,0,1600,910)).save(out/'ux28_expanded.png')
    a.sidebar.open_browser('B','files')
    for _ in range(10):a.update()
    ImageGrab.grab(bbox=(0,0,1600,910)).save(out/'ux28_media.png')
    for role in ('A','B','Music'):
        f=a.sidebar.sections[role]['frame']
        print(role, 'frame',f.winfo_rootx(),f.winfo_rooty(),f.winfo_width(),f.winfo_height())
    m=a.visual_mix
    for group in [m.preview_actions,m.transition_group,m.audio_group]:print(group,'bbox',group.winfo_rootx(),group.winfo_rooty(),group.winfo_width(),group.winfo_height())
    a.close(force=True)
