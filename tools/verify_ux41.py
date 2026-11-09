#!/usr/bin/env python3
"""UX41 bounded acceptance: UX39/40 interaction, UX41 controls, signed update safety."""
import json,os,sys,time,unittest,tempfile
from pathlib import Path
from io import StringIO
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'app_source'),str(ROOT/'tools')]
MODULES=('tests.test_ux39_performance','tests.test_ux40_module_controls',
         'tests.test_ux41_final_controls','tests.test_ux38_updates')
class RunResult(unittest.TextTestResult):
    def startTest(self,test):
        print('RUN',test.id(),flush=True)
        super().startTest(test)

def main():
    suite=unittest.TestSuite(unittest.TestLoader().loadTestsFromName(x) for x in MODULES)
    with tempfile.TemporaryDirectory(prefix='ux41-acceptance-') as td:
        os.environ.update(OMNE_SEQUENCER_SANDBOX=td,NEOSPECTOR_NO_NATIVE_DROP='1')
        text=StringIO();start=time.monotonic()
        result=unittest.TextTestRunner(stream=text,verbosity=2,resultclass=RunResult).run(suite)
    summary={'version':'0.7.25-ux41','tests':result.testsRun,
        'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        'failures':[test.id() for test,_ in result.failures],
        'errors':[test.id() for test,_ in result.errors],
        'skipped':[test.id() for test,_ in result.skipped],
        'seconds':round(time.monotonic()-start,2),
        'status':'PASS' if result.wasSuccessful() else 'FAIL'}
    out=ROOT/'.verification-runs'/'ux41';out.mkdir(parents=True,exist_ok=True)
    (out/'acceptance.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'acceptance.log').write_text(text.getvalue())
    print('UX41 GATE',json.dumps(summary,indent=2),flush=True)
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':
    rc=main();sys.stdout.flush();sys.stderr.flush()
    # External backend workers may not exit promptly after all closed fixtures.
    # The selected tests have already completed and their report is flushed.
    os._exit(rc)
