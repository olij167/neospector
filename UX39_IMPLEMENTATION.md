# UX39 Engineering Notes — Fast Controls, Stable Tk Widgets

**Baseline:** UX38 0.7.22-ux38; project 1.3 preserved. **Scope:** UI/input performance only.

## Root causes traced

1. `InstrumentApp.write_parameter` called `changed()` on every pointer event, indirectly refreshing queues, flushing treatment history, reconfiguring audio sources, revising previews, resetting autosave and updating the window title.
2. `SequencerApp.end_gesture` forced `deck.refresh(force=True)` on every parameter release.
3. `ParameterFader.refresh` always set the Tk DoubleVar and displayed StringVar, even when values were unchanged. Reaction indicators did the same.
4. `InstrumentDeck.select_owner` always called `relayout`, even if the same owner had already been selected by that very fader.
5. The 100 ms transport UI poll repeatedly traversed the rack during active parameter dragging; repeated owner selection variables also caused Tk trace callbacks.

## Implementation

- `InstrumentApp._ux39_schedule_parameter`: per-gesture, at-most-once-per-33ms model-change notification. The parameter data changes synchronously in the main Tk thread; coalescing only concerns expensive downstream UI/frame notification. The first change notifies immediately; the latest value wins.
- `_ux39_complete_parameter`: flush on normal release, cancel scheduled notifications on undo cancellation. `InstrumentApp.changed` retains full structural update semantics for other operations.
- Program gesture releases use non-forced deck refresh, preserving module and group widgets. Other gesture kinds continue their prior refresh handling.
- `ParameterFader` and reaction strips compare values and state before configuring Tk widgets. Idled values no longer produce redundant redraw traffic.
- `InstrumentDeck.refresh` only changes selected owner variables if they actually differ. Selecting an unchanged owner no longer triggers a relayout.
- While a program gesture is active, playback/UI clock continues but skips full rack polling; regular polling resumes after release.

## Invariants

- Individual pointer changes still write the authoritative parameter synchronously (including keyframes and conductor-lock metadata). The undo gesture still holds a single checkpoint. Save/close and cancel complete or discard pending notifications. Preview and sound playback remain on the original engine.
- User profiles, recording/export, transition rack, source capture, themes, and signed-updater security/trust are unchanged.
- No owner signing key is included in this source or archive.

## Performance measurement limitations

On a virtual X display, a synthetic batch of 300 UI-thread parameter writes into the unchanged UX38 control path took ~306ms in total (0.813ms median call); the UX39 coalesced path took below 1ms total for the same callback batch. This is not a measurement of Tk mouse-event delivery, rendering, camera or microphone latency, nor evidence of real-world FPS improvements. Owner visual acceptance is required.
