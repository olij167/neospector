#!/usr/bin/env bash
# Run only from the checked-out olij167/neospector repo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REPO='olij167/neospector'
TAG='v0.7.25-ux41'
ARCHIVE="${NEOSPECTOR_UX41_ARCHIVE:-$HOME/Downloads/Neospector_UX41_Final_Reactions_PingPong_20261109.zip}"
MODE="${1:---check}"
case "$MODE" in --check|--publish) ;; *) echo 'Usage: bash scripts/publish_first_release.sh --check|--publish' >&2;exit 2;;esac
python3 scripts/verify_first_release.py "$ARCHIVE"
[[ "$(git remote get-url origin)" == 'https://github.com/olij167/neospector.git' ]] || { echo 'Incorrect Git remote' >&2;exit 2; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Commit/push source changes before publishing' >&2;exit 2; }
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || { echo 'Local HEAD differs from origin/main; push first' >&2;exit 2; }
command -v gh >/dev/null || { echo 'GitHub CLI gh is required' >&2;exit 2; }
gh auth status >/dev/null
if gh release view "$TAG" -R "$REPO" >/dev/null 2>&1;then echo "Release $TAG already exists. Refusing to replace or clobber assets." >&2;exit 2;fi
[[ "$MODE" == --publish ]] || { echo 'CHECK ONLY: No release was created. To publish pass --publish.';exit 0; }
gh release create "$TAG" "$ARCHIVE" "$ROOT/source/$(basename "$ARCHIVE").sha256" "$ROOT/web/stable.json" "$ROOT/web/releases.json" \
 -R "$REPO" --target main --title 'Neospector 0.7.25 UX41 — Linux Xorg evaluation' \
 --notes 'Accepted Neospector UX41 native Linux source release, signed automatic-update manifest, and public platform catalogue. Windows and macOS native installer candidates are not yet approved for distribution.' --latest
printf '\nPUBLICATION CREATED: https://github.com/%s/releases/tag/%s\n' "$REPO" "$TAG"
echo 'Next: verify GitHub assets, then run the native CI candidate workflow.'
