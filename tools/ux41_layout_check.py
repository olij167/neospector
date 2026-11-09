"""Visual geometry smoke: module footer and ping-pong timing remain visible."""
import os,sys,tempfile
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app_source')]
from neospector_console import NeospectorApp
from effects_engine import make_effect

def bounds(w):
    return (w.winfo_rootx(),w.winfo_rooty(),w.winfo_width(),w.winfo_height())

with tempfile.TemporaryDirectory() as td:
    os.environ['OMNE_SEQUENCER_SANDBOX']=td;os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
    app=NeospectorApp(test_mode=True);app.geometry('1250x810+0+0')
    fx=make_effect('scanlines');app.project.master_rack.append(fx)
    app.open_effects_context('Master');app.deck.refresh(True);app.update()
    cell=app.deck.selected_cell();controls=cell.card_controls[fx.id]
    footer=cell.card_parts[fx.id][0].footer
    print('FOOTER',bounds(footer),'BUTTONS',[(k,bounds(controls[k]),controls[k].winfo_viewable()) for k in ('react_all','source_all','band_all')],flush=True)
    for k in ('react_all','source_all','band_all'):
        w=controls[k];assert w.winfo_viewable(),k
        assert bounds(w)[0]>=bounds(footer)[0],(k,bounds(w),bounds(footer))
        assert bounds(w)[0]+bounds(w)[2]<=bounds(footer)[0]+bounds(footer)[2]+1,(k,bounds(w),bounds(footer))
    for w in (900,1100):
        app.geometry(f'{w}x720+0+0');app.update()
        mix=app.visual_mix
        if not app.project.extra.get('ux41_pingpong',{}).get('enabled'):mix.pingpong_button.invoke()
        app.update()
        for entry in (mix.hold_entry,mix.fade_entry):
            assert entry.winfo_viewable(),(w,entry)
            assert entry.winfo_rootx()+entry.winfo_width()<=app.winfo_rootx()+app.winfo_width()+1,(w,bounds(entry),bounds(app))
        print('SCREEN',w,'PINGPONG',bounds(mix.tempo_row),flush=True)
    mix.fade_var.set('3.5');mix.commit_pingpong_timing();app.update()
    assert abs(app.project.extra['ux41_pingpong']['fade']-3.5)<1e-6
    app.close(force=True)
print('LAYOUT CHECK PASS')
