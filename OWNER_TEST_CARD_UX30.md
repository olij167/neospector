# UX30 Owner Acceptance · Zorin OS Xorg

1. Extract, verify manifest, install and launch. Run `python3 tools/verify_ux30.py` for selected software regressions.
2. Open AUDIO → MIX; confirm vertical QUEUE/A SOUND/B SOUND/MIC strips and scroll for additional sources. MIC exists before activation. Drag gain, mute/enable and verify meter and recording effects. Confirm `⋯` routes Sound/React/Monitor deliberately rather than a duplicate mixer.
3. Run `sudo apt install pulseaudio-utils` only if needed. Check `command -v pactl` and `command -v parec`. Play Spotify. Run `pactl -f json list sink-inputs`; if Spotify is absent there, test a browser audio stream. Refresh Sources, identify the stream by app or browser, add a reaction cue, activate in Mixer and verify captured sound. Never silently assume successful per-app capture from a listed name.
4. Verify the top bar contains Record/Output/Focus, Transition/React/A-B mix and CAM A/B/MIC + matching queue toggles. Test normal and narrower window with Media & Sources or Effects open.
5. Open the Module Library from Effects, check explicit × close, Single/Groups filter, Group selected (2+ adjacent rack selections), Edit group Controls companion, and Random/Mutate settings. Confirm edits are undoable and no existing module effects disappear.
6. Regression: queuing files; A/B camera toggle handoff; live source switch; audio queue repeat/stop; reaction; recording and export.

Physical hardware, PipeWire streaming and render/export acceptance are not simulated by the container. Keep UX29 as fallback until this card is accepted.
