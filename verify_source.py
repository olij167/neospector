#!/usr/bin/env python3
"""Fresh isolated full-suite report; unavailable GUI tests remain errors/skips."""
import gc,json,os,platform,subprocess,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent

class NativeFixtureResult(unittest.TextTestResult):
    def startTest(self,test):
        # Hundreds of independent Tk roots are made by this suite. Collect the
        # preceding destroyed fixture on Tk's owning thread, not opportunistically
        # inside a later encoder worker. This fixture cleanup supplements the
        # application-owned collection policy; it skips no tests and does not
        # extend the export deadline.
        gc.collect()
        super().startTest(test)


def main(directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True);clock=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='neospector-r5-source-test-') as profile:
        os.environ['OMNE_SEQUENCER_SANDBOX']=profile
        suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
        with (out/'tests.log').open('w') as log:result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=NativeFixtureResult).run(suite)
    display_only=bool(result.errors) and all('no display name and no $DISPLAY' in detail for _,detail in result.errors)
    status='FAIL' if result.failures or (result.errors and not display_only) else 'BLOCKED_NATIVE_DISPLAY' if display_only else 'PARTIAL_SKIPS' if result.skipped else 'PASS'
    summary={'command':'python verify_source.py '+str(directory),'profile':'isolated temporary OMNE_SEQUENCER_SANDBOX','run':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'elapsed_seconds':time.monotonic()-clock,'error_ids':[t.id() for t,_ in result.errors],'all_errors_missing_display':display_only,'status':status}
    (out/'test-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
    import tkinter,PIL,numpy
    environment={'platform':platform.platform(),'python':sys.version,'tk':tkinter.TkVersion,'Pillow':PIL.__version__,'NumPy':numpy.__version__,'ffmpeg':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0]}
    (out/'environment.json').write_text(json.dumps(environment,indent=2));return 0 if status=='PASS' else 2 if status.startswith(('BLOCKED','PARTIAL')) else 1
if __name__=='__main__':raise SystemExit(main(sys.argv[1] if len(sys.argv)>1 else ROOT/'verification-runs'/'source'))
