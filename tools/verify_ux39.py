#!/usr/bin/env python3
"""UX39 targeted performance and preserved instrument interaction regression gate."""
from __future__ import annotations
import json,os,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'app_source'),str(ROOT/'tools')]
from verify_ux38 import SUPERSEDED,flatten
MODULES=(
 'tests.test_ux26_actions','tests.test_ux29_browser_mixer',
 'tests.test_ux31_controls','tests.test_ux31_tk',
 'tests.test_ux32_contract','tests.test_ux33_authored',
 'tests.test_ux34_smooth_welcome','tests.test_ux37_unified_preferences',
 'tests.test_ux38_updates','tests.test_ux39_performance',
)
class StreamingResult(unittest.TextTestResult):
    def startTest(self,test):
        print('RUN',test.id(),flush=True)
        super().startTest(test)
def main():
    loader=unittest.TestLoader()
    allcases=[c for name in MODULES for c in flatten(loader.loadTestsFromName(name))]
    skipped=[case.id() for case in allcases if case.id() in SUPERSEDED]
    cases=[case for case in allcases if case.id() not in SUPERSEDED]
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='neospector-ux39-') as home:
        os.environ['OMNE_SEQUENCER_SANDBOX']=home
        os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
        from io import StringIO
        stream=StringIO()
        res=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=StreamingResult).run(unittest.TestSuite(cases))
    summary={'version':'0.7.23-ux39','tests_run':res.testsRun,'passed':res.testsRun-len(res.errors)-len(res.failures)-len(res.skipped),
      'failed':[case.id() for case,_ in res.failures], 'errors':[case.id() for case,_ in res.errors],
      'skipped':skipped,'runtime_s':round(time.monotonic()-start,3),
      'status':'PASS' if res.wasSuccessful() else 'FAIL'}
    folder=ROOT/'.verification-runs'/'ux39';folder.mkdir(parents=True,exist_ok=True)
    (folder/'acceptance.json').write_text(json.dumps(summary,indent=2)+'\n')
    (folder/'acceptance.log').write_text(stream.getvalue())
    print(stream.getvalue()[-12000:],flush=True)
    print('UX39 GATE:',json.dumps(summary,indent=2),flush=True)
    return 0 if res.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
