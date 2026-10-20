# Product

<!-- impeccable:product-schema 1 -->

## Platform

oled

Raspberry Pi 4 + Denki Oto shieldXL appliance. Operator surface is a 128×64 SSD1322 OLED with three keys (K1 K2 K3) and three encoders (E1 E2 E3). Not a website, not iOS, not Android. The Mac pygame window is a scaled copy of the same framebuffer, not a second product.

## Users

Primary user: live show operator at the Shield XL in a dark venue, hands on the physical keys and encoders. QLC+ stays headless. The operator does not use a QLC GUI during the show.

## Product Purpose

Shield XL Light Console is the operator UI and orchestration layer for a standalone lighting console. It makes it possible to run a prepared show and to patch/map live outputs from the OLED: master, scenes, chasers, WiZ devices, network mode, QLC on/off, status, and shutdown.

Success: the operator can run the night from this box without opening QLC, and a UI crash does not stop the show.

## Positioning

QLC+ is the show engine. This product is not a DMX/show engine, not Norns OS, and not a replacement for wizbridge. It is a Norns-like console UI on Raspberry Pi OS that talks to QLC+ and owns appliance control (WiZ AP/lifecycle, LIGHT-CONTROL network mode, QLC start/stop, shutdown).

A neighboring lighting desk could copy “OLED + knobs.” It could not truthfully claim this specific split: QLC remains the engine; Light Console is UI and fail-isolated orchestration on shieldXL hardware.

## Operating Context

- Physical console: Raspberry Pi 4 + shieldXL, SSD1322 128×64, K1–K3, E1–E3.
- Interaction model: Norns-like. K1 toggles PLAY ↔ MENU. Physical control names are used everywhere. This is not Norns OS and not a Norns image.
- Show engine: QLC+ 5.2.2 headless (`qlcplus-qml -w -o /home/light/shows/master.qxw`). Launchpad Mini is USB MIDI into QLC, not into this UI.
- Outputs: Art-Net U1 localhost → wizbridge → WIZ-LIGHTS on wlan1; Art-Net U2 → AIR2DMX `192.168.88.242`. LIGHT-CONTROL is the operator LAN on wlan0.
- Processes are fail-isolated: QLC, wizbridge, and light-console die independently. Light Console reconnects; it must not restart QLC on connection loss.
- Mac simulator exists for development; it renders the same 128×64 UI.

## Capabilities and Constraints

Confirmed capabilities:

- Live PLAY: master, scene, chaser, GO.
- MENU pages: shows, scenes, chasers, params, output, WiZ (control, devices, map), system (QLC, network mode, version, shutdown).
- WiZ CONTROL owns WIZ-LIGHTS AP + wizbridge lifecycle. Operator intent `wiz_enabled` persists across reboot.
- NETWORK / STANDALONE switches LIGHT-CONTROL on wlan0 only; must never down WIZ-LIGHTS.
- WiZ device map/slots, identify-as-status, QLC on/off from OLED.

Confirmed constraints:

- Do not write a DMX/show engine. QLC+ stays the engine.
- UI crash must not stop QLC+ or the show.
- Do not deploy onto the production wiz-bridge Pi (`valot.local` / `192.168.88.248`) or reuse the Norns Shield SD card. No targeted traffic to `.248`.
- Do not guess GPIO pins; hardware facts live in `research/shieldxl.md`.
- Internet/upstream is not required for WiZ. WIZ-LIGHTS must not depend on wlan0, LIGHT-CONTROL, or a default route.
- OLED vocabulary: operator-facing status words in `light_console/ui/vocab.py`. Editable booleans are only ON/OFF.

Undecided:

- Whether Impeccable will later design any non-OLED surface (docs site, marketing). Not in scope until requested.

## Brand Commitments

- Product name: **Shield XL Light Console**.
- Identity is the physical console and the 128×64 wordmark, not a web brand system.
- Interaction language is Norns-like (PLAY/MENU, K/E names) without claiming to be Norns.
- Voice in the product is short, uppercase OLED labels and status words (READY, FAILED, ACTIVE, NETWORK, STANDALONE). Do not invent a marketing voice.

## Evidence on Hand

- Hardware research: `research/shieldxl.md`.
- UI model: `docs/norns-ui-model.md`, `docs/ui-architecture.md`.
- Architecture and output: `docs/architecture.md`, `docs/output-architecture.md`, `docs/wiz.md`.
- Live appliance on `shieldxl-light` (wlan0 `192.168.88.246`), physically verified through QLC integration and WiZ AP/lifecycle.
- Show content lives in QLC workspace `/home/light/shows/master.qxw` (repo copy `qlc/projects/siirtyma-shield.qxw`). Do not fabricate testimonials, customer names, or performance claims.

## Product Principles

1. **The show outlives the UI.** QLC is the engine; Light Console failure must leave output running.
2. **Hands on the box.** The operator runs and patches the night from shieldXL keys and encoders, not from a QLC window.
3. **Norns grammar, not Norns product.** Keep K1 PLAY/MENU and physical K/E names; do not become Norns OS.
4. **Radios stay in their lanes.** wlan0 is LIGHT-CONTROL; wlan1 is WIZ-LIGHTS. Network-mode changes must never take the lamps’ AP down.
5. **Fail closed on output control.** If WiZ AP cannot be established, TX stays off and the UI reports failure; do not bounce the AP to look healthy.
