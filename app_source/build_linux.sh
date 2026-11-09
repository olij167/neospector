#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"; cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-python3}"
for tool in "$PYTHON_BIN" ffmpeg ffprobe ffplay dpkg-deb; do command -v "$tool" >/dev/null 2>&1 || { echo "Required build tool is missing: $tool" >&2; exit 2; }; done
VERSION="$($PYTHON_BIN - <<'PY'
import ast,pathlib
p=pathlib.Path('omne_sequencer.py');t=ast.parse(p.read_text(encoding='utf-8'))
print(next(ast.literal_eval(n.value) for n in t.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='VERSION' for x in n.targets)))
PY
)"
case "$(uname -m)" in x86_64|amd64) ARCH_LABEL="x64";DEB_ARCH="amd64";; arm64|aarch64) ARCH_LABEL="arm64";DEB_ARCH="arm64";; *) echo "Unsupported Linux architecture" >&2;exit 2;; esac
APP_NAME="OmN-e Sequencer";PACKAGE_NAME="omne-sequencer";INSTALL_ROOT="/usr/lib/$PACKAGE_NAME"
VENV="$ROOT/.build-venv"; [[ -x "$VENV/bin/python" ]] || "$PYTHON_BIN" -m venv "$VENV"
PY="$VENV/bin/python"; "$PY" -m pip install --upgrade pip; "$PY" -m pip install 'pyinstaller>=6.22,<7' 'pillow>=10.4,<13' 'numpy>=1.26,<3'
rm -rf build dist dist-linux;mkdir -p dist-linux
"$PY" -m PyInstaller --noconfirm --clean --windowed --hidden-import=PIL._tkinter_finder --name "$APP_NAME" \
  --add-binary "$(command -v ffmpeg):tools" --add-binary "$(command -v ffprobe):tools" --add-binary "$(command -v ffplay):tools" --add-data "ui_profile.json:." --add-data "../examples:examples" ./omne_sequencer.py
DIST="$ROOT/dist/$APP_NAME";[[ -d "$DIST" ]] || { echo "Missing PyInstaller output" >&2;exit 1; }
PKG="$ROOT/dist-linux/pkg";mkdir -p "$PKG$INSTALL_ROOT" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/DEBIAN"
cp -a "$DIST/." "$PKG$INSTALL_ROOT/"
cat > "$PKG/usr/bin/omne-sequencer" <<EOF
#!/usr/bin/env sh
exec "$INSTALL_ROOT/$APP_NAME" "\$@"
EOF
chmod 0755 "$PKG/usr/bin/omne-sequencer"
cat > "$PKG/usr/share/applications/omne-sequencer.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OmN-e Sequencer
Comment=Quick local-first music video sequencing and audiovisual mutation
Exec=/usr/bin/omne-sequencer
Icon=video-x-generic
Terminal=false
Categories=AudioVideo;Video;Graphics;
StartupNotify=true
EOF
SIZE="$(du -sk "$PKG"|awk '{print $1}')"
cat > "$PKG/DEBIAN/control" <<EOF
Package: $PACKAGE_NAME
Version: ${VERSION/-r/~r}
Section: video
Priority: optional
Architecture: $DEB_ARCH
Maintainer: OmN-e / Pungent Funk <support@omne.space>
Homepage: https://omne.space/
Installed-Size: $SIZE
Description: OmN-e Sequencer quick music-video workbench
 A local-first audiovisual sequencer and music-video editor in the OmN-e tool family.
EOF
DEB="$ROOT/dist-linux/OmN-e_Sequencer_v${VERSION}_Linux_${ARCH_LABEL}.deb";dpkg-deb --root-owner-group --build "$PKG" "$DEB";sha256sum "$DEB" > "$DEB.sha256"
echo "Linux package complete: $DEB"
