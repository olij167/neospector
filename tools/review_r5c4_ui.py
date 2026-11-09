import os,sys,tempfile,time,json
from pathlib import Path
root=Path.cwd();sys.path.insert(0,str(root/'app_source'))
from neospector_console import NeospectorApp
from PIL import ImageGrab
out=root/'evidence/r5c4/ui-integration';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as td:
 os.environ['OMNE_SEQUENCER_SANDBOX']=td
 a=NeospectorApp(test_mode=True);errors=[];a.report_callback_exception=lambda *e:errors.append(repr(e))
 def pump(t=.4):
  until=time.monotonic()+t
  while time.monotonic()<until:a.update();time.sleep(.005)
 def shot(name):
  a.event_generate('<Motion>',warp=True,x=1,y=1);pump();x,y=a.winfo_rootx(),a.winfo_rooty();ImageGrab.grab(bbox=(x,y,x+a.winfo_width(),y+a.winfo_height()),xdisplay=os.environ['DISPLAY']).save(out/(name+'.png'))
 try:
  a.geometry('1440x940+0+0');a.open_example();pump(1);a.new_treatment();pump(1);shot('instrument')
  cell=a.deck.owner_cells[('Master',a.project.id)]
  fx=next((effect for effect in a.project.master_rack if effect.params),None)
  if fx:
   cell.react_parameter(fx.id,next(iter(fx.params)));shot('react-companion');cell.close_tray()
  a.conductor.recipe();shot('conductor-advanced')
  a.open_capture('record');shot('record')
  a.open_capture('export');shot('export')
  a.close_context_tray();a.geometry('1080x740+0+0');a.load_layout({});pump(.5);shot('small')
  a.open_capture('export');shot('small-export')
  report={'errors':errors,'phase_errors':a.playback_diagnostics()['phase_errors'],'sizes':['1440x940','1080x740'],'scope':'Native Tk screenshots and callback checks under Xvfb; no physical input or audible acceptance.'}
  (out/'summary.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
 finally:a.close(force=True)
