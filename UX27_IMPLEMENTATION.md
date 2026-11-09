# UX27 implementation — queue layout conservation

**Baseline:** `Neospector_UX26_Consolidated_20261106.zip` (see SOURCE_IDENTITY.json).

## Root causes from UX26

- `ux26_queue_layout.py` reserved 163px for a collapsed visual queue although
  Tk's actual header + current card + progress requested ~109px. This made
  empty space beneath each collapsed queue inevitable.
- Audio lived in `programme` as an extra packed row beneath `visual_mix`.
  That created an arbitrary layout relationship between audio and reactions,
  even though the queue is an independent audio transport.
- Audio used an extra full-width `UP NEXT` row rather than the inline queue
  header disclosure already used by A/B, and the current transport's input
  meter competed with essential queue controls in a narrower column.

## Changes

- `ux26_queue_layout.py`: measured compact constants (`VISUAL_CLOSED=114`,
  `VISUAL_OPEN_BASE=130`, `AUDIO_CLOSED=105`, `AUDIO_OPEN_BASE=120`); role-aware
  constrained-space minimums; same 42px list-row increment for A/B/Music.
- `ux17_sidebar.py`: independently anchored music stage card, persistent
  bottom-left toggle; A/B continue shared right stack; disclosure/row-count
  change signatures include Music; removed extra inter-card trailing gutter.
- `instrument_shell.py`: music anchor follows preview left edge after optional
  workbench; content-limited height; constant bottom rail; no mixer reflow.
- `omne_workspace.py` and `instrument_mix.py`: queue is no longer packed below
  React, MIC remains next to React, audio control lives at the left dock; visual
  dock labels explicitly identify QUEUE A/B.
- `instrument_media.py`: music header has the same Add/Count/Disclosure grammar;
  concise transport, no duplicate input meter; cleaner empty-state message.

### State boundary

Only view geometry, disclosure controls, labels and widget ownership change.
`music_queue`, `queue_model`, `ux26_queue_actions`, `audio_bus`, DSP, live source
routing, capture, effects and export retain their UX26 semantics and are
protected by regression tests. There is no project format migration.
