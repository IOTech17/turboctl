# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the D-Bus menu of the tray icon, without a session bus."""
import os
import tempfile
import unittest
from unittest import mock

from test_turboctl import load

try:
    gui = load("turboctl_gui", "turboctl-gui")
except (ImportError, ValueError) as err:  # PyGObject or GTK 3 missing
    gui = None
    reason = str(err)


class FakeConnection:
    def __init__(self):
        self.signals = []

    def register_object(self, *args):
        return 1

    def emit_signal(self, _dest, _path, _iface, name, params):
        self.signals.append((name, params.unpack() if params else None))


@unittest.skipIf(gui is None, "PyGObject with GTK 3 is not installed")
class DBusMenu(unittest.TestCase):
    def setUp(self):
        self.connection = FakeConnection()
        self.menu = gui.DBusMenu(self.connection)
        self.label = self.menu.add({"label": "reading", "enabled": False})
        self.radio = self.menu.add({"label": "Cool", "toggle-type": "radio", "toggle-state": 0})

    def test_layout(self):
        root, props, children = self.menu.layout(0)
        self.assertEqual(root, 0)
        self.assertEqual(props["children-display"].unpack(), "submenu")
        self.assertEqual([child.unpack()[0] for child in children], [self.label, self.radio])
        self.assertEqual(children[1].unpack()[1]["toggle-type"], "radio")

    def test_update_sends_only_changes(self):
        self.menu.update(self.radio, **{"toggle-state": 1, "label": "Cool"})
        self.menu.update(self.radio, **{"toggle-state": 1})
        expected = [("ItemsPropertiesUpdated", ([(self.radio, {"toggle-state": 1})], []))]
        self.assertEqual(self.connection.signals, expected)


@unittest.skipIf(gui is None, "PyGObject with GTK 3 is not installed")
class Language(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = mock.patch.object(gui, "CONFIG", os.path.join(self.directory.name, "turboctl", "gui.json"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_round_trip(self):
        self.assertEqual(gui.saved_language(), "")
        gui.save_language("fr")
        self.assertEqual(gui.saved_language(), "fr")
        gui.save_language("")
        self.assertEqual(gui.saved_language(), "")

    def test_unknown_or_broken_file_follows_system(self):
        os.makedirs(os.path.dirname(gui.CONFIG))
        for content in ('{"language": "xx"}', "[1]", "not json"):
            with open(gui.CONFIG, "w") as file:
                file.write(content)
            self.assertEqual(gui.saved_language(), "")


if __name__ == "__main__":
    unittest.main()
