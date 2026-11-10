#!/usr/bin/env bash
# UX42 Linux self-contained candidate. Build dependencies are never installed
# on the customer's device and the launcher never downloads or runs Python pip.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
APP_VERSION="$(python3 -c 'import ast,pathlib; p=ast.parse(pathlib.Path("app_source/release_identity.py").read_text()); print(next(n.value.value for n in p.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=="VERSION" for x in n.targets)))')"
DEB_VERSION="${APP_VERSION/-ux/~ux}"
[[ "$APP_VERSION" != "0.7.25-ux41" ]] || { echo "Prepare a new release version in Owner Companion before native building" >&2;exit 3; }
[[ "$(uname -s)" == 'Linux' ]] || { echo 'Linux builder only' >&2;exit 2; }
case "$(uname -m)" in x86_64|amd64) ARCH='x64';DEBARCH='amd64';; *) echo 'Only x86-64 candidate supported' >&2;exit 2;; esac
for cmd in python3 dpkg-deb ffmpeg ffprobe;do command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2;exit 2;};done
# Build from current accepted checkout. This intentionally does not overwrite
# immutable v0.7.25-ux41 source archives or the published Linux DEB.
for f in app_source/neospector.py app_source/neospector_console.py app_source/release_identity.py app_source/ux42_viewport.py;do
  [[ -f "$f" ]] || { echo "Missing source: $f" >&2;exit 2; }
done
VENV="$ROOT/build-work/native-builder-venv"
if [[ ! -x "$VENV/bin/python" ]];then python3 -m venv "$VENV";fi
"$VENV/bin/python" -m pip install 'pyinstaller==6.16.0' 'pillow==12.3.0' 'numpy==2.3.5' 'tkinterdnd2==0.4.4.1' 'cryptography>=44,<48'
# Use the same isolated build runtime for tests, not system Python (which may lack NumPy).
"$VENV/bin/python" -m unittest discover -s tests -p 'test_ux43*.py' -q
WORK="$ROOT/build-work/native-frozen"
rm -rf "$WORK"
mkdir -p "$WORK" "$ROOT/artifacts"
ARGS=(--noconfirm --clean --windowed --name Neospector
 --distpath "$WORK/dist" --workpath "$WORK/pyinstaller-build" --specpath "$WORK"
 --paths "$ROOT/app_source" --collect-all tkinterdnd2 --hidden-import PIL._tkinter_finder
 --add-data "$ROOT/app_source/ui_profile.json:."
 --add-binary "$(command -v ffmpeg):tools" --add-binary "$(command -v ffprobe):tools")
if [[ -f "$ROOT/updates/public.pem" ]];then ARGS+=(--add-data "$ROOT/updates/public.pem:updates");fi
## No developer examples, tests, .git, source archives or build documentation ship.
if command -v ffplay >/dev/null;then ARGS+=(--add-binary "$(command -v ffplay):tools");fi
"$VENV/bin/python" -m PyInstaller "${ARGS[@]}" "$ROOT/app_source/neospector.py"
DIST="$WORK/dist/Neospector"
[[ -x "$DIST/Neospector" ]] || { echo 'Native executable missing' >&2;exit 1; }
PKG="$WORK/pkg";mkdir -p "$PKG/opt/neospector" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/DEBIAN"
# Dedicated self-contained updater (no runtime pip and no source ZIPs).
"$VENV/bin/python" -m PyInstaller --noconfirm --clean --onefile --console \
  --name NeospectorUpdater --distpath "$WORK/updater-dist" --workpath "$WORK/updater-build" \
  --specpath "$WORK" --paths "$ROOT/app_source" \
  "$ROOT/app_source/native_installer_helper.py"
[[ -x "$WORK/updater-dist/NeospectorUpdater" ]] || { echo 'Updater executable missing' >&2;exit 2; }
cp -a "$DIST/." "$PKG/opt/neospector/"
install -m 0755 "$WORK/updater-dist/NeospectorUpdater" "$PKG/opt/neospector/NeospectorUpdater"
# An immutable, standalone verifier is installed beside the native app.
mkdir -p "$PKG/opt/neospector/updates"



cp "$ROOT/updates/public.pem" "$PKG/opt/neospector/updates/public.pem"
cat > "$PKG/usr/bin/neospector" <<'LAUNCH'
#!/bin/sh
exec /opt/neospector/Neospector "$@"
LAUNCH
chmod 0755 "$PKG/usr/bin/neospector"
cat > "$PKG/usr/share/applications/neospector.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Neospector
GenericName=Audiovisual Instrument
Comment=Local-first audiovisual synthesiser by Pungent Funk
Exec=/usr/bin/neospector
Icon=video-x-generic
Terminal=false
Categories=AudioVideo;Audio;Video;Graphics;
StartupNotify=true
DESKTOP
SIZE="$(du -sk "$PKG" | awk '{print $1}')"
cat > "$PKG/DEBIAN/control" <<EOF
Package: neospector
Version: $DEB_VERSION
Architecture: $DEBARCH
Section: video
Priority: optional
Maintainer: Pungent Funk <support@omne.space>
Homepage: https://omne.space/downloads/neospector
Depends: ffmpeg, ca-certificates, pkexec, libx11-6, libxext6, libxrender1, libgl1
Installed-Size: $SIZE
Description: Neospector self-contained Linux native installer candidate
 Audio-visual workstation with local preview, media and module racks.
 This is not a verified Flathub release or signed-repository package.
EOF
OUT="$ROOT/artifacts/Neospector_${APP_VERSION}_linux-x64.deb"
dpkg-deb --root-owner-group --build "$PKG" "$OUT"
python3 "$ROOT/scripts/verify_shipping.py" "$OUT"
sha256sum "$OUT" > "$OUT.sha256"
echo "PRIVATE CANDIDATE: $OUT — requires native installation, audio and display acceptance."
echo 'Do not publish a sideloaded DEB as a zero-warning trusted installer.'
