# UX28 verification record

- Version: `0.7.12-ux28`, date 2026-11-08
- Focused validation: `python3 tools/verify_ux28.py` (Tk/Xvfb)
- Result: **41 passed, 0 failed, 0 errors, 0 skipped in the selected gate** (including 8 UX28 tests).
- Seven older assertions explicitly superseded by UX28's layout/style are enumerated by exact ID in the gate runner, excluded and not counted as passing.
- Package integrity and independent extraction: see release-generation result; `python3 install_linux.py --check` checks the packaged per-file manifest.
- Physical camera/microphone, desktop capture and export: **unqualified**, pending Zorin owner acceptance.
