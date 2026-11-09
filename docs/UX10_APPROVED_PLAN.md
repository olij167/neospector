# NEOSPECTOR UX10 — COMPLETE INSTRUMENT INTERFACE OVERHAUL

**Status:** Design specification and implementation handoff — proposed, not implemented  
**Date:** 2 November 2026  
**Baseline:** `Neospector_UX9_Connected_20261102.zip` (Linux Xorg candidate, 0.5.0-ux9)  
**Secondary reference:** `omne-av-synth-main(2).zip`, including Waves interaction contract and broadcast viewer  
**Governing direction:** OmN-e, Design Webtoys, Pungent Funk; utility → form → features → aesthetics  
**Principle:** Preserve the functioning instrument; change the interaction architecture rather than adding more chrome to it.

> **Product promise:** Import some music and visuals, immediately see what they produce, shape the picture with tactile effects, make it react to sound, mix two visual sources, and record the result without needing to understand the engine first.

## 1. Decision / non-negotiable target

Build **one persistent three-zone instrument** rather than a collection of competing editors:

1. **Left: MEDIA DESK.** A/B visual queues arranged as two **side-by-side vertical columns**, one shared horizontal A↔B crossfader immediately above, a full-width MUSIC queue below, and a compact PROJECT MEDIA folder below that. These are one integrated sidebar, not tabbed workspaces.
2. **Centre: OUTPUT + RACK.** The visual output is always visible above a primary, large module rack. Rack modules are playable hardware-like objects, not property forms. A, B and Output are explicit editing scopes and never imply immediate live switching.
3. **Right: MODULE DRAWER.** A collapsible, resizable module library and builder with a stable leftward relationship to the rack. Closed by default; opens when adding a module, searching recipes or explicitly building/editing a group. **Never below the module rack.**
4. **Top: SYSTEM STRIP.** Only project/file, preferences/settings, output-window controls, record/capture and export, plus unobtrusive status. Global play, media source selection, module controls and general Libraries do not live here.

**Exactly two user-facing visual channels, A and B.** MUSIC is an audio queue/reaction input, not a third visual channel. The Output rack processes their result and is not a third queue. Preserve any extra-channel project data during migration; do not delete or silently reinterpret it.

**No visual-queue tabs. No dropdowns inside queue or project-library panels**, except the tiny source-device choice attached to each camera/microphone toggle as explicitly requested. More options should be visible through relevant controls, appropriate context surfaces, and selection, not buried in arbitrary overflow menus.

## 2. Evidence / audit status

This document is grounded in archive inspection and UX9's supplied screenshots, not in a fresh owner-hardware interactive test. The UX9 release documents report a 191-test targeted gate, recorded screenshots, save/reopen verification and a sample MP4. Physical cameras, live audio capture/monitoring, PC/app loopback, external file-manager drag, real screen/window capture and prolonged owner-session usability still require live qualification. No new tests were run as part of this design plan.

### 2.1 What UX9 gets right and must retain

- Working visual/audio engine, clip and media queues, A/B mixing, source selection, group effects, parameter animation and modulation.
- Local-first projects, save/reopen/history, current media asset identifiers, recording/export, source-specific racks, project media import, and existing module recipes.
- Selection versus performing/source-taking distinction; browsing must not automatically change live output.
- Control base value versus modulated effective value, reactions to MUSIC/microphone/other eligible sources, bands, signed travel and response shape.
- Individual module reorder, bypass, duplicate, reset, vary, groups, promotions, recipe persistence and advanced precise parameters.
- A visual programme/monitor separate from editor state; genuine video/audio encoding; source capture with explicit consent and device error handling.

### 2.2 Observed UX problems in UX9 screenshots

**Observed from `evidence/ux9/UX9_workspace.png` and `UX9_small_window.png`:**

- Left column puts music source, capture routes, channel controls, queue list, take controls and file drop prompts in one repetitive stack. Each small control has almost identical visual weight. A and B are vertically separated and cannot be compared at a glance.
- The A/B crossfader currently sits under the central programme preview, making the visual mix physically remote from the visual queues it controls.
- The central preview occupies considerable vertical room while the rack shows dense, small modules; the small-window screenshot exhibits simultaneous vertical and horizontal rack scrolling, and the Ingredients shelf occupies the same central work area beneath it.
- Module faces contain multiple rows of small action glyphs, `More`, `React` buttons, secondary sliders and repeated tiny numeric fields. A user must decode structure before performing.
- The reaction expansion enlarges a module laterally and crowds its neighbours. It exposes technical configuration in the same visual plane as active effect dials.
- The global strip carries Play, Record, Undo, Redo, Picture, Ingredients, Save and Export. Functional meanings are mixed.
- Same rectangle/border treatment is applied to many unrelated controls; visual hierarchy is weak.

**Observed in source:** `instrument_shell.py` divides the stage into left media and right preview/rack, then places the Ingredients shelf under the rack. `instrument_media.py` creates Music/A/B and optionally C/D in a vertical source canvas. `instrument_mix.py` has a working direct A/B fader that adopts complementary mix on deliberate manipulation, while preserving older independent opacities as Custom. `instrument_rack.py` implements A/B/Output scopes and module interactions. `module_library.py` and `playable_rack.py` implement the existing module browser and builder. `omne_workspace.py` composes the current shell and recording/source control surfaces.

**Not established without usability testing:** precisely how often new users make errors, whether any one existing control is always misunderstood, or whether a particular layout will meet task-time targets. These are predictions to test, not measured results.

### 2.3 Why incremental repairs keep failing

Adding a button to reduce one click merely increases the number of unrelated buttons; hiding the button behind a menu reduces surface clutter at the expense of search cost. The missing piece is **object ownership**: every action must live with the object whose behaviour it changes, and the three main workspaces must reflect the actual creation flow. The redesign must replace the old navigation grammar, not put new controls on top of it.

## 3. The new spatial composition

