#!/usr/bin/env python3
"""UX20 independent Tk process gate: verify retained behaviours and new right-rail UI.

Separate Tk processes per historical release avoid leaking Tk native event handles
across 100+ UI tests. Retired expectations are listed by exact test id.
"""
from __future__ import annotations
import json,os,subprocess,sys,time,unittest
from pathlib import Path
from verify_ux19 import PATTERNS as PRIOR_PATTERNS, SUPERSEDED as UX19_SUPERSEDED
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.verification-runs'/'ux20'
PATTERNS=('test_ux20_consolidation.py','test_ux19_hierarchy.py')+tuple(p for p in PRIOR_PATTERNS if p!='test_ux19_hierarchy.py')
SUPERSEDED=set(UX19_SUPERSEDED)
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
    with tempfile.TemporaryDirectory(prefix='neospector-ux20-'+pattern.replace('.py','')+'-') as sandbox:
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
    missing=SUPERSEDED-discovered
    if missing:
        print('BLOCKED: retired expectations are not found:',sorted(missing));return 2
    batches=[];errors=[];start=time.monotonic()
    for pat in PATTERNS:
        try:
            cp=subprocess.run([sys.executable,__file__,'--batch',pat],cwd=str(ROOT),
                              capture_output=True,text=True,timeout=75)
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
    report={'product':'Neospector','version':'0.7.4-ux20',
            'status':'PASS' if not errors else 'FAIL','counts':totals,'failures':errors,
            'retired_prior_ui_assertions':sorted(SUPERSEDED),'batches':batches,
            'elapsed_seconds':round(time.monotonic()-start,2),
            'limitations':['Owner-device camera/mic/audio routing and recording/export not yet verified',
                           'The dock can scroll when many modules exceed the available screen height',
                           'Named modulation lanes and codec-level datamoshing remain unimplemented']}
    (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('UX20 GATE',json.dumps({k:v for k,v in report.items() if k not in ('batches','retired_prior_ui_assertions')},indent=2))
    return 0 if not errors else 1
if __name__=='__main__':raise SystemExit(main())
