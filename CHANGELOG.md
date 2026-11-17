# Changelog

## 1.1.0

- AMD Ryzen: turbo and max frequency on amd-pstate and acpi-cpufreq; sustained power
  and throttle temperature through the SMU on Ryzen 6000/7035, 7040/8040 and 200 series
  (tested on a Ryzen 7 H 255). `turboctl-watch.service` lowers the power limits again
  when the firmware raises them (power profile change, charger plugged in or out)
- Automatic updates for installs made with `install.sh`: a daily timer installs newer
  releases signed with the release key; `turboctl update`; `AUTO_UPDATE=0` to opt out.
  The window restarts in the new version
- Language selector in the window (system default, English, Français), saved in
  `~/.config/turboctl/gui.json`; the window and tray menu switch at once
- The services stay enabled when the distribution resets services to its presets
  (a Solus update disabled them): `80-turboctl.preset`

## 1.0.0

First public release.

- Profiles `off`, `cool`, `stock` and `custom`, derived from each CPU's factory limits
- Turbo ratios per active core, PL1 (MCHBAR mirror, MSR fallback), throttle temperature
- Undervolt from 0 to −100 mV with a crash guard and a stability test (`uvtest`)
- systemd service that reapplies the limits at boot and after sleep
- GTK 3 window and StatusNotifierItem tray icon, English and French
- Intel Core 4th to 10th generation, up to 8 cores (tested on Broadwell)
