# UX34 · Stable UI Refresh and Task-First Welcome

## Objective and root-cause evidence

UX33 could visibly replace parts of panels in stages even when the underlying
objects had not changed. The root causes were in the Tk presentation layer:

1. `RightSourceStack._sync()` called `pack_forget()` on every A/B/Audio card,
   then re-packed all opened cards for any single disclosure event.
2. `SourceShelf.show()` unmounted its entire tab content and rebuilt the file
   list even when the already-selected tab was requested.
3. `SharedProjectBrowser.refresh(force=True)` deleted every Treeview item and
   reinserted it, losing stable row identities and visible continuity.
4. `InstrumentRack.refresh()` called `relayout()` even for unchanged owner and
   value-only updates; the selected module cell already updated its faders.

## Fixes

The queue stack now mounts and unmounts only peers whose visibility changes.
Existing peers are neither destroyed nor blanked; unchanged padding is not
reconfigured. The browser leaves the current page alone and reconciles rows by
stable asset IDs, preserving selection, row identity and scroll. The rack
relayouts on changed owner, project restore, forced refresh, or an explicit
structural/resize callback, not every periodic value update.

These changes do not alter audio/video rendering, queue policy, module
processing, or project serialization. The desired result is a single coherent
visual update per user action, rather than a sequence of blank/rebuilt states.

## Measured evidence

In isolated Xvfb, 60 warmed, unchanged Transition-rack `refresh(False)` calls
with Tk idle handling yielded median **0.501 ms (UX33)** versus **0.296 ms
(UX34)**. These are environment-specific UI-control timings, **not playback
frame rates** or a claim about all possible project sizes. Behavioural tests
assert no peer unmounts, no redundant browser-row deletion, and no repeated
geometry pass during a stable refresh.

## Welcome and onboarding

Three task-based starts: try First Light (respects discard guard); import your
own files; resume project. Progressive learn-in-place controls reveal the
*existing* Media, Queue, and Effects panels rather than creating a second
training-only copy. The welcome preserves startup preference, theme controls,
interactive help, recent project entry points and Escape. Initial entry does
not request camera, microphone, application sound or recording permission.

The cards use one row at desktop width and one column when narrow, with a
scrollable body and a persistent Continue button. This preserves a clear
hierarchy without large unused bands.

## Qualification

Automated tests and synthetic desktop preview are evidence for the specified
paths only. Test on Zorin with a densely populated module rack, Files/Sources
switching, multiple open queues, live playback, actual hardware/audio, and
recorded output. Final hardware and perceptual approval remains with owner.
