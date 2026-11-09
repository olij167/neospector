# UX29 owner acceptance — Zorin OS Xorg

Use the normal display then try a narrower window with the left browser and right Audio mixer open. You do not need to run old full suites.

1. Open **Media & Sources**. It should contain **Files | Sources** within the browser. No A/B/Audio destinations or Now/Next/End actions at the bottom; Effects remains an alternative workbench page.
2. In **Files**, import image, audio, silent video and audio-bearing video. Each appears immediately. Click its row's ▶, ⏭ or ＋: a small destination menu must show A/B only for visuals, Audio only for audio, and all eligible choices for a video with audio. No queue mutation before choosing a destination.
3. In **Sources**, check that a camera, default mic, X11 desktop, each open capturable window and any available app sound stream appear as individual rows, each with ▶/⏭/＋. Refresh while an app starts/stops sound. Selecting a row must not start capture. For application/mic/PC sound, ▶/⏭/＋ schedules a **live reaction cue**, whereas enabling the input in Mixer routes its Sound/React/Record contribution.
4. Test a *playing* application audio stream. For Pulse/PipeWire compatibility on Zorin verify `command -v pactl` and `command -v parec` if app sound streams are absent; `sudo apt install pulseaudio-utils` is an optional system-level dependency. Confirm app stream can be enabled and recorded/reaction-routed independently of the microphone and system mix (subject to application backend restrictions).
5. Open Audio tray at bottom right. Switch **QUEUE → MIXER → QUEUE**, beginning from collapsed. Switching should expand automatically. Queue transport and upcoming items should return without losing current track; mixer rows should show gain, mute, metering, and advanced sound/react/monitor routing.
6. With A, B and Audio open, test populated/empty queues and mixer at compact window size. Preview toolbar, source browser, all queue headers and recording controls must stay reachable.
7. Verify camera toggles, microphone, source handoff, reaction, short audio recording, output recording and short export in the real workstation environment. Automated tests cannot establish physical hardware or actual exported media quality.

If an item fails, supply a screenshot, `.run-logs/` and source kind/stream name; keep UX28 as fallback.
