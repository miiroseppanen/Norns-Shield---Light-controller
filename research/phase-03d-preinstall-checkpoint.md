# 0.3D pre-install checkpoint

Date: 2026-09-02. Host: `shieldxl-light`. Taken before Qt6/5.2.2 install.

## QLC (Debian)

```
ii  qlcplus        4.14.1-1     arm64
ii  qlcplus-data   4.14.1-1     all
```

Runtime: `Q Light Controller Plus version 4.14.1` via `QT_QPA_PLATFORM=offscreen qlcplus --version`. Binary `/usr/bin/qlcplus`. No `qlcplus-qml`.

Manual 4.14.1 process (pid 3052, `-m -n -w -p`) was **stopped** after this snapshot so 5.2.2 can replace it.

`~/.qlcplus` exists (empty fixture/input/midi/rgb dirs). No autostart `.qxw`.

## Hardware baseline

- `light` groups include **spi** and **gpio**
- `/dev/spidev0.0` `crw-rw---- root:spi` (0660)
- `/usr/lib/udev/rules.d/z65-spi.rules`: `SUBSYSTEM=="spidev", MODE="0666"` (from 4.14.1; not applied to live node)
- `/usr/lib/udev/rules.d/99-com.rules`: `SUBSYSTEM=="spidev", GROUP="spi", MODE="0660"`
- No `/etc/udev/rules.d/z65-spi.rules`
- `verify-boot.py`: **BOOT_CHECK PASS** (K/E/OLED GPIOs unused, `dtparam=spi=on`, `/dev/spidev0.0` YES)
- Combined smoke: known **PASS** from 0.3A with 4.14.1 concurrent
- Stack: `gpiod` / `python3-libgpiod` / `libgpiod3` 2.2.1-2+deb13u1; `python3-spidev` 3.6-1+b6

`/boot/firmware/config.txt`: `dtparam=spi=on`, `arm_64bit=1`, no Shield-specific overlay changes in this milestone.

## Reconstructed 5.2.2 artifact (Mac, not git)

Path: `/tmp/qlcplus-0.3d-artifact/qlcplus_5.2.2_arm64.deb` (copied to Pi `/tmp/qlcplus_5.2.2_arm64.deb`)

| | |
|--|--|
| Package | `qlcplus` |
| Version | `5.2.2` |
| Architecture | `arm64` |
| Size | 9 495 108 bytes |
| SHA256 | `9a16ee3a02c49361cfae4021114c83afbff13d075516ff8a318950eb8f7043e8` |
| md5sums | 2928/2928 match image |
| `/usr/bin/qlcplus-qml` | present, ELF aarch64, md5 `1f96146a18d9dd7db1e7cfe9c043299b` |

## Install blocked

`sudo -n` on `shieldxl-light` now requires a password. Script waiting: `/tmp/0.3d-install.sh`.
