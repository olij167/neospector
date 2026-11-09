# UX36 verification — 2026-11-08

- Baseline: full delivered UX35 0.7.19-ux35 archive, SHA-256 `64ded490a532b108dee697006da0cfc34be7fea2f864835ad9bb0f68d93ed15a`.
- Working-source selected gate: **119/119 PASS**, isolated Xvfb, ~57.6 seconds. It retains UX26–UX35 queue, playback, rack, capture-control and module cases. Two UX34 onboarding assertions were retired by exact test ID, because the user explicitly removed First Light and Learn in Place; their replacement routes are validated by UX36 tests.
- New UX36 tests: **14/14 PASS** including six published Funk themes, preference preview rollback, theme custom-copy isolation, discovered input dropdowns, immediate Welcome default saving, optional folder setting, General Updates/Support and direct appearance editor.
- Working-source application-entry smoke: **PASS**, 56 preview frames, 0 Tk callback errors, 0 phase errors, clean close; demo media only.
- Reviewed virtual-display screenshots for Welcome, Devices & Media and full Appearance editor. Editing/palette controls use a scrollable Appearance area, not a separate Theme Studio window.
- Physical Zorin hardware, Spotify application audio, actual export quality and owner visual approval remain pending; these tests do not claim otherwise.
- User-provided UX35 logs mention Chromium/Mesa/NSS errors; there is no Neospector Python exception in those extracts. This UI pass does not modify graphics drivers or Chromium.
