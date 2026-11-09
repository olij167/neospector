# UX30 verification record

- `python3 tools/verify_ux30.py`: selected source/UI + retained compatibility gate **60/60 passed, zero errors, zero skips** under Xvfb. Prior deliberate UI layout supersessions are listed individually in `.verification-runs/ux30/acceptance.json` (not represented as passes).
- `tools/ux30_smoke_entry.py`: unchanged native `app_source/neospector.py` boot and sample playback, 51 frames presented, no phase errors, orderly close under Xvfb. The older `tools/smoke_entry.py` expects deliberately retired hidden controls and is **not** a valid UX30 acceptance test.
- Package integrity: installer `MANIFEST.sha256` hashes each release file; external ZIP SHA-256 is available separately.
- **Not verified**: actual Spotify/per-app audio acquisition, physical mic, capture/output hardware, recording/export and Zorin performance under user load.
