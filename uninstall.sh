#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Remove turboctl.
#
#   sudo ./uninstall.sh            remove the files, keep the saved settings
#   sudo ./uninstall.sh --purge    also remove the saved settings in /var/lib/turboctl
#   ./uninstall.sh --files-only    only remove the files, for packagers (honours DESTDIR)
#
# Use the same PREFIX, SYSCONFDIR, UNITDIR and PRESETDIR as for install.sh.
set -eu

PREFIX=${PREFIX:-/usr}
SYSCONFDIR=${SYSCONFDIR:-/etc}
BINDIR=${BINDIR:-$PREFIX/bin}
SBINDIR=${SBINDIR:-$PREFIX/sbin}
DATADIR=${DATADIR:-$PREFIX/share}
LOCALEDIR=${LOCALEDIR:-$DATADIR/locale}
UNITDIR=${UNITDIR:-$PREFIX/lib/systemd/system}
PRESETDIR=${PRESETDIR:-$PREFIX/lib/systemd/system-preset}
DESTDIR=${DESTDIR:-}
APP_ID=io.github.iotech17.turboctl

files_only=0
purge=0
case "${1:-}" in
    --files-only) files_only=1 ;;
    --purge) purge=1 ;;
    "") ;;
    *) echo "usage: uninstall.sh [--purge | --files-only]" >&2; exit 1 ;;
esac
if [ "$files_only" = 0 ] && [ "$(id -u)" != 0 ]; then
    echo "uninstall.sh: run as root (sudo ./uninstall.sh), or use --files-only" >&2
    exit 1
fi

if [ "$files_only" = 0 ]; then
    systemctl disable --now turboctl-watch.service turboctl-update.timer 2>/dev/null || true
    systemctl disable turboctl.service turboctl-shutdown.service 2>/dev/null || true
    # Stopping the shutdown unit removes the undervolt marker, as at a clean shutdown.
    systemctl stop turboctl-shutdown.service 2>/dev/null || true
fi

rm -f "$DESTDIR$SBINDIR/turboctl" \
      "$DESTDIR$BINDIR/turboctl-gui" \
      "$DESTDIR$UNITDIR/turboctl.service" \
      "$DESTDIR$UNITDIR/turboctl-shutdown.service" \
      "$DESTDIR$UNITDIR/turboctl-watch.service" \
      "$DESTDIR$UNITDIR/turboctl-update.service" \
      "$DESTDIR$UNITDIR/turboctl-update.timer" \
      "$DESTDIR$DATADIR/turboctl/allowed_signers" \
      "$DESTDIR$PRESETDIR/80-turboctl.preset" \
      "$DESTDIR$DATADIR/applications/$APP_ID.desktop" \
      "$DESTDIR$SYSCONFDIR/xdg/autostart/$APP_ID.desktop" \
      "$DESTDIR$DATADIR/icons/hicolor/scalable/apps/turboctl.svg" \
      "$DESTDIR$DATADIR/polkit-1/actions/$APP_ID.policy" \
      "$DESTDIR$DATADIR/polkit-1/rules.d/50-turboctl.rules" \
      "$DESTDIR$LOCALEDIR"/*/LC_MESSAGES/turboctl.mo

rmdir "$DESTDIR$DATADIR/turboctl" 2>/dev/null || true
[ "$files_only" = 1 ] && exit 0

rm -f /var/lib/turboctl/install.env "$SYSCONFDIR/systemd/system-preset/80-turboctl-update.preset"
[ "$purge" = 1 ] && rm -rf /var/lib/turboctl
rm -rf /run/turboctl
systemctl daemon-reload
echo "turboctl removed. Reboot to bring the CPU back to its factory limits."
