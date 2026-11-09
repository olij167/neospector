# UX31 Owner Acceptance · Zorin OS Xorg

1. Extract and install. With no audio track assigned, open **AUDIO → MIX**. The deck should be a small empty state, not a bank of silent QUEUE/A/B/MIC placeholders. No input starts on its own.
2. Queue an audio track. The **QUEUE** fader should appear; play, pause, adjust its level and mute. Remove the track and verify the fader disappears without losing recorded/project history.
3. Enable the microphone explicitly. Confirm a **MIC** strip appears only once the input is starting/live. Disable it; verify it disappears after stopping. Test Sound, React, Monitor and recording separately through the existing route exceptions.
4. Play Spotify; if needed `sudo apt install pulseaudio-utils`. Run `pactl -f json list sink-inputs` to inspect stream discovery. In Neospector, open Sources, refresh, select a supported application audio stream, then enable it. Verify it appears in MIX while live and disappears after stopping, not merely because it was discovered. Browser playback may be shown as Firefox/Chromium. Do not interpret a listed but unavailable PipeWire node as working audio.
5. Click the **Transition** style in the top performance bar. In Creative Controls, edit Shape, Motion curve, Edge softness, and an Effect + intensity. Set a nonzero effect and move the A/B crossfader. Verify the change peaks during the blend and is absent at either endpoint. Test the style step arrows and Undo.
6. Open Module Library → Random / Mutate. Switch to **Rack Variation**. Save new module count, randomise/mutation range and optional seed. Run Randomise, then Mutate. Verify selected-only mutation requires an explicit selection and locks remain respected. Confirm the transition editor preserves its settings independently.
7. Regressions: A/B camera toggle handoff, source placement, queue stop/repeat, Mix ON/mute, grouping/edit group, recording, reopening a project, export, and narrower window layout.

Physical capture, PipeWire, Spotify and export need owner-side acceptance; this archive cannot validate the actual connected devices.
