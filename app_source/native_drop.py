"""Load the pinned, repaired Linux XDND extension before any target registers."""
from __future__ import annotations
import hashlib,platform,sys
from pathlib import Path

LINUX_X64_HASH='1debfb466da2eff687fd74375fcbcb8fee314aef35e1810f72de46878cb609b3'

def require_native_drop(root):
    if not sys.platform.startswith('linux') or platform.machine()!='x86_64':
        from tkinterdnd2 import TkinterDnD
        return getattr(TkinterDnD,'require',getattr(TkinterDnD,'_require'))(root)
    folder=Path(__file__).resolve().parent/'native/linux-x64'
    binary=folder/'libtkdnd2.9.5.so'
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=LINUX_X64_HASH:
        raise RuntimeError('Native drop binary checksum mismatch. Use Files… and reinstall this source package.')
    if root.tk.call('package','provide','tkdnd'):
        loaded=str(root.tk.call('info','loaded'))
        if str(binary) not in loaded:
            raise RuntimeError('Another TkDnD binary was loaded first; file drop stays disabled for this launch.')
        return root.tk.call('package','provide','tkdnd')
    root.tk.call('lappend','auto_path',str(folder))
    version=root.tk.call('package','require','tkdnd','2.9.5')
    if version!='2.9.5' or str(binary) not in str(root.tk.call('info','loaded')):
        raise RuntimeError('The repaired TkDnD binary did not load; file drop stays disabled.')
    return version
