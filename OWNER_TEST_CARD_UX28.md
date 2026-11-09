# UX28 Owner acceptance — Zorin OS Xorg

Perform on your normal screen size and once in a smaller window. No need to run full historical suites.

1. Upper-right should show **CAM A / QUEUE A**, **CAM B / QUEUE B**, **MIC / AUDIO** in three tidy columns. No queue toggles at bottom.
2. Open one, two, then all three queues: all are bottom-right, don't cover the Sources & Media panel, and don't stretch past the preview top. Collapsed panels do not leave a blank tail.
3. A/B expanded headers contain **CAM**; Audio contains **MIC**. Toggle in a header and verify the same active state at top; toggle again to return/advance correctly. Test a camera already queued as well as a persistent camera.
4. Preview toolbar: **Record, Output, Focus** left; **Transition and React** right. Resize window to roughly 1024px wide, with Media & Sources open: controls should wrap rather than disappear or overlap.
5. Add images/videos to A/B, audio tracks to Audio, expand short and long lists, use next, take, reorder, remove-current, repeat and stop. Playback must remain intact during queue disclosure and tab changes.
6. Confirm source-browser import appears immediately, Effects and Media & Sources are mutually exclusive, and an Add action highlights the destination in the browser.
7. Check live hardware camera/microphone, device/system capture, recording, and a short export on the target workstation. The automated gate does not establish these.

If anything fails, supply a screenshot and `.run-logs/` from the UX28 folder. Note window dimensions, which queues were open/expanded, which media panel was open, and actual source type.
