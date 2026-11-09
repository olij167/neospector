# UX35 Design & Implementation — 2026-11-08

## User tasks
1. Start work via new project, recent/open project, first-light example or import.
2. Set default camera and microphone, optionally auto-import a directory of local media on new empty projects.
3. Configure Output and Recording without hunting through multiple windows.
4. Reach Theme Studio, check update website, or support product directly without detours.
5. Edit all module parameters without obscuring controls on their last row.

## UI architecture
- `app_source/welcome_ui.py`: task-first, scrollable responsive Tk welcome surface with recent-project actions, brand hierarchy and direct destinations.
- `app_source/preferences_ui.py`: singleton Preferences Toplevel, six Notebook pages, explicit Apply, saved profile defaults. File and Welcome call `app.open_preferences(page)`; direct output/recording menu commands route there.
- `app_source/omne_workspace.py`: preferences state, shared window lifecycle, menu routes, optional bounded import; no new capture pathway.
- `app_source/instrument_rack.py`: faceplate height calculated after visible fader/control rows are known, with footer clearance. Existing parent rack scroll remains responsible for tall collections.
- `app_source/neospector_console.py`: controlled new-project and startup auto-import entry points.

## Safety and boundaries
- Default devices are identifiers/preferences, not permission to start capture.
- Auto-import uses supported suffixes, skips symlinks and nested folders, max 200 items, and applies only on an empty project.
- No automatic update API/feed: menu opens `https://omne.space/` for update checks. A single support action opens `https://omne.space/support`; website availability/destination not verified from this offline build.
- Project format 1.3 and existing AV render/record/export systems are unchanged.

## Acceptance
- See `tools/verify_ux35.py`, `tests/test_ux35_preferences_welcome.py`, and the owner card.
- Testing of physical device selection and output export remains for the Zorin owner.
