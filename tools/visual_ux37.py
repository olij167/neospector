from pathlib import Path
from PIL import ImageGrab
import sys,os,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from neospector_console import NeospectorApp
with tempfile.TemporaryDirectory(prefix='ux37-visual-') as home:
 os.environ['OMNE_SEQUENCER_SANDBOX']=home
 os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
 a=NeospectorApp(test_mode=True)
 a.geometry('1700x900+0+0');a.update()
 w=a.show_startup_window(True);w.geometry('800x675+30+140')
 p=a.open_preferences('output');p.geometry('800x690+855+140')
 for _ in range(4):a.update()
 ImageGrab.grab(bbox=(0,0,1700,900)).save('/mnt/data/Neospector_UX37_Output_Preview.png')
 p.select('appearance')
 for _ in range(5):a.update()
 ImageGrab.grab(bbox=(0,0,1700,900)).save('/mnt/data/Neospector_UX37_Themes_Preview.png')
 a.close(force=True)
