#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ "$(uname -s)" == 'Darwin' ]] || { echo 'Run on macOS' >&2;exit 2; }
case "$(uname -m)" in arm64) ARCH='arm64';; x86_64) ARCH='x64';; *) exit 2;; esac
python3 scripts/prepare_source.py --verify-only
rm -rf build-work/source
SOURCE="$(python3 scripts/prepare_source.py --output "$ROOT/build-work/source" | tail -1)"
python3 -m pip install 'pyinstaller>=6.16,<7' 'pillow>=10.4,<13' 'numpy>=1.26,<3' 'tkinterdnd2>=0.4,<1'
for cmd in ffmpeg ffprobe codesign pkgbuild hdiutil; do command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2;exit 2; }; done
mkdir -p artifacts native/dist native/pyinstaller-build
ARGS=(--noconfirm --clean --windowed --name Neospector --osx-bundle-identifier space.omne.neospector
  --distpath "$ROOT/native/dist" --workpath "$ROOT/native/pyinstaller-build" --specpath "$ROOT/native"
  --paths "$SOURCE/app_source" --collect-all tkinterdnd2 --hidden-import PIL._tkinter_finder
  --add-data "$SOURCE/examples:examples"
  --add-data "$SOURCE/app_source/ui_profile.json:."
  --add-data "$SOURCE/updates/public.pem:updates"
  --add-binary "$(command -v ffmpeg):tools" --add-binary "$(command -v ffprobe):tools")
if command -v ffplay >/dev/null;then ARGS+=(--add-binary "$(command -v ffplay):tools");fi
python3 -m PyInstaller "${ARGS[@]}" "$SOURCE/app_source/neospector.py"
APP="$ROOT/native/dist/Neospector.app"
[[ -d "$APP" ]] || { echo 'Missing app bundle' >&2;exit 1; }
python3 - "$APP" <<'PY'
import pathlib,plistlib,sys
p=pathlib.Path(sys.argv[1])/'Contents/Info.plist';d=plistlib.loads(p.read_bytes())
d.update({'CFBundleShortVersionString':'0.7.25','CFBundleVersion':'41','NSCameraUsageDescription':'Use an explicitly enabled camera as a local visual source.', 'NSMicrophoneUsageDescription':'Use a microphone for local reaction and optional recording.', 'NSScreenCaptureDescription':'Capture a selected display or window for local audiovisual performance.'})
p.write_bytes(plistlib.dumps(d))
PY
if [[ -n "${NEOSPECTOR_APPLE_APPLICATION_ID:-}" ]]; then
  codesign --force --deep --options runtime --entitlements "$ROOT/native/macos_entitlements.plist" --sign "$NEOSPECTOR_APPLE_APPLICATION_ID" "$APP"
else
  codesign --force --deep --sign - "$APP"
  echo 'AD-HOC SIGNED: Gatekeeper may block distribution. Not a public release.' >&2
fi
codesign --verify --deep --strict "$APP"
PKG="$ROOT/artifacts/Neospector_0.7.25-ux41_macos-${ARCH}.pkg"
PACK_ARGS=(--component "$APP" --install-location /Applications --identifier space.omne.neospector --version 0.7.25)
if [[ -n "${NEOSPECTOR_APPLE_INSTALLER_ID:-}" ]];then PACK_ARGS+=(--sign "$NEOSPECTOR_APPLE_INSTALLER_ID");fi
pkgbuild "${PACK_ARGS[@]}" "$PKG"
STAGE="$ROOT/build-work/macos-dmg";rm -rf "$STAGE";mkdir -p "$STAGE";ditto "$APP" "$STAGE/Neospector.app";ln -s /Applications "$STAGE/Applications"
DMG="$ROOT/artifacts/Neospector_0.7.25-ux41_macos-${ARCH}.dmg"
hdiutil create -volname 'Neospector 0.7.25' -srcfolder "$STAGE" -ov -format UDZO "$DMG"
if [[ -n "${NEOSPECTOR_APPLE_NOTARY_PROFILE:-}" ]];then
  xcrun notarytool submit "$DMG" --keychain-profile "$NEOSPECTOR_APPLE_NOTARY_PROFILE" --wait
  xcrun stapler staple "$DMG"
  xcrun notarytool submit "$PKG" --keychain-profile "$NEOSPECTOR_APPLE_NOTARY_PROFILE" --wait
  xcrun stapler staple "$PKG"
else echo 'NOT NOTARISED — private/test candidate only.' >&2;fi
for item in "$PKG" "$DMG";do shasum -a 256 "$item" > "$item.sha256";done
echo "macOS $ARCH build candidates generated: $PKG $DMG"
