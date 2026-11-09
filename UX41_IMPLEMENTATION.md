# UX41 engineering notes

**Baseline:** Verified UX40 source ZIP (`SOURCE_IDENTITY.json` includes its checksum). Project format 1.3.0 unchanged.

## Root causes and decisions

1. **Reaction depth reset.** The slim `ux18_reaction_surface` Scale received periodic `refresh` calls which wrote the persisted value back during active dragging. It also read the Tk variable on mouse release, potentially before a queued Scale callback. The new small control marks an active drag, refuses external value projection while dragging, reads the actual Scale thumb at release, then makes a single validated `RackContext` transaction. The signed `±%` label and tooltip explain native travel.
2. **Master routing.** Existing `module_reaction.apply_all_reactions` handled on/off only. New `apply_all_routing` updates Source and Band for all exposed parameters in one transaction without altering reaction amounts, keyframes, modes, attack, release or threshold. Chosen master routing is retained when React All is enabled later. The controls reuse the footer, not another panel or popup.
3. **Automatic A/B timing.** `timed_mix.py` samples a bounded, deterministic, serializable 4-stage clock (hold A, ease to B, hold B, ease to A). A single `project.extra.ux41_pingpong` stores enabled, start time, hold, fade and first channel. `SignalEvaluator.value` uses it only for the actual voice_mix parameter. The alternate independent-channel compositor also respects the same mix when auto is enabled. This avoids timer churn, per-frame project mutation, or inconsistent preview/export progress. Automatic mode disables manual fader; enabling React ends automatic mode.
4. **Performance.** All new input writes commit on meaningful actions; changing the timing does not cause a per-keypress transaction. The new mix follows the existing render sampling, and UI style changes are conditional. UX39 coalescing and UX40 input persistence are preserved.

## Acceptance evidence

- New UX41 unit/Tk tests: reaction slider drag and bulk routing; deterministic Hold/Fade; reversals; invalid timing; save/load; sampled evaluator; visible controls.
- Bounded UX39, UX40, UX41 and signed UX38 updater regression gate: see VERIFIED_RESULTS_UX41.md.
- Native physical audio and hardware capture are unverified.
