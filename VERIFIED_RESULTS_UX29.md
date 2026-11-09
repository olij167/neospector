# UX29 verification record

Source: delivered UX28 archive, preserving `application/vnd.*` project semantics and version 1.3.0.

- Selected UX29 plus retained compatibility tests: **49/49 passed**, **0 errors**, **0 failures**, **0 skipped** in a headless X11 test display.
- Eight historical layout-specific assertions are excluded by explicit full test IDs in `.verification-runs/ux29/acceptance.json`; they are not counted as passing tests.
- Files/Sources navigation, in-row source actions, contextual destination eligibility, delayed mutation and Audio Queue/Mixer expansion are covered.
- Linux packaging integrity, independent extraction and re-run are checked separately during release creation.
- Pending: owner's real cameras, microphones, sound input streams, actual applications, recordings and media exports.
