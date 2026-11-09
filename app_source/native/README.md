# Linux TkDnD lifetime repair

The distributed Python wrapper is tkinterdnd2 0.4.4.1 (bundled wheel SHA-256
`d1af61a544a2ec6bdec26baa04c0853c97be044fd89816c0879367887419f713`).
Its upstream Linux x64 TkDnD 2.9.5 binary crashed with `BadWindow / X_GetProperty`
when the foreign source window vanished before XdndEnter. The compiled extension
under `linux-x64` is rebuilt from the matching upstream 2.9.5 tag
`6efca37a22b93b2336dc973f2b4a9ba1e3feceaf`, with the narrow repair in
`tkdnd-2.9.5/unix/TkDND_XDND.c`. Original copyright/license notices are preserved
in the source and `tkdnd-2.9.5/license.terms`.

`bash build_linux_drop.sh` needs CMake, GCC, Tcl/Tk and X11 development headers.
Ordinary users do **not** need these. The shipped installer uses the bundled
Python wheel and already built `.so`; `native_drop.py` checks its hash and confirms
that exact path loaded before registering a drop target. A failed check leaves
Files… import available and records why native drop is unavailable.

The repair synchronizes foreign X property reads under one display lock and an
error-handler lifetime, swallowing only the matching BadWindow for that exact
request and forwarding unrelated errors. It rejects malformed property responses
and a vanished source without changing project/import state. Linux Xorg/Xwayland
qualification remains distinct from Wayland portal and owner file-manager tests.
