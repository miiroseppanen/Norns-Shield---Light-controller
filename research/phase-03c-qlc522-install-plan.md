# 0.3C — QLC+ 5.2.2 package extraction + install plan

Date: 2026-09-02. **Plan only.** Nothing installed or removed on `shieldxl-light`. Debian QLC+ 4.14.1 still running (pid 3052). No wizbridge, WIZ-LIGHTS, labwc copy, `--web-auth`, systemd, or production `.qxw`.

Source image: `/tmp/qlcplus-0.3b-inspect/qlcplus_raspios_trixie_20260613.img` (see `phase-03b-existing-qlc5-package.md`).

## 1. Installed package metadata (image dpkg status)

There is **one** installed QLC package on the image: `qlcplus` 5.2.2. No `qlcplus-data`. Fixtures/web/translations live inside this package.

| Field | Value |
|-------|--------|
| Package | `qlcplus` |
| Version | **5.2.2** |
| Architecture | **arm64** |
| Status | `install ok installed` |
| Maintainer | Massimo Callegari `<massimocallegari@yahoo.it>` |
| Installed-Size | 40192 (KB) |
| Suggests | *(none)* |
| Conflicts / Replaces / Provides | *(none recorded)* |

**Depends** (verbatim):

```
libasound2t64 (>= 1.1.1), libc6 (>= 2.38), libfftw3-double3 (>= 3.3.10),
libftdi1-2 (>= 1.5), libgcc-s1 (>= 3.0), libgpiod3 (>= 2.1),
libqt63dcore6 (>= 6.6.1), libqt63dextras6 (>= 6.6.1),
libqt63dlogic6 (>= 6.6.1), libqt63drender6 (>= 6.6.1),
libqt6core6t64 (>= 6.8.2), libqt6gui6 (>= 6.4.0),
libqt6multimedia6 (>= 6.6.1), libqt6network6 (>= 6.1.2),
libqt6printsupport6 (>= 6.1.2), libqt6qml6 (>= 6.6.0),
libqt6quick6 (>= 6.6.0), libqt6serialport6 (>= 6.6.0),
libqt6svg6 (>= 6.6.0), libqt6websockets6 (>= 6.6.0),
libqt6widgets6 (>= 6.1.2), libstdc++6 (>= 14),
libudev1 (>= 183), libusb-1.0-0 (>= 2:1.0.16)
```

**Recommends:** `libsndfile1`, `libqt5multimedia5-plugins` (Qt 5 leftover; **do not install**).

**Conffiles:**

| Path | md5 |
|------|-----|
| `/etc/udev/rules.d/z65-anyma-udmx.rules` | `3d5d17fd15cf94fa682ae2f8a80da815` |
| `/etc/udev/rules.d/z65-dmxusb.rules` | `b5281529d26b6e64dd9f0b0edbcb240c` |
| `/etc/udev/rules.d/z65-fx5-hid.rules` | `f686bb01639a984991c308b1cdd221d4` |
| `/etc/udev/rules.d/z65-peperoni.rules` | `e1ad0ceb2d2b8b358525eb82ef01be29` |
| `/etc/udev/rules.d/z65-spi.rules` | `a1ec69561c6e901eb4fb058bb060bb34` |

**Maintainer scripts:** `postinst` / `postrm` only (`update-menus` if present, `update-mime-database`, `udevadm control --reload-rules`). No network, hostname, systemd, or labwc changes.

**Files:** `qlcplus.list` has **3118** entries; **2928** md5sums (directories have none). Payload is almost all `/usr/share/qlcplus/` (3051 paths: fixtures, translations, web). Runtime set:

