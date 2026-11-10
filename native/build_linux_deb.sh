#!/usr/bin/env bash
# Offline packaging of the ACCEPTED UX41 source, retaining its verified runtime/bootstrap.
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
command -v dpkg-deb >/dev/null || { echo 'dpkg-deb required' >&2; exit 2; }
command -v python3 >/dev/null || exit 2
python3 "$ROOT/scripts/prepare_source.py" --verify-only
WORK="$ROOT/build-work/linux-deb";rm -rf "$WORK";mkdir -p "$WORK/source" "$ROOT/artifacts"
SRC="$(python3 "$ROOT/scripts/prepare_source.py" --output "$WORK/source" | tail -1)"
VERSION="$(python3 - "$SRC" <<'PY'
import ast,sys,pathlib
n=ast.parse((pathlib.Path(sys.argv[1])/'app_source/release_identity.py').read_text())
print(next(v.value.value for v in n.body if isinstance(v,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in v.targets)))
PY
)"
DEB_VERSION="${VERSION//-/'~'}"
PKG="$WORK/pkg"
mkdir -p "$PKG/usr/share/neospector/release" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/DEBIAN"
cp -a "$SRC/." "$PKG/usr/share/neospector/release/"
cat > "$PKG/usr/bin/neospector" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
VERSION='@VERSION@'
SOURCE='/usr/share/neospector/release'
MANAGED="${XDG_DATA_HOME:-$HOME/.local/share}/omne/neospector"
# Approved signed updates are installed into the managed version directory.
if [[ -f "$MANAGED/current.json" && -x "$MANAGED/launch.sh" ]]; then
  exec "$MANAGED/launch.sh" "$@"
fi
DEST="$MANAGED/versions/$VERSION"
if [[ ! -f "$DEST/MANIFEST.sha256" ]]; then
  command -v python3 >/dev/null || { echo 'Python 3 required' >&2; exit 2; }
  PARENT="$(dirname "$DEST")";mkdir -p "$PARENT"
  TEMP="$(mktemp -d "$PARENT/.neospector-install.XXXXXXXX")"
  trap 'rm -rf -- "$TEMP"' EXIT
  cp -a "$SOURCE/." "$TEMP/"
  chmod -R u+rwX "$TEMP"
  (cd "$TEMP" && python3 install_linux.py --check) || { echo 'Neospector source verification failed' >&2; exit 2; }
  if [[ -d "$DEST" ]]; then mv "$DEST" "${DEST}.incomplete.$(date +%s)"; fi
  mv "$TEMP" "$DEST"
  trap - EXIT
fi
cd "$DEST"
# The initial DEB install also uses the managed launch path.
mkdir -p "$MANAGED"
python3 - "$MANAGED/current.json" "$VERSION" <<'PYPOINTER'
import json,sys,os,tempfile
from pathlib import Path
p=Path(sys.argv[1]);v=sys.argv[2]
if not p.exists():
 with tempfile.NamedTemporaryFile('w',dir=p.parent,prefix='.launch-',delete=False) as f:
  json.dump({'version':v, 'previous':None},f);f.write('\n');temp=f.name
 os.replace(temp,p)
PYPOINTER
exec bash "$DEST/RUN_POC.sh" "$@"
LAUNCHER
sed -i "s/@VERSION@/${VERSION}/g" "$PKG/usr/bin/neospector"
chmod 0755 "$PKG/usr/bin/neospector"
cat > "$PKG/usr/share/applications/neospector.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Neospector
GenericName=Audiovisual Instrument
Comment=OmN-e audiovisual sequencing and modular live performance by Pungent Funk
Exec=neospector
Icon=video-x-generic
Terminal=false
Categories=AudioVideo;Audio;Video;Graphics;
StartupNotify=true
DESKTOP
SIZE="$(du -sk "$PKG" | awk '{print $1}')"
cat > "$PKG/DEBIAN/control" <<EOF
Package: neospector
Version: $DEB_VERSION
Architecture: amd64
Section: video
Priority: optional
Maintainer: Pungent Funk <support@omne.space>
Homepage: https://omne.space/downloads/neospector
Depends: python3 (>= 3.11), python3-venv, python3-tk, ffmpeg, ca-certificates
Installed-Size: $SIZE
Description: Neospector local-first audiovisual instrument
 Neospector by Pungent Funk. First launch provisions a separate user-owned
 version from verified bundled source and Python wheels. Requires Xorg x64.
EOF
OUT="$ROOT/artifacts/Neospector_${VERSION}_linux-x64.deb"
chmod 0755 "$PKG/DEBIAN"; chmod g-s "$PKG/DEBIAN"
dpkg-deb --root-owner-group --build "$PKG" "$OUT"
sha256sum "$OUT" > "$OUT.sha256"
dpkg-deb --info "$OUT"
echo "RELEASE_CANDIDATE_DEB=$OUT"
