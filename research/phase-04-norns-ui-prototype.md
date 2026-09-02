# Milestone 0.4 — Norns-like UI prototype

Date: 2026-09-02  
Target: `light@shieldxl-light.local` (do not touch `valot.local`)

## What this is

UI framework only. Same application/UI/renderer code on Mac simulator and Shield.

Not in this milestone: wizbridge, WIZ-LIGHTS, PKNight, Launchpad, production `.qxw`, systemd/autostart, audio, UART MIDI.

## Architecture

See [`docs/ui-architecture.md`](../docs/ui-architecture.md).

Hardware events → pages → `AppState` → renderer. `QlcBinding` is the only path from state to QLC. **E1=master / K1=blackout is HOME-page mapping, not GPIO configuration.**

## HOME (OLED)

```
LIGHT CONSOLE      ●
SCENE: WASH
MASTER         80%
SPEED          124
```

`●` = QLC connected, `×` = offline.

## MENU

K3 opens. E2 selects. K3 enters. K2 back.

```
MENU
> SCENES
  LIVE
  EFFECTS
  OUTPUT
  SYSTEM
```

## Shield backend

`light_console/hardware/shieldxl.py` + `oled.py`:

- Buttons K1=22, K2=26, K3=13 (active low), proven 0.2
- Encoders E1=4/27, E2=12/25, E3=24/23, CW = A leads B
- SSD1322 `/dev/spidev0.0`, DC=5 RESET=6, remap `0x04,0x11`, 128 bytes/row, 8192/frame

## QLC

Optional. Shield runs `QlcWebSocketClient` to `ws://127.0.0.1:9999/qlcplusWS`. If QLC+ is not running (cold boot has no autostart), UI stays on HOME with `×` and still accepts encoders/keys. Reconnect is automatic. No WiZ/DMX output from this prototype.

## Tests (Mac)

```bash
python -m pytest
```

Covered: HOME→MENU, selection, enter, back, HOME return, master 0..100, blackout, QLC offline/online, renderer every page, WS client offline pump.

Mac: `python3.11 -m pytest` — **38 passed**.

## Deploy

Copy tree to `/home/light/light-console` on the Shield Pi. No systemd. Run in the foreground over SSH.

OLED one-shot HOME frame on the Pi succeeded (`oled HOME frame written`). Live UI is not autostarted.

## Physical acceptance

Operator: see HOME, E1 master, K1 blackout, K3 MENU, E2 cursor, K3 enter page, K2 back, visit SCENES LIVE EFFECTS OUTPUT SYSTEM, OLED readable.
