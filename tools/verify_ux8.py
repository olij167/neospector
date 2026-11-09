#!/usr/bin/env python3
"""Current UX8 workflow and preserved engine release gate.

Requires a desktop/display. Historic interface tests remain available separately:
PYTHONPATH=app_source python3 -m unittest discover -s tests -p 'test_*.py'
They assert multiple incompatible previous layouts; do not use as a UX8 UI spec.
"""
import sys,unittest,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app_source'),str(ROOT/'tests')]
ENGINE_MODULES=(
 'test_model','test_v02_model','test_v03_instrument','test_v03_audio',
 'test_v03_capture','test_export_v02','test_compositor','test_render_smoke',
 'test_render_parity','test_audio_transport','test_signals','test_process_tools',
 'test_playable_intent','test_playable_queues','test_playable_randomise',
 'test_playable_lifecycle','test_playable_export_scope','test_playable_retention',
 'test_r5c4_clip_clock','test_r5c4_linked_audio',
 'test_n1_control_continuity','test_r5c4_live_parameters',
 'test_ux4_module_library.CatalogueContractTests',
 'test_ux4_module_library.GroupingContractTests',
)
loader=unittest.TestLoader();suite=loader.discover(str(ROOT/'tests'),pattern='test_ux8*.py')
for name in ENGINE_MODULES:suite.addTests(loader.loadTestsFromName(name))
result=unittest.TextTestRunner(verbosity=2).run(suite)
report={'run':result.testsRun,'failures':[case.id() for case,_ in result.failures],
        'errors':[case.id() for case,_ in result.errors],'skipped':[(case.id(),reason) for case,reason in result.skipped],
        'engine_modules':ENGINE_MODULES,'status':'PASS' if result.wasSuccessful() and not result.skipped else 'FAIL'}
if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2))
raise SystemExit(0 if report['status']=='PASS' else 1)
