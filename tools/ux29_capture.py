import os,sys,tempfile
from pathlib import Path
from PIL import ImageGrab
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from neospector_console import NeospectorApp
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as sandbox:
 os.environ['OMNE_SEQUENCER_SANDBOX']=sandbox
 os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
 app=NeospectorApp(test_mode=True)
 app.geometry('1500x920+0+0')
 def pump():
  for _ in range(15):app.update()
 try:
  app.sidebar.open_browser('A','files');pump()
  ImageGrab.grab(bbox=(0,0,1500,920)).save(out/'ux29_files.png')
  app.sidebar.open_browser('A','sources')
  app.sidebar.source_shelf.populate_sources([
    {'kind':'camera','label':'USB Camera','device':'test'},
    {'kind':'screen','label':'Screen 1','device':{'kind':'screen','name':'Screen 1','id':1}},
    {'kind':'application','label':'Browser · audio stream 23','device':{'kind':'application','backend':'pulse','device':'monitor','stream':23}},
  ],[])
  pump();ImageGrab.grab(bbox=(0,0,1500,920)).save(out/'ux29_sources.png')
  audio=app.queue_deck.pages['Music']
  audio.show_audio_view('mixer');pump();ImageGrab.grab(bbox=(0,0,1500,920)).save(out/'ux29_mixer.png')
  print('mixer frame geom',app.sidebar.sections['Music']['frame'].winfo_geometry())
  app.sidebar.open_browser('Music','sources');app.geometry('1060x780+0+0');pump();ImageGrab.grab(bbox=(0,0,1060,780)).save(out/'ux29_narrow.png')
 finally:app.close(force=True)
