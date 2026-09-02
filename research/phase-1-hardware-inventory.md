# Phase 1 — Read-only hardware inventory

Date: 2026-09-01. Host: `light@shieldxl-light.local` (wlan0 `192.168.88.246`).  
Collected over SSH. **No packages installed, no `config.txt` edits, no overlays added, no reboot.**

Operator already confirmed first boot + SSH. This note is the read-only inventory (milestone doc “Phase 2”). Phase 1 PASS here means: inventory is complete enough to plan GPIO tests. **K1/K2/K3 not started.**

## 1. Pi hardware

| Item | Value |
|------|--------|
| Model | Raspberry Pi 4 Model B Rev 1.5 |
| Revision | `c03115` |
| Serial | `100000002d8a53cb` |
| RAM | 3.7 GiB |
| `vcgencmd get_throttled` | `0x0` (not throttled) |
| `vcgencmd measure_temp` | 47.7 °C |

Shield XL is physically on the Pi (operator).

## 2. OS / kernel / arch

| Item | Value |
|------|--------|
| OS | Debian GNU/Linux 13 (trixie), Raspberry Pi OS Lite 64-bit |
| Kernel | `6.18.34+rpt-rpi-v8` `#1 SMP PREEMPT Debian 1:6.18.34-1+rpt1 (2026-06-09)` |
| Arch | aarch64 / arm64 |
| Hostname | `shieldxl-light` |

SSH locale warning `LC_CTYPE=UTF-8 invalid` is present; inventory used `LC_ALL=C` and was not blocked.

## 3. Boot config and overlays

`/boot/firmware/config.txt` is stock Raspberry Pi OS Lite. Relevant lines:

- `#dtparam=i2c_arm=on` — **commented, off**
- `#dtparam=i2s=on` — **commented, off**
- `#dtparam=spi=on` — **commented, off**
- `dtparam=audio=on` — analog BCM2835 headphones + HDMI codec path, **not** CS4270
- `dtoverlay=vc4-kms-v3d`, `max_framebuffers=2` — HDMI/GPU DRM
- `camera_auto_detect=1`, `display_auto_detect=1`
- `arm_64bit=1`, `arm_boost=1`

**Loaded Shield XL / norns overlays: none.** No `ssd1322-spi`, `norns-buttons-encoders`, `monome-snd-4270`, `midi-uart0`.

Device-tree status:

| Block | Status |
|-------|--------|
| SPI0 (`spi@7e204000`) | **disabled** |
| I2C1 / I2C0 (ARM) | **disabled** |
| I2S | **disabled** |
| PL011 serial (`serial@7e201000`) | okay (Bluetooth HCI, not header UART) |

## 4. GPIO / pinctrl (read-only)

`pinctrl` and `gpioinfo` present. Header GPIOs **2–27 are all `input`**, no alt function, **no gpioinfo consumer** except onboard ACT LED on GPIO42.

Idle levels vs `research/shieldxl.md` (active-low keys have 10 kΩ pull-ups on the shield):

| Function (research) | BCM | pinctrl | Idle level | Claimed? |
|---------------------|-----|---------|------------|----------|
| I2C SDA (CS4270) | 2 | input pu | hi | no |
| I2C SCL (CS4270) | 3 | input pu | hi | no |
| E1 A | 4 | input pu | hi | no |
| OLED D/C | 5 | input pu | hi | no |
| OLED RESET | 6 | input pu | hi | no |
| OLED CE0 | 8 | input pu | hi | no |
| OLED MOSI | 10 | input pd | lo | no |
| OLED SCLK | 11 | input pd | lo | no |
| overlay e2 A | 12 | input pd | lo | no |
| K3 | 13 | input pd | **hi** | no (shield pull-up) |
| UART TX MIDI | 14 | input pn | hi | no (not UART alt) |
| UART RX MIDI | 15 | input pu | hi | no |
| Codec reset | 17 | input pd | lo | no |
| I2S 18–21 | 18–21 | input pd | lo | no |
| K1 | 22 | input pd | **hi** | no |
| overlay e3 B | 23 | input pd | lo | no |
| overlay e3 A | 24 | input pd | lo | no |
| overlay e2 B | 25 | input pd | lo | no |
| K2 | 26 | input pd | **hi** | no |
| E1 B | 27 | input pd | lo | no |

**Shield XL GPIOs are free** (not claimed by a driver). Physically wired to the shield; do not reuse codec/I2S/I2C pins.

## 5–8. SPI / I2C / UART / `/dev`

| Device | Present? |
|--------|----------|
| `/dev/spidev*` | **no** |
| `/dev/i2c-*` | **no** |
| `/dev/fb*` | **no** |
| `/dev/dri/card0` | yes — V3D |
| `/dev/dri/card1` | yes — `vc4` GPU / HDMI |
| `/dev/gpiochip0` | yes (58 lines) |
| `/dev/gpiomem` | yes |
| `/dev/input/event0–3` | HDMI CEC / HDMI jack only |
| Header UART `/dev/ttyAMA0` as GPIO14/15 | **not in alt UART mode** |

