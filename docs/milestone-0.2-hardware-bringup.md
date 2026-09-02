# Milestone 0.2 — Shield XL hardware bring-up (gated)

Status: **COMPLETE.** Milestone 0.2 hardware bring-up PASS (controls + OLED + combined + reboot + cold boot). **Stop. Do not start QLC until separately approved.** Tag `v0.1.0` is the restore point.

Inventory: `research/phase-1-hardware-inventory.md`. Buttons: `research/phase-3-buttons.md`. E1: `research/phase-4a-encoder-e1.md`. E2/E3: `research/phase-4b-encoders-e2-e3.md`. OLED: `research/phase-5-oled.md`. Combined: `research/phase-6-combined.md`. Reboot: `research/phase-7-reboot.md`. Cold boot: `research/phase-8-cold-boot.md`. Summary: `research/milestone-0.2-hardware-pass.md`.

Target hardware: Raspberry Pi 4 + Denki Oto shieldXL, **new** microSD. Not the Norns card. Not `valot.local`.

## Hard rules

- One phase at a time. A phase that is not PASS is a **STOP**.
- Do not start phase N+1 until phase N is physically proven.
- Do not install QLC+, wizbridge, WIZ-LIGHTS AP, Launchpad config, Norns/matron/crone, a live `ShieldXLBackend`, or a custom OLED SPI driver in 0.2.
- Kernel/framebuffer OLED path is preferred if the OS actually has it (research U3/U4). Userspace SPI is a last resort and stays inside `hardware/`.
- Encoder identity (U1) is the first physical control test: one knob at a time, record events. No guessed E2/E3 mapping.

## Forbidden until a later milestone

QLC+, wizbridge, WIZ-LIGHTS, Launchpad, Norns image files, production Pi SSH/deploy.

## Phase 0 — Clean OS on the new SD

**This phase runs on the Mac. After flash: STOP. Do not inventory.**

| | |
|--|--|
| Image | Official **Raspberry Pi OS Lite 64-bit** (current stable on raspberrypi.com). Not a Norns image. Not desktop. |
| Target | The whole disk returned by `scripts/identify-sd.py` **this session** (device node is not hardcoded). |
| Identity must match | Built In SDXC Reader; SanDisk SDSR64G / SR64G; known serial; ~63.9 GB; Protocol Secure Digital; Removable; Writable Yes; Write Protect No; **not** Macintosh HD / disk0 / disk3 |
| Mac flash command | `scripts/flash-raspios-sd.sh` — `xzcat IMAGE \| dd of=/dev/rdiskN bs=4m status=progress` then a separate `sync`. **Never** `conv=sync` on that pipe (macOS dd pads short reads and will write the whole card). |

**PASS**

- SHA256 of the downloaded `.img.xz` matches the official checksum.
- Write destination was the identified `/dev/diskN` (or `/dev/rdiskN`) after a successful identity check in the same session.
- `dd` transferred exactly the uncompressed image size (2,977,955,840 bytes for the 2026-06-18 Lite image) and prefix bytes match the image.
- Boot FAT mounts and is recognized; contains first-boot config: hostname `shieldxl-light`, SSH enabled, user that can log in, timezone `Europe/Helsinki`, Finnish keymap.
- Wi-Fi only if credentials were supplied out of band (PSK is not in git).
- No QLC/wizbridge/AP packages on the image.

**FAIL**

- Disk identity drifted or was uncertain → **do not write**.
- Checksum mismatch.
- Image is Norns or Raspberry Pi OS Desktop.
- `dd` byte count != uncompressed image size, FAT unrecognized, or prefix cmp mismatch. No automatic retry.

**GATE:** User inserts the SD into the Shield XL Pi 4, powers it, and **confirms SSH**. Do not start Phase 1 until that confirmation. **Met 2026-09-01.**

User account planned for flash: `light` (SSH key from the operator Mac; password generated at flash time, not stored in git).

Wi-Fi: **not** preconfigured in 0.2 unless a credential is explicitly supplied. First SSH is expected over Ethernet or `.local` once the Pi is on a network the Mac can reach.

---

## Phase 1 — Boot + SSH (operator)

| | |
|--|--|
| Actor | Human |
| Actions | Put SD in Shield XL Pi 4. Power on. Confirm SSH. |

**PASS**

- `ssh light@shieldxl-light.local` (or Ethernet IP) works.
- `hostname` is `shieldxl-light`.
- `cat /sys/firmware/devicetree/base/model` is a Raspberry Pi 4.

**FAIL:** no SSH, wrong hostname, not a Pi 4.

**PASS (2026-09-01, operator):** `ssh light@shieldxl-light.local` works. Hostname `shieldxl-light`. Raspberry Pi 4 Model B Rev 1.5. Debian 13, kernel `6.18.34+rpt-rpi-v8`, aarch64. wlan0 `192.168.88.246` on LIGHT-CONTROL. Shield XL physically on the Pi. Locale warning `LC_CTYPE=UTF-8 invalid` left unfixed.

**GATE:** operator says SSH works. Then inventory may start. **Met.**

---

## Phase 2 — Inventory (read-only)

On the Pi, collect only. Do not load overlays yet if that can wait until the relevant phase.

Record: OS, kernel, `model`, `vcgencmd` throttled, `ls /dev/spidev*`, `ls /dev/fb*`, `ls /dev/input/event*`, `ls /boot/firmware/overlays/*ssd1322* *norns* *rotary*`, `dtparam` / `config.txt` as shipped, `gpioinfo` or `pinctrl` if present.

**PASS (2026-09-01):** `research/phase-1-hardware-inventory.md`. No show stack installed. No packages, overlays, GPIO daemons, OLED, QLC, or reboot.

