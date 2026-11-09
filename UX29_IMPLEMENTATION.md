# UX29 — Implementation, contracts and limits

## 1. Files and Sources are one browser

- `app_source/ux23_source_shelf.py`: one SourceShelf with browser-local `Files` and `Sources` tabs; no global A/B/Audio destination selector and no footer placement buttons. `SourceShelf.show()` maps legacy camera/screen/audio mode requests to the new Sources page for compatibility.
- `app_source/ux22_project_browser.py`: displays all assets regardless of destination; Now, Next and End actions on each row invoke one contextual choice menu, only then use established `app.place_media`. Selection alone is inert.
- `app_source/ux29_browser_model.py`: pure eligibility rules for files and live inputs. Soundless video is visual-only; a video with audio can route to both visual or sound. Incompatible batches have no destination.
- `app_source/ux29_source_list.py`: discovers cameras, microphones, screens, windows and per-application sound using existing backend enumeration. Sources are separate rows with matching inline actions; the destination menu calls live inputs Audio · timed reaction cue to avoid misleading users about a live cue being a playlist track. Slow device scanning is off Tk's UI thread; late responses are discarded after project/context changes.

## 2. Audio Queue and Mixer share an authority

- `app_source/instrument_media.py`: adds QUEUE/MIX mode selector inside Audio tray. Changing mode opens the right-side Audio tray and controls whether the existing transport or SourceMixer is visible. The currently selected mode is not an independent sound state.
- `app_source/sound_panel.py`: uses original `SourceMixer` with gain/mute, Sound/React/Monitor routing and audio meters; skips mixer-only updates while hidden. Live inputs default off and are intentionally enabled by the user.
- `app_source/ux17_sidebar.py`, `app_source/ux26_queue_layout.py`: share preview-bound vertical area with A/B queues, allocating more space to a visible mixer without hiding other queues or overflowing the preview.

## 3. Preserved behaviour / not implemented

Programme history, A/B visibility, queues, stop/repeat, per-source gain, existing camera control, reaction engine, sound monitoring, project serialization, recording and export remain existing implementations; no new codec, capture engine or project migration has been added. Some platforms have no application-stream enumeration, and sound capture requires tools and permissions. Publication/owner companion and startup-menu redesign are intentionally deferred until user accepts this work.

## 4. Verification boundary

- Nine UX29 interaction/integration tests were added, plus 40 retained compatibility and playback tests; gate = 48. Eight obsolete historical UI assertions are explicitly excluded and documented inside the JSON result.
- No physical device connection, running audio-app capture, recordings or output export on the owner's workstation have been demonstrated by headless Tk tests.
