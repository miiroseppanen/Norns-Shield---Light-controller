# Milestone 0.2 — Shield XL hardware bring-up (gated)

Status: **in progress (OS flash only)**. Tag `v0.1.0` is the restore point. Do not mix QLC / wizbridge / network AP work into this milestone.

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
| Target | **Only** `/dev/disk4` after identity re-check |
| Identity must match | Built In SDXC Reader; ~63.9 GB; Protocol Secure Digital; Removable; **not** Macintosh HD / disk0 / disk3 |

**PASS**

- SHA256 of the downloaded `.img.xz` matches the official checksum.
- Write destination was `/dev/disk4` (or `/dev/rdisk4`) after a successful identity check in the same session.
- Boot FAT contains first-boot config: hostname `shieldxl-light`, SSH enabled, user that can log in, timezone `Europe/Helsinki`, Finnish keymap.
- No Wi-Fi stanza unless credentials were already known (do not guess).
- No QLC/wizbridge/AP packages on the image.

**FAIL**

- Disk identity drifted or was uncertain → **do not write**.
- Checksum mismatch.
- Image is Norns or Raspberry Pi OS Desktop.

**GATE:** User inserts the SD into the Shield XL Pi 4, powers it, and **confirms SSH**. Do not start Phase 1 until that confirmation.

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

**GATE:** operator says SSH works. Then inventory may start.

---

## Phase 2 — Inventory (read-only)

On the Pi, collect only. Do not load overlays yet if that can wait until the relevant phase.

Record: OS, kernel, `model`, `vcgencmd` throttled, `ls /dev/spidev*`, `ls /dev/fb*`, `ls /dev/input/event*`, `ls /boot/firmware/overlays/*ssd1322* *norns* *rotary*`, `dtparam` / `config.txt` as shipped, `gpioinfo` or `pinctrl` if present.

**PASS:** a dated inventory note in `research/` (or logs) with those facts. No show stack installed.

**FAIL:** missing model/kernel, or accidental package installs of QLC/norns.

**GATE:** inventory committed or pasted; then buttons only.

---

## Phase 3 — Buttons only (K1 K2 K3)

Enable **only** gpio-keys (or equivalent) for BCM **22, 26, 13** (active low). No encoders. No OLED writes.

**PASS**

- Pressing left/middle/right key produces distinct events (`evtest`).
- Release is visible.
- No encoder nodes required yet.

**FAIL:** no events, all three keys the same, or keys inverted without documented active-low.

**GATE:** three keys proven. Then encoders.

---

## Phase 4 — Encoders only (U1, U2)

Enable **only** rotary-encoder overlays for the researched pin pairs. Turn **one physical knob at a time**.

Pin pairs from `research/shieldxl.md` (overlay names, not assumed silkscreen):

| Overlay | GPIO A | GPIO B |
|---------|--------|--------|
| e1 | 4 | 27 |
| e2 | 12 | 25 |
| e3 | 24 | 23 |

**PASS**

- Each of the three knobs maps to exactly one overlay instance (table filled: left/middle/right → e1/e2/e3).
- Clockwise delta sign recorded per knob (U2).
- No button regression.

**FAIL:** two knobs on one device, missing knob, or guessed mapping without `evtest` log.

**GATE:** U1 table written. Then OLED.

---

## Phase 5 — OLED only (U3, U4, U5)

**Do not write a userspace SPI driver until kernel/framebuffer is ruled out.**

Order:

1. Check whether this OS/kernel ships `ssd1322` / `ssd1322-spi` / `fb_ssd1322`.
2. If yes: enable SPI + overlay (DC=GPIO5, RESET=GPIO6, CE0). Identify `/dev/fbN` with HDMI connected and disconnected (U4).
3. Draw `LIGHT CONSOLE` (U8). Check rotation vs enclosure (U5).

**PASS**

- Panel shows `LIGHT CONSOLE` (readable).
- Path documented: framebuffer device **or** explicit “no kernel driver, userspace SPI approved for a later patch”.
- Buttons/encoders not required for this PASS (may be disconnected in software).

**FAIL:** black panel with no diagnosis; or a large custom SPI stack added “just in case” while an overlay existed.

**GATE:** OLED path chosen and proven. Then combined test.

---

## Phase 6 — Combined proof

Keys + encoders + OLED in one boot. Minimal userspace: print events, keep `LIGHT CONSOLE` (or a tiny status line). Still no QLC.

**PASS:** all three keys, all three encoders, OLED still drawing after a minute of use.

**FAIL:** one subsystem dies when another is enabled (SPI vs encoder pin conflict must be diagnosed, not ignored).

---

## Phase 7 — Reboot

`sudo reboot`. SSH comes back. Repeat a short combined check.

**PASS:** SSH + keys + one encoder + OLED text after reboot.

**FAIL:** no boot, no SSH, or overlay lost.

---

## Phase 8 — Cold boot

Power off ≥10 s. Power on from wall. No Mac required.

**PASS:** same as Phase 7 without a soft reboot.

**FAIL:** needs a second plug-in, or OLED/keys dead until HDMI/SSH dance.

---

## Milestone 0.2 complete when

Phases 0–8 are PASS. Then stop again. Milestone 0.3 (QLC WebSocket) is a separate approval.

## Rollback

```text
git checkout v0.1.0
```

OS on the SD can be re-flashed; production Pi and Norns SD are never the target.
