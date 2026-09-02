# Milestone 0.3A — QLC+ package / headless proof

Date: 2026-09-01. Host: `shieldxl-light` (not production). No systemd unit, no wizbridge, no WIZ-LIGHTS, no `.qxw` import.

## Inventory (Debian 13 / Raspberry Pi OS Lite)

| Item | Fact |
|------|------|
| Distro package | `qlcplus` **4.14.1-1** (Qt 5), `qlcplus-data` 4.14.1-1 |
| Executable | `/usr/bin/qlcplus` |
| Qt | Qt 5.15 (`libqt5gui5t64`); platform plugins: eglfs, linuxfb, minimal, offscreen, vnc, xcb |
| Offscreen plugin | `/usr/lib/aarch64-linux-gnu/qt5/plugins/platforms/libqoffscreen.so` |
| Simulate | 79 new packages, **0 to remove**; gpiod / python3-libgpiod / python3-spidev untouched |
| QLC+ 5 | **Not in Debian trixie.** This is 4.14.1 web UI, not the 5.x WebSocket API assumed in `docs/qlc-integration.md`. |

`apt-get update` was required (stale index 404 on `libgraphite2-3`). No `full-upgrade`/`dist-upgrade`. Install pulled **2** dependency upgrades only: `libdrm-common`, `libdrm2`. 96 other packages left un-upgraded.

## Headless launch (manual, not systemd)

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/qlcplus -m -n -w -p
```

`-m/--nowm` `-n/--nogui` `-w/--web` `-p/--operate`. No `--web-auth`, no project file.

Without `QT_QPA_PLATFORM=offscreen`, `qlcplus --help` aborts (`xcb` cannot connect to a display).

## Runtime proof

| Check | Result |
|-------|--------|
| Process | pid 3052 `/usr/bin/qlcplus -m -n -w -p`, no crash-loop |
| Listen | `*:9999` |
| Localhost | `http://127.0.0.1:9999/` HTTP 200, title `QLC+ Webaccess` |
| LAN | `http://shieldxl-light.local:9999/` HTTP 200 (wlan0 192.168.88.246) |
| GPIO after QLC up | `BOOT_CHECK PASS` (K/E/OLED lines free) |
| OLED while QLC up | `test-oled.py` drew `LIGHT CONSOLE` / `OLED PASS`; QLC still pid 3052, port 9999 |

## Shield hardware smoke

- OLED: **PASS** concurrent with QLC+
- K1/K2/K3: **PASS** (`test-combined.py` while QLC pid 3052 still up)
- E1/E2/E3: **PASS** CW and CCW in the same run

## 0.3A PASS

QLC+ 4.14.1 installs and stays headless; web on 9999; Shield XL hardware works at the same time. **Stop.** No wizbridge, WIZ-LIGHTS, Launchpad, production `.qxw`, or systemd.

## Warnings

- Engine is **QLC+ 4.14.1**, not 5.2.x. Do not assume v5 WebSocket commands yet.
- Empty workspace (no production `.qxw`).
- Process is **manual**; it will die on logout/reboot until a later systemd phase.
- Multimedia plugins (`libqt5multimedia5-plugins`) not installed (`--no-install-recommends`).
