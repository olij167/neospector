# Neospector UX36 — Owner evaluation on Zorin OS

1. Open Welcome from File; confirm OmN-e / Neospector / by Pungent Funk, New/Open/Import, recent projects, default devices/media, theme, Check Updates, one Support button. First Light and Learn in Place must be absent.
2. With webcam and microphone connected, confirm both Welcome and Preferences → Devices & Media show detected devices. Select them without turning capture on, reopen Preferences to verify the saved choices. Use Refresh devices after attaching hardware.
3. Type a default media-folder path and use Browse; toggle automatic import (off by default), create a new empty project and verify only direct supported files are imported. Test an empty path with auto-import off.
4. File → Theme Studio and File → Appearance must open the SAME Preferences → Appearance page; no extra window. Edit a colour, Apply, close/reopen, save a custom copy, import and export; ensure built-in palettes remain unchanged.
5. Cycle through Pungent Funk, Space Funk, Smitzu Funk, LindZ Funk, Beth Funk, and Mik Funk and verify no unexpected inherited accent/background colours. Check a light and a dark preset.
6. Close Appearance after previewing a different palette *without* Apply: previous chosen palette should return.
7. General contains Check Updates and Support; no separate Updates tab. File menu still retains separate Output Settings and Recording Settings entry points.
8. Repeat previously accepted camera/mic, A/B queues, Transition rack, recording/export tests. Physical capture and performance acceptance are **not** provided by automated Xvfb checks.

Note: your UX35 log mentions Mesa GBM permission and Chromium NSS/GPU warnings; these are not Neospector Python tracebacks and are not addressed by this UI-focused pass. If repeatable capture or export failure accompanies them, capture full diagnostics and isolate separately.
