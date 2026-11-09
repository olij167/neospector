"""Collect cyclic Tk object graphs on the thread that owns their interpreter.

CPython may otherwise initiate automatic cyclic GC in an export/analysis worker.
Finalising a Tk Variable there attempts a cross-thread Tcl call while the native
owner is not running mainloop (notably repeated-window tests and shutdown).
Reference counting is unchanged. Cyclic collection runs at bounded UI intervals
and shutdown, and the caller's automatic-GC policy is restored after the last root.
"""
import gc,threading,weakref

_roots={}
_previous=None

def activate(root):
    global _previous
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Create the native interface on the main thread')
    if not _roots:
        _previous=gc.isenabled();gc.disable();gc.collect()
    ref=weakref.ref(root);_roots[id(root)]=ref
    def pulse():
        owner=ref()
        if owner is None or getattr(owner,'closing',False):return
        gc.collect()
        owner._collection_job=owner.after(5000,pulse)
    root._collection_job=root.after(5000,pulse)

def deactivate(root):
    global _previous
    token=getattr(root,'_collection_job',None)
    if token:
        try:root.after_cancel(token)
        except Exception:pass
    root._collection_job=None;_roots.pop(id(root),None)
    gc.collect()
    if not _roots:
        if _previous:gc.enable()
        _previous=None
