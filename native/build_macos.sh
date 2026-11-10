#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)";cd "$ROOT"
[[ "$(uname -s)" == Darwin ]] || { echo 'Run on macOS' >&2;exit 2; }
case "$(uname -m)" in arm64) ARCH=arm64;;x86_64) ARCH=x64;;*)exit 2;;esac
VERSION="$(python3 -c 'import ast,pathlib;p=ast.parse(pathlib.Path("app_source/release_identity.py").read_text());print(next(n.value.value for n in p.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=="VERSION" for x in n.targets)))')"
[[ "$VERSION" != "0.7.25-ux41" ]] || { echo 'Prepare the new release identity first' >&2; exit 3; }
for cmd in python3 ffmpeg ffprobe codesign pkgbuild xcrun spctl;do command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2;exit 2; };done
python3 -m pip install 'pyinstaller>=6.16,<7' 'pillow>=10.4,<13' 'numpy>=1.26,<3' 'tkinterdnd2>=0.4,<1' 'cryptography>=44,<48'
mkdir -p artifacts native/dist native/pyinstaller-build
ARGS=(--noconfirm --clean --windowed --name Neospector --osx-bundle-identifier space.omne.neospector
  --distpath "$ROOT/native/dist" --workpath "$ROOT/native/pyinstaller-build" --specpath "$ROOT/native"
  --paths "$ROOT/app_source" --collect-all tkinterdnd2 --hidden-import PIL._tkinter_finder
  --add-data "$ROOT/app_source/ui_profile.json:."
  --add-binary "$(command -v ffmpeg):tools" --add-binary "$(command -v ffprobe):tools")
python3 -m PyInstaller "${ARGS[@]}" "$ROOT/app_source/neospector.py"
APP="$ROOT/native/dist/Neospector.app"
[[ -d "$APP" ]] || { echo 'Missing Neospector.app' >&2;exit 2; }
python3 -m PyInstaller --noconfirm --clean --onefile --console --name NeospectorUpdater \
  --distpath "$ROOT/native/dist" --workpath "$ROOT/native/pyinstaller-updater" --specpath "$ROOT/native" \
  --paths "$ROOT/app_source" "$ROOT/app_source/native_installer_helper.py"
install -m 0755 "$ROOT/native/dist/NeospectorUpdater" "$APP/Contents/MacOS/NeospectorUpdater"
mkdir -p "$APP/Contents/MacOS/updates"
cp "$ROOT/updates/public.pem" "$APP/Contents/MacOS/updates/public.pem"
python3 - "$APP" "$VERSION" <<'PY'
import pathlib,plistlib,sys
p=pathlib.Path(sys.argv[1])/'Contents/Info.plist';d=plistlib.loads(p.read_bytes());version=sys.argv[2]
d.update({'CFBundleShortVersionString':version.split('-')[0],'CFBundleVersion':''.join(x for x in version if x.isdigit())[-8:],
 'NSCameraUsageDescription':'Explicitly enabled camera visual source.','NSMicrophoneUsageDescription':'Optional local audio-reactive input.',
 'NSScreenCaptureDescription':'Explicitly selected live screen source.'})
p.write_bytes(plistlib.dumps(d))
PY
if [[ -n "${NEOSPECTOR_APPLE_APPLICATION_ID:-}" && -n "${NEOSPECTOR_APPLE_INSTALLER_ID:-}" && -n "${NEOSPECTOR_APPLE_NOTARY_PROFILE:-}" ]];then
  codesign --force --deep --timestamp --options runtime --sign "$NEOSPECTOR_APPLE_APPLICATION_ID" "$APP"
else
  codesign --force --deep --sign - "$APP"
  echo 'Private build only: missing Apple Developer ID or notary credentials' >&2
fi
codesign --verify --deep --strict "$APP"
PKG="$ROOT/artifacts/Neospector_${VERSION}_macos-${ARCH}.pkg"
ARGS=(--component "$APP" --install-location /Applications --identifier space.omne.neospector --version "${VERSION%%-*}.${VERSION#*-ux}")
if [[ -n "${NEOSPECTOR_APPLE_INSTALLER_ID:-}" ]];then ARGS+=(--sign "$NEOSPECTOR_APPLE_INSTALLER_ID");fi
pkgbuild "${ARGS[@]}" "$PKG"
if [[ -n "${NEOSPECTOR_APPLE_APPLICATION_ID:-}" && -n "${NEOSPECTOR_APPLE_INSTALLER_ID:-}" && -n "${NEOSPECTOR_APPLE_NOTARY_PROFILE:-}" ]];then
  xcrun notarytool submit "$PKG" --keychain-profile "$NEOSPECTOR_APPLE_NOTARY_PROFILE" --wait
  xcrun stapler staple "$PKG"
  xcrun stapler validate "$PKG"
  pkgutil --check-signature "$PKG"
  spctl --assess --type install --verbose=4 "$PKG"
else echo 'NOT NOTARISED — do not publish.' >&2;fi
shasum -a 256 "$PKG" > "$PKG.sha256"
echo "macOS native PKG candidate: $PKG"