```text
┌──────────────────────────────── SYSTEM STRIP ────────────────────────────────────────────────┐
│ NEOSPECTOR  [Project ▾] [Save] [Settings]                  [Output ↗] [● Record] [Export] │
├────────────── MEDIA DESK ───────────────────────┬─────────── OUTPUT + MODULE RACK ────┬───────┤
│                                                │                                    │ MODULE│
│    VISUAL MIX     A ════●════════ B           │  ┌──────────── LIVE OUTPUT ──────┐ │ DRAWER│
│                       A 50 / B 50              │  │                              │ │       │
│  ┌──────── QUEUE A ─────┐┌──── QUEUE B ──────┐ │  │   live visual programme      │ │ Search│
│  │ A     [Camera] [⌄]  ││ B   [Camera] [⌄] │ │  │                              │ │       │
│  │ [↺][◀][⏯]            ││ [↺][◀][⏯]         │ │  └──────────────────────────────┘ │ effect│
│  │ [▶▶][⏭][Loop]        ││ [▶▶][⏭][Loop]      │ │                                    │ cards │
│  │ ┌─ NOW ────────────┐ ││ ┌─ NOW ─────────┐ │ │  EDIT  [ A ] [ B ] [ OUTPUT ] [+]   │       │
│  │ │ thumbnail / time │ ││ │ thumb / time  │ │ │  ┌── MODULE RACK ───────────────┐ │ recipe│
│  │ └──────────────────┘ ││ └───────────────┘ │ │  │ [effect][effect][group]       │ │ cards │
│  │ ▶ next clip          ││ ▶ next clip       │ │  │ [effect][effect][+ slot]      │ │       │
│  │ ▶ next clip          ││ ▶ next clip       │ │  │                               │ │ [Build]│
│  │ + add / drop         ││ + add / drop      │ │  └───────────────────────────────┘ │ [Close]│
│  └──────────────────────┘└────────────────────┘ │                                    │       │
│  ┌─ MUSIC / REACTION AUDIO ──────────────────┐  │   Context strip belongs to         │       │
│  │ [↺][◀][⏯][▶▶][⏭]   [Mic][⌄]  level ▁▆▃ │  │   the selected module, if needed.  │       │
│  │ ♪ now playing   01:42 / 03:58           │  │                                    │       │
│  │ next song / next song / + add           │  │                                    │       │
│  └───────────────────────────────────────────┘  │                                    │       │
│  PROJECT MEDIA  [Search…] [All|Visual|Audio]   │                                    │       │
│  [+ Files]    [thumbnail] [thumbnail] [...]    │                                    │       │
└────────────────────────────────────────────────┴────────────────────────────────────┴───────┘
```

Diagram is an information-architecture wireframe, **not pixel-perfect**. Desktop includes the right drawer only while it is open. `Loop` is a direct small toggle at the same queue that it controls and must not be disguised as a dropdown.

### 3.1 Desktop layout goals (provisional, tune on real render)

- **1600×900:** left 350–390 px, right drawer 300–350 px open, centre takes the remaining width. With drawer closed, centre expands. Preview about 31–38% of the centre's available height; rack gets the rest.
- **1280×800:** left 315–350 px, centre dominant. Drawer closed normally; opening temporarily overlays only the right edge or shrinks only if the rack still meets minimum playable module dimensions.
- **1024×768:** preserve visible A/B side by side, MUSIC and a minimal Project Media strip. Right drawer is a dismissible overlay and cannot consume the minimum module-rack width. Avoid requiring horizontal or nested vertical scrolling inside a single module.
- **Tablet:** source column / performance stage are the two stable zones; right drawer appears as a right sheet. Keep A/B side by side until the viewport genuinely cannot support minimum hit targets.
- **Phone:** two visual queues remain recognisable as A and B and can vertically stack if the actual width requires it; never become mutually exclusive tabs. Centre stage and rack become a responsive vertical surface. The module picker becomes a temporary edge/bottom sheet with explicit return. Functional parity is required, not identical geometry.
- All three zones are independently resizable where there is space. User resizing is persistent, constrained to useful minima, and does not reset playback, preview ownership or parameter focus.

### 3.2 Hierarchy and focus

1. **Output picture** = immediate feedback. The eye should find it first.
2. **Rack** = largest interactive workspace. The hand should find it first.
3. **Visual queues + mix** = clearly labelled performance inputs, second highest importance.
4. **MUSIC** = identifiable audio source and audio-reactive input.
5. **Project Media** = supporting tray of available assets; no competition with live sources.
6. **Module drawer** = temporarily visible context, not always-on property inspector.

No persistent general-purpose status strings across the main work area. Put brief inline status on the object affected and one tiny global noninteractive status area if essential.

## 4. MEDIA DESK — detailed specification

### 4.1 A/B crossfader above both queues

One long horizontal hardware fader at the top of the left sidebar, with permanent endpoint markers `A` and `B`, centre notch, thumb, and live ratio numerals. It controls visual contribution only; moving it does not select a rack or load a clip. Values map to `A = 1 - x`, `B = x`, `x ∈ [0,1]` in **the new linked mode**. Leftmost = only A; midpoint = 50% A / 50% B; rightmost = only B. For an empty visual channel, correctly show an empty/black or explicitly transparent contribution per current compositor semantics; **never invent** content.

Historical UX9 projects may contain independently assigned opacity strengths. Until explicitly edited, show the actual ratio and a small `Unlinked`/`Legacy mix` indication, without claiming 50/50 normalisation. On a deliberate crossfader gesture, use the existing complementary adoption operation and make it a single undoable command. Do not auto-normalise legacy files on load. Verify fade curves, non-normal blending and master effects to avoid brightness jumps.

### 4.2 Visual queue anatomy

The only routine top controls on **each** queue are:

- **Clear identity:** big `A` or `B`, source icon and current media/capture state.
- **Camera toggle:** `Camera` activates or deactivates capture for this queue; a tiny adjacent chevron opens **only** the list of available webcams and monitor/window capture sources. Its choices are device-specific, with an explicit permission/selection path; the menu closes on selection, Escape or outside click. The queue's files remain intact underneath.
- **Player transport:** `Restart`, `Reverse`, `Pause/Play`, `Fast-forward`, `Next` and a direct `Repeat` state control, mapped to the current queue/clip according to the state contract below. Because each visual column is narrow, render as **two rows of three icon-sized targets** plus the source selector, instead of shrinking six targets into a single unreadable line. All icons have tooltips and accessible names.
- **Now playing:** a comparatively large thumbnail, clipped title, elapsed/total time or `LIVE`, and a slim progress indicator/scrub target where seekable.
- **Queue:** vertical thumbnail rows, current item emphasized, upcoming entries lighter, per-row `▶ Take/play`, drag handle on selected/hover and delete/reorder action on selection. No duplicate toolbar for `Select a media` and `Take`.
- **Add/drop:** one visible `+`/drop target at the end of each list. Dropping audio in a visual list routes to MUSIC only after a clear feedback cue, preserving the existing audio placement rule; dropping supported visual files appends to the target A/B queue without switching the currently live source.

