# 0.3B local inspection — existing QLC+ RaspiOS Trixie archive

Date: 2026-09-02. Mac only. **Nothing installed on `shieldxl-light`.** Debian QLC+ 4.14.1 left untouched. No wizbridge, WIZ-LIGHTS, or production `.qxw`.

Companion guide (same Dropbox folder): `QLC+_RaspberryPi_RaspiOS_Guide.pdf` (header says revision 1.9; last changelog row is 1.10, 2026-05-01, “Updated for Trixie changes”).

## Archive identity

| | |
|--|--|
| Path | `~/Library/CloudStorage/Dropbox/Valot/softa/qlcplus_raspios_trixie_20260613.7z` |
| Exists | **Yes** (`-rw-r--r--@`, 2026-08-11) |
| Size | **516 903 003** bytes (493 MiB) |
| SHA256 | `88c8be7490953455fad0610212adc14e7d88487fe7b97038775791b7dcbba67e` |
| File type | 7-zip archive data, version 0.4 |

7z listing **before extract** (single member):

```
qlcplus_raspios_trixie_20260613.img
```

Not a `.deb`, not a tarball of binaries, not an install script.

## Extract (outside the repo)

Temporary dir: `/tmp/qlcplus-0.3b-inspect/` (not in git).

| | |
|--|--|
| Image path | `/tmp/qlcplus-0.3b-inspect/qlcplus_raspios_trixie_20260613.img` |
| Image size | **2 818 572 288** bytes (2.6 GiB) |
| Image SHA256 | `f96c2bb205c9d21ea543f4d95fdab1811cd122ec2797ed22bb4a14a1c9c0dbc9` |
| Image type | DOS/MBR Raspberry Pi OS disk image |

Partitions:

| # | Type | Start sector | Size | Role |
|---|------|--------------|------|------|
| 1 | 0x0c FAT32 | 16384 | 512 MiB | `bootfs` |
| 2 | 0x83 Linux ext4 | 1064960 | ~2.12 GiB | rootfs |

`issue.txt` / `/etc/rpi-issue`: Raspberry Pi reference **2026-06-14**, pi-gen stage2. `/etc/debian_version`: **13.5**. `/usr/lib/os-release`: Debian 13 (trixie). `config.txt`: `arm_64bit=1`, `dtparam=spi=on`, `hdmi_force_hotplug=1` (“QLC+ workaround for headless case”).

## What this actually is

**Official QLC+ Raspberry Pi OS appliance image** (full SD card contents). Intended use per the PDF: extract 7z → flash `.img` with Raspberry Pi Imager onto a **≥4 GB card** (erases the card). Default user **`pi` / `raspberry`**, hostname **`raspberrypi`**.

It is **not** a drop-in package for the existing Shield XL Lite install (`light` @ `shieldxl-light`).

## QLC+ payload inside the image

Inspected via ext4 read of rootfs (no QEMU, no ARM execution).

| | |
|--|--|
| dpkg | `qlcplus` **5.2.2**, `Status: install ok installed`, **Architecture: arm64** |
| Maintainer | Massimo Callegari (upstream), not Debian’s Jerome Lebleu 4.14.1 package |
| Binary | **`/usr/bin/qlcplus-qml`** present. ELF **64-bit AArch64**. No `/usr/bin/qlcplus` |
| Version string in engine | `Q Light Controller Plus` **`5.2.2`** |
| Desktop | `qlcplus5.desktop` → `Exec=qlcplus-qml --open %f` |
| Debian 4.14.1 | **Not installed.** Apt metadata on the image still *lists* distro `qlcplus 4.14.1-1` as an available package; installed package is the custom 5.2.2 |

### Launch (image default, not production-headless)

`labwc-session.service` (user `pi`, `WantedBy=multi-user.target`) starts Wayland. Then `$HOME/.config/labwc/autostart`:

```sh
export QT_QPA_PLATFORM=wayland
# …
exec qlcplus-qml -f -3 --nowm --web --web-auth $LOADPROJECT
```

`$LOADPROJECT` is set only if `$HOME/.qlcplus/autostart.qxw` exists. **No autostart project** on this image.

Web: `--web` (QLC+ default port **9999**). Extra vs production note: **`--web-auth`**. Platform is **wayland**, not `offscreen`. Qt6 **does** ship `libqoffscreen.so`. PDF FAQ: if QLC+ will not start without HDMI, change `QT_QPA_PLATFORM=wayland` → `offscreen`.