- `/usr/bin/qlcplus-qml` (5 091 024 bytes, ELF aarch64, md5 `1f96146a18d9dd7db1e7cfe9c043299b` — matches image)
- `/usr/lib/aarch64-linux-gnu/libqlcplusengine.so`
- `/usr/lib/aarch64-linux-gnu/libqlcpluswebaccess.a` (static; web is linked into the binary)
- Qt6 plugins under `/usr/lib/aarch64-linux-gnu/qt6/plugins/qlcplus/`
- Desktop/mime/doc/metainfo
- Web UI: `webaccess-v5.html` / `.js` / `.css`, `simpledesk-v5.*`, `websocket.js`

No `/usr/bin/qlcplus`. No `qlcplus.service`. No labwc files in the package.

## 2. Original `.deb` on the image

**Not present.** Searched `/var/cache/apt/archives/` (empty of debs), `partial/`, `/home`, `/root`, `/opt`, `/usr/src`, `/usr/local`, `/tmp`, `/boot`. Apt lists mention Debian **4.14.1-1**, not this 5.2.2 build.

Cannot SHA256 an upstream `.deb`. Analysis uses installed files + dpkg metadata.

## 3. Reconstruction (Mac, not Pi)

`dpkg-repack` on Shield would require the package to already be installed — circular. Reliable path: **repack from the image rootfs** using `qlcplus.list` + `qlcplus.md5sums` + scripts.

Spot-check (image file md5 vs dpkg md5sums): `qlcplus-qml`, `libgpio.so`, `libspi.so`, `libartnet.so`, `libmidiplugin.so` all **match**.

Procedure (outside the repo, e.g. `/tmp/qlcplus-0.3c-deb/`):

1. Extract every regular file in `qlcplus.list` from ext4 (offset 545259520).
2. Verify all 2928 md5sums.
3. Build a Debian binary package (`debian-binary` + `control.tar` + `data.tar`) with the status fields above (without the `Status:` line).
4. Record SHA256 of the new `.deb`. Do not commit it (tens of MB).

That `.deb` is what gets copied to the Pi later.

## 4. Plugin inventory

Directory: `/usr/lib/aarch64-linux-gnu/qt6/plugins/qlcplus/`

| File | Role |
|------|------|
| `libartnet.so` | Art-Net |
| `libmidiplugin.so` | MIDI / ALSA |
| `libe131.so` | sACN E1.31 |
| `libosc.so` | OSC |
| `libloopback.so` | Loopback |
| `libdmxusb.so` / `libudmx.so` / `libdmx4linux.so` / `libpeperoni.so` / `libenttecwing.so` / `libhidplugin.so` | USB/HID DMX |
| `libolaio.so` | OLA (optional; ola not a Depends) |
| `libos2l.so` | OS2L |
| `libgpio.so` | Raspberry Pi GPIO I/O plugin (**new vs Debian 4.14.1**) |
| `libspi.so` | SPI LED/DMX output (`/dev/spidev0.0`) |
| `libuart.so` | UART DMX |
| `audio/libsndfileplugin.so` | Audio (needs Recommends `libsndfile1`) |

WebSocket/web access is **not** a `.so`. It is built into `qlcplus-qml` (`qlcplusWS`, `9999`, `Webaccess` strings present) plus `/usr/share/qlcplus/web/webaccess-v5.*`.

## 5. GPIO / SPI: load vs claim

QLC+ loads IO plugins at process start. That is **not** the same as claiming hardware.

### SPI (`plugins/spi/spiplugin.cpp` tag `QLC+_5.2.2`)

- `init()`: sets `m_spifd = -1`. **Does not open the device.**
- `outputs()`: `QFile::exists("/dev/spidev0.0")` only.
- `open("/dev/spidev0.0", O_RDWR)` happens in **`openOutput()`**, i.e. when a universe is mapped to SPI.

Empty workspace (this proof) does not map SPI → plugin must not open `spidev0.0`. Debian 4.14.1 already ships `libspi.so` (Qt5 path); combined smoke **PASS** while that QLC was running.

### GPIO (`plugins/gpio/gpioplugin.cpp` + `gpioreaderthread.cpp` tag `QLC+_5.2.2`)

Debian 4.14.1 **has no** `libgpio.so`. 5.2.2 does.

