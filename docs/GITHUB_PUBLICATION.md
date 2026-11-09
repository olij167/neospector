# GitHub Releases + Cloudflare Worker (no R2)

Status: ready for source import / owner release publication, **not yet live**.

## First release

1. Import verified UX41 files using `bootstrap_ux41_repo.py` from the separate preparation kit.
2. Inspect changes and commit/push to `olij167/neospector`.
3. Run `bash scripts/publish_first_release.sh --check` and then, explicitly, `--publish`.
4. Review the GitHub release assets: original ZIP, its `.sha256`, `stable.json`, `releases.json`. No private PEM.
5. Run `gh workflow run neospector-native-candidates.yml -R olij167/neospector`; review candidates, do not publish unsigned binaries.

## Cloudflare

`cd web && wrangler deploy` after confirming routes do not conflict. Only `/downloads/neospector*` and `/neospector/updates/*` are configured. Do not alter `/waves`, `/waves-demo` or the main site Worker.

- `/downloads/neospector` serves the public page.
- `/downloads/neospector/releases.json` and `/neospector/updates/stable.json` are proxied from the latest GitHub Release assets.
- The `/neospector/updates/<archive-name>.zip` route and the Linux ZIP download alias fetch the same GitHub Release object. The Worker streams the response; it **does not** redirect the client to GitHub, keeping the signed updater's same-origin requirement.
- All unauthenticated GitHub requests depend on the repository/release being public. There is no R2 binding and no secrets.

## Future publication

The owner signing key remains strictly on the owner's machine. Stage a new signed ZIP + `stable.json` + updated `releases.json` as assets of a new public GitHub Release that is marked **Latest**. Check that the signed manifest archive name and checksum match the uploaded ZIP. Native entries in `releases.json` must remain `ready=false` until the platform passes native acceptance and any required signing/notarisation.

**Limitations:** Windows/macOS native builds and in-app update transports are not production-qualified. Signed-update client still handles Linux x64. Do not use GitHub Actions artifacts as public release downloads until accepted.
