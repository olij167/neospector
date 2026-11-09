#!/usr/bin/env python3
"""UX28 gate: retained behaviour + new paired controls and right tray geometry.

Earlier snapshot tests named in SUPERSEDED_UI_ASSERTIONS describe a previous
layout, not runtime safety invariants. They are not counted as passes.
"""
from __future__ import annotations
import json,os,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from verify_ux26 import flatten,RETIRED
ROOT=Path(__file__).resolve().parents[1]
SUPERSEDED_UI_ASSERTIONS={
    'tests.test_ux27_docks.UX27Tk.test_audio_docked_in_left_corner_and_toolbar_does_not_expand':'UX28 audio moves to right stack',
    'tests.test_ux27_docks.UX27Tk.test_audio_expanded_does_not_displace_visual_docks':'UX28 all three queues share right stack',
    'tests.test_ux27_docks.UX27Tk.test_music_dock_respects_open_left_workbench':'UX28 music right, never left',
    'tests.test_ux26_integration.UX26Integration.test_mix_strip_keeps_height_and_mic_is_next_to_react':'UX28 mic moves top with cameras',
    'tests.test_ux26_integration.UX26Integration.test_queue_heights_symmetric_and_never_cover_preview_top':'UX28 Music added to three top toggles',
    'tests.test_ux25_polish.UX25Tk.test_shared_shelf_updates_without_tab_navigation':'UX28 signal style token changed; import refresh retained by other tests',
    RETIRED:'Retired prior to UX26: detached sidebar drag assumed',
}
def run():
    sys.path[:0]=[str(ROOT),str(ROOT/'app_source')]
    loader=unittest.TestLoader();cases=[]
    for name in ('tests.test_ux28_hierarchy','tests.test_ux27_docks','tests.test_ux26_layout',
                 'tests.test_ux26_actions','tests.test_ux26_integration','tests.test_r5c4_queues'):
        cases.extend(flatten(loader.loadTestsFromName(name)))
    for method in ('test_queued_camera_is_seen_by_top_toggle_and_skips_on_toggle_off',
                   'test_shared_shelf_updates_without_tab_navigation'):
        cases.extend(flatten(loader.loadTestsFromName('tests.test_ux25_polish.UX25Tk.'+method)))
    retired=[c.id() for c in cases if c.id() in SUPERSEDED_UI_ASSERTIONS]
    if set(retired)!=set(SUPERSEDED_UI_ASSERTIONS):
        raise RuntimeError('Unexpected obsolete test selection: '+repr(retired))
    cases=[c for c in cases if c.id() not in SUPERSEDED_UI_ASSERTIONS]
    started=time.monotonic()
    from io import StringIO
    capture=StringIO()
    with tempfile.TemporaryDirectory(prefix='neospector-ux28-test-') as home:
        os.environ['OMNE_SEQUENCER_SANDBOX']=home
        os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
        result=unittest.TextTestRunner(stream=capture,verbosity=2).run(unittest.TestSuite(cases))
    summary={'version':'0.7.12-ux28','run':result.testsRun,
             'passed':result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
             'errors':[c.id() for c,_ in result.errors],
             'failures':[c.id() for c,_ in result.failures],
             'skipped':[c.id() for c,_ in result.skipped],
             'superseded_historical_ui_assertions':SUPERSEDED_UI_ASSERTIONS,
             'elapsed_seconds':round(time.monotonic()-started,2),
             'status':'PASS' if result.wasSuccessful() else 'FAIL'}
    out=ROOT/'.verification-runs'/'ux28';out.mkdir(parents=True,exist_ok=True)
    (out/'acceptance.log').write_text(capture.getvalue())
    (out/'acceptance.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(capture.getvalue()[-15000:])
    print('UX28 GATE',json.dumps(summary,indent=2))
    return 0 if result.wasSuccessful() else 1

def main():
    needs_display=not os.environ.get('DISPLAY')
    if sys.platform.startswith('linux') and not needs_display:
        try:
            import tkinter as tk
            root=tk.Tk();root.withdraw();root.destroy()
        except (tk.TclError,OSError):needs_display=True
    if needs_display and sys.platform.startswith('linux'):
        xvfb=shutil.which('xvfb-run')
        if not xvfb:
            print('BLOCKED: DISPLAY or xvfb-run required',file=sys.stderr);return 2
        return subprocess.call([xvfb,'-a','-s','-screen 0 1800x1000x24',sys.executable,__file__],cwd=ROOT)
    return run()
if __name__=='__main__':raise SystemExit(main())
