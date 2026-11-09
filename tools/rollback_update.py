#!/usr/bin/env python3
"""Restore the previous managed Neospector version without deleting any release."""
import argparse,json,sys
from pathlib import Path
from update_installer import atomic_json,managed_root

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--yes',action='store_true');args=p.parse_args()
    root=managed_root();pointer=root/'current.json'
    if not pointer.exists():print('No managed update is installed');return 2
    try:
        state=json.loads(pointer.read_text());previous=state.get('previous')
        if not previous or '/' in previous or '..' in previous:raise ValueError('No previous version recorded')
        if not (root/'versions'/previous/'RUN_POC.sh').is_file():raise ValueError('Previous version unavailable')
        if not args.yes:
            print('Would restore Neospector',previous,'; pass --yes to confirm.');return 0
        atomic_json(pointer,{'version':previous,'previous':state['version'],'rollback_from':state['version']})
        print('Previous version restored. Start with:',root/'launch.sh');return 0
    except (OSError,ValueError,KeyError) as e:print('SAFE STOP:',str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
