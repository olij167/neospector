# UX38 — Owner acceptance card

1. **Welcome & main instrument:** Launch normally, open Welcome, verify previous project/media controls, A/B/Audio, effects, recording, and preview remain available. No live input starts automatically.
2. **Updates:** Open File → Check for Updates…, Welcome → Check for Updates and Preferences → General → Check for updates now. All must use the same update window. Enable/disable auto checking and restart; the setting must persist.
3. **Offline check:** Disable Wi-Fi/network and launch. Instrument must start without a blocking dialog or freeze. Updates should be reported unavailable only when explicitly checked.
4. **Signed public feed:** After publishing a real new signed release, launch the previous installed version. Verify only the newer release appears, with its release notes.
5. **Download only:** Download but do not install; confirm existing project and files remain untouched.
6. **Install & restart:** Save project, approve install. Verify new version starts through the managed launcher and the previous extracted copy remains intact. Close without saving changes and verify update does not proceed.
7. **Rollback:** After one managed version update, run `python3 tools/rollback_update.py --yes` from the installed release and launch from `~/.local/share/omne/neospector/launch.sh`. Previous managed version should open.
8. **Publication:** Use owner companion to stage a ZIP using your owner private key, inspect stable.json, and test SSH or rclone upload only to a confirmed deployment target. Verify signature tampering is rejected.
9. **Hardware acceptance:** Camera, mic, individual application audio, recording and export on Zorin remain owner-only checks.

**Note:** The proposed `https://omne.space/neospector/updates/stable.json` feed is not yet provisioned by this local build. No public availability claims are made until it is actually deployed and checked.