`/usr/sbin/qlcplus-start.sh` and `/usr/lib/systemd/system/qlcplus.service`: **absent** on this Trixie image (PDF still mentions them from older revisions).

### Qt / dependencies (from dpkg)

- Qt **6.8.2** (`libqt6core6t64`, QML/Quick, WebSockets, Wayland, 3D, Multimedia, SerialPort, SVG). PDF “Features” still says Qt 6.4.2 — **stale vs this image**.
- `libgpiod3` 2.2.1, `gpiod`, `python3-libgpiod` installed (QLC GPIO plugin).
- Plugins include **`libgpio.so`**, **`libspi.so`**, UART, MIDI, Art-Net, E1.31, OLA, USB DMX.

### Install / maintainer scripts

No standalone installer in the 7z. The **inner** Debian maintainer scripts:

**`qlcplus.postinst`** (would run if this `.deb` were installed on a live system):

1. `update-menus` if present
2. `update-mime-database /usr/share/mime`
3. `udevadm control --reload-rules`

**`qlcplus.postrm`**: same menu/mime/udev reload.

**Conffiles / udev** (world-writable device nodes):

- `/etc/udev/rules.d/z65-spi.rules` → `SUBSYSTEM=="spidev", MODE="0666"`
- USB DMX / FTDI / Peperoni / Anyma / FX5 HID rules, `MODE="0666"`

No network rewrite, no WIZ AP, no hostname change, no systemd QLC unit in the `.deb` itself. Autostart on the **image** is labwc + the `pi` autostart file, not the `.deb`.

## Production comparison (documented target)

| Production / 0.3 target | This archive |
|-------------------------|--------------|
| `/usr/bin/qlcplus-qml` | **Match** |
| QLC+ **5.2.2** | **Match** (arm64 dpkg + engine string) |
| `QT_QPA_PLATFORM=offscreen` | **Mismatch** — image uses `wayland`; offscreen plugin exists; PDF documents the swap |
| Web port 9999 | **Match** (`--web`; not live-tested on Mac) |
| Headless manual, no autostart | **Mismatch** — labwc session enabled on `multi-user.target`, QLC exec on graphical login |
| `--web-auth` | Image **on**; 0.3A / typical production command **off** |

## Wiz / production-show specifics

**None found** in the image: no `wizbridge`, `WIZ-LIGHTS`, `valot.local`, production `.qxw`, or Launchpad unit. Sample workspace only: `/usr/share/qlcplus/Sample.qxw`. This is upstream QLC+ Pi OS, not a clone of the lighting Pi.

## Guide PDF vs image (do not treat the PDF as a script to run)

- Flash-the-whole-card workflow. Example filename in the PDF is still `qlcplus_raspios_bookworm_*.img`.
- Chapter 10 “Manual installation” still says `wget …/qlcplus_x.y.z_armhf.deb` (**32-bit**). **No `.deb` is in this 7z**; the installed payload is **arm64 5.2.2**.
- SPI display overlays (`piscreen`, `pitft`, …) and GPIO plugin pin map would fight Shield XL OLED/encoders if enabled.
- Default SSH `pi`/`raspberry`. Shield host is `light` @ `shieldxl-light`.

**The PDF was not executed.** Flashing or running chapter 10 on `shieldxl-light` would be a later, explicit step.

## Why this must not be flashed onto the Shield card

Flashing would wipe the 0.2 bring-up (hostname, user `light`, OLED userspace, proven GPIO map) and replace it with a `pi` appliance that auto-starts QLC on Wayland and ships GPIO/SPI plugins plus `spidev` udev `0666`.

## Verdict

**B — usable but requires changes.**

The *software inside* is the right class of build: **QLC+ 5.2.2, aarch64/arm64, RaspiOS Trixie**, binary `qlcplus-qml`, Qt 6 offscreen plugin present, web 9999, no wizbridge/production show.

The *archive* is a **full OS image**, not a safe install onto the existing Shield Pi. Next step if approved (not done): extract or obtain the **arm64 `qlcplus` 5.2.2 `.deb`**, install onto current Lite OS **after** a plan for replacing 4.14.1, pulling Qt 6 deps, **not** enabling labwc autostart, launching with `QT_QPA_PLATFORM=offscreen`, and keeping GPIO/SPI plugins off Shield XL pins. Do not flash this `.img` onto the Shield microSD.

**Stop.** No Pi package changes until explicit approval.
