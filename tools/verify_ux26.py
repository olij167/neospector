#!/usr/bin/env python3
"""Focused UX26 acceptance, retained UX25 camera and R5 queue/PCM invariants."""
from __future__ import annotations
import json,os,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RETIRED='tests.test_r5c4_queues.QueueWorkspace.test_queue_toolbar_gap_drag_and_audition_keep_programme_clock'
# R5 fixture assumes the deprecated detached Queues sidebar is visible when
# shell.show('Queues') is invoked. UX26 controls are bottom-docked and covered
# by test_ux26_integration.test_visual_row_end_reorder_is_immediate.

def flatten(suite):
    for c in suite:
        if isinstance(c,unittest.TestSuite):yield from flatten(c)
        else:yield c

def run():
    sys.path.insert(0,str(ROOT))
    sys.path.insert(0,str(ROOT/'app_source'))
    cases=[]
    loader=unittest.TestLoader()
    for name in ('tests.test_ux26_layout','tests.test_ux26_actions',
                 'tests.test_ux26_integration','tests.test_r5c4_queues'):
        cases.extend(flatten(loader.loadTestsFromName(name)))
    for method in ('test_queued_camera_is_seen_by_top_toggle_and_skips_on_toggle_off',
                   'test_shared_shelf_updates_without_tab_navigation'):
        cases.extend(flatten(loader.loadTestsFromName('tests.test_ux25_polish.UX25Tk.'+method)))
    retired=[c.id() for c in cases if c.id()==RETIRED]
    if retired!=[RETIRED]:raise RuntimeError('Expected one exact deprecated UI fixture; cannot retire an unknown test')
    cases=[c for c in cases if c.id()!=RETIRED]
    started=time.monotonic()
    from contextlib import redirect_stdout,redirect_stderr
    from io import StringIO
    capture=StringIO()
    with tempfile.TemporaryDirectory(prefix='neospector-ux26-test-') as home:
        os.environ['OMNE_SEQUENCER_SANDBOX']=home
        os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
        result=unittest.TextTestRunner(stream=capture,verbosity=2).run(unittest.TestSuite(cases))
    summary={'version':'0.7.10-ux26','focused_run':result.testsRun,
             'passed':result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
             'errors':[t.id() for t,_ in result.errors],
             'failures':[t.id() for t,_ in result.failures],
             'skipped':[t.id() for t,_ in result.skipped],
             'retired_historical_ui_fixture':RETIRED,
             'elapsed_seconds':round(time.monotonic()-started,2),
             'status':'PASS' if result.wasSuccessful() else 'FAIL'}
    out=ROOT/'.verification-runs'/'ux26';out.mkdir(parents=True,exist_ok=True)
    (out/'acceptance.log').write_text(capture.getvalue())
    (out/'acceptance.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(capture.getvalue()[-12000:],flush=True)
    print('UX26 GATE',json.dumps(summary,indent=2),flush=True)
    return 0 if result.wasSuccessful() else 1

def main():
    needs_display=not bool(os.environ.get('DISPLAY'))
    if sys.platform.startswith('linux') and not needs_display:
        # Some CI/container shells export DISPLAY=:0 without an X server.
        # Verify connectivity instead of trusting a non-empty environment.
        try:
            import tkinter as tk
            probe=tk.Tk();probe.withdraw();probe.destroy()
        except (tk.TclError,OSError):needs_display=True
    if needs_display and sys.platform.startswith('linux'):
        xvfb=shutil.which('xvfb-run')
        if not xvfb:
            print('BLOCKED: DISPLAY or xvfb-run required for GUI acceptance',file=sys.stderr)
            return 2
        return subprocess.call([xvfb,'-a','-s','-screen 0 1400x880x24',sys.executable,__file__,'--display-ready'],cwd=str(ROOT))
    return run()
if __name__=='__main__':raise SystemExit(main())
