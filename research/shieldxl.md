# Shield XL hardware research

Status: Milestone 0.1 research. **No GPIO driver is implemented from this document yet.**

This file records facts from primary sources. Missing items are listed as UNKNOWN with a verification plan. Do not copy pin numbers from the original norns Compute Module documentation onto a Raspberry Pi 4.

## Identity

| Item | Fact | Source | Confidence |
|------|------|--------|------------|
| Product | Denki Oto **shieldXL** — rework of monome norns shield | [denki-oto product](https://denki-oto.com/products/shieldxl-diy-norns-synthesizer-kit), [okyeron/shieldXL](https://github.com/okyeron/shieldXL) | HIGH |
| Hardware lineage | Based on monome norns shield **210330** (CS4270 codec) | shieldXL README: “based on the 210330 version”; KiCad README “Based on the 210330 norns shield” | HIGH |
| shieldXL PCB revision seen in repo | ShieldXL-M-20230615 (KiCad 8) | [okyeron/shieldXL `kicad/`](https://github.com/okyeron/shieldXL/tree/main/kicad/ShieldXL-M-20230615) | HIGH |
| Software compatibility claim | Stock norns **shield** disk image (pre-211028 / cs4270), Pi 3 or Pi 4 | shieldXL README; [norns-image 231114](https://github.com/monome/norns-image/releases/tag/231114-img) | HIGH as a norns claim; **not used by this project** |
| Pi support | Pi 3B / 3B+ / 4B | BOM.md | HIGH |
| This project’s Pi | Raspberry Pi 4 + **new** microSD (Raspberry Pi OS / Debian). Not the Norns image. | Project brief | HIGH |

GitHub repo inspected: `https://github.com/okyeron/shieldXL` (branch `main` at research time). Design files are GPLv3.

## Critical: two different norns pinouts

| Platform | GPIO map | Must not use for shieldXL |
|----------|----------|---------------------------|
| Original norns (CM3) | KEY1=GPIO31, KEY2=GPIO35, KEY3=GPIO39, ENC 28/29, 32/33, 36/37; OLED SPI + GPIO5/6 | **Do not use this map on Pi 4.** Those GPIOs are not on the 40-pin header. |
| norns shield / shieldXL on Pi 3/4 | Overlay defaults overridden in `config.txt` (see below) | Use this family |

Source for the CM3 map: [monome/norns-image `readme-hardware.md`](https://github.com/monome/norns-image/blob/main/readme-hardware.md). Explicitly CM3. Confirmed in [norns-image#49](https://github.com/monome/norns-image/issues/49) (okyeron): those numbers are not Pi 40-pin header GPIOs.

The kernel overlay `norns-buttons-encoders` **defaults** to the CM3 pins, but exposes `__overrides__` (`e1_pin_a`, `b1_pin`, …). The shield image / shieldXL MIDI install config **overrides** those defaults.

## A) OLED

| Item | Fact | Source | Confidence |
|------|------|--------|------------|
| Panel | Newhaven **NHD-2.7-12864WDW3-M** (Molex/FPC), 2.7", white. Yellow variant NHD-2.7-12864WDY3-M optional. | shieldXL README, BOM.md, [Newhaven spec](https://newhavendisplay.com/content/specs/NHD-2.7-12864WDW3.pdf) | HIGH |
| Resolution | 128 × 64 pixels | Newhaven spec; norns software | HIGH |
| Controller IC | **SSD1322** | Newhaven spec “Driver IC: SSD1322”; norns `dtoverlay=ssd1322-spi` | HIGH |
| Greyscale | 16-step (4-bit) white OLED | Newhaven spec; norns-image hardware notes | HIGH |
| Host interface on this PCB | **4-wire SPI** | Eagle 210330: BS0 and BS1 tied to GND. Newhaven: BS1=0, BS0=0 → 4-wire serial | HIGH |
| SPI MOSI | Pi **SPI0 MOSI = GPIO10** (header pin 19) | Eagle net `MOSI`: `X1.SPI_MOSI` → OLED `SDIN` | HIGH |
| SPI SCLK | Pi **SPI0 SCLK = GPIO11** (header pin 23) | Eagle net `SCK`: `X1.SPI_SCLK` → OLED `SCLK` | HIGH |
| SPI CS | Pi **SPI0 CE0 = GPIO8** (header pin 24) | Eagle net `CE0`: `X1.SPI_CE0` → OLED `/CS` | HIGH |
| D/C | **GPIO5** (header pin 29) | Eagle net `O_DC`: `X1.GPIO05` → OLED `D/C` | HIGH |
| RESET | **GPIO6** (header pin 31), active low | Eagle net `O_RESET`: `X1.GPIO06` → OLED `/RES` | HIGH |
| MISO | Not wired to the OLED (write-only SPI) | No MISO net to `U$1` in Eagle 210330 | HIGH |
| Init | Newhaven example: `/RES` low ≥200 µs, then command sequence (`0xAE` off … `0xAF` on). Kernel `fb_ssd1322` / overlay does this if used. | Newhaven spec “Example Software Routines” | HIGH for datasheet; overlay init **not re-read from a running Pi yet** |
| Linux driver (norns) | `dtoverlay=ssd1322-spi`, `dtparam=spi=on`, `dtparam=rotate=180` | shieldXL `install/boot/config.txt` | HIGH for norns image; **must be revalidated on Raspberry Pi OS** |
| Framebuffer | norns: fbtft SSD1322, historically `/dev/fb1` (or `fb0` if no HDMI). 4-bit packed greyscale. | norns-image hardware notes; matron screen code | MEDIUM — device node name is distro/HDMI dependent |
| Cable | 20-pin 1 mm pitch FFC, opposite-side contacts, 31 or 51 mm. Blue side up, away from PCB, into bottom Molex. | BUILD.md, BOM.md | HIGH |
| Can we reuse norns driver? | **Possibly** the kernel overlay + `fb_ssd1322`, **not** matron/cairo/norns userspace. Overlay must exist on the **new** OS kernel. | Research conclusion | MEDIUM until proven on Raspberry Pi OS |

Do not assume SSD1306. This panel is SSD1322.

## B) Encoders E1 / E2 / E3

Mechanical: Bourns **PEC11R-4015F-N0024**, 24 pulse incremental, D-shaft (BOM.md).

Schematic (Eagle norns-shield-210330, nets `A1`/`B1` … and parts `E1`/`E2`/`E3`):

| Schematic part | A (net) | B (net) | BCM GPIO A | BCM GPIO B |
|----------------|---------|---------|------------|------------|
| E1 | A1 | B1 | **4** | **27** |
| E2 | A2 | B2 | **24** | **23** |
| E3 | A3 | B3 | **12** | **25** |

Passive network per encoder: 10 kΩ series resistors, 10 kΩ pull-ups to 3.3 V, 10 nF to GND (RC). Kernel overlay also sets `brcm,pull = <2>` (pull-up). Quadrature via Linux `rotary-encoder` (`relative-axis`, `half-period` in the norns overlay).

**norns overlay parameters** from shieldXL `install/boot/config.txt` (this is what the norns shield image actually loads):

```
dtoverlay=norns-buttons-encoders
dtparam=e1_pin_a=4
dtparam=e1_pin_b=27
dtparam=e2_pin_a=12
dtparam=e2_pin_b=25
dtparam=e3_pin_a=24
dtparam=e3_pin_b=23
```

| Norns overlay name | Pins | Matches schematic part |
|--------------------|------|------------------------|
| e1 | GPIO 4 / 27 | E1 | HIGH |
| e2 | GPIO 12 / 25 | schematic **E3** | see UNKNOWN |
| e3 | GPIO 24 / 23 | schematic **E2** | see UNKNOWN |

Direction (CW vs CCW) and which physical knob is norns “E2” vs “E3” are **not** assumed. Verify with `evtest` on hardware (Milestone 0.2).

Debounce: hardware RC plus kernel encoder driver. Userspace extra debounce is optional.

Interrupts: kernel overlay / `rotary-encoder`, not userspace polling. Userspace should read **evdev**, not bit-bang GPIO.

## C) Buttons K1 / K2 / K3

| Button | BCM GPIO | Header pin | Active | Pull-up |
|--------|----------|------------|--------|---------|
| K1 | **22** | 15 | **LOW** (switch to GND) | 10 kΩ to 3.3 V + overlay pull-up |
| K2 | **26** | 37 | LOW | same |
| K3 | **13** | 33 | LOW | same |

Sources: Eagle nets `K1`/`K2`/`K3`; shieldXL `config.txt` `b1_pin=22`, `b2_pin=26`, `b3_pin=13`. Schematic and overlay **agree**. Confidence: **HIGH**.

Hardware: 10 nF debounce to GND, 10 kΩ series to GPIO. Overlay: `gpio-keys`, `linux,code` 1/2/3 (KEY_ESC / KEY_1 / KEY_2 in norns). Active low in DTS (`gpios = <&gpio N 1>` GPIO_ACTIVE_LOW).

Long-press is **not** in hardware; implement in light-console userspace.

## D) Audio / MIDI / pin conflicts

### CS4270 audio (present, unused by this project)

| Function | GPIO |
|----------|------|
| Codec reset | GPIO17 |
| I2S SCLK | GPIO18 |
| I2S LRCK / FS | GPIO19 |
| I2S SDOUT (codec → Pi) | GPIO20 |
| I2S SDIN (Pi → codec) | GPIO21 |
| I2C SDA | GPIO2 (SDA1) |
| I2C SCL | GPIO3 (SCL1) |
| MCLK | 12.288 MHz crystal on shield, not a Pi GPIO |

norns overlay: `dtoverlay=monome-snd-4270`, `dtparam=i2s=on`, `dtparam=i2c=on`.

**This project does not need audio.** Do not load `monome-snd-4270` unless a later milestone needs it. Those GPIOs are still **physically connected** to the codec; do not reuse them for other functions.

### UART MIDI (shieldXL addition)

shieldXL adds TRS MIDI in/out. norns stock shield 210330 Eagle had only a small `J3` header on UART; KiCad remix labels `MIDI_TX` / `MIDI_RX` next to Pi `TXD`/`RXD`.

| Item | Fact | Confidence |
|------|------|------------|
| Overlay used by norns MIDI install | `enable_uart=1`, `dtoverlay=miniuart-bt`, `dtoverlay=uart0`, `dtoverlay=midi-uart0` | HIGH (shieldXL `install/boot/config.txt`, README) |
| Pi UART0 pins | Header pin 8 = GPIO14 TXD, pin 10 = GPIO15 RXD | HIGH (Pi 40-pin standard) |
| MIDI_TX/RX tied to that UART | Labels sit on the GPIO sheet beside TXD/RXD; overlay is midi-uart0 | HIGH for intent; **confirm continuity in 0.2** |
| MIDI baud | midi-uart0 → 31250 | HIGH as overlay behaviour |
| Needed for this project? | **No.** Scene control is USB Launchpad → QLC+. TRS MIDI jacks can stay unused. | HIGH |
| Conflict | If `midi-uart0` is enabled, GPIO14/15 are UART. Do not use them as GPIO. Bluetooth moves to mini-UART. | HIGH |

## E) Raspberry Pi 4 overlays (norns image — reference only)

From shieldXL `install/boot/config.txt` (norns shield image, **not** something this project installs in 0.1):

```
dtparam=spi=on
dtoverlay=ssd1322-spi
dtparam=rotate=180
dtparam=i2s=on
dtparam=i2c=on
dtoverlay=monome-snd-4270
dtoverlay=norns-buttons-encoders
dtparam=e1_pin_a=4
dtparam=e1_pin_b=27
dtparam=e2_pin_a=12
dtparam=e2_pin_b=25
dtparam=e3_pin_a=24
dtparam=e3_pin_b=23
dtparam=b1_pin=22
dtparam=b2_pin=26
dtparam=b3_pin=13
```

Plus optional MIDI block (see D).

**Milestone 0.2 must re-derive overlays for Raspberry Pi OS.** Do not copy the norns `kernel=` line or norns userspace.

## What norns code may be reused later vs must not be assumed

### May reuse (ideas / kernel bits, after proving on Raspberry Pi OS)

- Device tree overlay **pattern**: `ssd1322-spi` + `norns-buttons-encoders` with the pin overrides above.
- Linux `rotary-encoder` + `gpio-keys` → `/dev/input/event*` (evdev).
- Framebuffer write to SSD1322 if `fb_ssd1322` exists on the new kernel.
- Newhaven SSD1322 init sequence if we talk SPI from userspace instead of fbtft.

### Must not assume / must not copy blindly

- Entire norns disk image, matron, maiden, crone, SuperCollider, JACK.
- CM3 GPIO numbers from `readme-hardware.md`.
- `/dev/fb1` always being the OLED.
- Fates (okyeron) GPIO map — Fates is **different** from the monome shield ([llllllll Fates thread](https://llllllll.co/t/fates-a-diy-norns-dac-board-for-raspberry-pi/22999/1716)).
- Encoder E2/E3 silkscreen vs norns overlay index without `evtest`.
- That Raspberry Pi OS ships `ssd1322-spi.dtbo` / `norns-buttons-encoders.dtbo` — norns uses a custom kernel. Stock Pi OS may need overlays copied or userspace SPI/GPIO instead.

## UNKNOWN — verification plan

| ID | Unknown | How to verify (Milestone 0.2, new SD, do not touch Norns card) |
|----|---------|----------------------------------------------------------------|
| U1 | Physical knob E2 vs E3 vs overlay `e2`/`e3` | `evtest` on each encoder while turning the left/middle/right knob |
| U2 | Encoder CW delta sign | Turn clockwise; record REL axis sign |
| U3 | Raspberry Pi OS has `fb_ssd1322` / overlay | `ls /boot/firmware/overlays/*ssd1322*`; `modinfo fb_ssd1322`; fallback: userspace SPI |
| U4 | Framebuffer device name | `ls /sys/class/graphics/fb*` with HDMI connected and disconnected |
| U5 | Rotate 180 required on this enclosure | Draw a known pixel; check orientation vs silkscreen |
| U6 | MIDI_TX/RX continuity to GPIO14/15 | Continuity or scope; only if we ever enable UART MIDI |
| U7 | Button bounce in userspace | Press K1–K3; confirm no double events after 10 nF + gpio-keys |
| U8 | OLED contrast / init on Pi OS | First “LIGHT CONSOLE” proof |
| U9 | Header pin numbers vs BCM | Cross-check with `pinctrl` / `gpioinfo` once overlay loads |
| U10 | shieldXL KiCad vs 210330 Eagle delta besides MIDI | Diff nets if a later PCB revision is in hand (BOM has 20251025 xlsx) |

## Sources (URLs)

- https://github.com/okyeron/shieldXL
- https://github.com/okyeron/shieldXL/blob/main/README.md
- https://github.com/okyeron/shieldXL/blob/main/BUILD.md
- https://github.com/okyeron/shieldXL/blob/main/bom/BOM.md
- https://github.com/okyeron/shieldXL/blob/main/install/boot/config.txt
- https://github.com/okyeron/shieldXL/tree/main/kicad/ShieldXL-M-20230615
- https://denki-oto.com/products/shieldxl-diy-norns-synthesizer-kit
- https://github.com/monome/norns-shield
- https://github.com/monome/norns-shield/blob/main/eagle/norns-shield-210330.sch
- https://github.com/monome/norns-image/blob/main/readme-hardware.md
- https://github.com/monome/linux/blob/norns-4.14.y/arch/arm/boot/dts/overlays/norns-buttons-encoders-overlay.dts
- https://newhavendisplay.com/content/specs/NHD-2.7-12864WDW3.pdf
- https://docs.qlcplus.org/v5/advanced/web-interface/web-api
