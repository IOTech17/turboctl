# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the hardware-independent logic of turboctl (no root, no MSR access)."""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(ROOT, filename))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


turboctl = load("turboctl", "turboctl")

# An i7-5700HQ as detect_cpu() reports it, with its factory limits.
I7_5700HQ = {
    "name": "Intel(R) Core(TM) i7-5700HQ CPU @ 2.70GHz",
    "model": 0x47,
    "generation": "Broadwell",
    "tested": True,
    "cores": 4,
    "tjmax": 105,
    "base_ratio": 27,
    "ratio_writable": True,
    "tcc_writable": True,
    "power_unit": 8,
}
FACTORY = {"ratios": [35, 35, 35, 35], "tcc": 103, "pl1": 47.0}


class Profiles(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(turboctl, "CUSTOM_FILE", "/nonexistent/custom.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cool_matches_the_measured_profile(self):
        # Measured on an i7-5700HQ: 85 C max with 8 threads of AVX load for 8 minutes.
        cool = turboctl.build_profiles(I7_5700HQ, FACTORY)["cool"]
        self.assertEqual(cool, {"ratios": [35, 34, 33, 32], "pl1": 30, "tcc": 90, "turbo": True})

    def test_stock_and_off_keep_factory_limits(self):
        profiles = turboctl.build_profiles(I7_5700HQ, FACTORY)
        self.assertEqual(profiles["stock"], {"ratios": [35] * 4, "pl1": 47, "tcc": 103, "turbo": True})
        self.assertFalse(profiles["off"]["turbo"])
        self.assertNotIn("custom", profiles)

    def test_cool_never_goes_below_base_or_rises(self):
        cpu = dict(I7_5700HQ, cores=8, base_ratio=30)
        factory = {"ratios": [33, 33, 32, 32, 31, 31, 31, 31], "tcc": 100, "pl1": 15.0}
        cool = turboctl.build_profiles(cpu, factory)["cool"]
        self.assertEqual(cool["ratios"], [33, 32, 30, 30, 30, 30, 30, 30])
        self.assertTrue(turboctl.valid_profile(cool, cpu, factory))

    def test_every_built_profile_is_valid(self):
        for name, profile in turboctl.build_profiles(I7_5700HQ, FACTORY).items():
            with self.subTest(name):
                self.assertTrue(turboctl.valid_profile(profile, I7_5700HQ, FACTORY))

    def test_bounds(self):
        self.assertEqual(
            turboctl.bounds(I7_5700HQ, FACTORY),
            {"ratio": [27, 35], "pl1": [14, 47], "tcc": [70, 105], "undervolt": [-100, 0]},
        )

    def test_invalid_profiles(self):
        good = {"turbo": True, "ratios": [35, 34, 33, 32], "pl1": 30, "tcc": 90}
        bad = {
            "rising ratios": dict(good, ratios=[32, 33, 34, 35]),
            "ratio above factory": dict(good, ratios=[36, 34, 33, 32]),
            "ratio below base": dict(good, ratios=[35, 34, 33, 26]),
            "wrong core count": dict(good, ratios=[35, 34]),
            "PL1 too high": dict(good, pl1=48),
            "PL1 as bool": dict(good, pl1=True),
            "throttle too low": dict(good, tcc=69),
            "turbo not bool": dict(good, turbo=1),
            "not a dict": [good],
        }
        self.assertTrue(turboctl.valid_profile(good, I7_5700HQ, FACTORY))
        for name, profile in bad.items():
            with self.subTest(name):
                self.assertFalse(turboctl.valid_profile(profile, I7_5700HQ, FACTORY))


class Undervolt(unittest.TestCase):
    def test_offset_encoding(self):
        self.assertEqual(turboctl.offset_units(0), 0)
        self.assertEqual(turboctl.offset_units(-60), 0x7C3)
        for mv in range(-100, 1):
            self.assertEqual(turboctl.offset_mv(turboctl.offset_units(mv)), mv)

    def test_valid_undervolt(self):
        self.assertEqual([turboctl.valid_undervolt(v) for v in (0, -100, -50)], [True] * 3)
        self.assertEqual([turboctl.valid_undervolt(v) for v in (1, -101, -50.0, True, "-50")], [False] * 5)

    def test_crash_guard(self):
        state = tempfile.mkdtemp()
        paths = {
            "STATE_DIR": state,
            "UNDERVOLT_FILE": state + "/undervolt",
            "UNDERVOLT_PENDING": state + "/pending",
            "UNDERVOLT_CRASH": state + "/crash",
        }
        boot = ["first"]
        with mock.patch.multiple(turboctl, boot_id=lambda: boot[0], **paths):
            turboctl.set_saved_undervolt(-60)
            turboctl.write_text(paths["UNDERVOLT_PENDING"], "first -60\n")
            self.assertEqual(turboctl.checked_undervolt(), -60, "same boot (resume) keeps the undervolt")

            boot[0] = "second"  # the first boot never shut down cleanly
            self.assertEqual(turboctl.checked_undervolt(), 0)
            self.assertEqual(turboctl.undervolt_crash(), "-60")
            self.assertEqual(turboctl.saved_undervolt(), 0)
            self.assertFalse(os.path.exists(paths["UNDERVOLT_PENDING"]))

            turboctl.set_saved_undervolt(-40)
            os.remove(paths["UNDERVOLT_CRASH"])
            boot[0] = "third"  # no marker: the previous boot shut down cleanly
            self.assertEqual(turboctl.checked_undervolt(), -40)
            self.assertIsNone(turboctl.undervolt_crash())


class KernelErrors(unittest.TestCase):
    def test_failure_signatures(self):
        # Lines seen when an undervolt was too deep, then lines that must not count.
        failures = [
            'sched_ext: BPF scheduler "flash" disabled (runnable task stall)',
            "WARNING: security/commoncap.c:928 at cap_bprm_creds_from_file",
            "mce: [Hardware Error]: Machine check events logged",
            "watchdog: BUG: soft lockup - CPU#3 stuck for 22s!",
        ]
        normal = [
            "msr: Write to unrecognized MSR 0x150 by turboctl",
            'sched_ext: BPF scheduler "flash" enabled',
            "filter_write: 3 callbacks suppressed",
        ]
        for line in failures:
            self.assertTrue(turboctl.KERNEL_ERROR.search(line), line)
        for line in normal:
            self.assertFalse(turboctl.KERNEL_ERROR.search(line), line)


if __name__ == "__main__":
    unittest.main()
