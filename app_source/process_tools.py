"""Bounded, cancellable child processes; workers never invoke a shell."""
from __future__ import annotations
import os
import subprocess
import threading
import time


class Cancelled(RuntimeError): pass


def popen_options():
    return {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' and hasattr(subprocess,'CREATE_NO_WINDOW') else {}


def stop_process(proc):
    if proc is None:return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=2)
    except (OSError,subprocess.SubprocessError):pass


def run_process(cmd,*,cancel=None,timeout=120,check=True,input=None):
    if cancel is not None and cancel.is_set():raise Cancelled('Operation cancelled')
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**popen_options())
    start=time.monotonic();first=True
    try:
        while True:
            try:
                out,err=proc.communicate(input=input if first else None,timeout=.1)
                break
            except subprocess.TimeoutExpired:
                first=False
                if cancel is not None and cancel.is_set():raise Cancelled('Operation cancelled')
                if time.monotonic()-start>timeout:raise TimeoutError(f'Process exceeded {timeout:g} seconds')
        if check and proc.returncode:
            failure=RuntimeError((err.decode('utf-8','replace') or 'Media process failed')[-12000:])
            failure.command=list(cmd);failure.stderr=err.decode('utf-8','replace');raise failure
        return subprocess.CompletedProcess(cmd,proc.returncode,out,err)
    finally:
        stop_process(proc)
        # communicate owns the pipes while active; cancellation still drains and closes.
        try:proc.communicate(timeout=1)
        except (OSError,ValueError,subprocess.SubprocessError):pass


class EncoderPipe:
    """Continuous stderr draining plus a watchdog that also unblocks stdin writes."""
    def __init__(self,command,log_path,*,cancel=None):
        self.command=list(command);self.cancel=cancel;self.done=threading.Event();self.error_tail=[]
        self.log=open(log_path,'wb')
        self.proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,bufsize=0,**popen_options())
        self.reader=threading.Thread(target=self._drain,daemon=True);self.reader.start()
        self.guard=threading.Thread(target=self._watch,daemon=True);self.guard.start()
    def _drain(self):
        try:
            while True:
                chunk=self.proc.stderr.read(4096)
                if not chunk:break
                self.log.write(chunk);self.log.flush();self.error_tail.append(chunk)
                if len(self.error_tail)>16:self.error_tail.pop(0)
        finally:
            try:self.proc.stderr.close()
            except OSError:pass
    def _watch(self):
        while not self.done.wait(.1):
            if self.cancel is not None and self.cancel.is_set():stop_process(self.proc);break
    def write(self,data):
        if self.cancel is not None and self.cancel.is_set():raise Cancelled('Export cancelled')
        try:
            view=memoryview(data)
            while view:
                count=self.proc.stdin.write(view)
                if not count:raise BrokenPipeError('Encoder closed its input')
                view=view[count:]
        except (OSError,ValueError) as exc:
            if self.cancel is not None and self.cancel.is_set():raise Cancelled('Export cancelled') from exc
            self.reader.join(timeout=.2)
            raise RuntimeError('Encoder failed: '+b''.join(self.error_tail).decode('utf-8','replace')[-6000:]) from exc
    def finish(self):
        try:
            if self.proc.stdin and not self.proc.stdin.closed:self.proc.stdin.close()
            deadline=time.monotonic()+120
            while self.proc.poll() is None:
                if self.cancel is not None and self.cancel.is_set():raise Cancelled('Export cancelled')
                if time.monotonic()>deadline:raise TimeoutError('Encoder finalisation timed out')
                time.sleep(.05)
            self.reader.join(timeout=3)
            if self.proc.returncode:raise RuntimeError(b''.join(self.error_tail).decode('utf-8','replace')[-10000:] or 'Encoder failed')
        finally:self.close()
    def close(self):
        self.done.set();stop_process(self.proc)
        try:
            if self.proc.stdin and not self.proc.stdin.closed:self.proc.stdin.close()
        except (OSError,ValueError):pass
        self.reader.join(timeout=3)
        if not self.log.closed:self.log.close()
