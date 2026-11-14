# turboctl

Tame Intel Turbo Boost instead of disabling it.

Many laptops run their CPU at 95-100 °C under sustained load, and the usual fix is to
disable Turbo Boost entirely. turboctl keeps the turbo bursts and caps what makes the
heat: the per-core turbo ratios, the long-term power limit (PL1) and the throttle
temperature. It can also undervolt the CPU, with a guard against unstable values.

- Command line tool, systemd service that reapplies the limits at boot and after sleep
- GTK 3 window and tray icon showing temperature, power, frequency and the active limit
- Profiles: `off`, `cool`, `stock`, and a `custom` profile set from the window
- Values are read from the CPU itself; every write is read back and verified,
  and turbo stays off if anything fails

On an i7-5700HQ laptop, the `cool` profile keeps an 8-thread AVX load at 85 °C
(stock: 95-100 °C) while single-threaded bursts still reach 3.5 GHz.

## Supported hardware

Intel Core 4th to 10th generation, up to 8 cores, on Linux with systemd:

| Generation | Status |
|---|---|
| Broadwell (5th gen) | tested (i7-5700HQ) |
| Haswell, Skylake, Kaby Lake, Coffee Lake, Whiskey Lake, Comet Lake | expected to work, **untested** |
| Ice Lake and later, AMD | not supported |

turboctl refuses to run on other CPUs. Each feature is used only if the CPU allows it:
turbo ratios and throttle temperature can be locked by the CPU (shown as `locked`), and
undervolting is locked by firmware or microcode on many CPUs since 2020 (Plundervolt).
If you try an untested generation, please open an issue with the output of
`sudo turboctl status`.

## Install

Dependencies: Python 3.9+, PyGObject with GTK 3, polkit (`pkexec`), and gettext to
install the translations. Most desktops have them already.

| Distribution | Command |
|---|---|
| Debian 12+, Ubuntu 24.04+, Mint, Pop!_OS | `sudo apt install python3-gi gir1.2-gtk-3.0 pkexec gettext` (Ubuntu 22.04: `policykit-1` instead of `pkexec`) |
| Fedora | `sudo dnf install python3-gobject gtk3 polkit gettext` |
| Arch, Manjaro | `sudo pacman -S python-gobject gtk3 polkit gettext` |
| openSUSE | `sudo zypper install python3-gobject-Gdk typelib-1_0-Gtk-3_0 polkit gettext-tools` |
| Solus | `sudo eopkg install python-gobject gettext` |

Then, from this directory:

```sh
sudo ./install.sh          # starts with the "cool" profile
sudo ./install.sh stock    # or another profile
```

Packagers: `make install DESTDIR=... PREFIX=/usr` copies the files without enabling
anything. See the variables at the top of `install.sh`.

### Tray icon

The tray icon uses the StatusNotifierItem standard. It works out of the box on KDE Plasma,
Budgie, Cinnamon, XFCE (with the status notifier plugin), LXQt and COSMIC. On GNOME, install
the *AppIndicator and KStatusNotifierItem Support* extension. Without a tray, the window
works on its own.

Left click opens the window, right click opens the menu (live readings and profiles).

### Language

The window follows the system language (English or French). To choose another one, use the
*Language* menu at the bottom of the window; the window restarts in that language.

### Password

`install.sh` installs a polkit rule so that administrators (groups `wheel`, `sudo` or
`admin`) of a local, active session run `turboctl` without a password: this is what lets
the tray icon start at login. The trade-off: any program running under such an account
can change the CPU limits, but only within the bounds turboctl accepts. To be asked for a
password instead, install with `sudo NOPASSWD=0 ./install.sh`.

## Profiles

Values derived from each CPU's factory limits (example: i7-5700HQ):

| Profile | Turbo | Ratio per active core | PL1 | Throttle at |
|---|---|---|---|---|
| `off` | off | factory | factory (47 W) | factory (103 °C) |
| `cool` | on | factory minus one step per extra core (3.5 / 3.4 / 3.3 / 3.2 GHz) | 65 % of factory (30 W) | TjMax − 15 °C (90 °C) |
| `stock` | on | factory (3.5 GHz) | factory (47 W) | factory (103 °C) |
| `custom` | set in the window | | | |

