#!/usr/bin/env python3
"""Current UX9 release gate; superseded UX8 layout assertions stay in history."""
import ast,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app_source'),str(ROOT/'tests')]
SUPERSEDED={
 'test_ux8_media.InstrumentMediaActions.test_tab_selection_deliberately_selects_layer_rack':'Queue tabs removed; browsing no longer changes owner.',
 'test_ux8_media.InstrumentMediaTk.test_stable_tabs_audio_summary_and_flat_library':'Simultaneous source lanes and intentional ingredient shelf replace queue tabs.',
 'test_ux8_r2_immediate.ImmediateTests.test_inputs_stay_inside_small_preview':'Inputs moved from preview to source column.',
 'test_ux8_rack.InstrumentRackTests.test_reaction_stays_inside_module_and_survives_external_click':'Principal fader replaced by a dial; actual dial hit/gesture and reaction bounds checked by UX9.',
 'test_ux8_shell.InstrumentShellTests.test_fixed_regions_and_migration':'Library moved to the main-column shelf.',
 'test_ux8_shell.InstrumentShellTests.test_focus_and_media_restore':'Ingredients toggle preserves simultaneous sources.',
}
loader=unittest.TestLoader();suite=unittest.TestSuite()
def flat(t):
 for case in t:
  if isinstance(case,unittest.TestSuite):yield from flat(case)
  else:yield case
for pattern in ('test_ux9*.py','test_ux8*.py'):
 for case in flat(loader.discover(str(ROOT/'tests'),pattern=pattern)):
  if case.id() not in SUPERSEDED:suite.addTest(case)
node=ast.parse((ROOT/'tools/verify_ux8.py').read_text());modules=next(ast.literal_eval(n.value) for n in node.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ENGINE_MODULES' for t in n.targets))
for name in modules:suite.addTests(loader.loadTestsFromName(name))
result=unittest.TextTestRunner(verbosity=2).run(suite)
report={'run':result.testsRun,'failures':[c.id() for c,_ in result.failures],'errors':[c.id() for c,_ in result.errors],'skipped':[(c.id(),r) for c,r in result.skipped],'superseded_ux8_layout_assertions':SUPERSEDED,'status':'PASS' if result.wasSuccessful() and not result.skipped else 'FAIL'}
if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2))
raise SystemExit(0 if report['status']=='PASS' else 1)
