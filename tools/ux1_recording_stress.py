#!/usr/bin/env python3
"""Bounded UX1 recording-integrity stress harness.

Uses the production OutputRecorder repeatedly with deterministic generated frames.
It verifies single-media publication, private integrity-cache retention and thread-count growth.
This is a checkpoint gate; long physical-device/30-minute soak remains owner-side.
"""
from __future__ import annotations
import argparse, json, os, sys, tempfile, threading, time
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app_source'))
from instrument_model import new_instrument
from performance_capture import OutputRecorder


def run(cycles:int=10):
    before=len(threading.enumerate());errors=[];complete=0
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='neospector-ux1-stress-') as td:
        root=Path(td)
        for i in range(cycles):
            try:
                p=new_instrument();p.width=64;p.height=48;p.duration=.35
                rec=OutputRecorder(root/f'work-{i}',0,(64,48),fps=8)
                rec.submit(0,Image.new('RGB',(64,48),(20+i,30,50)))
                rec.submit(.25,Image.new('RGB',(64,48),(60,30+i,90)))
                out=root/f'cycle-{i}.mp4'
                rec.finish(p,.35,out,integrity={'schema':'neospector/recording-integrity-v1','stress_cycle':i})
                private=root/f'work-{i}'/'recording.json'
                if out.is_file() and private.is_file() and not out.with_name(out.name+'.neospector.json').exists():complete+=1
                else:errors.append(f'cycle {i}: incomplete media/private-integrity result')
            except Exception as exc:errors.append(f'cycle {i}: {type(exc).__name__}: {exc}')
        time.sleep(.15)
        after=len(threading.enumerate())
    result={'cycles':cycles,'complete_media':complete,'callback_errors':errors,'elapsed_seconds':round(time.monotonic()-started,3),'threads_before':before,'threads_after':after,'status':'PASS' if complete==cycles and not errors and after<=before else 'FAIL'}
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cycles',type=int,default=10);ap.add_argument('--output',type=Path)
    a=ap.parse_args();result=run(max(1,a.cycles));text=json.dumps(result,indent=2,sort_keys=True)
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text+'\n')
    print(text);return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
