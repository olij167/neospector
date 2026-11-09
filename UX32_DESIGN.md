# UX32 design and architecture decision

## Why UX31 was insufficient

The Creative Controls popup repeated module authoring using preset selectors, while artists already edit effect chains, grouped macros and dynamic parameters in the persistent rack. UX32 removes the duplicate authoring surface. The runtime owns the transition field, and the existing effects rack owns how it is configured.

## Shared substrate, distinct semantics

- **Rack model:** Project.transition_rack contains the same Effect/Module data as other racks; nested groups, automation, protected slots, global undo/redo and module library are reused. Separate FX bypass is recorded in project.extra.transition_rack_bypassed. A/B/Output continue using existing owners.
- **Transition-specific semantics:** Transition evaluates a composited A/B bridge only while 0 < crossfade < 1; at both endpoints returns original source object. Special Reveal Field (`transition_reveal`) is a mask operator with Angle, Softness and Amount, not a normal image filter. General effects operate on the composited image with a blend envelope peaking mid-transition. Group macros use signal evaluator where provided. Echo and Frame Blend remain forbidden: they require history absent from this bridge.
- **Base transition:** Direct Shape, Curve and Edge parameters remain above the Transition rack, while the old style arrows are fast shortcuts. If no authored Transition rack exists, original UX31 preset transition settings remain valid, preserving earlier projects.
- **Inline variation:** Shared field grammar for Random Rack/Mutate across A/B/Transition/Output. Expandable second toolbar uses FlowRow for responsive wrapping; persistence in project.extra.randomise_settings; selected-only and locks remain explicit. It is not another window.
- **Audio controls:** Mixer + navigates to existing browser Sources page. Detection, queueing, fader participation and recording remain separate deliberate operations.
- **Contextual controls:** Native menu lifecycle preserved through `post_native_menu`, with `popup_coordinates` desktop-aware positioning. Styled popovers use shared context controller and outside-click/Escape dismissal. System Tk combobox and chooser behaviour is not globally overridden.

## Tradeoffs / guardrails

Reusing the existing Effect and group structure greatly reduces migration and duplicate editing code. The transition bridge deliberately omits history-dependent modules. A special field operator enables authored compositing rather than a preset+strength façade. This is a code and simulated Tk release: real capture, recording, A/B transition perceptual smoothness and export need owner acceptance.
