# Changelog

## 1.0.0

First public release.

- Profiles `off`, `cool`, `stock` and `custom`, derived from each CPU's factory limits
- Turbo ratios per active core, PL1 (MCHBAR mirror, MSR fallback), throttle temperature
- Undervolt from 0 to −100 mV with a crash guard and a stability test (`uvtest`)
- systemd service that reapplies the limits at boot and after sleep
- GTK 3 window and StatusNotifierItem tray icon, English and French
- Intel Core 4th to 10th generation, up to 8 cores (tested on Broadwell)
