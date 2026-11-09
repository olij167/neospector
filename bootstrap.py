#!/usr/bin/env python3
"""Isolated source runner. No source, existing project, or system install is changed."""
from __future__ import annotations
import datetime,os,platform,shutil,subprocess,sys,venv
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'app_source'))
from release_identity import VERSION,RELEASE

def run() -> int:
    if sys.version_info<(3,10):
        print('SAFE STOP: Python 3.10 or later is required.');return 2
    try:import tkinter
    except ImportError:
        print('SAFE STOP: this Python does not include Tk. On Zorin/Ubuntu: sudo apt install python3-tk python3-venv');return 2
    missing=[x for x in ('ffmpeg','ffprobe') if shutil.which(x) is None]
    if missing:
        print('SAFE STOP: install '+', '.join(missing)+' and put them on PATH. On Zorin/Ubuntu: sudo apt install ffmpeg');return 2
    if shutil.which('ffplay') is None:print('NOTE: ffplay is missing. Song monitoring is silent; the assigned song is still included in export.')
    probe='import tkinter,PIL,numpy,re; from PIL import Image,ImageTk; pv=tuple(map(int,re.findall(r"[0-9]+",PIL.__version__)[:2])); nv=tuple(map(int,re.findall(r"[0-9]+",numpy.__version__)[:2])); assert (10,4)<=pv<(13,0) and (1,26)<=nv<(3,0), "Dependency versions outside the supported range"; print("Pillow",PIL.__version__,"NumPy",numpy.__version__)'
    if '--check' in sys.argv:
        return subprocess.call([sys.executable,'-c',probe])
    environment=ROOT/'.runtime-neospector-omne-r5'
    python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    # A private runtime is generated locally and must never be shipped. If a stale,
    # incomplete or non-executable copy exists, repair only this installation's runtime.
    runtime_invalid = environment.exists() and (not python.is_file() or (os.name!='nt' and not os.access(python,os.X_OK)))
    if runtime_invalid:
        print('Repairing the private Python environment for this Neospector copy…',flush=True)
        try:shutil.rmtree(environment)
        except Exception as exc:print('SAFE STOP: private environment repair failed:',exc);return 2
    if not python.is_file():
        print(f'Creating a private Python environment for Neospector {VERSION}…',flush=True)
        try:venv.create(environment,with_pip=True,system_site_packages=False)
        except Exception as exc:print('SAFE STOP: environment creation failed:',exc);return 2
    if subprocess.call([str(python),'-c',probe],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL):
        if sys.platform.startswith('linux') and platform.machine()=='x86_64' and sys.version_info[:2]==(3,12):
            import hashlib
            runtime_wheels=(('pillow-12.3.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl','78cb2c6865a35ab8ff8b75fd122f6033b92a62c82801110e48ddd6c936a45d91'),
                            ('numpy-2.3.5-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl','0d8163f43acde9a73c2a33605353a4f1bc4798745a8b1d73183b28e5b435ae28'))
            for name,expected in runtime_wheels:
                wheel=ROOT/'vendor/wheels'/name
                if not wheel.is_file() or hashlib.sha256(wheel.read_bytes()).hexdigest()!=expected:
                    print('SAFE STOP: bundled runtime dependency checksum mismatch: '+name);return 2
            print('Installing verified Pillow and NumPy from this archive…',flush=True)
            result=subprocess.call([str(python),'-m','pip','install','--disable-pip-version-check','--no-index','--no-deps',*[str(ROOT/'vendor/wheels'/name) for name,_ in runtime_wheels]])
        else:
            print('Installing Pillow and NumPy in the private environment. First setup needs internet access for this Python version.',flush=True)
            result=subprocess.call([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(ROOT/'requirements.txt')])
        if result:print('SAFE STOP: dependency installation failed; no projects were changed.');return result
    if sys.platform.startswith('linux') and platform.machine()=='x86_64':
        # The pinned Python wrapper is included in the source release; the
        # checked native library is loaded separately from app_source/native.
        import hashlib
        wheels=(('six-1.17.0-py2.py3-none-any.whl','4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274'),
                ('python_xlib-0.33-py2.py3-none-any.whl','c3534038d42e0df2f1392a1b30a15a4ff5fdc2b86cfa94f072bf11b10a164398'),
                ('tkinterdnd2-0.4.4.1-py3-none-any.whl','d1af61a544a2ec6bdec26baa04c0853c97be044fd89816c0879367887419f713'))
        for name,expected in wheels:
            wheel=ROOT/'vendor/wheels'/name
            if not wheel.is_file() or hashlib.sha256(wheel.read_bytes()).hexdigest()!=expected:
                print('SAFE STOP: bundled Linux input dependency checksum mismatch: '+name);return 2
        check='import importlib.metadata as m; assert m.version("tkinterdnd2")=="0.4.4.1" and m.version("python-xlib")=="0.33" and m.version("six")=="1.17.0"'
        if subprocess.call([str(python),'-c',check],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL):
            print('Installing pinned Linux input wrappers from this source archive…',flush=True)
            if subprocess.call([str(python),'-m','pip','install','--disable-pip-version-check','--no-index','--no-deps',*[str(ROOT/'vendor/wheels'/name) for name,_ in wheels]]):
                print('SAFE STOP: bundled Linux input wrappers could not be installed.');return 2
    else:
        marker=environment/'.drop-setup-attempted'
        if not marker.exists():
            if subprocess.call([str(python),'-c','import tkinterdnd2'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL):
                print('Enabling native file drop (optional; folder import always works)…',flush=True)
                try:subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','--retries','0','--timeout','10','-r',str(ROOT/'requirements-drop.txt')],timeout=60,check=False)
                except subprocess.TimeoutExpired:print('File-drop setup timed out. The application will still start.')
            marker.touch()
    if '--verify' in sys.argv:
        return subprocess.call([str(python),str(ROOT/'tools/verify_ux34.py')],cwd=str(ROOT))
    if '--verify-native-legacy' in sys.argv:
        return subprocess.call([str(python),str(ROOT/'verify_native.py')],cwd=str(ROOT))
    logs=ROOT/'.run-logs';logs.mkdir(exist_ok=True)
    log=logs/('neospector-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
    print(f'Neospector · {RELEASE} · {VERSION}\nLauncher log: {log}',flush=True)
    command=[str(python),str(ROOT/'app_source/neospector.py'),*sys.argv[1:]]
    process=subprocess.Popen(command,cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
    try:
        with log.open('w',encoding='utf-8') as output:
            output.write('Command: '+repr(command)+'\n');output.flush()
            for line in process.stdout:
                output.write(line);output.flush();print(line,end='',flush=True)
        result=process.wait()
        if result:print('Application exited with status',result,'— diagnostics retained in',log)
        return result
    except KeyboardInterrupt:
        process.terminate()
        try:return process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait();return 130
    finally:
        if process.stdout:process.stdout.close()

if __name__=='__main__':raise SystemExit(run())
