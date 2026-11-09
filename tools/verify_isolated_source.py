#!/usr/bin/env python3
"""Run complete unittest discovery with one interpreter per test module.

Tk roots and multimedia workers are isolated between modules. Discovery IDs are
reconciled against the observed verbose results; a process crash, timeout,
missing ID or unexpected skip prevents a PASS result.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINE = re.compile(r"^(\S+) \(([^)]+)\) \.\.\. (ok|FAIL|ERROR|skipped .+|expected failure|unexpected success)$")


def walk(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from walk(item)
        else:
            yield item


def main(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    discovered = list(walk(unittest.defaultTestLoader.discover(str(ROOT / 'tests'))))
    expected = defaultdict(set)
    for test in discovered:
        module = test.__class__.__module__
        expected[module].add(test.id())
    if len(discovered) != sum(map(len, expected.values())):
        raise RuntimeError('Duplicate discovered test IDs')
    summary = {'command': 'python3 tools/verify_isolated_source.py ' + str(output),
               'discovered': len(discovered), 'modules': len(expected),
               'status': 'IN_PROGRESS', 'module_results': [], 'missing_ids': [],
               'extra_ids': [], 'skipped_ids': [], 'failed_ids': [], 'error_ids': []}
    start = time.monotonic()
    env = dict(os.environ)
    env.setdefault('SDL_AUDIODRIVER', 'dummy')
    env['PYTHONPATH'] = str(ROOT / 'app_source') + os.pathsep + env.get('PYTHONPATH', '')
    for module in sorted(expected):
        if not (ROOT / 'tests' / (module + '.py')).is_file():
            raise RuntimeError('Cannot isolate discovered module ' + module)
        log = output / (module + '.log')
        command = [sys.executable, str(Path(__file__).resolve()), '--module', module, str(log)]
        begun = time.monotonic()
        module_env=dict(env,OMNE_SEQUENCER_SANDBOX=str(output/'profiles'/module))
        with (output/(module+'.diagnostics.log')).open('w') as stream:
            try:
                process = subprocess.run(command, cwd=ROOT, env=module_env, stdout=stream,
                                         stderr=subprocess.STDOUT, timeout=240, check=False)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = 'TIMEOUT'
        observed = {}
        for line in log.read_text(errors='replace').splitlines():
            match = LINE.fullmatch(line)
            if match:
                observed[match[2]] = match[3]
        missing = sorted(expected[module] - observed.keys())
        extra = sorted(observed.keys() - expected[module])
        summary['missing_ids'].extend(missing)
        summary['extra_ids'].extend(extra)
        summary['skipped_ids'].extend(k for k, v in observed.items() if v.startswith('skipped'))
        summary['failed_ids'].extend(k for k, v in observed.items() if v in ('FAIL', 'unexpected success'))
        summary['error_ids'].extend(k for k, v in observed.items() if v == 'ERROR')
        result = {'module': module, 'expected': len(expected[module]), 'observed': len(observed),
                  'exit_code': code, 'elapsed_seconds': round(time.monotonic() - begun, 2),
                  'missing_ids': missing, 'extra_ids': extra, 'log': log.name}
        summary['module_results'].append(result)
        summary['completed_modules'] = len(summary['module_results'])
        summary['observed_total'] = sum(item['observed'] for item in summary['module_results'])
        (output / 'test-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(f"{module}: {len(observed)}/{len(expected[module])} exit={code}", flush=True)
    summary['elapsed_seconds'] = round(time.monotonic() - start, 2)
    summary['passed'] = summary['observed_total'] - len(summary['skipped_ids']) - len(summary['failed_ids']) - len(summary['error_ids'])
    clean = (not (summary['missing_ids'] or summary['extra_ids'] or summary['skipped_ids']
                  or summary['failed_ids'] or summary['error_ids'])
             and all(item['exit_code'] == 0 for item in summary['module_results'])
             and summary['observed_total'] == len(discovered))
    summary['status'] = 'PASS' if clean else 'FAIL'
    (output / 'test-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({key: summary[key] for key in ('status', 'discovered', 'observed_total',
          'passed', 'modules', 'elapsed_seconds', 'missing_ids', 'extra_ids',
          'skipped_ids', 'failed_ids', 'error_ids')}, indent=2), flush=True)
    return 0 if clean else 1


def reconcile(output):
    """Reconcile an already finished run without rerunning the test processes."""
    output = Path(output).resolve()
    summary_path = output / 'test-summary.json'
    summary = json.loads(summary_path.read_text())
    discovered = list(walk(unittest.defaultTestLoader.discover(str(ROOT / 'tests'))))
    expected = defaultdict(set)
    for test in discovered:
        expected[test.__class__.__module__].add(test.id())
    summary.update(missing_ids=[], extra_ids=[], skipped_ids=[], failed_ids=[], error_ids=[])
    for result in summary['module_results']:
        module = result['module']
        observed = {}
        for line in (output / result['log']).read_text(errors='replace').splitlines():
            match = LINE.fullmatch(line)
            if match:
                observed[match[2]] = match[3]
        result['observed'] = len(observed)
        result['missing_ids'] = sorted(expected[module] - observed.keys())
        result['extra_ids'] = sorted(observed.keys() - expected[module])
        summary['missing_ids'].extend(result['missing_ids'])
        summary['extra_ids'].extend(result['extra_ids'])
        summary['skipped_ids'].extend(k for k, v in observed.items() if v.startswith('skipped'))
        summary['failed_ids'].extend(k for k, v in observed.items() if v in ('FAIL', 'unexpected success'))
        summary['error_ids'].extend(k for k, v in observed.items() if v == 'ERROR')
    summary['observed_total'] = sum(result['observed'] for result in summary['module_results'])
    summary['passed'] = summary['observed_total'] - sum(len(summary[k]) for k in ('skipped_ids', 'failed_ids', 'error_ids'))
    complete = set(expected) == {result['module'] for result in summary['module_results']}
    clean = (complete and not any(summary[k] for k in ('missing_ids', 'extra_ids', 'skipped_ids', 'failed_ids', 'error_ids'))
             and summary['observed_total'] == len(discovered)
             and all(result['exit_code'] == 0 for result in summary['module_results']))
    summary['status'] = 'PASS' if clean else 'FAIL'
    summary_path.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({key: summary[key] for key in ('status', 'discovered', 'observed_total', 'passed',
          'modules', 'completed_modules', 'missing_ids', 'extra_ids', 'skipped_ids', 'failed_ids', 'error_ids')}, indent=2))
    return 0 if clean else 1


def run_module(module, log):
    # Keep test results on their own explicit stream, separate from native UI
    # diagnostics, so every discovered result remains independently observable.
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=module+'.py')
    with Path(log).open('w',buffering=1) as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    if len(sys.argv)>3 and sys.argv[1]=='--module':
        raise SystemExit(run_module(sys.argv[2],sys.argv[3]))
    if len(sys.argv) > 2 and sys.argv[1] == '--reconcile':
        raise SystemExit(reconcile(sys.argv[2]))
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'verification-runs' / 'isolated'))