On `init()` the plugin:

1. Scans `/dev` for gpiochips and constructs `gpiod::chip` to call `get_info()` (enumerate, not `do_request()`).
2. Auto-selects the first chip, then `updateLinesList()` — another `get_info()` / line metadata read.
3. Each line starts `m_enabled = false`, `m_direction = NoDirection`.

Line **request** (`prepare_request` / `do_request` with INPUT or OUTPUT) happens only if a workspace sets a pin to Input/Output (`setLineDirection` / `setLineValue` / reader thread). `openInput()` explicitly does **not** start the reader until pins are configured.

So: **shared library is loaded at start; lines are not requested unless the GPIO plugin is used in the project.** Empty workspace must not drive Shield K/E pins. Residual risk is only the gpiochip `get_info()` open, which libgpiod treats as non-exclusive vs line requests. Prove with combined smoke; if it ever fights python-libgpiod, move `libgpio.so` aside (not the default plan).

Do **not** treat file presence as a GPIO/SPI conflict.

## 6. `spidev MODE=0666`

Exact file from the 5.2.2 package (and already from Debian 4.14.1):

```
SUBSYSTEM=="spidev", MODE="0666"
```

| | 4.14.1 on Shield today | 5.2.2 package |
|--|------------------------|---------------|
| Path | `/usr/lib/udev/rules.d/z65-spi.rules` | `/etc/udev/rules.d/z65-spi.rules` (conffile) |
| Content | identical 34-byte rule | identical |

Raspberry Pi OS also has `/usr/lib/udev/rules.d/99-com.rules`:

```
SUBSYSTEM=="spidev", GROUP="spi", MODE="0660"
```

Lexical order: `99-com.rules` then `z65-spi.rules`, so **z65 wins** and would set **0666** on the next udev add/reboot. Today `/dev/spidev0.0` is still `crw-rw---- root:spi` because 4.14.1 `postinst` only `udevadm control --reload-rules` and did not retrigger existing nodes. `light` is in group `spi`; OLED userspace SSD1322 needs group write, not world write.

0666 would **not** stop OLED; it only widens permissions. It is **not required** for this console (no QLC SPI LED panels). **Do not keep z65-spi.rules on the Shield.** After `dpkg -i`, delete `/etc/udev/rules.d/z65-spi.rules` and `udevadm control --reload-rules`. Do not `udevadm trigger` on `spidev`. USB `z65-*.rules` can stay (no such devices expected).

## 7. Depends vs current Shield Pi (Debian 13.5)

Host matches image userspace: Debian **13.5**, aarch64.

Already satisfied (no install): `libasound2t64`, `libc6`, `libfftw3-double3`, `libftdi1-2`, `libgcc-s1`, **`libgpiod3`**, `libqt6core6t64`, `libstdc++6`, `libudev1`, `libusb-1.0-0`. GPIO/SPI Python stack already present: `gpiod`, `python3-libgpiod`, `python3-spidev`.

Missing (must install): Qt 6 GUI/QML/Quick/WebSockets/Multimedia/3D/SVG/SerialPort/Print/Widgets + `libqt6gui6` (owns **`libqoffscreen.so`**).

`apt-get -s --no-install-recommends install` of those Qt6 libraries: **105 packages to install, 0 to remove.** No `Remv`/`Purg` of `python3-spidev`, `python3-libgpiod`, `gpiod`, or `libgpiod3`.

`libqt6gui6` Recommends `qt6-wayland` and `qt6-qpa-plugins`. **`--no-install-recommends`** so Wayland is not pulled. Offscreen comes from `libqt6gui6`, not from `qt6-qpa-plugins` (that package is VNC/uioTouch only).

Do **not** `full-upgrade` / `dist-upgrade`. Do **not** autoremove Qt5 after 4.14.1 removal (rollback convenience).

## 8. Coexistence with 4.14.1

