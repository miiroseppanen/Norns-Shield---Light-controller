# 0.3D — QLC+ 5.2.2 install + runtime proof

Date: 2026-09-02. Host: `shieldxl-light` (not production). No systemd, no wizbridge, no WIZ-LIGHTS, no production `.qxw`, no Launchpad. No reboot during proof; operator requested a halt after PASS.

Pre-install snapshot: [`phase-03d-preinstall-checkpoint.md`](phase-03d-preinstall-checkpoint.md).

## Reconstruct

Mac artifact (not in git): `/tmp/qlcplus-0.3d-artifact/qlcplus_5.2.2_arm64.deb`

| | |
|--|--|
| Package | `qlcplus` |
| Version | 5.2.2 |
| Architecture | arm64 |
| Size | 9 495 108 bytes |
| SHA256 | `9a16ee3a02c49361cfae4021114c83afbff13d075516ff8a318950eb8f7043e8` |
| md5sums vs image | 2928/2928 |
| `/usr/bin/qlcplus-qml` | ELF aarch64, md5 `1f96146a18d9dd7db1e7cfe9c043299b` |

First install script failed (`/tmp/pkgs-before-0.3d.txt: Permission denied` — sticky `/tmp` + `fs.protected_regular`). Logs moved to `/var/tmp/qlcplus-0.3d/`. Second run: **OK**.

## Install

- Qt 6 Depends: `--no-install-recommends`, **no** `upgrade`/`full-upgrade`. **104** packages added, **0** removed in that step.
- `apt-get remove` `qlcplus` `qlcplus-data` (4.14.1 only). Qt5 left installed (no autoremove). **96** other packages still not upgraded.
- `dpkg -i` reconstructed 5.2.2.

GPIO/SPI stack after: `gpiod` / `python3-libgpiod` / `libgpiod3` 2.2.1-2+deb13u1, `python3-spidev` 3.6-1+b6 — unchanged.

## Udev

Removed `/etc/udev/rules.d/z65-spi.rules`. Left `/usr/lib/udev/rules.d/99-com.rules` (`GROUP="spi", MODE="0660"`). `/dev/spidev0.0` stayed `crw-rw---- root:spi`.

## Version

```
qlcplus  5.2.2  arm64
Q Light Controller Plus version 5.2.2
/usr/bin/qlcplus-qml  ELF 64-bit LSB pie executable, ARM aarch64
```

## Headless (manual, not systemd)

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/qlcplus-qml -w
```

pid 5194 stayed up (no crash-loop). Log notes missing `QtQuick.Controls` / `QtQuick.Layouts` for the native QML UI; **web path still served**.

| Check | Result |
|-------|--------|
| Listen | `*:9999` (`qlcplus-qml`) |
| `http://127.0.0.1:9999/` | HTTP 200, title `QLC+ Web Interface`, `webaccess-v5.css` |
| `http://shieldxl-light.local:9999/` | HTTP 200 |

## WebSocket (QLC+ 5 API)

`ws://127.0.0.1:9999/qlcplusWS` → HTTP 101.

| | |
|--|--|
| Request | `QLC+API\|isProjectLoaded` |
| Response | `QLC+API\|isProjectLoaded\|false` |

Empty workspace (no project). Engine alive after the round-trip.

## Shield hardware while 5.2.2 up

- `verify-boot.py`: **BOOT_CHECK PASS** (K/E/OLED GPIOs unused)
- `test-oled.py`: frame written (`LIGHT CONSOLE` / `OLED PASS`); QLC still pid 5194, port 9999 HTTP 200
- `test-combined.py`: K1/K2/K3 PRESS+RELEASE; E1 CW, E2 CCW, E3 CW; Ctrl-C held=False. QLC still pid 5194, HTTP 200 after the run

No SPI/GPIO steal of Shield lines.

## 0.3D PASS

QLC+ **5.2.2** arm64 is the engine on `shieldxl-light`. Headless web + WebSocket API work. Shield XL hardware works at the same time.

## Cold-boot runtime proof

After operator power-off and power-on (SSH returned). **No systemd.** Manual start only.

Boot state: `qlcplus` 5.2.2; `/usr/bin/qlcplus-qml` present; `/dev/spidev0.0` `crw-rw---- root:spi` (not 0666); `light` in `spi`; **no** QLC process; port 9999 free; no `qlcplus` unit.

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/qlcplus-qml -w
```

nohup pid **1097**. Runtime `Q Light Controller Plus version 5.2.2`. `http://127.0.0.1:9999/` HTTP 200. WebSocket `QLC+API|isProjectLoaded` → `QLC+API|isProjectLoaded|false`.

Hardware while 1097 up: `BOOT_CHECK PASS`; OLED `test-oled.py` PASS; combined: K1/K2/K3 PRESS+RELEASE; E1/E2/E3 CW and CCW. QLC still pid 1097, HTTP 200 after combined.

**Cold-boot runtime proof PASS.** Test process stopped after this record.

## Milestone 0.3 engine baseline COMPLETE

**Stop.** No wizbridge, WIZ-LIGHTS, Launchpad, production `.qxw`, or systemd autostart.