**No per-channel permanent FX menu in the queue header.** To edit effects, click the A/B identity or its `FX` icon beside the identity, which selects that specific rack scope in the centre. Keep media and treatment distinct but spatially connected.

### 4.3 Transport semantics — must be consistent in A, B and MUSIC

| Action | Proposed semantic | Boundary |
|---|---|---|
| Restart `↺` | Current item at in-point / restart a non-seekable live source only if a meaningful restart exists | No queue deletion or play-owner change |
| Reverse `◀` | Toggle reverse playback direction on supported seekable media | If unsupported for camera/window, disabled with explanation, never a silent fake |
| Play/Pause `⏯` | Pause/resume that queue's playhead | Never change editing scope; capture permission independent |
| Fast forward `⏩` | Momentary scan or stepped forward seek; distinguish clearly from `Next` | Prefer a hold-to-scan with visible speed/position feedback; keyboard equivalent |
| Next `⏭` | Trigger next queue entry, respecting its transition/loop policy | Show which item is about to start |
| Repeat `↻` | Cycle `Off` / `One` / `All` by pressing icon with concise state text/icon | No dropdown required |
| Camera/Mic | Switch live source/react input without destroying media queue | Capture starts only on explicit activation and success |

For still images or procedural-only content, do not emulate unsupported time manipulation. For fast-forward behaviour that the engine does not yet implement, supply a true seek-based variant where available or explicitly defer it; **no decorative buttons**. Reverse should preserve direction state across pause/resume and save/reopen only if the engine supports that contract. Exact integration requires verifying current source-policy implementation before editing.

### 4.4 Three distinct user actions, one clear grammar

- **Select** a queue row: highlight for inspection/rack clip editing; do not put it on air.
- **Take/play** a queue row: deliberately perform it in that lane; show current/live indicator.
- **Reorder** a queue row: drag vertically, or use keyboard move-up/down after selection. Show insertion line while dragging. Undo restores exact order and previous live selection if applicable.

These are intentionally different, as in live-video software and Ableton's clip-launch vocabulary. Avoid a single click meaning three different things.

### 4.5 MUSIC queue — full-width audio player below A/B

MUSIC resembles an ordinary media-player queue: title, progress/waveform/activity, transport set, current audio, next items, reorder, add/drop. It is always visible without navigating to another pane. It is **one audio programme deck**, not a multitrack DAW. Existing soundtrack-event editing and crossfades remain available through selection/context controls; a timeline can appear as a contextual advanced mode only if relevant.

**Mic** button + source chevron occupy the same conceptual position as the camera controls in A/B. The chevron selects a *reaction input* (microphone device, PC/application audio when supported, or permitted alternative sources). The active signal and a live meter are visible next to it. The user should not need to guess whether the mic is feeding analysis, audible output, monitoring or recording.

Provide small, truthful route labels/indicators directly underneath when relevant: `REACT` (driving modules), `HEAR` (included in audible programme), and `MONITOR` (local monitoring), with existing routing defaults preserved. **Do not automatically send a live microphone to output or monitoring** when selecting it for reaction. Resolve feedback risks through actual routing guards. Sources that require permission are stopped and restored safely when dismissed, project replaced or device vanishes.

Music files remain in the queue when the user switches reaction analysis to live mic. A visually reactive composition can hear prerecorded programme audio and use another input for reaction, if the backend routes it. This distinction must be represented truthfully: `Playing: file` and `Reacting to: mic` are not contradictory.

### 4.6 PROJECT MEDIA — simple project folder

The only permanent library under MUSIC is a project-local unified media browser containing audio, video and images **together**. Treat it like a folder, not a global catalogue, album manager or multi-tab asset browser.

- Header: `PROJECT MEDIA` + clear `+ Import files`.
- One search box filtering visible filenames, tags, media metadata where indexed.
- Inline filter chips `All`, `Visual`, `Audio` (no dropdowns); inline sort modes such as `Recent`, `Name`, `Duration`, toggled directly without a cascading menu.
- Compact thumbnail/name/type rows or a responsive thumbnail grid. Double-click to inspect/audition; drag to A/B/MUSIC; select then `Add to A`, `Add to B`, `Add to Music` contextual action if drag is unavailable.
- Selected media reveals `Locate`, `Relink`, `Details` (only if needed), and `Remove from project`. Removing a referenced asset must explain which queues/occurrences depend on it and support `Cancel`/explicit detach. **Never delete the external original**, and never remove from other projects.
- File paths are references, not irrevocable imports. Persist stable asset IDs and fingerprints; show missing file as a repairable row with `Relink` rather than silently hiding it.
- `Import` does not play/take a source automatically; import progress appears on each row; duplicate detection and supported formats use existing backend.
- Do not surface unrelated prior projects, albums, recipes or saved modules here. Recipes belong to the MODULE DRAWER. Project media remains one folder-like object regardless of how source files are physically stored.
- Offer portable project bundling through the file/export workflow where supported, keeping source originals untouched and preserving non-lock-in.

## 5. CENTRE — OUTPUT AND MODULE RACK

### 5.1 Programme viewer

Keep the programme fixed above the rack, large enough to see what a module changes but never allowed to dominate the workspace. Responsive sizing should prefer the rack on smaller screens rather than leaving only a thin strip of module controls. The picture itself owns only direct visual interactions (when supported), a small `Output` indicator and optional `Fullscreen/Open viewer` action. Remove redundant Help, Focus, Output and technical quality controls from the viewer's permanent chrome; move them to consistent locations.

One click on picture shows output focus if useful; it must not take a queue item live. User-resizing the preview must not remount/recreate the video renderer or lose playback/capture state. When capture, source files or GPU rendering are unavailable, display honest fallback feedback without hiding the rack.

### 5.2 Editing scope bar

Right under preview, above the rack:

`EDIT   [ A ] [ B ] [ OUTPUT ]                              [+ ADD MODULE]`

Selected state is bold and spatially unmistakable; labels are always visible, never icon-only here. Context breadcrumb below it appears *only as needed*, e.g. `A / Clip: Violet current / Group: Dream Trails`. Clicking a queue's FX identity directly selects its rack, and opening a group changes the breadcrumb rather than creating a new modal.

