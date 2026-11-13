# SPDX-License-Identifier: GPL-3.0-or-later
# For packagers: make install DESTDIR=... PREFIX=/usr
# Users can run "sudo ./install.sh" instead, which also enables the services.

PREFIX ?= /usr
export PREFIX DESTDIR SYSCONFDIR BINDIR SBINDIR DATADIR LOCALEDIR UNITDIR NOPASSWD

.PHONY: install uninstall check pot

install:
	./install.sh --files-only

uninstall:
	./uninstall.sh --files-only

check:
	python3 -m unittest discover -s tests -v
	ruff check .
	shellcheck install.sh uninstall.sh

pot:
	TZ=UTC xgettext --language=Python --from-code=UTF-8 --keyword=_ --package-name=turboctl \
		--copyright-holder="turboctl contributors" --output=po/turboctl.pot turboctl-gui
