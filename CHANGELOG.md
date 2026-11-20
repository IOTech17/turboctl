# Changelog

## 1.2.1

- Intel: an undervolt of 0 mV, the default, made the CPU go back to its factory turbo
  ratios, while MSR 0x1AD still read the profile's ratios; re-applying the profile did not
  help. The ratios are now written again after each undervolt write

## 1.2.0

- Intel: PL2 and the PL1 time window can be set in the custom profile. With the factory
  28 s window and 58 W PL2, the CPU can run well above its PL1 for several seconds and
  overshoot the throttle temperature; lowering both keeps the power close to PL1.
  The other profiles, and custom settings saved before, keep the factory values
- The active limit shows every limit hit during the last second (read 10 times a second),
  not only the one in force at the instant of the reading

## 1.1.1

- Updates are also checked 5 minutes after each boot, so a laptop that was off finds them
- Update interval in the window: every 12 hours, daily, weekly, monthly or never
  (`turboctl update-interval`); the choice is kept across updates and reinstalls

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
