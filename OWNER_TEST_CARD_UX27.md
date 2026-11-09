# Neospector UX27 — owner acceptance card

**Target:** Zorin OS, Linux Xorg, physical audio/camera inputs.

1. Open both A/B queues. In collapsed mode verify the header and currently
   playing item have no blank extension below; each should be about 114px tall.
2. Open `♫ AUDIO` at bottom-left; collapse and expand its upcoming list.
   Verify its header contains Add, Queue empty / upcoming count, and disclosure.
3. Expand A and B, add a small queue to one and a long queue to the other.
   Confirm the longer queue gets more room, both can scroll, and neither covers
   the transition toolbar or the fixed corner toggles.
4. Open Sources & Media or Effects in the left workbench. Confirm Audio moves
   with the preview's left edge and does not cover the workbench.
5. MIC remains beside React above preview, Camera A/B in upper right; toggling
   any queue does not grow the reaction strip.
6. Verify Music Play/Next/Stop/Repeat/Remove and visual queue equivalent
   controls with real files. Confirm stop disables repeat and removing the
   current item advances without damaging history.
7. Verify camera and mic input, playback, recording and a short export.
   Test the imported media list refresh without tab navigation.

Report any screenshot with the OS window size, A/B/Audio open/collapsed states,
number of upcoming items, and whether Sources or Effects was open.
