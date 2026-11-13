#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Install turboctl.
#
#   sudo ./install.sh [PROFILE]   install, enable the services and apply PROFILE (default: cool)
#   ./install.sh --files-only     only copy the files, for packagers (honours DESTDIR)
#
# Variables: PREFIX (/usr), SYSCONFDIR (/etc), UNITDIR, DESTDIR,
#            NOPASSWD=0 to keep the password prompt (see README).
set -eu
cd "$(dirname "$0")"

PREFIX=${PREFIX:-/usr}
SYSCONFDIR=${SYSCONFDIR:-/etc}
BINDIR=${BINDIR:-$PREFIX/bin}
SBINDIR=${SBINDIR:-$PREFIX/sbin}
DATADIR=${DATADIR:-$PREFIX/share}
LOCALEDIR=${LOCALEDIR:-$DATADIR/locale}
UNITDIR=${UNITDIR:-$PREFIX/lib/systemd/system}
NOPASSWD=${NOPASSWD:-1}
DESTDIR=${DESTDIR:-}
APP_ID=io.github.iotech17.turboctl

files_only=0
profile=cool
case "${1:-}" in
    --files-only) files_only=1 ;;
    "") ;;
    *) profile=$1 ;;
esac
if [ "$files_only" = 0 ] && [ "$(id -u)" != 0 ]; then
    echo "install.sh: run as root (sudo ./install.sh), or use --files-only" >&2
    exit 1
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

# put SOURCE TARGET MODE: install with the @...@ paths filled in
put() {
    sed -e "s|@SBINDIR@|$SBINDIR|g" -e "s|@BINDIR@|$BINDIR|g" -e "s|@LOCALEDIR@|$LOCALEDIR|g" "$1" > "$tmp"
    install -D -m "$3" "$tmp" "$DESTDIR$2"
}

put turboctl "$SBINDIR/turboctl" 755
put turboctl-gui "$BINDIR/turboctl-gui" 755
put data/turboctl.service "$UNITDIR/turboctl.service" 644
put data/turboctl-shutdown.service "$UNITDIR/turboctl-shutdown.service" 644
put data/$APP_ID.desktop "$DATADIR/applications/$APP_ID.desktop" 644
put data/$APP_ID-autostart.desktop "$SYSCONFDIR/xdg/autostart/$APP_ID.desktop" 644
put data/turboctl.svg "$DATADIR/icons/hicolor/scalable/apps/turboctl.svg" 644
put data/$APP_ID.policy "$DATADIR/polkit-1/actions/$APP_ID.policy" 644
if [ "$NOPASSWD" = 1 ]; then
    put data/50-turboctl.rules "$DATADIR/polkit-1/rules.d/50-turboctl.rules" 644
else
    rm -f "$DESTDIR$DATADIR/polkit-1/rules.d/50-turboctl.rules"
fi

if command -v msgfmt >/dev/null 2>&1; then
    for po in po/*.po; do
        lang=$(basename "$po" .po)
        msgfmt -o "$tmp" "$po"
        install -D -m 644 "$tmp" "$DESTDIR$LOCALEDIR/$lang/LC_MESSAGES/turboctl.mo"
    done
else
    echo "install.sh: msgfmt (gettext) not found, translations skipped" >&2
fi

[ "$files_only" = 1 ] && exit 0

gtk-update-icon-cache -q -t "$DATADIR/icons/hicolor" 2>/dev/null || true
systemctl daemon-reload
"$SBINDIR/turboctl" set "$profile"
systemctl enable turboctl.service
systemctl enable --now turboctl-shutdown.service
echo "turboctl installed. Start \"Turbo Boost\" from the menu, or log in again for the tray icon."