Headline facts: SPI off; no `/dev/spidev*` / `/dev/fb*` / SSD1322 overlay; HDMI vc4 DRM only; header GPIOs 2–27 unclaimed; CS4270 not loaded; stock `vc4-kms-v3d` does not conflict with Shield XL pins.

**FAIL:** missing model/kernel, or accidental package installs of QLC/norns.

**GATE:** inventory committed or pasted; then buttons only. **Stop here until Phase 3 is approved.**

---

## Phase 3 — Buttons only (K1 K2 K3)

Enable **only** gpio-keys (or equivalent) for BCM **22, 26, 13** (active low). No encoders. No OLED writes.

**PASS**

- Pressing left/middle/right key produces distinct events (`evtest`).
- Release is visible.
- No encoder nodes required yet.

**FAIL:** no events, all three keys the same, or keys inverted without documented active-low.

**PASS (2026-09-01, operator):** `scripts/test-buttons.py` over SSH. Idle HIGH. K1=GPIO22, K2=GPIO26, K3=GPIO13, one PRESS+RELEASE each, order K1 K2 K3, no chatter. Report: `research/phase-3-buttons.md`. Userspace libgpiod (no overlay).

**GATE:** three keys proven. Then encoders one knob at a time, starting with E1.

---

## Phase 4 — Encoders only (U1, U2)

Userspace libgpiod proof (no overlay in 0.2): E1 done (`research/phase-4a-encoder-e1.md`). E2+E3 in one run: `scripts/test-encoders-e2-e3.py` (PAIR-A=12/25, PAIR-B=24/23). Do not assume silkscreen vs overlay names.

**PASS**

| Overlay | GPIO A | GPIO B |
|---------|--------|--------|
| e1 | 4 | 27 |
| e2 | 12 | 25 |
| e3 | 24 | 23 |

**PASS**

- Each of the three knobs maps to exactly one overlay instance (table filled: left/middle/right → e1/e2/e3).
- Clockwise delta sign recorded per knob (U2).
- No button regression.

**PASS (2026-09-01):** userspace libgpiod, no overlay. E1=4/27. Physical E2=GPIO12/25 (overlay e2, schematic E3). Physical E3=GPIO24/23 (overlay e3, schematic E2). A-leads-B = physical CW. Reports: `research/phase-4a-encoder-e1.md`, `research/phase-4b-encoders-e2-e3.md`.

**FAIL:** two knobs on one device, missing knob, or guessed mapping without `evtest` log.

**GATE:** U1 table written. Then OLED. **Met — userspace SSD1322 (no stock overlay).**

---

## Phase 5 — OLED only (U3, U4, U5)

**Do not write a userspace SPI driver until kernel/framebuffer is ruled out.** Ruled out in Phase 1. Userspace SSD1322 on `spidev0.0` is the 0.2 path (`scripts/test-oled.py`). Enable only stock `dtparam=spi=on`. No ssd1306/1327/1331/1351 overlay.

Order:

1. Check whether this OS/kernel ships `ssd1322` / `ssd1322-spi` / `fb_ssd1322`.
2. If yes: enable SPI + overlay (DC=GPIO5, RESET=GPIO6, CE0). Identify `/dev/fbN` with HDMI connected and disconnected (U4).
3. Draw `LIGHT CONSOLE` (U8). Check rotation vs enclosure (U5).

**PASS**

- Panel shows `LIGHT CONSOLE` (readable).
- Path documented: framebuffer device **or** explicit “no kernel driver, userspace SPI approved for a later patch”.
- Buttons/encoders not required for this PASS (may be disconnected in software).

**PASS (2026-09-01):** userspace SSD1322, `dtparam=spi=on` only. Geometry 128×64 (128 bytes/row, 8192/frame). Text readable after remap `0x04,0x11` (U5 180°). Report: `research/phase-5-oled.md`.

**FAIL:** black panel with no diagnosis; or a large custom SPI stack added “just in case” while an overlay existed.

**GATE:** OLED path chosen and proven. Then combined test. **Met.**

---

## Phase 6 — Combined proof

Keys + encoders + OLED in one boot. Minimal userspace: print events, keep `LIGHT CONSOLE` (or a tiny status line). Still no QLC.

**PASS (2026-09-01):** `scripts/test-combined.py`. All three keys (repeated PRESS+RELEASE), E1/E2/E3 both directions, OLED still drawing after >60 s. Report: `research/phase-6-combined.md`.

**FAIL:** one subsystem dies when another is enabled (SPI vs encoder pin conflict must be diagnosed, not ignored).

**GATE:** combined proven. Then Phase 7 reboot + Phase 8 cold boot. QLC waits for 0.2 COMPLETE.

---

## Phase 7 — Reboot

`sudo reboot`. SSH comes back. Repeat a short combined check.

**PASS (2026-09-01):** `SPI_PERSIST_OK`, `BOOT_CHECK PASS`, OLED text, combined K1–K3 + E1–E3. `research/phase-7-reboot.md`.

**FAIL:** no boot, no SSH, or overlay lost.

---

## Phase 8 — Cold boot

Power off ≥10 s. Power on from wall. No Mac required.

**PASS (2026-09-01):** `shutdown -h now`, power off, SSH back, combined keys+encoders+OLED. `research/phase-8-cold-boot.md`.

**FAIL:** needs a second plug-in, or OLED/keys dead until HDMI/SSH dance.

---

## Milestone 0.2 complete when

Phases 0–8 are PASS. **Met 2026-09-01.** Stop. Milestone 0.3 (QLC) needs a new approval.

## Rollback

```text
git checkout v0.1.0
```

OS on the SD can be re-flashed; production Pi and Norns SD are never the target.
