# UX33 · Authored transition animation and organised modules

## Scope and priority

Base: delivered UX32 release (0.7.16). Primary issue: the A/B wipe direction,
glitch and pixel transition animations were still selected as style presets even
though their appearance could be treated with rack modules. UX33 makes animation
generation part of that same rack. Secondary issue: module family organisation
and portable authoring/recipe import. Welcome and publication companion remain
out of scope.

## One rack, distinct semantics

- **A/B/Output**: persistent image processing of their respective channel/output.
- **Transition**: temporary A/B bridge in crossfade interior. Identity at both
  0% and 100%. Animation operators are available only here, yet ordinary
  non-history image FX can also be arranged between animation operators.
- **Modules**: individual parameterised operators in the existing Effect model.
- **Groups**: multiple operations editable as one module, with macro controls,
  per-member editing, reordering, bypass, undo and project persistence.

### Transition composition operators

| Module | Authorable dimensions | Function |
|---|---|---|
| Timing Curve | Start, end, acceleration curve, smoothing | Drives transition-local progress; can change the feel of any mask or slide |
| Reveal Field | Direction angle, softness, amount | Directional threshold mask; replaces individual wipe presets |
| Iris Field | Centre X/Y, invert, softness, amount | Radial animated mask |
| Pixel Field | Cell size, randomness, softness, amount | Deterministic pixel-cell reveal |
| Tear Field | Strip count, displacement, noise, softness, amount | Deterministic glitch-like tearing field |
| Slide Motion | Direction, travel, amount | Moves A and B across the visual field |

All use the shared parameter editor, including existing automation/reaction.
An authored geometry or timing module starts from a neutral A/B crossfade,
independent of the UX16 shape preset. Operations run in saved rack order except
that Timing Curve modifiers are collected to establish the transition-local
clock before spatial stages, allowing groups to be moved without breaking their
internal time relationship. Transient image FX remain enveloped at the midpoint.

**Legacy projects:** an empty Transition rack preserves the original UX16
transition kind/easing/effect. An FX-only Transition rack also retains the
legacy underlying crossfade treatment. Old data is not silently rewritten.
The old preset arrows and shape/easing/edge selector have been removed from
visible UI but retained as backward-compatible data parsers.

### Editable starter groups

Directional Wipe, Iris Bloom, Pixel Scatter, Glitch Tear, Moving Slide,
Soft Dissolve. Each is a *real editable group of registered primitive
operators*, not a hidden preset executor.

## Discoverability and organisation

The Module Library retains direct **All / Single / Groups / Saved** type
filters, searchable titles/operations/tags, grid/list modes and sorting.
It adds direct family chips (Motion, Colour, Texture, Spatial, Adjust,
Light, Time, Custom). Unsupported choices are disabled for the current
rack, not shown as broken actions. Motion operators and their factory
combinations are absent from normal A/B/Output racks. Imported custom
modules have type Saved and can be filtered with their authored family.

The preview's Transition button opens the same rack editor. The visible
Transition header describes composition rather than duplicating controls.

## Safe user-authored recipes

`*.neospector-module.json` files can describe ordered operations made from
registered primitives. A recipe supports a title, family, tags and bounded
numeric parameters. It creates an editable grouped module and stores it as a
normal versioned local ingredient. See `examples/recipes/Custom_Pixel_Gate.neospector-module.json`.

Strict validations: max 64 KiB input, 1–16 operations, 1–80-character title,
up to 8 tags, existing registry keys only, finite parameters within declared
bounds, no history FX in transition, no transition FX in ordinary families,
no unknown schema fields. There is **no eval/exec, scripting, Python import,
network access or arbitrary shader execution**. This is declarative
programming over registered operators, not an API for new executable effects.

## Constraints and verification

No changes to camera/audio source capture, queues, recording, rendering
architecture, exporting, or installer dependency supply. Verify with
`python3 tools/verify_ux33.py`, then owner test the live A/B transition smoothness,
changing group internals, saved project reload, transition undo, audio and export.
Automated tests do not establish hardware capture or perceptual acceptance.
