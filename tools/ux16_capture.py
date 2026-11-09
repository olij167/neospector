"""Actual Tk captures; never used as test proof of physical-device capture."""
import os,sys,tempfile,time
from pathlib import Path
from PIL import ImageGrab
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from neospector_console import NeospectorApp
from neospector_catalog import build_group
from effects_engine import make_effect
out=Path(__file__).resolve().parents[1]/'evidence/ux16';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='neospector-ux16-capture-') as profile:
    os.environ['OMNE_SEQUENCER_SANDBOX']=profile;os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
    app=NeospectorApp(test_mode=True)
    try:
        app.geometry('1550x950+0+0');app.update()
        def shot(name):
            for _ in range(5):app.update();time.sleep(.04)
            x,y=app.winfo_rootx(),app.winfo_rooty()
            ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(out/name)
        shot('UX16_Minimal.png')
        app.open_effects_context('Master');app.update()
        app.insert_module_from_library(build_group('CCD Afterglow'),'CCD Afterglow',entry_type='Group')
        app.insert_module_from_library(make_effect('liquid'),'Liquid',entry_type='Custom')
        app.visual_mix.toggle_transitions();app.update()
        shot('UX16_Rack.png')
        app.visual_mix.toggle_transitions();app.visual_mix.toggle_reactions()
        app.toggle_module_library(True);app.update()
        shot('UX16_Reactions.png')
        app.toggle_module_library(False);app.geometry('1024x768+0+0');app.update()
        shot('UX16_Narrow.png')
        app.toggle_effects_context('Master')
        app.queue_deck.pages['B'].toggle_browser();app.update()
        shot('UX16_Source_Browser.png')
        print({str(p.relative_to(out)):p.stat().st_size for p in out.glob('*.png')})
    finally:app.close(force=True)
