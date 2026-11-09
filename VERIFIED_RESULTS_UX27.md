# UX27 automated verification

- Date: 2026-11-08
- Version: `0.7.11-ux27`
- Command: `python3 tools/verify_ux27.py` (auto-uses Xvfb if no display)
- Result: **39 passed, 0 failed, 0 errors, 0 skipped**
- Includes 8 new UX27 height/dock tests, retained UX26 layout/action/integration,
  R5 queue/PCM/history checks and UX25 camera/media refresh tests.
- A historical R5 test for a removed full sidebar remains explicitly excluded
  by exact identity, as in UX26; no new tests were skipped.

`python3 install_linux.py --check` verifies all files against the packaged
MANIFEST.sha256. Hardware acceptance remains pending for camera, mic, system
capture and export on the owner's machine.
