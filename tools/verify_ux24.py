#!/usr/bin/env python3
"""UX23 independent Tk process gate: verify retained behaviours and new right-rail UI.

Separate Tk processes per historical release avoid leaking Tk native event handles
across 100+ UI tests. Retired expectations are listed by exact test id.
"""
from __future__ import annotations
import json,os,shutil,subprocess,sys,time,unittest
from pathlib import Path
from verify_ux20_legacy import PATTERNS as PRIOR_PATTERNS, SUPERSEDED as UX20_SUPERSEDED
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.verification-runs'/'ux24'
PATTERNS=('test_ux24_flow.py','test_ux23_sources.py','test_ux22_sources.py','test_ux21_streamline.py','test_ux20_consolidation.py',
          'test_ux19_hierarchy.py','test_ux18_workbench.py','test_r5c4_queues.py',
          'test_ux8_mix.py','test_ux8_groups.py','test_ux15_rack.py','test_v03_instrument.py')
SUPERSEDED=set(UX20_SUPERSEDED)|{
    'test_ux19_hierarchy.UX19Hierarchy.test_compact_header_keeps_camera_mic_and_source_access_visible',
    'test_ux13_surface.UX13SurfaceTests.test_application_menu_only_offers_file_functions',
    'test_ux8_rack.InstrumentRackTests.test_current_item_with_prepared_cycle_has_explicit_guard',
    'test_ux20_consolidation.UX20Consolidation.test_sources_have_one_named_discoverable_group',
    'test_ux20_consolidation.UX20Consolidation.test_compact_preview_preserves_sources_mixer_and_rack_identity',
    'test_ux18_workbench.UX18Workbench.test_audio_radio_player_is_not_six_visual_transport_buttons',
}
SUPERSEDED.update({
    'test_ux23_sources.UX23Tk.test_empty_visual_player_has_one_source_entry_and_not_legacy_source_tabs',
    'test_ux23_sources.UX23Tk.test_native_mix_menu_is_managed_with_outside_click',
    'test_ux23_sources.UX23Tk.test_outside_click_dismisses_transition_menu',
    'test_ux21_streamline.UX21Streamline.test_file_menu_owns_save_export_and_top_has_clear_output_view',
    'test_ux21_streamline.UX21Streamline.test_sources_are_in_global_toolbar_with_live_toggle_pairs',
    'test_ux19_hierarchy.UX19Hierarchy.test_empty_queue_has_one_clear_browse_action',
})

def flatten(s):
    for c in s:
        if isinstance(c,unittest.TestSuite):yield from flatten(c)
        else:yield c

def batch(pattern):
    sys.path.insert(0,str(ROOT/'app_source'))
    sys.path.insert(0,str(ROOT/'tests'))
    loader=unittest.TestLoader()
    cases=list(flatten(loader.discover(str(ROOT/'tests'),pattern=pattern,top_level_dir=str(ROOT/'tests'))))
    selected=[t for t in cases if t.id() not in SUPERSEDED]
    OUT.mkdir(parents=True,exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(prefix='neospector-ux24-'+pattern.replace('.py','')+'-') as sandbox:
        os.environ['OMNE_SEQUENCER_SANDBOX']=sandbox
        os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
        with (OUT/(pattern+'.log')).open('w') as log:
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.TestSuite(selected))
    status={'pattern':pattern,'total':len(cases),'selected':len(selected),'run':result.testsRun,
            'failures':[t.id() for t,_ in result.failures],'errors':[t.id() for t,_ in result.errors],
            'skipped':len(result.skipped),'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped)}
    (OUT/(pattern+'.json')).write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps(status),flush=True)
    sys.stdout.flush();sys.stderr.flush()
    # Native Tk/video/background threads may outlive test root close().
    os._exit(0 if result.wasSuccessful() else 1)

def main():
    if len(sys.argv)==3 and sys.argv[1]=='--batch':return batch(sys.argv[2])
    if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
        print('BLOCKED: DISPLAY required for Tk acceptance tests');return 2
    OUT.mkdir(parents=True,exist_ok=True)
    # Exact-match retired expectation auditing means a new test name cannot
    # silently disappear from the suite.
    sys.path.insert(0,str(ROOT/'tests'))
    discovered=set()
    for pat in PATTERNS:
        discovered.update(t.id() for t in flatten(unittest.TestLoader().discover(str(ROOT/'tests'),pattern=pat,top_level_dir=str(ROOT/'tests'))))
    missing={x for x in SUPERSEDED if x.rsplit(".",2)[0].split(".")[0]+".py" in PATTERNS and x not in discovered}
    if missing:
        print('BLOCKED: retired expectations are not found:',sorted(missing));return 2
    batches=[];errors=[];start=time.monotonic()
    for pat in PATTERNS:
        try:
            # A fresh virtual X server per batch avoids Tk native event state leaking
            # across verification processes. When Xvfb is unavailable (e.g. a Zorin
            # desktop without the optional test package), use the existing DISPLAY.
            command=[sys.executable,__file__,'--batch',pat]
            if sys.platform.startswith('linux') and shutil.which('xvfb-run'):
                command=['xvfb-run','-a','-s','-screen 0 1280x850x24',*command]
            cp=subprocess.run(command,cwd=str(ROOT),capture_output=True,text=True,timeout=55)
            summary=json.loads((OUT/(pat+'.json')).read_text())
            batches.append(summary)
            print(f"{pat}: {summary['passed']}/{summary['run']} PASS (retired {summary['total']-summary['selected']})",flush=True)
            if cp.returncode!=0:
                errors.append({'pattern':pat,'code':cp.returncode,'failures':summary['failures'],'errors':summary['errors']})
                print((OUT/(pat+'.log')).read_text()[-3500:],flush=True)
        except (subprocess.TimeoutExpired,ValueError,FileNotFoundError) as exc:
            errors.append({'pattern':pat,'error':str(exc)})
            print('BLOCKED:',pat,str(exc),flush=True)
    totals={k:sum(row[k] for row in batches) for k in ('total','selected','run','passed','skipped')}
    report={'product':'Neospector','version':'0.7.8-ux24',
            'status':'PASS' if not errors else 'FAIL','counts':totals,'failures':errors,
            'retired_prior_ui_assertions':sorted(SUPERSEDED),'batches':batches,
            'elapsed_seconds':round(time.monotonic()-start,2),
            'limitations':['Owner-device webcam, display/application capture, microphone, audio routing, and recording/export not yet verified',
                           'Queueing a live camera currently acquires its device during placement preflight, even for future cues',
                           'Queued live AUDIO input cues change reaction-source routing, not soundtrack PCM; export/capture qualification pending']}
    (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('UX24 GATE',json.dumps({k:v for k,v in report.items() if k not in ('batches','retired_prior_ui_assertions')},indent=2))
    return 0 if not errors else 1
if __name__=='__main__':
    status=main()
    sys.stdout.flush();sys.stderr.flush()
    # Some Tk/Xlib worker handles survive interpreter shutdown even after
    # all batches finish. Reports are durably flushed above.
    os._exit(status)
