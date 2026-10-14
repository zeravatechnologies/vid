#!/usr/bin/env bash
# Builds dist/vid_<version>_<arch>.deb: a self-contained PyInstaller folder
# under /opt/vid, /usr/bin/vid, and a systemd user service that starts
# with every login. Nothing is installed from the network.
# Usage: packaging/deb/build.sh [python]   (python with the build deps; default python3)
set -euo pipefail
umask 022
cd "$(dirname "$0")/../.."
PY="${1:-python3}"
VERSION=$("$PY" -c "import sys; sys.path.insert(0, 'src'); import vid; print(vid.__version__)")
DEBVER="${VERSION/.dev/~dev}"
ARCH=$(dpkg --print-architecture)
PKG=vid

rm -rf build/pyinstaller dist/pyinstaller
"$PY" -m PyInstaller --noconfirm --clean --log-level WARN \
  --onedir --name vid \
  --paths src --collect-data vid \
  --distpath dist/pyinstaller --workpath build/pyinstaller --specpath build/pyinstaller \
  packaging/pyinstaller/vid_entry.py

STAGE=build/deb/$PKG
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/opt" "$STAGE/usr/bin" "$STAGE/usr/lib/systemd/user" "$STAGE/usr/share/doc/$PKG"
cp -a dist/pyinstaller/vid "$STAGE/opt/vid"
ln -s /opt/vid/vid "$STAGE/usr/bin/vid"
install -m 0644 packaging/deb/vid.service "$STAGE/usr/lib/systemd/user/vid.service"
{ cat NOTICE; echo; echo "On Debian systems the GPL-3 text is in /usr/share/common-licenses/GPL-3; it is also in LICENSE in the source."; } > "$STAGE/usr/share/doc/$PKG/copyright"

SIZE=$(du -sk "$STAGE" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<EOT
Package: $PKG
Version: $DEBVER
Architecture: $ARCH
Maintainer: Zerava Technologies Inc. <info@zeravatech.ca>
Installed-Size: $SIZE
Section: net
Priority: optional
Homepage: https://www.zeravatech.ca/
Description: local watcher between an AI agent and its model
 Vid runs on this computer between an AI agent and the model it calls, reads
 what reaches the agent and shows what is hidden. It does not block.
 Point the agent's base URL at http://127.0.0.1:8787/v1 (OpenAI-compatible)
 or http://127.0.0.1:8787/anthropic (Anthropic). Nothing leaves the machine
 except the calls the agent already makes.
EOT
cat > "$STAGE/DEBIAN/postinst" <<'EOT'
#!/bin/sh
set -e
if [ "$1" = "configure" ] && command -v systemctl >/dev/null 2>&1; then
    # Start for every user at login; a user can opt out with
    # `systemctl --user disable vid`.
    systemctl --global enable vid.service >/dev/null 2>&1 || true
fi
exit 0
EOT
cat > "$STAGE/DEBIAN/prerm" <<'EOT'
#!/bin/sh
set -e
if [ "$1" = "remove" ] && command -v systemctl >/dev/null 2>&1; then
    systemctl --global disable vid.service >/dev/null 2>&1 || true
fi
exit 0
EOT
chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm"

mkdir -p dist
OUT="dist/${PKG}_${DEBVER}_${ARCH}.deb"
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$OUT" >/dev/null
echo "$OUT"
