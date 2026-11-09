# UX36: Final Welcome, Preferences, and Theme consolidation

Baseline: UX35 (0.7.19-ux35), project format 1.3.0 preserved.

## Single editor and shared routes
- `welcome_ui.py` presents project actions, recents, default devices/media and a compact appearance choice. No First Light or tutorial strip.
- `preferences_ui.py` has five pages. `ThemeEditor`, extracted from the standalone `ThemeStudio` widget in `ui_chrome.py`, occupies the Appearance page directly. Its controls are fully scrollable. Both File → Theme Studio and File → Appearance target that page.
- Live preview uses the existing app apply_theme contract. Apply persists the selected built-in theme or a new custom palette, without overwriting the six published definitions. Close without Apply restores the previous palette. Save as/Import/Export remain available.
- Device defaults use `device_defaults.available_input_defaults`, the existing `live_sources.enumerate_devices` discovery provider, and preservations for unplugged saved selections. The provider only enumerates, never starts capture. PipeWire PulseAudio device names are discovered via `pactl` when available; monitors are excluded from mic defaults.
- The media-folder field stores a path string with optional folder chooser, and bounded auto-import is optional. Empty folder allowed when auto-import disabled; otherwise an existing folder is required.
- General has Settings / Updates & Support together. The official website opens for update checking because a signed update feed has not been configured.

## Themes
Published order: Pungent Funk, Space Funk, Smitzu Funk, LindZ Funk, Beth Funk, Mik Funk. Their builtin appearance types and exact palettes remain unchanged. Legacy aliases map to original approved names.

## Acceptance boundaries
Synthetic Tk and source tests validate mapping, preview rollback, device default persistence and shared routes. No physical device activation, Chromium GPU error repair, export change or new owner companion is included in UX36.
