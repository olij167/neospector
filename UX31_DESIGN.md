# UX31 · Two scopes, one advanced editing grammar

## Purpose
Reduce configuration and visual density without reducing the power of existing instrument workflows. The UI is an instrument: a fader strip exists only when a source is engaged, while inputs remain discoverable in the Sources browser and + action.

## Ownership and compatibility
- **Sound mix**: `sound_routes` and `source_states()` remain authoritative. The new sparse `DeskFaderMixer` is a projection of active entries, not a new mix model. A soundtrack with queued audio can appear while paused, a channel-sound strip needs eligible audio plus an enabled route, and external live captures need a starting/live state. No source is enabled merely by opening MIX.
- **Transition FX**: the saved `project.extra['ux16_transition']` is extended, not replaced. Default remains a plain crossfade. Shape, easing and softness control the existing transition compositor. A bounded, transient effect draws from the established `effects_engine.EFFECTS` primitives and is enveloped to zero at A/B endpoints. History-dependent effects are unavailable here because they need the existing rack's frame-history provider.
- **Rack variation**: existing `randomise_settings`, `apply_rack_randomise`, `vary_rack`, group locks, seed and inline rack controls remain authoritative. Advanced selection and reproducibility surface existing capabilities rather than another module graph.

## Shared vs distinct
The **Creative Controls** editor provides the same typography, spatial rhythm, explicit Save/Apply and reversible actions for both topics. Its mutually exclusive pages are *Transition FX* (temporal bridge) and *Rack Variation* (module configuration). They share visual grammar and effect discovery, but **do not share project fields or execute each other's actions**. A button from Transition opens Transition; a button from the Library/Rack opens Rack, without extra navigation.

## Boundary decisions
The transition editor only uses non-temporal effects from the shared registry. Full-time animations, audio-reaction mappings, grouped module chains and time-history effects remain in the module rack. This avoids copying module APIs into the transition engine and avoids affecting existing programme audio or recording.

## Verification
`tools/verify_ux31.py` runs UX31 state and Tk tests plus selected retained coverage. Historical tests whose core expectation contradicts a current owner requirement are excluded by exact ID with reasons. Live hardware tests are still manual.
