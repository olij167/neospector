# UX40 · 2026-11-09

Parameter last-value, numeric-entry, animated-value and module React All fixes; top-header remove; theme-control parity. UX39 baseline and signing/update code preserved.

# Neospector status — UX36

Current release: **0.7.20-ux36**, based exclusively on the delivered UX35 ZIP. Five-page shared Preferences, integrated Theme Studio, direct input selectors, simplified Welcome, preserved instrument engine. Linux Xorg evaluation candidate pending owner acceptance. UX35 remains rollback.

## UX36 · 2026-11-08
- Removed First Light and Learn in Place from Welcome; retained new, open, import, recents, defaults, appearance, update website and a single support link.
- Appearance now embeds full Theme Studio editing; removed separate editor window from Neospector UI. Builtin palettes are immutable when customising; previews revert on Close unless applied.
- Discoverable camera and microphone defaults are read-only selectors (without capture); editable optional folder path with native folder browser and separate opt-in import.
- Updates and support now live in General Preferences; direct File menu actions preserved.
- No audiovisual pipeline or project format changes.

# Neospector development status

Current: **0.7.17-ux33**, built on 2026-11-08 from the delivered UX32 ZIP.

Transition geometry and time animation are now authored through the same
module rack as normal effects; wipe/pixel/iris/glitch/slide are real operators
with editable parameterised groups rather than style presets. The Module Library
adds direct family categories, richer search and guarded declarative recipe
import. Former UX16 styles remain supported for legacy projects, and other
racks/queues/audio/capture/record/export paths are preserved.

**Status:** Linux Xorg evaluation candidate. See UX33 acceptance runner and
owner test card for evidence and unresolved physical acceptance. UX32 remains
rollback. Welcome and owner publication companion remain deferred.

## UX34 · 2026-11-08
- Stable Tk queue mounting, no-op browser tab switching, diff-based file rows,
  and selective rack geometry updates. Measured warm idle rack UI refresh under
  Xvfb (60 samples): 0.501 ms UX33 → 0.296 ms UX34 median.
- Redesigned Welcome with three clear entry paths and learn-in-place links to
  existing Media/Queue/Effects panels. No implicit capture/record action.
- No changes to authored transitions, module engines, recording/export or
  physical source discovery. Owner visual/hardware acceptance pending.

## UX35 · 2026-11-08
- Fix actual instrument module faceplate clipping using content-aware height for visible parameter rows and footer controls; maintain rack scrolling.
- Redesign Welcome around brand, recent projects, defaults, appearance, official update link and one support action.
- Shared six-page Preferences browser replaces duplicated per-setting popups, with menu shortcuts into each relevant page.
- Optional guarded media-folder auto-import when starting an empty project; no implicit hardware capture.
- Virtual X11 regression and packaged smoke are release gates; owner physical AV acceptance pending. UX34 is fallback.

## UX37 · Theme state and inline sequence preferences
One shared Welcome/Appearance theme name, persistent native welcome recolouring, reversible live preview, inline Output canvas controls, and visible Preferences footer. See UX37_IMPLEMENTATION.md and VERIFIED_RESULTS_UX37.md.
