#!/usr/bin/env python3
"""UX32 acceptance: retained runtime contracts plus transition rack and inline settings.

Obsolete UI snapshot assertions are retired explicitly by test ID, not counted as
passes, and replaced with UX32 interaction and model coverage.
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
    'tests.test_ux26_integration.UX26Integration.test_browser_single_list_and_destination_exclusive_with_effects':'UX29 replaces global A/B/Audio destination filters with browser-local Files/Sources and contextual row menus',
    RETIRED:'Retired prior to UX26: detached sidebar drag assumed',
    'tests.test_ux30_tk.UX30Tk.test_mixer_includes_mic_and_vertical_faders':'UX31 mixer shows engaged sources, not disconnected placeholders',
    'tests.test_ux29_browser_mixer.UX29Tk.test_audio_mixer_and_queue_switch_expand_tray':'UX31 removes inactive soundtrack placeholder; switching is separately tested',
    'tests.test_ux29_browser_mixer.UX29Tk.test_mixer_height_can_expand_and_stays_within_preview':'UX31 empty mixers contract to content; active mixer sizing has a replacement live Tk check',
    'tests.test_ux31_controls.SharedEditor.test_editor_supports_distinct_transition_and_rack_sections':'UX32 removes the separate Creative Controls Toplevel in favour of Transition rack and inline variation',
    'tests.test_ux31_tk.UX31Tk.test_advanced_editor_switches_modes_without_editing_other_scope':'UX32 uses rack scopes instead of Creative Controls window',
    'tests.test_ux31_tk.UX31Tk.test_library_variation_opens_shared_editor':'UX32 expands variation in the local module rack toolbar',
}
def run():
    sys.path[:0]=[str(ROOT),str(ROOT/'app_source')]
    loader=unittest.TestLoader();cases=[]
    for name in ('tests.test_ux32_contract','tests.test_ux31_controls','tests.test_ux31_tk','tests.test_ux30_audio_and_ui','tests.test_ux30_tk','tests.test_ux29_browser_mixer','tests.test_ux28_hierarchy','tests.test_ux27_docks','tests.test_ux26_layout',
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
    with tempfile.TemporaryDirectory(prefix='neospector-ux32-test-') as home:
        os.environ['OMNE_SEQUENCER_SANDBOX']=home
        os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
        result=unittest.TextTestRunner(stream=capture,verbosity=2).run(unittest.TestSuite(cases))
    summary={'version':'0.7.16-ux32','run':result.testsRun,
             'passed':result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
             'errors':[c.id() for c,_ in result.errors],
             'failures':[c.id() for c,_ in result.failures],
             'skipped':[c.id() for c,_ in result.skipped],
             'superseded_historical_ui_assertions':SUPERSEDED_UI_ASSERTIONS,
             'elapsed_seconds':round(time.monotonic()-started,2),
             'status':'PASS' if result.wasSuccessful() else 'FAIL'}
    out=ROOT/'.verification-runs'/'ux32';out.mkdir(parents=True,exist_ok=True)
    (out/'acceptance.log').write_text(capture.getvalue())
    (out/'acceptance.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(capture.getvalue()[-15000:])
    print('UX32 GATE',json.dumps(summary,indent=2))
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
