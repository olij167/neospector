# UX28 implementation and design decisions

## Purpose and principle

Minimise interpretive distance between live source and queue while maintaining the preview as the dominant field. **Live-source activation** and **queue visibility** are separate concepts and use different button treatments. The same control links local tray headers to the top-right channel pair; opening a queue never turns on its live device.

## Changes by surface

- **Top channels**: 3 aligned pairs, CAM A/QUEUE A, CAM B/QUEUE B, MIC/AUDIO, compact consistent row heights and active indicators.
- **Preview strip**: left action cluster Record/Output/Focus and right cluster Transition/React/Band. At <760px available **toolbar width** (not app width), the right cluster shifts to a second aligned row, preventing overflow when the left workbench is open.
- **Queue trays**: all three are peers in one bottom-right stack, with proportional content-based height, no internal sashes; preserved current-source and live playback controls. A/B and Audio headers share CAM/MIC + Add + disclosure grammar.
- **Surface language**: UX28 semantic ttk styles distinguish source/live toggles from queue toggles, destructive/record actions, insertion, and disclosure, with reduced padding where useful. Existing per-user themes still determine overall palette.

## Architectural boundaries

Presentation-only changes. No new media/queue engine, no change to `project.extra`, `VoiceMix`, playback clock, source identity, persistence or export. The existing command routing retains reversible queue mutations. Camera and mic local keys call the same live source commands as their top counterparts.

## Verification strategy

Tests added in `tests/test_ux28_hierarchy.py`: top pair alignment, right stack ownership, local/top toggle callbacks, left/right action ordering, narrow toolbar wrapping, concurrent three-queue expanded sizing, distinct controls, and stable toolbar height on open/close. Retained queue history/PCM/camera transitions and immediate media refresh in the UX28 gate. Seven earlier tests that specifically assert superseded layouts or styling are *explicitly* excluded and named in `tools/verify_ux28.py`. The old fixtures remain in source as historical context.

The run uses Tk/Xvfb for layout checks, which cannot prove actual camera, system audio or desktop recording on Zorin.

## UX evidence and outside references

Screenshots in `evidence/ux28` demonstrate simulated UI states only, not hardware performance. The design uses Nielsen Norman Group's visibility/consistency and recognition-rather-than-recall heuristics; WCAG's non-text contrast guidance informs active control boundaries; and Python `ttk.Style` semantics inform native control states. These are design reference points, **not evidence of measured usability improvements**.

- https://www.nngroup.com/articles/ten-usability-heuristics/
- https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
- https://docs.python.org/3/library/tkinter.ttk.html
