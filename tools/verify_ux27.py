#!/usr/bin/env python3
"""UX27 focused acceptance: queue geometry plus retained audio/visual invariants."""
from __future__ import annotations
import json,os,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from verify_ux26 import flatten,RETIRED
ROOT=Path(__file__).resolve().parents[1]

def run():
    sys.path[:0]=[str(ROOT),str(ROOT/'app_source')]
    loader=unittest.TestLoader();cases=[]
    for name in ('tests.test_ux27_docks','tests.test_ux26_layout','tests.test_ux26_actions',
                 'tests.test_ux26_integration','tests.test_r5c4_queues'):
        cases.extend(flatten(loader.loadTestsFromName(name)))
    for method in ('test_queued_camera_is_seen_by_top_toggle_and_skips_on_toggle_off',
                   'test_shared_shelf_updates_without_tab_navigation'):
        cases.extend(flatten(loader.loadTestsFromName('tests.test_ux25_polish.UX25Tk.'+method)))
    retired=[c.id() for c in cases if c.id()==RETIRED]
    if retired!=[RETIRED]:raise RuntimeError('Unexpected retired R5 fixture selection')
    cases=[c for c in cases if c.id()!=RETIRED]
    started=time.monotonic()
    from io import StringIO
    capture=StringIO()
    with tempfile.TemporaryDirectory(prefix='neospector-ux27-test-') as home:
        os.environ['OMNE_SEQUENCER_SANDBOX']=home
        os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
        result=unittest.TextTestRunner(stream=capture,verbosity=2).run(unittest.TestSuite(cases))
    summary={'version':'0.7.11-ux27','tests':result.testsRun,
             'passed':result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
             'errors':[t.id() for t,_ in result.errors],
             'failures':[t.id() for t,_ in result.failures],
             'skipped':[t.id() for t,_ in result.skipped],
             'retired_preexisting_fixture':RETIRED,
             'elapsed_seconds':round(time.monotonic()-started,2),
             'status':'PASS' if result.wasSuccessful() else 'FAIL'}
    dest=ROOT/'.verification-runs'/'ux27';dest.mkdir(parents=True,exist_ok=True)
    (dest/'acceptance.log').write_text(capture.getvalue())
    (dest/'acceptance.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(capture.getvalue()[-14000:],flush=True)
    print('UX27 GATE',json.dumps(summary,indent=2),flush=True)
    return 0 if result.wasSuccessful() else 1

def main():
    needs_display=not bool(os.environ.get('DISPLAY'))
    if sys.platform.startswith('linux') and not needs_display:
        try:
            import tkinter as tk
            root=tk.Tk();root.withdraw();root.destroy()
        except (tk.TclError,OSError):needs_display=True
    if needs_display and sys.platform.startswith('linux'):
        xvfb=shutil.which('xvfb-run')
        if not xvfb:
            print('BLOCKED: DISPLAY or xvfb-run required',file=sys.stderr);return 2
        return subprocess.call([xvfb,'-a','-s','-screen 0 1400x880x24',sys.executable,__file__],cwd=ROOT)
    return run()
if __name__=='__main__':raise SystemExit(main())
