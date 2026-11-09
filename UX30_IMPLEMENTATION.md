# UX30 implementation and design decisions

## Ownership and compatibility

Neospector still uses one `project.extra.sound_routes` source of truth, gesture-based mixer edits, the existing audio bus, queue history, module engine and visual renderer. All changes are surface/adaptor changes except optional *read-only* PipeWire fallback enumeration. No independent audio routing model was introduced.

## Audio stream discovery

`system_audio.pulse_choices()` remains the authoritative Pulse sink-input detector and requires `parec` before offering app capture. New `pipewire_app_choices()` reads the existing `pw-dump` graph to show named playback applications without capture capability. PipeWire graph node ids must never be fed into `parec --monitor-stream`. Disabled entries cannot be queued (`ux29_browser_model.source_destinations`); the browser explains the missing tooling. Install `pulseaudio-utils` to enable `pactl`/`parec` and refresh during actual playback. No system installations or routing changes are made by Neospector.

## Fader model

`DeskFaderMixer(SourceMixer)` reuses inherited refresh, discovery, route context menu, gain history, mic enable and meter signals. Its ScrollFrame replacement uses horizontally scrolling vertical strips, with microphone always materialized via `source_order()`. Physical monitoring is independent of visible source labels. No duplicate Audio Queue is rendered in Mixer mode.

## Library and performance

`ModuleLibraryPanel` now has direct close, group selected, edit selected group and random/mutate controls; they call existing authoritative deck and settings methods. Single/Groups filters and per-item visual labelling are preserved.

`VisualMixStrip` is mounted once in the top-row centre, between existing File/Effects/Media actions and the CAM/MIC controls. Width-aware reflow stacks transition and reaction groups on narrower windows, keeping the source and queue toggles in place.

## Tests and limitations

New UX30 pure adapter and Tk fixture tests cover PipeWire fallback, unavailable capture safety, always-present mic, vertical mixer, library actions, top bar hierarchy and compact geometry. The release gate extends the UX29 regression suite. All device capture and Spotify sound still need Zorin owner validation.
