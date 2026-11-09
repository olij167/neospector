# UX40 verification results — 2026-11-09

- **Combined virtual-X-display acceptance:** 85/85 selected tests pass; 0 failures, 0 errors, 47.7s, including 10 new UX40 edit, reaction, and theme cases. Source: `.verification-runs/ux40/acceptance.json` (run output not bundled to avoid runtime clutter).
- **Retained UX39 gate:** 75/75 pass independently. Historical superseded UI assertions are listed in `tools/verify_ux40.py` and the acceptance report.
- **Static:** Python source and tools compile; module-card header/footer checked in live Tk geometry.
- **Launch and package:** See final fresh-extraction verification and smoke result; physical devices, audiovisual export, and owner hardware remain unqualified.
- **Bounded change:** UX39 performance coalescing and existing signed-update trust chain retained unchanged; no owner private key bundled.
