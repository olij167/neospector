# UX34 verification record · 8 November 2026

## Executed checks on working source

- New UX34 desktop/Tk test module: **8/8 passed**. Assertions include no
  unmount of A when B opens; no-op Files tab unchanged; Treeview stable row
  identity under forced refresh; zero redundant rack relayouts during stable
  periodic refresh; cancel-demo save guard; narrow welcome layout; safe
  learn-in-place Effects access.
- Combined retained UX33/UX34 acceptance runner: **100/100 passed**, zero
  failed, skipped or errored tests according to its saved `acceptance.json`.
  Fifteen older assertions retired by earlier releases remain documented by
  exact identifier in `tools/verify_ux34.py`; none was counted as passing.
- Startup smoke, actual `app_source/neospector.py` entry: **PASS**. Bundled
  First Light example, 56 presented preview frames, no reported phase errors,
  current toolbar controls visible, Welcome has three expected navigation
  actions, clean shutdown. Synthetic Xvfb; no physical AV certification.
- `compileall` for the application, new tests and runners: **PASS**.
- Benchmark methodology: isolated Xvfb at 1800x1000, NeospectorApp(test_mode)
  after startup; same selected Transition rack; 60 warm `refresh(False)` calls
  with `update_idletasks` per revision. Median UX33 0.501 ms versus UX34
  0.296 ms; p95 UX33 0.645 ms versus UX34 0.365 ms. This represents the
  measured Tk refresh path only, not the video compositor or physical hardware.

## Fresh archive validation

The final ZIP contains its own `MANIFEST.sha256` and is independently checked
at extraction time. Installer `--check` verifies every file without installing,
launching or altering user preferences. The outer ZIP checksum is also provided.

## Known limits

The runner wrapper occasionally remained active after its complete PASS report,
causing an external command timeout; the result JSON and test log contain the
completed 100/100 PASS run. Hardware source capture, actual Spotify/PipeWire
routing, recording/export, perceived frame pacing and owner usability acceptance
remain unverified on Zorin. The owner publication companion is not in UX34.
