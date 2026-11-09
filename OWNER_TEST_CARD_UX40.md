# UX40 · Workstation acceptance card

Base: UX39, version 0.7.24-ux40. No owner publication changes.

1. Load several visual modules including Scanlines and a saved multi-parameter group. Rapidly drag each slider and release: the displayed number must stay at the release position; inspect preview response.
2. Type a number and press Return; type another and click outside. Both should persist through rack switches and save/reopen. For Scanlines Spacing, fractional typed numbers round to an integer.
3. Set a parameter to Keys (Animate); move playhead and edit. Confirm its displayed position follows the saved keyframe at that time, without changing the original base.
4. In an effect or group, press ∿ ALL in the bottom strip. All parameters should react, with per-parameter band, source and depth still editable. Press again to disable bulk reaction (pre-existing keyframes retained). Test Undo/Redo.
5. Check the × remove control is top-right, next to LOCK, and undo restores the module. Verify header and footer do not clip for compact and long group cards.
6. Cycle through Pungent, Space, Smitzu, LindZ, Beth, and Mik Funk. Top queue toggles, live input buttons, Preview, Sources, dropdowns, popup menus and faders should update palette immediately. In particular, open a dropdown *before* switching theme, then reopen after switching.
7. Run playback with media + microphone/video source and multiple modules. Drag many controls; confirm no delayed reset, preview interruptions, UI freezes, or recording/export regressions.

Automated unit and Xvfb checks cannot qualify physical capture, recording, export, or human-perceived responsiveness. UX39 is the fallback if workstation acceptance fails.
