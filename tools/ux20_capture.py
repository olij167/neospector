"""Rendered acceptance screenshots (not synthetic mockups)."""
import os,sys,tempfile
from pathlib import Path
from PIL import ImageGrab
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from neospector_console import NeospectorApp
from effects_engine import make_effect
out=Path(__file__).resolve().parents[1]/'evidence'/'ux20';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as d:
 os.environ['OMNE_SEQUENCER_SANDBOX']=d;os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
 a=NeospectorApp(test_mode=True);a.geometry('1500x920+0+0');a.update()
 def shot(n):
  a.update_idletasks();a.update();ImageGrab.grab(bbox=(0,0,1500,920)).save(out/n)
 shot('01_Default.png')
 a.project.master_rack.append(make_effect('blur'))
 a.open_effects_context('Master');a.deck.refresh(True);a.update();shot('02_Output_Rack.png')
 a.open_effects_context('B');a.deck.refresh(True);a.visual_mix.set_reactive(True);a.update();shot('03_B_Reactive_Mix.png')
 a.geometry('1024x768+0+0');a.sidebar.set_open('Music',True);a.open_effects_context('Master');a.update();ImageGrab.grab(bbox=(0,0,1024,768)).save(out/'04_Compact.png')
 a.close(force=True)
