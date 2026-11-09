# Neospector

**OmN-e Neospector — by Pungent Funk.** Native, local-first audiovisual performance instrument.

Source baseline: **0.7.25-ux41** (accepted Linux Xorg evaluation build, 9 November 2026).

## Source and release integrity

- `app_source/`, `tools/`, `tests/`, `examples/` and supporting files contain the verified UX41 release source.
- The original, SHA-256-pinned, Ed25519-signed UX41 ZIP lives in **[GitHub Releases](https://github.com/olij167/neospector/releases)**, not Git history.
- `source/*.sha256`, `web/stable.json` and `updates/public.pem` are public verification materials. **Never commit the private owner signing key, tokens, or credentials.**
- `MANIFEST.sha256` describes original UX41 files; distribution infrastructure is outside that manifest.

## Native build candidates

`Actions → Neospector UX41 native installer candidates → Run workflow` builds candidate Linux DEB, Windows Setup EXE/portable ZIP, and Apple Silicon/Intel macOS DMG+PKG artifacts. Windows/macOS binaries are **not yet signed, notarised, native-tested, or publicly released**. In-app signed updates are currently Linux-only.

The workflow downloads the exact accepted source ZIP from the `v0.7.25-ux41` GitHub Release and verifies its SHA-256 and internal 413-file manifest before building. The `.deb` is also a Zorin acceptance candidate.

## Public website and update service

The Cloudflare Worker lives in `web/` and streams PUBLIC GitHub Release files through `omne.space` without R2. The routes are limited to:

- `/downloads/neospector` — download page
- `/downloads/neospector/files/latest/*` — approved download aliases
- `/neospector/updates/stable.json` — signed Linux update manifest
- `/neospector/updates/Neospector_*.zip` — signed update ZIP

**Do not deploy web routes until repository release assets are published and route conflicts have been checked.** `web/releases.json` keeps native platforms disabled pending acceptance.

## Verify

```bash
python3 scripts/prepare_source.py --verify-only   # needs source ZIP downloaded from GitHub Release
python3 scripts/verify_publication.py              # same requirement
python3 -m unittest discover -s tests -p test_distribution.py -v
node --test tests/github_worker.test.mjs
```

For complete local-release and deployment instructions see `docs/GITHUB_PUBLICATION.md`.
