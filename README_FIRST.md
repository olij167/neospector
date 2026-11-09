# Neospector UX41 · Reaction controls and automatic A/B mixing

**0.7.25-ux41** · 9 November 2026 · Linux Xorg evaluation candidate.

## Install

```bash
bash INSTALL_LINUX.sh
bash RUN_POC.sh
```

`python3 install_linux.py --check` verifies all packaged files without modifying profiles. Installer backs up existing profile metadata before creating a private runtime. UX40 remains a fallback.

## Changes

- Per-parameter audio reaction depth is **signed percentage of native parameter range**: `0%` means no modulation; `+100%` rises towards the maximum; `−100%` falls towards the minimum. Actual motion depends on audio level, attack/release, parameter bounds and clamping. Changes commit on slider release without a periodic refresh snapping the thumb back.
- The module bottom bar has **React All**, **Source** (Mix / Song / Mic) and **Band** (Full / Bass / Mid / High / Hits). Source and Band apply to all exposed parameters in one undoable transaction; existing individual amounts and keyframes are preserved. Editing a source or band alone does not start capture.
- The A/B header has **Auto Ping-pong**. When enabled it shows **Hold each (s)** and **Fade (s)** fields. Timing is stored with the project. The authored Transition rack still controls transition visual character. Auto overrides manual/audio A/B mix while active; turn Auto off to resume manual mix. Audio React ON disables Auto.

## Verification and constraints

Use `xvfb-run -a python3 tools/verify_ux41.py` (36 selected tests) and `xvfb-run -a python3 tools/ux41_layout_check.py`. The historical UX40 85-test runner exceeded the bounded execution limit and is not counted as passed. See UX41_IMPLEMENTATION.md and OWNER_TEST_CARD_UX41.md.

No owner publisher changes, feed deployment or signing-key distribution. Real GPU, Spotify, microphone, recording/export, and pointer-to-preview response still require owner testing.
