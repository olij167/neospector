# UX37 verification — 8 November 2026

Working tree, isolated Xvfb display:

- `tools/verify_ux37.py`: **127 tests, 127 passed, 0 failures/errors/skips**; duration ~65.9 s. Includes 8 UX37 cases and 119 retained selected cases.
- UX37 dedicated tests: **8 passed**. The red run before implementation failed on mismatched theme controls and the extra Sequence Settings popup, verifying coverage.
- Visual checks: `evidence/ux37/output.png` and `evidence/ux37/appearance.png` show Welcome alongside Output and Appearance Preferences. Footer positioning was corrected after visual review and retested at 540 px height.

Fresh package checks and smoke results are recorded separately at release packaging time. Tests use a virtual X server; real hardware and export acceptance have not been claimed.
