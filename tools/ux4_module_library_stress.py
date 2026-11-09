#!/usr/bin/env python3
"""UX4 scale/resilience stress for the visual Module Library and grouping workflow."""
from __future__ import annotations
import json, os, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app_source'))
from effects_engine import make_effect
from module_engine import group_selected, ungroup, compile_rack
from sequencer_model import _encode


def widgets(widget):
    total=1
    for child in widget.winfo_children():total+=widgets(child)
    return total

def pump(app,seconds=.02):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.update();time.sleep(.002)

def main(out_path=None):
    from neospector_console import NeospectorApp
    report={'status':'FAIL','errors':[]}
    with tempfile.TemporaryDirectory(prefix='neospector-ux4-stress-') as sandbox:
        os.environ['OMNE_SEQUENCER_SANDBOX']=sandbox;os.environ['SDL_AUDIODRIVER']='dummy'
        app=NeospectorApp(test_mode=True);callbacks=[];app.report_callback_exception=lambda t,e,tb:callbacks.append(f'{t.__name__}: {e}')
        pump(app,.25)
        try:
            primitive=_encode([make_effect('brightness')])
            # 520 persistent Mine entries, deliberately including duplicate display names.
            t=time.monotonic()
            for i in range(520):
                app.catalog.save_ingredient('Duplicate module' if i%37==0 else f'User module {i:04d}','rack',{'rack':primitive,'scope':'module','version':1})
            # A large custom group exercises disclosure and persistence without creating a plug-in system.
            large=[make_effect(k) for k in ('brightness','contrast','gamma','saturation','hue','chroma_shift','blur','sharpness')]
            large_group=group_selected(large,[x.id for x in large]);app.catalog.save_ingredient('Large custom group','rack',{'rack':_encode([large_group]),'scope':'module','version':1})
            report['catalog_write_seconds']=time.monotonic()-t
            app.switch_workspace('Build');app.refresh_module_library();pump(app,.2)
            lib=app.module_library
            report['entry_count']=len(lib._rows);report['card_count']=len(lib.cards);report['widget_count_initial']=widgets(lib)
            if report['entry_count']<550:report['errors'].append('catalog did not exceed 500 user/factory entries')
            # Rapid search/filter/sort. Debounced typing is exercised by StringVar writes; explicit
            # refreshes stress the worst case more heavily than normal user interaction.
            t=time.monotonic();cats=('All','Effects','Groups','Mine');sorts=('Name','Family','Recent')
            for i in range(180):
                lib.query.set('duplicate' if i%7==0 else str(i%43));lib.category.set(cats[i%4]);lib.sort.set(sorts[i%3]);lib.refresh();
                if i%12==0:pump(app,.004)
            lib.query.set('');lib.category.set('All');lib.sort.set('Name');lib.refresh();pump(app,.08)
            report['filter_sort_seconds']=time.monotonic()-t;report['widget_count_after_filters']=widgets(lib)
            if report['widget_count_after_filters']!=report['widget_count_initial']:report['errors'].append('filter/sort changed retained widget count')
            # Catalogue revision must replace, not leak, one cached card.
            first=next(x for x in app.catalog.ingredients() if x['name'].startswith('User module'))
            app.catalog.save_ingredient(first['name'],'rack',{'rack':primitive,'scope':'module','version':1},ingredient_id=first['id']);app.refresh_module_library();pump(app,.05)
            report['widget_count_after_revision']=widgets(lib)
            if report['widget_count_after_revision']!=report['widget_count_initial']:report['errors'].append('catalog revision leaked/dropped a card widget')
            # Keyboard-only traversal across cards.
            lib.selected_id=lib._visible[0]
            for _ in range(120):lib._key_move(1)
            if not lib.selected_id:report['errors'].append('keyboard traversal lost selection')
            # Known Add -> module and exact insertion path.
            cell=app.deck.selected_cell();rack,_=cell.target();rack[:]=[];cell.refresh(True);pump(app,.04)
            base_rows={r['id']:r for r in lib._rows.values() if r['type']=='Base'}
            lib.add_row(base_rows['base:brightness']);lib.add_row(base_rows['base:hue'],index=0);pump(app,.05)
            if [x.kind for x in rack]!=['hue','brightness']:report['errors'].append('exact insertion order failed')
            # Group/ungroup 120 cycles with deterministic processing order.
            t=time.monotonic()
            for _ in range(120):
                g=group_selected(rack,[x.id for x in rack]);compile_rack(rack);ungroup(rack,g.id);compile_rack(rack)
            report['group_ungroup_seconds']=time.monotonic()-t
            if [x.kind for x in rack]!=['hue','brightness']:report['errors'].append('group/ungroup changed signal order')
            # Workspace transforms around the library must not destroy its retained panel identity.
            identity=str(app.library_frame)
            for _ in range(12):
                app.toggle_panel_maximize('Library');pump(app,.006);app.restore_maximized_panel();pump(app,.006)
                if not app.float_panel('Library'):report['errors'].append('float failed');break
                pump(app,.006)
                if not app.redock_panel('Library'):report['errors'].append('redock failed');break
                pump(app,.006)
            report['panel_identity_retained']=str(app.library_frame)==identity
            if not report['panel_identity_retained']:report['errors'].append('module library panel identity changed')
            report['callback_errors']=callbacks
            if callbacks:report['errors'].extend(callbacks)
            report['status']='PASS' if not report['errors'] else 'FAIL'
        finally:
            try:app.close(force=True)
            except Exception:pass
    text=json.dumps(report,indent=2)
    if out_path:Path(out_path).write_text(text)
    print(text);return 0 if report['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1] if len(sys.argv)>1 else None))