Queue and mix playback state must never imply rack owner. `A`, `B` and `Output` describe **where an effect is applied**, not which feed is currently strongest, selected or audible.

### 5.3 Module faces: playable first, precise when requested

The default card resembles a compact guitar pedal / Eurorack module:

```text
┌─────────── LIQUID DRIFT ───────────────┐
│ ● ON      [icon / one-line identity]   │
│                                       │
│             (large dial)              │
│              AMOUNT                   │
│           0.42  ⇢ 0.68                │
│        ~  REACT: MUSIC / BASS          │
│                                       │
│ [VARY] [DUPLICATE] [BYPASS] [EDIT]    │
└───────────────────────────────────────┘
```

- **Single main expressive control** per card, occasionally a second where truly necessary (e.g. speed and amount). Actual primary parameters vary by effect family; choose by user-visible impact, not model field order.
- Strong hierarchy: name, active state, main control, reaction indicator, then small contextual actions. A card must be identifiable at arm's length and usable without reading every number.
- Base value and effective modulated value are two marks on the *same control*. Preserve real editable base, signed reaction depth and animation behaviour.
- Turn dials vertically, scroll with focus, use arrows for keyboard control, Shift for precision, click numeric readout for exact value; double-click reset to loaded value if that UX9 contract remains, separate module Reset to defaults.
- Never use tiny mystery icons as the **sole** means to access a core action. One coherent icon grammar, consistent placement and short tooltips; avoid `...` on every module.
- Bypass is a latching hardware-like switch with legible visual distinction. Vary affects only permitted/unlocked parameters, is undoable, and gives perceptible feedback.
- Drag card handle to rearrange; keyboard move-left/right or before/after equivalent; show live insertion marker. Duplicate and delete via selected-card action bar with unambiguous icons.
- Selected module grows or obtains a **single inline contextual control deck**, with secondary parameters, no nested vertical scroll and no popup that obscures the dial. Selected-card detail uses existing field objects, including keyframes and exact configuration. Unselected modules remain simple.
- Cards wrap into rows. Avoid horizontal scrolling if cards can reasonably wrap, and avoid forcing one fixed oversized width. Module bank pagination only for **true** overflow and only when necessary.

### 5.4 Reactions as a property of a dial, not a separate editor

Each principal dial exposes a small `~`/pulse signifier and a ring showing current modulation. Clicking the reaction mark reveals a *concise inline attached strip*:

`SOURCE  [Music][Mic][Other supported]   BAND [Full][Low][Mid][High]   TRAVEL  ◄──●──►   SHAPE [Punch][Smooth][Swell]`

The currently selected source and band are evident without opening a menu. Source options must match actual active input availability. A signed Travel centre marker shows zero; the dial visibly moves to demonstrate travel direction/range. `Advanced` within the selected module reveals keyframe/range/manual envelope controls without moving that functionality to an unrelated inspector. On small screens use two short rows or a selected-module face with enough space, **never clip the reaction editor**.

When another card is selected, dismiss the previous contextual strip without losing edits. A change to reaction parameters must not re-create unrelated module widgets, reset scroll, affect playing selection or alter recording unexpectedly.

### 5.5 Module groups, recipes and performance controls

Treat a group as a module with a clear stacked-card emblem and a working preview/summary of its contents. `Open group` enters an in-place nested rack and `Back` restores parent with scroll and selection state preserved. Front/promoted group controls use exactly the same dial grammar as ordinary modules. Internal parameters remain accessible through group editing, not by navigating a separate technical form.

- Add, reorder, duplicate, bypass, reset, save recipe, rename and ungroup are contextual commands for the current rack/selected group.
- A recipe applied to the rack is an understandable previewable **module grouping**, not a mysterious library transaction. Insertion has explicit scope and position, indicated in the rack before commit.
- Keep existing lock semantics (composition, Conductor, workspace, parameter variation, etc.) distinct. A module variation lock is not the same as playback/panel lock; do not reuse one ambiguous padlock without labels.
- Randomise/Vary is a real playful affordance near the rack, but must respect scope, locks and current mix. Evolution/Conductor/sequence generation remain available through contextual performance controls, not permanent top-bar clutter.

## 6. RIGHT — MODULE COLLECTION AND BUILDER

### 6.1 One sidebar, two connected tasks

Clicking `+ Add Module` opens a **right-edge drawer**. Default content is a visual collection of **Effects / Groups & Recipes / user modules** with search, meaningful visual family labels, thumbnail motifs and prominent `+` insert. Library entry insertion uses the selected rack owner and deliberate drop position. The drawer closes after insertion by default (can be pinned when space allows).

Clicking `Build` on a selected module/group replaces drawer content with a builder view, with an explicit `← Modules` return at the top. **Not two always-visible tab pages**, and not a property sheet permanently taking rack height. Builder should directly manipulate an intelligible chain/stack and expose promoted front controls, relationships and internal routing. Advanced field forms remain in a secondary detail area of the builder only, not the first screen.

### 6.2 Module browser card

One visually distinctive card per effect family: clear title, short action-oriented descriptor, simple original motif suggesting the visual effect, live hover/selection preview *only when cheap*, and visible `+`. Search should find effects/recipes by intent (`blur`, `echo`, `symmetry`) as well as name. Avoid long textual taxonomies; short filter chips for family categories are appropriate. When opening the drawer, show relevant recent/favourite modules near the top, but keep all existing modules discoverable with search.

Do not silently insert into whichever owner happened to be selected after the drawer opened. The insertion target is captured on `+ Add`, identified visibly (`Add to A / after Liquid Drift`), and invalidated if scope changes, as UX9 already protects. The user should be able to reselect insertion point in a single click.

### 6.3 Module builder

Builder hierarchy: **What it does** (name, effect chain miniature, visible output) → **What it controls** (promoted knobs) → **How it is wired** (internal parameter mapping) → **Exact details**. Direct connections and reordering preferred to forms or generic dropdowns. Use an undoable session; Cancel restores uncommitted changes. Saving a reusable module never implicitly changes the entire project unless explicitly applied. Imported recipes must be validated before use.

### 6.4 Drawer behaviours

