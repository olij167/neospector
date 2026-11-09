# UX34 owner acceptance · Zorin Linux Xorg

1. Confirm header reports **0.7.18-ux34**. Open both visual queues and Audio;
   toggle A/B/Audio repeatedly. Existing queue panels should remain stable,
   without blanking/reappearing or moving to a different dock.
2. Open Files, select several imported sources and scroll mid-list. Re-select
   Files, switch Sources and back; list should appear as a coherent whole,
   preserve selection/scroll when possible, and avoid incremental row loading.
3. Open Transition and other module racks with many single/group effects;
   switch A/B/Output/Transition, vary faders, resize and open Module Library.
   Cards must remain readable and responsive without partial reflow flicker.
4. Open **File → Welcome**. Try First Light, import media, open an existing
   project; verify cancelled discard prompts keep the current instrument.
5. Use **Learn in place** to open Media, Queues, and Effects. Check these are
   the real UI panels, not duplicate tutorials, and that no input/capture is
   automatically activated. Check the compact layout on a narrower window.
6. Confirm `Show at startup`, appearance/tips, recent projects, Escape,
   and returning to the instrument all work. Open the interactive guide.
7. Perform a live-camera/microphone/audio session, play transition groups,
   record and export. This must be tested physically; Xvfb does not certify
   capture, audio playback quality or production export.

Rollback: preserve UX33 until the owner approves this version.
