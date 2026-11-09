"""Exercise the real instrument with isolated profile; physical devices excluded.

Run on a desktop: PYTHONPATH=app_source python3 tools/ux8_acceptance.py evidence/ux8
"""
import os,sys,tempfile,time,json,hashlib,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app_source'))
from PIL import ImageGrab,ImageTk
from neospector_console import NeospectorApp
from effects_engine import make_effect
from module_engine import group_effects,children,compile_rack
from sequencer_model import save_project,load_project,project_to_dict
from media_engine import render_project,probe_media
out=Path(sys.argv[1] if len(sys.argv)>1 else ROOT/'evidence/ux8').resolve();out.mkdir(parents=True,exist_ok=True)
report={'errors':[],'physical_devices':'Not exercised','screenshots':[]}
with tempfile.TemporaryDirectory(prefix='neospector-ux8-') as profile:
 os.environ['OMNE_SEQUENCER_SANDBOX']=profile
 app=NeospectorApp(test_mode=True);app.geometry('1480x960+0+0');app.report_callback_exception=lambda *e:report['errors'].append(str(e[1]))
 def pump(seconds):
  until=time.monotonic()+seconds
  while time.monotonic()<until:app.update();time.sleep(.01)
 def shot(name):
  pump(.25);x,y,w,h=app.winfo_rootx(),app.winfo_rooty(),app.winfo_width(),app.winfo_height()
  ImageGrab.grab(bbox=(x,y,x+w,y+h),xdisplay=os.environ.get('DISPLAY')).save(out/name);report['screenshots'].append(name)
 try:
  app.open_example();pump(.7)
  assert app.project.assets,'Example did not open'
  app.project.master_rack=[make_effect(k) for k in ('liquid','echo','tile')]
  app.open_channel_effects('Master');app.select_library_mode('modules');app.module_library.query.set('');app.module_library.refresh(True)
  app.project.master_rack[0].params['amount'].mode='react';app.project.master_rack[0].params['amount'].source='song'
  app.deck.refresh(True);pump(.4)
  app.toggle_play();hashes=[];times=[]
  for _ in range(25):
   pump(.12)
   if app.viewport.photo:
    hashes.append(hashlib.sha256(ImageTk.getimage(app.viewport.photo).tobytes()).hexdigest());times.append(app.viewport.display_time)
  app.pause();pump(.15)
  report['playback']=app.playback_diagnostics();report['distinct_displayed_frames']=len(set(hashes));report['distinct_displayed_times']=len(set(times))
  assert len(set(hashes))>=5 and len(set(times))>=5,'No demonstrated changing visual playback'
  assert not report['playback']['phase_errors'],report['playback']['phase_errors']
  shot('UX8_workspace.png')
  fx=app.project.master_rack[0];app.deck.open_parameter(fx.id,'amount');pump(.2)
  app.deck.selected_cell().scroll.canvas.yview_moveto(0)
  shot('UX8_reaction.png')
  app.deck.close_tray();g=group_effects(app.project.master_rack,[f.id for f in app.project.master_rack[:2]],'Dream Trails')
  app.deck.refresh(True);app.deck.enter_group(g.id);pump(.2)
  shot('UX8_group.png')
  child=children(g)[0];app.deck.edit_group_parameter((child.id,),'amount',{'value':.42})
  path=Path(profile)/'roundtrip.omne-sequence.json';save_project(app.project,path);restored=load_project(path)
  assert project_to_dict(restored)==project_to_dict(app.project),'Saved project changed data'
  assert len(compile_rack(restored.master_rack))==len(compile_rack(app.project.master_rack))
  report['project_roundtrip']='PASS'
  app.deck.leave_group();app.geometry('1024x768+0+0');pump(.4)
  shot('UX8_small_window.png')
  report['small_window']={'play_visible':bool(app.play_button.winfo_viewable()),'rack_visible':bool(app.deck.winfo_viewable()),'add_visible':bool(app.deck.add_button.winfo_viewable()),'library_visible':bool(app.library_modes.winfo_viewable())}
  assert all(report['small_window'].values())
  # Verify a real encoded result through the preserved production export path.
  sample=copy.deepcopy(app.project);sample.width=256;sample.height=144;sample.fps=10;sample.duration=1
  render_project(sample,out/'UX8_sample.mp4',temp_dir=Path(profile)/'export',profile='web',start=0,end=1,overwrite=True)
  info=probe_media(out/'UX8_sample.mp4');assert info['has_video'];report['encoded_sample']={'width':info['width'],'height':info['height'],'duration':info['duration']}
  assert not report['errors'],report['errors']
  report['status']='PASS'
 finally:
  app.close(force=True)
  (out/'acceptance.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
