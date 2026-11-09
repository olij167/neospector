# UX35 verification — 2026-11-08

- Baseline: delivered UX34 0.7.18-ux34.
- Development-tree selected UX34+UX35 regression: 107/107 PASS under isolated Xvfb, 48.586 s. Includes module bottom control fit, responsive Welcome, shared six-page Preferences, File-menu shortcuts, bounded auto-import and prior playback/queue/transition tests.
- Exact superseded legacy UI assertions are documented in acceptance JSON, not counted as passing.
- Package checksum, internal manifest, fresh-extraction acceptance and startup checks are reported separately when run; no physical Zorin device assertions are implied.
