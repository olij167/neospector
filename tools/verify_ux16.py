#!/usr/bin/env python3
"""UX16 gate: all retained engine behaviour plus contextual source/rack tests."""
from __future__ import annotations
import json,os,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app_source'))
sys.path.insert(0,str(ROOT/'tests'))
PATTERNS=(
    'test_ux16_instrument.py','test_ux15_rack.py','test_ux14_uniform.py','test_ux13_surface.py','test_ux12_refinement.py','test_ux11_workspace.py','test_ux10_workspace.py','test_v03_instrument.py',
    'test_r5c4_queues.py','test_v02_behaviour_regressions.py',
    'test_ux8_mix.py','test_ux8_groups.py','test_ux8_rack.py')
SUPERSEDED={
    # UX16 explicit UI changes, verified by test_ux16_instrument.py instead:
    'test_ux13_surface.UX13SurfaceTests.test_module_library_has_no_filter_or_sort_dropdowns',
    'test_ux13_surface.UX13SurfaceTests.test_narrow_module_browser_does_not_crush_active_pedal',
    'test_ux13_surface.UX13SurfaceTests.test_rack_actions_are_visible_without_overflow',
    'test_ux12_refinement.UX12Tests.test_independent_media_and_module_drawers',
    'test_ux12_refinement.UX12Tests.test_inline_reaction_compact_and_editable',
    'test_ux12_refinement.UX12Tests.test_module_insertion_with_media_hidden',
    'test_ux11_workspace.UX11WorkspaceTests.test_channels_and_output_are_distinct_edit_targets',
    'test_ux11_workspace.UX11WorkspaceTests.test_collapse_upcoming_only',
    'test_ux11_workspace.UX11WorkspaceTests.test_left_collapsing_future_gives_music_more_room',
    'test_ux10_workspace.UX10WorkspaceTests.test_short_window_keeps_queue_and_rack_operable',
    'test_r5c4_queues.QueueWorkspace.test_queue_toolbar_gap_drag_and_audition_keep_programme_clock',
    # Superseded spatial/dial expectations; retained engine tests still run.
    'test_ux11_workspace.UX11WorkspaceTests.test_transport_is_single_row_and_output_actions_are_progressively_disclosed',
    'test_ux10_workspace.UX10WorkspaceTests.test_one_permanent_two_channel_media_desk',
    'test_ux10_workspace.UX10WorkspaceTests.test_library_is_on_right_and_context_does_not_take_live',
    'test_ux10_workspace.UX10WorkspaceTests.test_import_button_does_not_invoke_legacy_library',
    'test_ux11_workspace.UX11WorkspaceTests.test_right_side_tabs_and_safe_collapse',
    'test_ux11_workspace.UX11WorkspaceTests.test_module_builder_does_not_replace_b',
    'test_ux8_rack.InstrumentRackTests.test_reaction_stays_inside_module_and_survives_external_click',
    'test_ux11_workspace.UX11WorkspaceTests.test_small_rack_primary_actions_fit_without_overflow',
    'test_ux8_rack.InstrumentRackTests.test_group_navigation_edit_promote_undo_roundtrip',
    'test_ux8_rack.InstrumentRackTests.test_undo_inside_group_keeps_navigation',
    'test_ux8_groups.GroupGestureIntegrationTests.test_group_add_reorder_bypass_remove_and_roundtrip',
    'test_ux8_groups.GroupGestureIntegrationTests.test_drag_undo_and_escape_restore_animation',
    'test_ux10_workspace.UX10WorkspaceTests.test_right_group_builder_returns_to_library',
}

def accepted(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from accepted(item)
        elif item.id() not in SUPERSEDED:yield item

def main():
    if not os.environ.get('DISPLAY') and sys.platform.startswith('linux'):
        print('BLOCKED: Xorg desktop or Xvfb required for Tk UI verification.');return 2
    out=ROOT/'.verification-runs'/'ux16';out.mkdir(parents=True,exist_ok=True)
    loader=unittest.TestLoader();suite=unittest.TestSuite();observed=set()
    for pat in PATTERNS:
        found=loader.discover(str(ROOT/'tests'),pattern=pat,top_level_dir=str(ROOT/'tests'))
        for test in accepted(found):suite.addTest(test)
        # Check superseded names exist, never silently filter non-existing names.
        found=loader.discover(str(ROOT/'tests'),pattern=pat,top_level_dir=str(ROOT/'tests'))
        def flatten(value):
            for case in value:
                if isinstance(case,unittest.TestSuite):yield from flatten(case)
                else:yield case.id()
        observed.update(flatten(found))
    missing=SUPERSEDED-observed
    if missing:
        print('BLOCKED: superseded tests changed unexpectedly:',sorted(missing));return 2
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='neospector-ux16-verify-') as sandbox:
        os.environ['OMNE_SEQUENCER_SANDBOX']=sandbox
        os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
        with (out/'verification.log').open('w') as log:
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    report={'product':'Neospector','version':'0.7.0-ux16',
        'status':'PASS' if result.wasSuccessful() else 'FAIL','tests_run':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'superseded_prior_ui_tests':sorted(SUPERSEDED),
        'patterns':list(PATTERNS),'elapsed_seconds':round(time.monotonic()-start,2),
        'limitations':'Physical camera/mic/desktop capture, recording/export and reverse playback need owner acceptance; glitter/glitch wipe is not video-codec datamosh'}
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if result.wasSuccessful() else 1
if __name__=='__main__':
    code=main()
    # Rendering tests may leave third-party native input threads alive; at this
    # point all tests have run, the report is on disk, and temp resources closed.
    # Exit the verification worker without waiting for unrelated native threads.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
