# UX37 implementation contract

## Theme state

- `app.theme_name` remains the single selected theme variable shared by the Welcome combobox and application preferences.
- `FamilyChromeMixin.apply_welcome_theme(name)` commits an explicit Welcome change through the active Appearance editor if open, otherwise through `OmneWorkspace.apply_theme`.
- `ThemeEditor.load_base()` sets the shared name before previewing the chosen built-in palette. `discard_preview` restores the last committed name and colours; `persist` commits/appends a custom theme when edited.
- `welcome_ui.show` registers `win.retheme()`; `OmneWorkspace.apply_theme()` calls it to recolour persistent native Tk frames, labels and canvas without destroying the window or losing scroll position.
- Exact built-in palette assignment is tested for all six published themes. No built-in theme data was modified.

## Preferences

- UX36 already embedded Theme Studio directly in Appearance; UX37 eliminates the remaining Sequence Settings popup by routing `sequence_settings()` to the existing Output Preferences page.
- Output offers project name, common canvas presets, custom dimensions, project duration and background in one page. Values are validated before applying, then committed together in a single project transaction.
- `PreferencesWindow.footer_frame` is packed before the expanding Notebook to keep Apply/Close reachable at smaller sizes.
- Welcome retains one Preferences entry; File-menu shortcuts retain direct Output/Recording navigation.

## Limitations

- Application-native colour picker dialogs, file/folder browsers and recording/output viewer are intentionally not removed; the request only replaces separate *advanced settings* windows.
- OS-native input device discovery varies by machine. Hardware recording/export and real-world GPU warnings remain outside this targeted UI change.
