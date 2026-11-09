# UX32 verified results · 2026-11-08

## Evidence

- Selected legacy + UX32 acceptance: **80 tests, 80 passed, 0 failures, 0 errors, 0 skips**. Executed `python tools/verify_ux32.py` under isolated Xvfb and a temporary user profile, after the responsive-toolbar correction.
- The UX32 additions test rack separation, transition-only reveal, image effect processing in the interior of a crossfade, nested group persistence, exclusion of temporal effects, independent FX bypass, module library filtering, inline mutation, width/visibility of the active controls, Audio `+` navigation, and popup desktop positioning.
- Explicitly retired three UX31 UI assertions that open the removed Creative Controls popup, plus historical UI assertions already retired in the UX31 gate. All exclusions are named and explained in `tools/verify_ux32.py`; none are counted as passes.
- `python -m py_compile` succeeded for the affected Python source and tools.
- `xvfb-run ... python tools/ux32_smoke_entry.py <release-root> <report>`: **PASS**. Actual `app_source/neospector.py` entry rendered **50 frames**, produced **0 phase errors**, and closed cleanly with no reported callback exceptions. This test is a simulated desktop without connected owner hardware.
- Package contents are independently hashed by `MANIFEST.sha256` and re-verified after fresh ZIP extraction; external `.zip.sha256` verifies the archive itself.

## Limitations

The tests do not establish perceptual transition quality with live media, real Spotify/PipeWire stream recording, microphone/camera device operation, or final A/V file export on the owner's Zorin workstation. These require completion of `OWNER_TEST_CARD_UX32.md` before an unconditional final release claim. Existing installations are left in place; UX31 remains a fallback.