- Close by pressing same launcher, `×`, Escape or clicking outside when transient; no orphan panels.
- On desktop, persistent pin is optional and remembered; when small, drawer opens as transient right sheet with strong back/close affordance, then gives rack back all space.
- Switching between searching and building never loses current effect selection or project playback.
- No global `Ingredients` shelf; remove bottom shelf from default and legacy layout state once migration is proven.

## 7. TOP STRIP — system only

**Keep:** project name/file menu, New/Open/Save/Save As, preferences/settings, Output Viewer / fullscreen, REC (visible red active + duration), Export, and a compact actionable error/status indicator. **Undo/Redo must not create extra top-bar chrome:** keep shortcuts and access via Project/Edit system menu or selected-rack contextual controls.

**Move:** Play/Pause/Restart/Skip to their audio/visual deck headers; Camera/Screen to the respective visual source headers; Mic/PC/App routing to MUSIC; FX/Add/Recipes/Vary to rack and right drawer; exact timing/automation to selected item/advanced contextual view; master visual mix to above A/B.

**Recording:** one `● REC` button starts/stops output recording. An adjacent recording-options control is permitted because recording has genuinely consequential options: `Programme video`, `Capture last N seconds`, `Sequence export` depending on existing capabilities, destination, size and sound routing. This is a **task-specific control**, not a dumping-ground dropdown. Clear armed/active/finalising/error states, elapsed time and actual saved path. Retained live-input capture controls are inside recording settings with their implications explained; never leave an unexplained global checkbox.

**Output:** `Open Output` launches/focuses the clean audience/OBS-friendly monitor. Edits, rack chrome and project media never contaminate that feed. Distinguish monitor mute from recording sound inclusion.

## 8. OTHER SYSTEMS: intentional placement, no feature loss

| Existing capability | New home / access |
|---|---|
| Conductor, autonomous/evolve variation | Rack-context `Performance` tool / selected output scope, with compact status and optional advanced pane |
| Parameter keyframes and timing | Selected module secondary controls; relevant queue-item timing via selected item context |
| Sequence/timeline and composition queue | Contextual editing surface anchored to output/rack or audio when deliberately opened, not permanently visible/taking main space |
| Masks, fit, source-in/out, per-media settings | Selected clip on A/B; concise direct controls, detailed editor only on request |
| Advanced audio routing / live-input details | MUSIC source + `Route` contextual dialog, preserving existing audio-bus semantics |
| Help and tutorial | Tiny `?` in System menu and contextual tooltips; interactive first-run cues attached to actual actions, not a Welcome screen occupying workspace |
| Themes / appearance | System prefs, respecting existing Pungent Funk theme adapters and accessibility |
| History, recovery, diagnostics | Project/System menu and developer layer; undo visibly accessible; never replace playable controls |
| Project module recipes | Right module browser, not Project Media |
| Saved takes / previous recordings | Recording/export history through the output action, not a permanent unrelated library tab |

Avoid a universal `More` funnel. Secondary settings must attach to an actual object or task, and appear only when a reasonable user needs them.

## 9. Consistent interaction language

**The same verbs and feedback across all surfaces:**

- **Click** to select, **▶** to perform/take, **drag** to reorder/adjust, **+** to add, **toggle** to latch ON/OFF, **wave** to make a parameter react, **duplicate** to copy, **↺** to restart/reset (with contextual distinction and descriptive tooltip), **Esc** to cancel, **Ctrl+Z** to undo, **right-click/long-press** for genuine less-common contextual commands.
- A selected object is highlighted by position/border and label, not colour alone. A live object gets an unmistakable live dot and motion/time state. An unavailable one has a reason and a recovery action.
- Avoid arbitrary typography and colour differences across controls serving identical roles. Distinguish channel A, channel B, audio, module, group and warning with restrained stable accent codes, distinct icons and labels.
- Click-outside menus dismiss, repeated trigger toggles them closed, Escape cancels preview without commit, focus returns to invoking control.
- Every adjustment has immediate visual/audio feedback; no `Apply` button for routine safe reversible changes. Introduce confirmation only for destructive, device-permission or expensive actions.
- Use undo/redo and stable focus; one drag = one semantic history command. Separate ephemeral preview from committed state. Handle source-loss and read-only state without discarding project intent.

## 10. Visual style / meaningful differences

Use the Pungent Funk acid / Y2K language but restrain it so the modules are instruments rather than a uniform magenta-outline dashboard. **Proposed** foundations: near-black/deep aubergine background; cream high-contrast text; magenta/lilac only for structure, selection and reaction; yellow for current principal actions; audio cyan/teal only as semantic identity. Colours require contrast evaluation against actual hardware, and all status is duplicated by form/text.

- Output viewer = visually calm, almost no chrome.
- Media rows = flatter, file-browser language with thumbnails and progress. A and B separate by identity and deliberate accent only.
- Module face = stronger body silhouette, large knobs, family-specific motifs, restrained hardware details, physical latch states, tactile press/drag feedback. Not generic grids of uniform buttons.
- Module browser = actual visual effect *specimens*, not form-heavy cards.
- Builder = chain/wiring schematic with direct connectors and promoted controls.
- Top system bar = smallest type/control hierarchy; not an attraction competing with the instrument.

Initial design tokens for prototyping (not a colour-contrast certification): background `#1B1024`, raised `#2C1B38`, text `#F5EEDF`, subtle line `#574066`, selection `#D47AEF`, primary `#F2CA51`, live `#77D5C4`, error `#FF777E`. 8px spacing baseline, modules min ~190px playable width on desktop, large dials ~52–70px diameter, ~44px effective interactive targets where feasible, focus rings and semantic labels.

Motion: 80–150ms press/selection response, physically meaningful dial changes, short structural reflow only when necessary. No visual confetti, permanent ambient twitching or heavy animations that compete with the programme video. Respect reduced motion; never remount renderer for stylistic animation.

## 11. Comparison case studies: take the good, reject the debt

