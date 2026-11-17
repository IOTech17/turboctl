# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the hardware-independent logic of turboctl (no root, no MSR access)."""
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tarfile
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


# A Ryzen 7 H 255 as detect_amd() reports it, with SMU access, and its factory limits.
RYZEN_H255 = {
    "vendor": "amd",
    "name": "AMD Ryzen 7 H 255 w/ Radeon 780M Graphics",
    "generation": "Hawk Point",
    "tested": True,
    "cores": 8,
    "max_freq": 4900,
    "min_freq": 1500,
    "smu": object(),
    "smu_note": None,
    "tctl": True,
}
AMD_FACTORY = {"max_freq": 4900, "power": 45.0, "slow": 54.0, "fast": 65.0, "temp": 100.0}


class AmdProfiles(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(turboctl, "CUSTOM_FILE", "/nonexistent/custom.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_profiles(self):
        profiles = turboctl.build_profiles(RYZEN_H255, AMD_FACTORY)
        self.assertEqual(profiles["stock"], {"max_freq": 4900, "power": 54, "temp": 100, "turbo": True})
        self.assertEqual(profiles["cool"], {"max_freq": 4900, "power": 35, "temp": 85, "turbo": True})
        self.assertFalse(profiles["off"]["turbo"])
        for name, profile in profiles.items():
            with self.subTest(name):
                self.assertTrue(turboctl.valid_profile(profile, RYZEN_H255, AMD_FACTORY))

    def test_bounds(self):
        self.assertEqual(
            turboctl.bounds(RYZEN_H255, AMD_FACTORY),
            {"max_freq": [1500, 4900], "power": [16, 54], "temp": [60, 100]},
        )

    def test_without_smu_only_frequency(self):
        cpu = dict(RYZEN_H255, smu=None, tctl=False, smu_note="smu_unsupported")
        factory = {"max_freq": 4900}
        profiles = turboctl.build_profiles(cpu, factory)
        self.assertEqual(profiles["cool"], {"max_freq": 4900, "turbo": True})
        self.assertEqual(turboctl.fields(cpu), ["max_freq"])
        self.assertTrue(turboctl.valid_profile(profiles["cool"], cpu, factory))
        self.assertFalse(turboctl.valid_profile(dict(profiles["cool"], power=30), cpu, factory))

    def test_invalid_profiles(self):
        good = {"turbo": True, "max_freq": 4000, "power": 30, "temp": 85}
        bad = {
            "frequency not a 100 MHz step": dict(good, max_freq=4050),
            "frequency above the hardware": dict(good, max_freq=5000),
            "power too low": dict(good, power=15),
            "power too high": dict(good, power=55),
            "temperature too low": dict(good, temp=59),
            "temperature above factory": dict(good, temp=101),
            "missing field": {"turbo": True, "max_freq": 4000, "power": 30},
            "Intel field": dict(good, pl1=30),
            "power as float": dict(good, power=30.0),
        }
        self.assertTrue(turboctl.valid_profile(good, RYZEN_H255, AMD_FACTORY))
        for name, profile in bad.items():
            with self.subTest(name):
                self.assertFalse(turboctl.valid_profile(profile, RYZEN_H255, AMD_FACTORY))


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


@unittest.skipUnless(shutil.which("ssh-keygen"), "needs ssh-keygen")
@unittest.skipIf(os.environ.get("TURBOCTL_UPDATING"), "run by turboctl update on the new release")
class Update(unittest.TestCase):
    """A fake GitHub release, signed with a test key; nothing is installed."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        key = os.path.join(self.tmp, "key")
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "test", "-f", key], check=True)
        with open(key + ".pub") as f:
            public = " ".join(f.read().split()[:2])
        self.signers = os.path.join(self.tmp, "allowed_signers")
        with open(self.signers, "w") as f:
            f.write(f'{turboctl.SIGNER} namespaces="{turboctl.SIGNER}" {public}\n')
        self.key = key
        self.settings = os.path.join(self.tmp, "install.env")
        with open(self.settings, "w") as f:
            f.write("PREFIX=/usr\nNOPASSWD=1\n")
        self.installs = []

    def release(self, version, tamper=False):
        """Build turboctl-VERSION.tar.gz from this tree with that version, and sign it."""
        top = f"turboctl-{version}"
        tree = os.path.join(self.tmp, top)
        shutil.copytree(os.path.join(ROOT, "tests"), os.path.join(tree, "tests"))
        with open(os.path.join(ROOT, "turboctl")) as f:
            source = f.read().replace(f'__version__ = "{turboctl.__version__}"', f'__version__ = "{version}"')
        with open(os.path.join(tree, "turboctl"), "w") as f:
            f.write(source)
        archive = os.path.join(self.tmp, top + ".tar.gz")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(tree, top)
        subprocess.run(["ssh-keygen", "-Y", "sign", "-q", "-f", self.key, "-n", turboctl.SIGNER, archive], check=True)
        if tamper:
            with open(archive, "ab") as f:
                f.write(b"\0")
        files = {top + ".tar.gz": archive, top + ".tar.gz.sig": archive + ".sig"}
        return {
            "tag_name": f"v{version}",
            "assets": [{"name": name, "browser_download_url": path} for name, path in files.items()],
        }

    def run_update(self, release):
        def fetch(url):
            if url == turboctl.LATEST_RELEASE:
                return io.BytesIO(json.dumps(release).encode())
            with open(url, "rb") as f:
                return io.BytesIO(f.read())

        real_run = subprocess.run

        def run(args, **kwargs):
            if args[:2] == ["sh", "install.sh"]:
                self.installs.append((args, kwargs["env"]["PREFIX"]))
                return subprocess.CompletedProcess(args, 0)
            return real_run(args, **kwargs)

        with mock.patch.multiple(turboctl, fetch=fetch, ALLOWED_SIGNERS=self.signers, INSTALL_FILE=self.settings), \
                mock.patch.object(turboctl.subprocess, "run", run), mock.patch("builtins.print"):
            turboctl.update()

    def test_installs_a_newer_signed_release(self):
        self.run_update(self.release("99.0.0"))
        self.assertEqual(self.installs, [(["sh", "install.sh", "--update"], "/usr")])

    def test_refuses_a_modified_archive(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_update(self.release("99.0.0", tamper=True))
        self.assertIn("bad signature", str(caught.exception))
        self.assertEqual(self.installs, [])

    def test_ignores_an_older_release(self):
        self.run_update(self.release("1.0.0"))
        self.assertEqual(self.installs, [])

    def test_package_installs_are_left_to_the_package_manager(self):
        os.remove(self.settings)
        with self.assertRaises(SystemExit):
            self.run_update(self.release("99.0.0"))
        self.assertEqual(self.installs, [])


class UpdateInterval(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        self.paths = {
            "STATE_DIR": tmp,
            "INSTALL_FILE": tmp + "/install.env",
            "UPDATE_INTERVAL_FILE": tmp + "/update-interval",
            "UPDATE_TIMER_DROPIN": tmp + "/timer.d/interval.conf",
            "UPDATE_PRESET": tmp + "/preset/80-turboctl-update.preset",
        }
        with open(self.paths["INSTALL_FILE"], "w") as f:
            f.write("PREFIX=/usr\n")
        self.calls = []
        run = lambda args, **kwargs: self.calls.append(args[2:])  # noqa: E731
        patchers = (mock.patch.multiple(turboctl, **self.paths), mock.patch.object(turboctl.subprocess, "run", run))
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def read(self, key):
        with open(self.paths[key]) as f:
            return f.read()

    def test_weekly_12h_then_never(self):
        self.assertEqual(turboctl.saved_update_interval(), "daily")
        turboctl.set_update_interval("weekly")
        self.assertEqual(turboctl.saved_update_interval(), "weekly")
        self.assertIn("OnCalendar=weekly", self.read("UPDATE_TIMER_DROPIN"))
        self.assertEqual(self.read("UPDATE_PRESET"), "enable turboctl-update.timer\n")
        self.assertEqual(self.calls[-1], ["restart", "turboctl-update.timer"])

        turboctl.set_update_interval("12h")
        self.assertIn("OnCalendar=*-*-* 00,12:00:00", self.read("UPDATE_TIMER_DROPIN"))

        turboctl.set_update_interval("never")
        self.assertFalse(os.path.exists(self.paths["UPDATE_TIMER_DROPIN"]))
        self.assertEqual(self.read("UPDATE_PRESET"), "disable turboctl-update.timer\n")
        self.assertEqual(self.calls[-1], ["disable", "--now", "turboctl-update.timer"])

    def test_package_installs_have_no_interval(self):
        os.remove(self.paths["INSTALL_FILE"])
        self.assertIsNone(turboctl.saved_update_interval())
        with self.assertRaises(turboctl.Unsupported):
            turboctl.set_update_interval("weekly")

    def test_request_from_the_window(self):
        self.assertEqual(turboctl.handle_request(None, None, '{"update_interval": "yearly"}'),
                         "unknown update interval")
        self.assertIsNone(turboctl.handle_request(None, None, '{"update_interval": "monthly"}'))
        self.assertEqual(turboctl.saved_update_interval(), "monthly")


if __name__ == "__main__":
    unittest.main()
