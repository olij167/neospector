#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)";cd "$ROOT";PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null;command -v ffmpeg >/dev/null;command -v ffprobe >/dev/null;command -v ffplay >/dev/null
VERSION="$($PYTHON_BIN - <<'PY'
import ast,pathlib
p=pathlib.Path('omne_sequencer.py');t=ast.parse(p.read_text(encoding='utf-8'));print(next(ast.literal_eval(n.value) for n in t.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='VERSION' for x in n.targets)))
PY
)"
case "$(uname -m)" in arm64|aarch64) ARCH_LABEL=arm64;; x86_64|amd64) ARCH_LABEL=x64;; *) exit 2;; esac
APP_NAME="OmN-e Sequencer";BUNDLE_ID="${OMNE_MACOS_BUNDLE_ID:-space.omne.sequencer}";APP_IDENTITY="${OMNE_MACOS_APPLICATION_IDENTITY:-}";INSTALLER_IDENTITY="${OMNE_MACOS_INSTALLER_IDENTITY:-}"
VENV="$ROOT/.build-venv"; [[ -x "$VENV/bin/python" ]] || "$PYTHON_BIN" -m venv "$VENV"; PYTHON_BIN="$VENV/bin/python"
"$PYTHON_BIN" -m pip install --upgrade pip;"$PYTHON_BIN" -m pip install 'pyinstaller>=6.22,<7' 'pillow>=10.4,<13' 'numpy>=1.26,<3';rm -rf build dist dist-macos;mkdir -p dist-macos
ARGS=(--noconfirm --clean --windowed --hidden-import=PIL._tkinter_finder --name "$APP_NAME" --osx-bundle-identifier "$BUNDLE_ID" --add-binary "$(command -v ffmpeg):tools" --add-binary "$(command -v ffprobe):tools" --add-binary "$(command -v ffplay):tools" --add-data "ui_profile.json:." --add-data "../examples:examples")
[[ -z "$APP_IDENTITY" ]] || ARGS+=(--codesign-identity "$APP_IDENTITY")
"$PYTHON_BIN" -m PyInstaller "${ARGS[@]}" ./omne_sequencer.py
# Native capture requires visible, purpose-specific consent in the signed bundle.
"$PYTHON_BIN" - <<'PYINFO'
import pathlib,plistlib
p=pathlib.Path('dist/OmN-e Sequencer.app/Contents/Info.plist')
v=plistlib.loads(p.read_bytes())
v['NSCameraUsageDescription']='Use the selected camera as an explicitly started local visual source or recorded take.'
v['NSMicrophoneUsageDescription']='Use the selected microphone for local visual reaction and optional recorded takes.'
v['CFBundleShortVersionString']='0.3.1';v['CFBundleVersion']='0.3.1.1'
p.write_bytes(plistlib.dumps(v))
PYINFO
if [[ -n "$APP_IDENTITY" ]]; then
  codesign --force --deep --options runtime --entitlements "$ROOT/macos_entitlements.plist" --sign "$APP_IDENTITY" "$ROOT/dist/$APP_NAME.app"
else
  codesign --force --deep --sign - "$ROOT/dist/$APP_NAME.app"
fi
APP_PATH="$ROOT/dist/$APP_NAME.app";PKG="$ROOT/dist-macos/OmN-e_Sequencer_v${VERSION}_macOS_${ARCH_LABEL}.pkg";PKG_ARGS=(--component "$APP_PATH" --install-location /Applications)
[[ -z "$INSTALLER_IDENTITY" ]] || PKG_ARGS+=(--sign "$INSTALLER_IDENTITY")
pkgbuild "${PKG_ARGS[@]}" "$PKG"
DMGROOT="$ROOT/dist-macos/dmg-root";rm -rf "$DMGROOT";mkdir -p "$DMGROOT";cp -R "$APP_PATH" "$DMGROOT/";ln -s /Applications "$DMGROOT/Applications";DMG="$ROOT/dist-macos/OmN-e_Sequencer_v${VERSION}_macOS_${ARCH_LABEL}.dmg";hdiutil create -volname "$APP_NAME $VERSION" -srcfolder "$DMGROOT" -ov -format UDZO "$DMG" >/dev/null;rm -rf "$DMGROOT"
shasum -a 256 "$PKG" > "$PKG.sha256";shasum -a 256 "$DMG" > "$DMG.sha256";echo "macOS package complete: $PKG / $DMG"