| Case study | Learn from | Deliberately avoid |
|---|---|---|
| **GarageBand Smart Controls** | Few high-value controls, consistent instrument-family grammar, immediate audition | Hiding too much behind patches/presets or a complex track editor |
| **Critter & Guitari EYESY** | Plug-in-and-play audio-reactive performance, a handful of meaningful knobs, mode identity | Fixed hardware limitations, shallow direct access to complex internal routing |
| **Mixxx / two-deck DJ software** | A/B mental model, crossfader centred on source decks, recognisable transport/playing states | Overloading each channel with DJ-specific cue/EQ/BPM/clutter Neospector does not need |
| **Resolume** | Distinct clip versus layer versus final-output effects; source drag/drop and immediate take/live semantics | Expansive performance grids, busy multi-layer clip taxonomy and dense technical property panes |
| **OBS Studio** | Strong distinction between preview/edit state and programme/live output, real source/capture semantics | Dock proliferation and settings dialog navigation for routine performer actions |
| **Ableton Session View** | Vertical columns of clips, separate row selection and clip launch, reorder and keyboard parity | Turning the AV instrument into a DAW-sized scene matrix with too many simultaneous tracks |
| **Waves / ooo.omne.space internal source** | Visual-first stage; small high-frequency Quick Deck; deep edit controls preserve model; explicit performance output | Reproducing its lengthy Compose/Style/Cue/Rules tab set in Neospector; a separate projection of the same data is enough |
| **Legacy UX9** | Preserve effective knobs, direct reaction primitives, stable project format, source ownership, live/output rendering | The competing Ingredients shelf, vertical A/B lanes, bottom-based browsing, tiny repeated More/FX buttons |

**External references inspected (manuals/official docs):**
- GarageBand Smart Controls: https://support.apple.com/en-au/guide/garageband/gbndf553bab8/mac
- EYESY manual: https://critterandguitari.github.io/cg-docs/EYESY/ey_os_3/
- Mixxx user interface: https://manual.mixxx.org/2.5/en/chapters/user_interface
- Resolume effects: https://resolume.com/support/en/effects and composition: https://www.resolume.com/support/en/composition
- OBS overview: https://obsproject.com/kb/obs-studio-overview
- Ableton Session View: https://www.ableton.com/en/manual/session-view/

**Internal reference qualification:** Public `ooo.omne.space` and `omne.space/waves` URLs could not be fetched in the browsing environment. The uploaded `omne-av-synth-main(2).zip`, especially `docs/omne-waves/v0.1.1m0/INTERACTION_CONTRACT.md` and `waves/index.html`, supports these internal comparisons. Do not claim live-site visual verification.

## 12. Engineering boundaries — integrate, do not replace the engine

### 12.1 Proposed component ownership

```text
Persistent Project / Sequence / Audio / Render / Capture / History models (unchanged first)
        ↓ read-only view models + semantic commands
┌───────────────────────────────────────────────────────────────────────────┐
│ UX10 ShellController                                                     │
│  ├─ MediaDeskViewModel ── Crossfade / AQueue / BQueue / Music / MediaFolder│
│  ├─ StageViewModel ──── Programme + active editing scope                  │
│  ├─ RackViewModel ───── Module/group faces + selection + reaction editor  │
│  └─ ModuleDrawerViewModel ─── Browser / Builder / InsertionTarget         │
└───────────────────────────────────────────────────────────────────────────┘
        ↓ commands only
Existing ProjectHistory / queue engines / visual_channels / sound_routes / module_engine
        ↓
Existing renderer, device adapters, recording/export and project persistence
```

One authoritative project state, one real playback clock, stable identifiers and a single undoable command path. View state (drawer open, focused scope, panel ratios, selected list row, hover/preview) must remain separate from serialized media/audio/composition state. Render loop should not reconstruct Tk widgets each frame. Do not introduce a second source/queue/effect model that diverges from the engine.

### 12.2 Exact likely source touch map (verified archive names)

| File / area | Responsibility during redesign |
|---|---|
| `app_source/instrument_shell.py` | Replace bottom Ingredients placement with left/centre/right layout; responsive resize and preservation of panel identity |
| `app_source/omne_workspace.py` | Remove duplicated global surface actions, mount integrated MediaDesk/ModuleDrawer, route actions to real commands |
| `app_source/instrument_media.py` | Music/A/B presentation rebuilt as two side-by-side visual queue columns + full-width audio deck; capture toggles and player transport |
| `app_source/instrument_mix.py` | Move fader above visual queues while preserving existing gesture semantics, Undo and Custom legacy state |
| `app_source/instrument_rack.py` | Stable rack header/scope and module-face projection, handoff to right drawer; no shelf-induced rack compression |
| `app_source/module_library.py` | Convert module library into drawer collection; preserve search, recipes, insertion-target validation and existing data services |
| `app_source/playable_rack.py` | Refactor current `ModuleBuilder(tk.Toplevel)` into an embeddable `ttk.Frame` builder content with optional compatibility wrapper; integrate it in the right drawer and preserve all parameters/promotions |
| `app_source/media_browser_view.py` and `creative_library.py` | Project-only folder view, filtering, safe project removal/relink; avoid conflating persistent catalogue with project membership |
| `app_source/music_queue.py`, `composition_queue.py`, `visual_channels.py`, `sound_routes.py` | Reuse semantic operations; modify only after specific transport/routing compatibility tests justify change |
| `app_source/instrument_sound_ui.py`, `instrument_timeline.py`, `conductor*.py` | Retain advanced functionality and mount contextually rather than remove |
| `app_source/frame_sources.py`, `multi_live.py`, `channel_camera_ui.py` | Keep real capture backends, device state/errors; never advertise unsupported camera/window/desktop routing |
| `app_source/ui_chrome.py` and widget helpers | Semantic tokens, icon grammar, focus/contrast/tactile feedback |
| Existing UI, media, playback, recording and project tests | Extend and adapt them to new presentation, not replace engine regressions with superficial screenshot assertions |

**Warning:** The archive contains inherited older layout structures (`instrument_app.py`, legacy entry code, workspace machinery) and current UX9 projection code. First identify runtime reachability and the actual entry class before deleting legacy code. Remove unused UI pathways only after tests demonstrate they are dead and current behaviour is preserved. This is a dependency audit, not a license to purge working engine files.

### 12.3 Compatibility and migration decisions

