#!/usr/bin/env python3
"""UX40 targeted gate: retain UX39 + verify module reliability and theme parity."""
import json,os,sys,tempfile,time,unittest
from pathlib import Path
from io import StringIO
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'app_source'),str(ROOT/'tools')]
from verify_ux39 import MODULES, SUPERSEDED,flatten

class Result(unittest.TextTestResult):
    def startTest(self,test):
        print('RUN',test.id(),flush=True)
        super().startTest(test)

def main():
    loader=unittest.TestLoader();modules=(*MODULES,'tests.test_ux40_module_controls')
    cases=[case for name in modules for case in flatten(loader.loadTestsFromName(name))]
    retired=[c.id() for c in cases if c.id() in SUPERSEDED]
    selected=[c for c in cases if c.id() not in SUPERSEDED]
    with tempfile.TemporaryDirectory(prefix='neospector-ux40-test-') as td:
        os.environ['OMNE_SEQUENCER_SANDBOX']=td
        os.environ['NEOSPECTOR_NO_NATIVE_DROP']='1'
        stream=StringIO();start=time.monotonic()
        result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(unittest.TestSuite(selected))
    summary={'version':'0.7.24-ux40','selected':result.testsRun,
             'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
             'failed':[t.id() for t,_ in result.failures],
             'errors':[t.id() for t,_ in result.errors],
             'superseded':retired,'elapsed_s':round(time.monotonic()-start,2),
             'status':'PASS' if result.wasSuccessful() else 'FAIL'}
    folder=ROOT/'.verification-runs'/'ux40';folder.mkdir(parents=True,exist_ok=True)
    (folder/'acceptance.json').write_text(json.dumps(summary,indent=2)+'\n')
    (folder/'acceptance.log').write_text(stream.getvalue())
    print('UX40 GATE',json.dumps(summary,indent=2),flush=True)
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':
    code=main();sys.stdout.flush();sys.stderr.flush()
    # The runtime may own non-daemon media threads; keep the isolated CI runner
    # bounded after all test fixture teardown and report writing have completed.
    os._exit(code)
