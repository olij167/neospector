# UX33 verification · 8 November 2026

## Selected acceptance gate (virtual X display)

Command: `xvfb-run -a -s '-screen 0 1800x1000x24' python tools/verify_ux33.py`.

**92 tests passed; 0 failed, 0 errors, 0 skipped.** New UX33 tests verify:
- six registered transition operators, 0/1 identity, and different mid-animation output;
- authored transition animation independent from the retained legacy style;
- timing progress editor, randomisation including a real animation operation;
- factory animation groups, nested macro compilation and project save/load;
- safe declarative import with finite value bounds and no code execution;
- actual Tk family filtering, importing and inserting a saved custom group;
- removal of preset transition arrows and the fourth rack's entry point.

The gate also retains applicable UX25–UX32 tests covering queue lifecycle, stop/repeat,
locked and grouped racks, source/camera handoff, audio desk and module editing.
**15 historical UI assertions are excluded by exact test identifier** because they
encode obsolete interface structure; the gate documents them and requires
replacement UX33 checks. They are not counted as passes.

## Application entry smoke

Command: `xvfb-run -a -s '-screen 0 1800x1000x24' python tools/smoke_ux33.py <extracted-root> <report.json>`.

Working-tree result: **PASS**. The unchanged `app_source/neospector.py` entry
rendered **56 preview frames**, reported no phase errors or callback errors, and
closed cleanly. Record, Output, crossfade, CAM A/B, MIC and transition-editor
controls were visible. Preset arrows remained hidden. This uses a bundled
example, not a physical camera/microphone or Spotify stream.

An older `tools/smoke_entry.py` harness fails UX33's *layout assertions* because it
expects unmounted legacy controls and an old initial panel arrangement. The
current harness tests the actual UX33 control surfaces.

## Package and unresolved owner checks

The ZIP's own SHA-256 and fresh extraction manifest must be checked after packaging;
external checksum is optional. Owner verification still required on Zorin Xorg:
actual live camera/mic and app audio, transition perceptual quality at playback
speed, save/reload in an existing collection, recording, exports and source relinking.
No live capture or full end-to-end export certification is claimed.
