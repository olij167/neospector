# UX39 Verification — 8 November 2026

## Source acceptance (isolated Xvfb desktop)
- Targeted UX39/UI/AV/Updater gate: **75 / 75 passed** (`tools/verify_ux39.py`).
- Covered queue commands, media placement, rack controls and gestures, authored transitions and recipe imports, stable panel updates, Preferences, signed update checks, and six new UX39 performance cases.
- Eight superseded historical assertions are explicitly excluded by the inherited UX38 exemption list (old layout or deprecated Creative Controls and Welcome paths). They are not counted as passes.

## Performance evidence
- Controlled virtual-display, 300 program-gesture writes over three runs on the same host: UX38 total ~305.8ms, median 0.813ms, p95 1.220ms; UX39 total ~0.2ms for the parameter-write calls. This metric excludes scheduled preview and final commit operations and must **not** be confused with measured end-to-end input latency or frame rate.
- UX39 sends at most ~30 program change notifications per second during sustained dragging, while changing the parameter model immediately, without per-motion queue or sound reconfiguration. These performance contracts are asserted in `tests/test_ux39_performance.py`.

## Launch smoke
- `tools/smoke_ux39.py` launched the actual application entry under Xvfb, loaded the example, checked current Welcome and update controls, presented preview frames, confirmed no phase errors, and closed cleanly. **PASS**.

## User acceptance still required
- Real mouse and keyboard input latency on the user's Zorin/Xorg NVIDIA setup; heavy 8+ module rack and group interactions; live camera, microphone and application sound; real recording/export; playback continuity during simultaneous parameter dragging; full owner-update publication end to end. None are claimed verified by virtual-display tests.

## Security and distribution
- This public release contains **no owner private signing key**. The UX38 Ed25519 verifier and local rollback paths are preserved. No remote update feed has been deployed by these checks.