1. **A/B-only channels:** New UX10 projects expose exactly A and B. For old projects with C/D, retain an untouched original and permit explicit **Save As UX10** conversion with review of affected sources, effects, mix and programme output; a faithful automatic 4→2 mix is not generally possible. Until conversion, open safely in compatibility or read-only mode with clear explanation. Never silently drop channels.
2. **Custom opacity/mix:** Preserve legacy linked/unlinked semantics on load. A deliberate crossfader gesture activates complementary linked A/B mix with an undoable edit. No invisible normalization.
3. **Sound:** Preserve existing soundtrack events, routes, monitoring and reaction input identity; keep react-only microphone use distinct from output audio.
4. **Module/group data:** No schema reset, missing nested controls or lost reaction/keyframe bindings. Keep unknown extensions through round trips.
5. **Project media:** Preserve original filesystem paths and metadata; safe removal affects membership/references only, never disk originals.
6. **Preference migration:** Map old pane width/fraction and shelf-open values to new left width and right drawer state (closed default); do not reinterpret project content as UI preference.
7. **Tests:** Record old assertion expectations intentionally superseded, replace with contract-based tests, and keep the historic failures visible. Avoid claiming whole-history green if only a focused gate passes.

## 13. Design decisions / trade-offs

**ADR-UX10-01: Stable three-zone topology.** Chosen over unlimited dockable panels (too much user assembly) and tabbed single-pane workspaces (constant navigation). Trade-off: less arbitrary rearrangement, more predictable instrument use. Small-window drawer remains transient.

**ADR-UX10-02: Two visual decks, one MUSIC deck.** Chosen over four-plus surfaced visual channels. Trade-off: clearer real-time workflow; older >2-channel documents need explicit compatibility.

**ADR-UX10-03: Inline object controls, no permanent inspector.** Chosen over separate properties form and over modules with every parameter visible. Trade-off: less at-a-glance access to every technical field, but one-click contextual detail with zero loss of capabilities.

**ADR-UX10-04: Collapsible right module drawer.** Chosen over bottom shelf and modal library. Trade-off: drawer may temporarily overlay at smaller widths; direct insertion and auto-close minimise interference.

**ADR-UX10-05: Separate select from take.** Chosen over click-to-play ambiguity. Trade-off: explicit play gesture, much safer live editing.

**ADR-UX10-06: Model-preserving presentation refactor.** Chosen over port/rewrite. Trade-off: Tk constraints require careful resizing and focus architecture; avoids jeopardising mature synthesis, audio and export.

## 14. Ordered implementation programme — functional, independently testable slices

### UX10.0 — Evidence and preservation gate

- Fresh-extract UX9; establish exact launcher and current Python/Tk class wiring. Snapshot working output, list all controls and commands, map legacy UI references.
- Run current reported targeted tests and smoke tests on an available environment, record actual results; establish save/reopen and rendered MP4 golden fixtures. Preserve a known-good ZIP/checksum and source hash.
- Build a **feature-reachability matrix** of every existing control, location, command, model field, future UX10 surface and regression test. This prevents accidental feature reduction.
- Produce focused screenshots at 1600×900, 1280×800 and 1024×768 and an issue ledger with observed vs inferred findings.
- **Exit:** no UI mutation until working behavior and rollback path are documented.

### UX10.1 — Shell replacement and hierarchy

- Create new left MediaDesk container, central Programme+Rack, right ModuleDrawer; remove bottom shelf placement without deleting services.
- Slim top system strip, move global play/capture/FX buttons from it, bind exact commands at new positions.
- Preserve all project/view state and play clocks across layout resizing. Close drawer by default.
- **Exit:** programme and rack stable across sizes, no duplicate source controls or bottom Ingredients panel, save/reopen golden project unchanged.

### UX10.2 — A/B queues and mixer

- A/B vertical columns side by side, shared fader above, current/upcoming rows, true transport contract, camera/window source picker.
- Implement explicit select vs take; keyboard reorder, accessible status. Remove queue tab remnants and `More` menus whose actions now have visible homes.
- Add exact linked-mix/legacy indication and safe older-project handling.
- **Exit:** all queue operations work by mouse/keyboard, camera selection does not delete file queue, mix preserves scope, legacy mix remains truthful.

### UX10.3 — MUSIC and Project Media

- Full-width soundtrack/media-player queue and live reaction-input selector/meter with clear audio routes.
- One project folder with search, sort, type chips, safe remove/relink, import/drag target mapping. No albums/global-library leakage in this surface.
- **Exit:** audio and visuals remain persistent together, changing reaction mic cannot accidentally monitor/output, removal never touches disk original, no hidden essential audio queue.

### UX10.4 — Rack/card interaction overhaul

- Lock stable front-panel geometry; replace tiny repeated toolbars with main knob(s), readable selection/bypass, card actions and inline contextual details.
- Adapt reaction editor so it fits one selected card/context region with no clipping at 1024×768, and preserve advanced keyframes/controls.
- Improve group nesting and promotion grammar; preserve all module effects and internal parameters.
- **Exit:** build an audible/reactive effect chain without navigating a global property menu; precise controls still reachable; one gesture = one undo command; no repeated remount/scroll jump.

### UX10.5 — Right drawer and builder

- Move module browser and ModuleBuilder into right sidebar with same selection/target ownership as UX9.
- Searchable visual cards, contextual add, recipe browsing, build mode with back; active rack remains visible.
- Explicit insertion preview, auto-close, stale target rejection, drag and keyboard parity.
- **Exit:** users can add, reorder, group, edit, save and reapply without bottom shelf; no cross-owner silent insertion.

### UX10.6 — Recording, advanced tools and visual finish

- Consolidate system/record controls, relocate Conductor/timing/help/status; unify icons and semantic tokens.
- Tune microinteractions and hotkeys; verify real/empty/error/capture states; remove obsolete layout adapters only after reachability audit.
- **Exit:** clean output window, recording and capture safety, all existing advanced capabilities still available, consistent focus and contrast.

### UX10.7 — Owner acceptance / release qualification

- Run full retained functional suite, compare golden render/audio, verify source/dialog, video export and project round trips.
- Fresh-launch under physical Xorg environment; test real camera/mic, PC/App audio and desktop/window selection with truthful unsupported failure paths. Windows/macOS unqualified unless actually tested.
- At each of three window sizes, test keyboard navigation, no clipping, no nested-scroll traps, reduced motion and recovery from device dropout or invalid file.
- Run uncoached user tasks below. Do not declare release complete on automated tests alone. Preserve reversible handoff and complete changelog.

## 15. User-task acceptance / usability predictions

These are **targets**, not measured current outcomes. Gather a baseline on UX9 and compare with UX10 using identical assets and tasks, at least one novice and one experienced operator; prefer repeated trials over anecdotal praise.