dmesg: `fe201000.serial: ttyAMA1` + `hci_uart_bcm serial0-0` — Bluetooth, not shield MIDI.

## 9. DRM / framebuffer / display

- No `/dev/fb0` (KMS without a connected HDMI panel; dmesg: `vc4-drm gpu: [drm] Cannot find any crtc or sizes`).
- DRM: `v3d` minor 0, `vc4` minor 1, connectors `HDMI-A-1` / `HDMI-A-2`.
- **No SSD1322 DRM/fb device.**

## 10. USB

Onboard xHCI + VIA hub only. No Launchpad (expected; not in 0.2).

## 11. ALSA / audio

Cards: `bcm2835 Headphones`, `vc4-hdmi-0`, `vc4-hdmi-1`.  
**No CS4270 / `monome-snd-4270` / I2S codec.** `snd_bcm2835` is the stock analog/HDMI enable from `dtparam=audio=on`.

## 12. Network

| Iface | State | Addr |
|-------|-------|------|
| wlan0 | UP | 192.168.88.246/24 (LIGHT-CONTROL) |
| eth0 | DOWN, no carrier | MAC `88:a2:9e:5f:ca:0f` |

## 13. Loaded modules (relevant)

`vc4`, `v3d`, `drm*`, `snd_bcm2835`, `snd_soc_hdmi_codec`, `brcmfmac`, `hci_uart`, `raspberrypi_gpiomem`.  
**Not loaded:** `spi_bcm2835`, `spidev`, `i2c_bcm2835`, `snd_soc_cs4270`, `fbtft`, any `fb_ssd*`.

## 14. dmesg (filtered)

Hits: pinctrl init, PL011/BT UART, `rpi-gpiomem`, `snd_bcm2835` staging warning, vc4/v3d DRM, HDMI input devices.  
**No** SPI probe, **no** SSD1322, **no** CS4270, **no** fbtft.

## 15. `vcgencmd`

Present (`/usr/bin/vcgencmd`). `get_throttled=0x0`. Not installed for this inventory.

## Overlay files on this OS (U3)

Under `/boot/firmware/overlays` and `/lib/modules/6.18.34+rpt-rpi-v8`:

- **No `ssd1322-spi.dtbo`**, no `fb_ssd1322.ko`, overlays README has **no ssd1322**.
- Nearby but **wrong IC**: `ssd1306-spi`, `ssd1327-spi`, `ssd1331-spi`, `ssd1351-spi`; fbtft has `fb_ssd1306`, `fb_ssd1331`, `fb_ssd1351` — not 1322.
- **No** `norns-buttons-encoders` / `monome-snd-4270`.
- **Usable later (not enabled):** `gpio-key.dtbo`, `rotary-encoder.dtbo`, `fbtft.dtbo`, `spi0-1cs.dtbo` / `dtparam=spi=on`.

## Comparison to `research/shieldxl.md`

| Question | Inventory answer |
|----------|------------------|
| SSD1322 ready-made support on this kernel? | **No overlay, no `fb_ssd1322`.** Do not use ssd1306/1327/1331/1351 overlays. OLED path is still U3 fallback: userspace SPI **or** bring a 1322 overlay later. |
| SPI enabled? | **No.** `dtparam=spi=on` commented; SPI0 `disabled`; no `/dev/spidev*`. |
| Framebuffer/DRM for OLED? | **No.** Only HDMI vc4/v3d DRM; no fbdev. |
| Shield XL GPIOs free? | **Yes** (header 2–27 unclaimed). Idle K1/K2/K3 high matches active-low + pull-ups. |
| CS4270 active? | **No.** I2S/I2C off; no codec driver. Pins still wired — do not steal 2, 3, 17–21. |
| Overlay conflict with shield? | **None loaded.** Stock `vc4-kms-v3d` is HDMI-only. `dtparam=audio=on` is PWM/HDMI, not I2S. Enabling `spi=on` + `gpio-key`/`rotary-encoder` later is the planned path; do **not** load norns audio/MIDI overlays. |

## Safe next-phase plan (not executed)

Phase 3 (buttons only), when approved:

1. Enable **only** `gpio-key` for BCM **22, 26, 13**, active_low, pull up.
2. Do not enable SPI, I2S, I2C, encoders, or OLED in that step.
3. Confirm with `evtest` / `/dev/input/event*`. Keep CS4270 pins untouched.

## Phase 1 PASS criteria

Inventory collected from a live Pi 4 + shieldXL, compared to pin research, no show-stack installs. **PASS.**
