#!/usr/bin/env python3
"""UX35 contract gate: retained UX33, stable panel refresh, and welcome onboarding."""
from __future__ import annotations
import json,os,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from verify_ux32 import SUPERSEDED_UI_ASSERTIONS as PRIOR,flatten
ROOT=Path(__file__).resolve().parents[1]
SUPERSEDED={**PRIOR,
    'tests.test_ux32_contract.UX32Tk.test_transition_shape_is_authored_in_rack_not_popup':
    'UX33 removes shape/easing preset controls; animations are rack modules and groups.'}

def run():
    sys.path[:0]=[str(ROOT),str(ROOT/'app_source')]
    loader=unittest.TestLoader();cases=[]
    for name in ('tests.test_ux33_authored','tests.test_ux32_contract','tests.test_ux31_controls',
                 'tests.test_ux31_tk','tests.test_ux30_audio_and_ui','tests.test_ux30_tk',
                 'tests.test_ux29_browser_mixer','tests.test_ux28_hierarchy','tests.test_ux27_docks',
                 'tests.test_ux26_layout','tests.test_ux26_actions','tests.test_ux26_integration',
                 'tests.test_r5c4_queues','tests.test_ux34_smooth_welcome','tests.test_ux35_preferences_welcome'):
        cases.extend(flatten(loader.loadTestsFromName(name)))
    for method in ('test_queued_camera_is_seen_by_top_toggle_and_skips_on_toggle_off',
                   'test_shared_shelf_updates_without_tab_navigation'):
        cases.extend(flatten(loader.loadTestsFromName('tests.test_ux25_polish.UX25Tk.'+method)))
    retired=[c.id() for c in cases if c.id() in SUPERSEDED]
    if set(retired)!=set(SUPERSEDED):raise RuntimeError('Unexpected superseded assertions: '+repr(retired))
    cases=[c for c in cases if c.id() not in SUPERSEDED]
    from io import StringIO
    capture=StringIO();start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='neospector-ux35-') as home:
        os.environ['OMNE_SEQUENCER_SANDBOX']=home
        os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
        result=unittest.TextTestRunner(stream=capture,verbosity=2).run(unittest.TestSuite(cases))
    summary={'version':'0.7.19-ux35','tests_run':result.testsRun,
             'passed':result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
             'errors':[c.id() for c,_ in result.errors],
             'failures':[c.id() for c,_ in result.failures],
             'skipped':[c.id() for c in result.skipped],
             'superseded_assertions':SUPERSEDED,
             'seconds':round(time.monotonic()-start,2),
             'status':'PASS' if result.wasSuccessful() else 'FAIL'}
    out=ROOT/'.verification-runs'/'ux35';out.mkdir(parents=True,exist_ok=True)
    (out/'acceptance.log').write_text(capture.getvalue())
    (out/'acceptance.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(capture.getvalue()[-10000:]);print('UX35 GATE',json.dumps(summary,indent=2))
    return 0 if result.wasSuccessful() else 1

def main():
    display=bool(os.environ.get('DISPLAY'))
    if display:
        try:
            import tkinter as tk
            root=tk.Tk();root.withdraw();root.destroy()
        except (tk.TclError,OSError):display=False
    if not display and sys.platform.startswith('linux'):
        xvfb=shutil.which('xvfb-run')
        if not xvfb:
            print('BLOCKED: DISPLAY or xvfb-run is required',file=sys.stderr);return 2
        return subprocess.call([xvfb,'-a','-s','-screen 0 1800x1000x24',sys.executable,__file__],cwd=ROOT)
    return run()
if __name__=='__main__':raise SystemExit(main())