| Task fixture | Ideal path | Proposed completion criterion |
|---|---|---|
| Import 2 videos + 1 song | `+ Files` / drop → thumbnails visible → queues | User knows where files went and can start a source without hunting |
| Load video into A then B | Project Media → explicit drag/drop or Add-to | A/B visible at once; no hidden tab; output takes only deliberately |
| Mix A and B | Move shared fader immediately above queues | Sees current ratio and result; midpoint matches linked 50/50 semantics |
| Activate webcam A | Camera toggle → optional device/window picker | Queue preserved; actual capture/permission state clear |
| Play MUSIC; react to microphone | MUSIC transport + Mic input selector | Distinguishes audibly playing file from reaction source/monitor routing |
| Add effect to Output | Select Output → `+` → choose effect from right | Correct target apparent, card appears and works without popup maze |
| Make a dial react to bass | Click `~` → Music → Low/Bass → Travel | Continuous visible feedback, remains within screen at 1024×768 |
| Modify advanced parameter and undo | Select card → details → numeric → Undo | Preserves exact value, keyframes, groups and history |
| Create and reuse module group | Group → Build sidebar → front controls → save recipe → reinsert | Existing module/recipe semantics round-trip |
| Remove a project file | Select asset → remove from project | Original file remains on disk; dependent occurrences handled safely |
| Record output with sound | `● Record` → Stop → verified output | Result matches live picture and intended audio route |
| Reopen project | Save → close/relaunch → Open | Identical logical mix, queue, source, rack, reaction and saved layout |

**Success criteria to establish with test participants:** no instruction needed for import/source/add-effect/mix/record; essential control discovery without hidden menus; fewer total interactions and navigation state changes than UX9; lower error rate; correct answers when asked “what is live?”, “what am I editing?”, “what is reacting to what?”, “what will be recorded?”, and “will removal delete my file?”. Quantify against UX9 baseline, not arbitrary marketing claims.

### 15.1 Automated acceptance tests

- Layout geometry and minimum click target dimensions; no left A/B overlap; both scrollable queues visible; rack remains playable at 1024×768.
- Mouse/keyboard/assistive label parity; focus retention after redraw, Escape cancellation, reduced motion and state-independent colouring.
- Two-channel creation; legacy C/D load and safe conversion path; linked mixing endpoints, centre, legacy Custom state, automation/undo.
- Queue add, select, take, restart, reverse, pause, fast forward, skip, repeat, reordering, source toggle and recovery; explicitly assert unsupported operations are disabled.
- Project library search/filter/sort, missing path relink, safe removal and external-file integrity.
- Module cards and secondary parameters, reaction bands/shape/travel, negative direction, groups/promotions/recipes and stale drawer insertion target rejection.
- Recording/export, active status, audio route difference, camera/screen/mic device failure, project change during import/audition.
- Render stability: no repeated widget recreation due to playback tick, no false recorded/saved claims, active clock and output session preserved through drawer and resize.

## 16. UX10 acceptance definition / no-go rules

UX10 **fails** if any of the following occurs, even when screenshots look better:

- It hides A or B behind tabs, or makes the MUSIC queue inaccessible during normal editing.
- It moves the module library or builder under the rack, or reduces the rack to a small strip when the library is open.
- It removes an engine feature or advanced control rather than moving it into an intelligible contextual location.
- It introduces a new arbitrary `More` dropdown in each card/queue as a substitute for a clear object model.
- User clicking a library/queue item unexpectedly changes on-air media or capture state.
- Right drawer inserts into the wrong owner after context changes.
- Legacy projects silently lose C/D, Custom mixing, reactions, routes, timing, keyframes, unknown fields or original media paths.
- File removal deletes a local original or allows orphaned occurrences without warning/recovery.
- Audio capture starts output or monitoring without clear authorisation; recorder silently omits included live audio.
- Small-screen controls clip, shift under the pointer, lose keyboard focus, or require horizontal scrolling within a module card.
- An attractive design is accepted without real engine regression tests and a fresh build run.

## 17. First implementation handoff (copy/paste)

> Implement Neospector UX10 from `Neospector_UX9_Connected_20261102.zip` using `Neospector_UX10_Complete_Interface_Overhaul_Plan_20261102.md` as the governing UX specification. Begin with UX10.0: identify the exact current launcher/UI wiring, audit command/field reachability, preserve a stable backup, verify the current targeted engine and UX tests, and record baseline screenshots. Do not create new features or rewrite the renderer, sequencer, audio bus or project schema unless an explicitly proved compatibility requirement demands it. Implement the three-zone interface as a **cohesive replacement**, not another overlay of existing toolbars: left side-by-side A/B queues with fader above and MUSIC/project-folder below; centre persistent programme above large tactile rack; right dismissible module library/builder; top only project/system/output/record/export. Preserve select-vs-take, exactly two visual channels for new projects, legacy Custom mix and C/D project safety, stable reaction/group/recipe internals, source permissions, undo, project files and output recordings. Use focused testable stages UX10.1–10.7; run real Tk screenshot/interaction checks at 1600×900, 1280×800 and 1024×768 and verify saved-project and video/audio semantics. Reject any pass that merely relocates clutter, hides primary controls in dropdowns, makes rack harder to use, or claims untested device capture. Deliver audited source, release ZIP, checksum, test evidence, comparison screenshots and a list of outstanding hardware qualification.

## 18. Remaining decisions deliberately kept visible

1. **Transport edge cases:** precise fast-forward scan duration and reverse semantics depend on the existing media source backends; do not draw enabled nonfunctional controls. Implement real seek where supported.
2. **Two-channel import of legacy C/D:** exact conversion requires a user-visible workflow because the old model can contain more than two independent visual layers. Archive-preserving compatibility is safer than silent visual reinterpretation.
3. **Window capture on Wayland:** current UX9 does not qualify this path. `Window` can appear only when a supported device backend can perform it, otherwise show unsupported and appropriate guidance.
4. **Small-window right drawer:** drawer overlays at constrained sizes rather than permanently shrinking the rack; automatic close after insertion should be tested with users.
5. **Capture/recording modes:** consolidate only documented and implemented paths. No fictional OBS connection or unverified routing assumptions.

---

**The desired product experience:** *The left hand loads and mixes media. The right hand builds and plays the rack. The eyes stay on the picture. Everything else stays out of the way until requested.*
