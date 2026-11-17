#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Install turboctl.
#
#   sudo ./install.sh [PROFILE]   install, enable the services and apply PROFILE (default: cool)
#   ./install.sh --files-only     only copy the files, for packagers (honours DESTDIR)
#   install.sh --update           run by "turboctl update" from a new release: keep the saved profile
#
# Variables: PREFIX (/usr), SYSCONFDIR (/etc), UNITDIR, PRESETDIR, DESTDIR,
#            NOPASSWD=0 to keep the password prompt (see README),
#            AUTO_UPDATE=0 to install new releases by hand.
set -eu
cd "$(dirname "$0")"

PREFIX=${PREFIX:-/usr}
SYSCONFDIR=${SYSCONFDIR:-/etc}
BINDIR=${BINDIR:-$PREFIX/bin}
SBINDIR=${SBINDIR:-$PREFIX/sbin}
DATADIR=${DATADIR:-$PREFIX/share}
LOCALEDIR=${LOCALEDIR:-$DATADIR/locale}
UNITDIR=${UNITDIR:-$PREFIX/lib/systemd/system}
PRESETDIR=${PRESETDIR:-$PREFIX/lib/systemd/system-preset}
NOPASSWD=${NOPASSWD:-1}
AUTO_UPDATE=${AUTO_UPDATE:-1}
DESTDIR=${DESTDIR:-}
APP_ID=io.github.iotech17.turboctl

files_only=0
update=0
profile=cool
case "${1:-}" in
    --files-only) files_only=1 ;;
    --update) update=1 ;;
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
    sed -e "s|@SBINDIR@|$SBINDIR|g" -e "s|@BINDIR@|$BINDIR|g" -e "s|@LOCALEDIR@|$LOCALEDIR|g" \
        -e "s|@DATADIR@|$DATADIR|g" "$1" > "$tmp"
    install -D -m "$3" "$tmp" "$DESTDIR$2"
}

put turboctl "$SBINDIR/turboctl" 755
put turboctl-gui "$BINDIR/turboctl-gui" 755
put data/turboctl.service "$UNITDIR/turboctl.service" 644
put data/turboctl-shutdown.service "$UNITDIR/turboctl-shutdown.service" 644
put data/turboctl-watch.service "$UNITDIR/turboctl-watch.service" 644
put data/turboctl-update.service "$UNITDIR/turboctl-update.service" 644
put data/turboctl-update.timer "$UNITDIR/turboctl-update.timer" 644
put data/allowed_signers "$DATADIR/turboctl/allowed_signers" 644
put data/80-turboctl.preset "$PRESETDIR/80-turboctl.preset" 644
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
if [ "$update" = 1 ]; then
    "$SBINDIR/turboctl" apply
else
    "$SBINDIR/turboctl" set "$profile"
fi
systemctl enable turboctl.service
systemctl enable --now turboctl-shutdown.service
systemctl enable turboctl-watch.service
systemctl restart turboctl-watch.service

# "turboctl update" installs new releases with these settings. Packages do not get
# this file: their package manager updates them.
install -d /var/lib/turboctl
cat > /var/lib/turboctl/install.env <<EOF
PREFIX=$PREFIX
SYSCONFDIR=$SYSCONFDIR
BINDIR=$BINDIR
SBINDIR=$SBINDIR
DATADIR=$DATADIR
LOCALEDIR=$LOCALEDIR
UNITDIR=$UNITDIR
PRESETDIR=$PRESETDIR
NOPASSWD=$NOPASSWD
EOF
# Sets up turboctl-update.timer, keeping the interval chosen in the window.
if [ "$AUTO_UPDATE" = 1 ]; then
    "$SBINDIR/turboctl" update-interval
else
    "$SBINDIR/turboctl" update-interval never
fi
if [ "$update" = 1 ]; then
    echo "turboctl updated."
else
    echo "turboctl installed. Start \"Turbo Boost\" from the menu, or log in again for the tray icon."
fi