## Usage

```sh
sudo turboctl status         # CPU, limits in place, undervolt
sudo turboctl monitor        # temperature, watts, ratio, active limit, once a second
sudo turboctl set cool       # apply and save a profile
sudo turboctl apply          # apply the saved profile again
turboctl-gui                 # the window (no sudo)
```

## Undervolt

One offset from 0 to −100 mV for the cores and cache, applied with every profile:

```sh
sudo turboctl undervolt -50  # or the Undervolt slider and its Apply button
```

**Too much undervolt corrupts data silently** before it crashes anything. Two safeguards:

- **Crash guard**: while an undervolt is active, a marker is kept in `/var/lib/turboctl`.
  A clean shutdown removes it. If the machine freezes or is forced off, the next boot finds
  the marker and starts at 0 mV, and the window says so. This also happens after a crash
  unrelated to the undervolt: just apply the value again.
- **Stability test**: `sudo turboctl uvtest` (needs `stress-ng`) steps from −20 to −100 mV
  by 10 mV (`sudo turboctl uvtest -40 -80` for another range). Each step runs three phases
  with result verification: all threads (5 min), one thread at max turbo (3 min) and a light,
  variable load (2 min). A step fails on a wrong result, a kernel error (MCE, `WARNING`,
  lockup, scheduler stall) or a phase that ends early. The test then restores the saved
  value and suggests the last stable step plus a 15 mV margin. Its log,
  `/var/lib/turboctl/uvtest.log`, is synced line by line: after a freeze it shows the step
  that crashed.

On the test machine, −80 mV passed both full-load phases but corrupted the kernel under
light load, with no machine check and no wrong result: only a scheduler stall and a kernel
`WARNING` before a freeze. Frequency changes, not full load, find the limit. After the test,
use the value for a few days (idle, video, sleep and resume) and watch
`journalctl -k | grep -iE "mce|hardware error|WARNING"`.

## How it works

| Setting | Where |
|---|---|
| Max ratio per number of active cores | MSR `0x1AD` |
| Throttle temperature (offset from TjMax) | MSR `0x1A2` |
| PL1 power limit | MMIO mirror at MCHBAR + `0x59A0` (MSR `0x610` is often locked); MSR `0x610` if the mirror is unavailable |
| Undervolt | MSR `0x150`, planes 0 (cores) and 2 (cache) |
| Turbo on/off | `intel_pstate/no_turbo` or `cpufreq/boost`, and bit 38 of MSR `0x1A0` |

The CPU forgets these settings at every boot and on resume, so `turboctl.service` writes
them again. Factory values are captured before the first write of each boot
(`/run/turboctl/factory.json`).

Other tools that manage CPU power (TLP, thermald, power-profiles-daemon, throttled,
auto-cpufreq) may write the same settings; turboctl's service runs after them, but avoid
running two tools for the same setting.

## Troubleshooting

**`msr: Write to unrecognized MSR ... tainting CPU_OUT_OF_SPEC` in the kernel log.**
Normal: the kernel flags every MSR write from user space and taints itself (`S` in
`/proc/sys/kernel/tainted`). It has no effect on the system. The kernel parameter
`msr.allow_writes=on` hides the message (the taint stays).

**`the kernel refused an MSR write`.** The kernel blocks MSR writes: kernel lockdown is
active (often with Secure Boot), or `msr.allow_writes=off` is set.

**`the kernel refused to map MCHBAR`** or **`/dev/mem access refused`**. The kernel is built
with `CONFIG_IO_STRICT_DEVMEM`. Add the kernel parameter `iomem=relaxed`. On Solus:
`echo iomem=relaxed | sudo tee /etc/kernel/cmdline.d/90-turboctl.conf && sudo clr-boot-manager update`.

**`the firmware or microcode locks undervolting`.** This CPU cannot be undervolted;
everything else works.

## Uninstall

```sh
sudo ./uninstall.sh          # keeps the saved settings
sudo ./uninstall.sh --purge  # also removes /var/lib/turboctl
```

Reboot to bring the CPU back to its factory limits.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).

Undervolting and changing power limits are done at your own risk. Undervolting too far
can corrupt data; test as described above.