**Not possible as two dpkg packages.** Same name `qlcplus`. Shared paths:

- `/usr/lib/aarch64-linux-gnu/libqlcplusengine.so`
- `/usr/share/qlcplus/**` (5.2.2 list vs `qlcplus-data` 4.14.1, 2912 files)

4.14.1 extras that **go away**: `/usr/bin/qlcplus`, `qlcplus-fixtureeditor`, Qt5 plugin dir, `qlcplus-data` package.

5.2.2 adds `/usr/bin/qlcplus-qml` and Qt6 plugin dir.

Keeping 4.14.1 is not required. Clean result: **remove `qlcplus` + `qlcplus-data`, then install reconstructed 5.2.2.** Cached rollback debs already on the Pi:

| File | SHA256 |
|------|--------|
| `/var/cache/apt/archives/qlcplus_4.14.1-1_arm64.deb` | `78e0b83242983bd9d86c1511f3d45f18e0b3b6cb5348192601102530208aa80a` |
| `/var/cache/apt/archives/qlcplus-data_4.14.1-1_all.deb` | `f0681ce0a0bc1a1b77787806e46a4af5d36912baa012628c837a6a97cd4af23d` |

## 9. Target runtime (proof only)

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/qlcplus-qml -w
```

No labwc/Wayland autostart, no `--web-auth`, no systemd, no project file. Port 9999 is compiled into the binary (`-w` / `--web`).

## 10. Install plan (execute only after approval)

Pi-changing commands start at step 2. Step 1 is Mac-only.

1. **Mac:** reconstruct `qlcplus_5.2.2_arm64.deb` from the image; verify all md5sums; record SHA256.
2. **Pi:** stop the manual 4.14.1 process (`pkill` the existing `qlcplus` pid). Confirm GPIO/OLED still free.
3. **Pi:** `apt-get install --no-install-recommends` the missing Qt6 Depends listed in §7 (explicit package names, no `full-upgrade`). Re-check `python3-spidev`, `python3-libgpiod`, `gpiod` still `install ok`. Confirm `/usr/lib/aarch64-linux-gnu/qt6/plugins/platforms/libqoffscreen.so`.
4. **Pi:** `apt-get remove` `qlcplus` `qlcplus-data` (not `autoremove`).
5. **Pi:** `dpkg -i` the reconstructed 5.2.2 `.deb`.
6. **Pi:** `rm -f /etc/udev/rules.d/z65-spi.rules` then `udevadm control --reload-rules`. Leave `/dev/spidev0.0` as `0660 root:spi`.
7. **Launch:** `QT_QPA_PLATFORM=offscreen /usr/bin/qlcplus-qml -w` (manual, `nohup`/ssh session; not systemd).
8. **Prove web:** process stays up; `ss` shows `*:9999`; `http://127.0.0.1:9999/` and `http://shieldxl-light.local:9999/` HTTP 200; page is v5 webaccess; WebSocket `ws://127.0.0.1:9999/qlcplusWS` accepts `QLC+API|isProjectLoaded` (or equivalent POLL).
9. **Hardware:** same combined smoke as 0.3A while 5.2.2 is up (`test-oled.py`, `test-combined.py` K1–K3 and E1–E3). `verify-boot.py` still PASS.

### Rollback

```bash
# stop 5.2.2
# dpkg -i the two cached 4.14.1 debs (SHA256 above)
# restore z65-spi handling as it was under /usr/lib (comes back with 4.14.1)
QT_QPA_PLATFORM=offscreen /usr/bin/qlcplus -m -n -w -p
```

Qt6 libraries may remain installed; they do not remove the GPIO/SPI Python stack.

### Out of scope

wizbridge, WIZ-LIGHTS, Launchpad, production `.qxw`, systemd, copying image `labwc-session.service` or `pi` autostart.

## Verdict

**READY TO INSTALL**

First action after approval is Mac-side `.deb` reconstruction, then the Pi sequence above. Still stopped before any Pi-mutating command.
