# Architecture

Version **0.1.0** — Mac simulator / design. No Pi deploy.

## Goal

Raspberry Pi 4 + Denki Oto shieldXL is a standalone lighting console:

```
Launchpad Mini (USB MIDI)
        │
        ▼
   QLC+ headless  ── Art-Net U0 ──► wizbridge ──► WiZ lamps
        │           Art-Net U1 ──► PKNight   ──► DMX
        ▲
 light-console (OLED + encoders + keys)
        ▲
   shieldXL hardware  or  Mac simulator
```

QLC+ is the show engine. light-console is UI and orchestration only. wizbridge stays a separate process (production code lives in the wiz-bridge repo; this repo does not vendor it in 0.1).

## Process isolation (failsafe)

| Process | Role | If it dies |
|---------|------|------------|
| `qlcplus` | Show engine, Art-Net, MIDI | Show stops — this is the engine, not our UI |
| `wizbridge` | Art-Net U0 → WiZ | WiZ looks freeze; DMX/PKNight unaffected |
| `light-console` | OLED, encoders, status, QLC WebSocket client | **QLC keeps running.** Last QLC state remains. |

light-console must never `systemctl restart qlcplus` on connection loss. It reconnects the WebSocket in the background and shows `QLC LOST`.

Blackout in 0.1 is **local UI state** for the simulator. Production (later) must map blackout to a QLC Grand Master / VC widget so Launchpad can clear it. The UI process must not own a second output path that can stick lamps off after a crash.

## Layers

```
simulator.run / main.py
        │
   ui.controller     ← event loop, fps-limited redraw
        │
   ┌────┴─────┬──────────┬──────────┐
   controls   display    qlc        status
   (map YAML) (128×64)   (client)   (pollers)
        │
   hardware.HardwareBackend
        ├── SimulatorBackend   (0.1, Mac)
        └── ShieldXLBackend    (0.2+, GPIO/evdev — stub only now)
```

Rules:

- Only `hardware/` talks to GPIO, evdev, SPI, or the pygame window.
- Display renders **AppState**; it does not query the network.
- Status workers update AppState. OLED is a view.
- QLC commands go through `QLCClient`. No raw WebSocket calls from UI widgets.

## AppState

See `light_console/state.py`. UI screens are functions of this snapshot. Workers take a lock or use a single-thread event loop (0.1 is single-threaded plus mock toggles).

## Control model

YAML maps E1–E3 and K1–K3 short/long actions. Defaults:

| Control | Action |
|---------|--------|
| E1 | master dimmer 0–100 |
| E2 | select scene/function |
| E3 | speed / BPM |
| K1 short | blackout toggle |
| K1 long | all off / panic (clear active + blackout) |
| K2 short | GO (activate selected) |
| K2 long | home screen |
| K3 short | `special` (name from config — not hardcoded fog) |
| K3 long | menu |

## Screens

- **boot** — QLC / WIZ AP / WiZ n/m / MIDI / DMX checklist
- **home** — scene name, WiZ count, DMX, dim, BPM, encoder legend, warnings
- **menu** — HOME SHOW WIZ NETWORK SYSTEM ABOUT
- **show / wiz / network / system / about** — diagnostics

Refresh 10–20 fps. Skip SPI/window blit if the 128×64 buffer is unchanged.

## QLC+

Documented API (QLC+ 5 web API): `ws://127.0.0.1:9999/qlcplusWS`, pipe-separated `QLC+API|…`.

Used later: `isProjectLoaded`, `getFunctionsList`, `getFunctionType`, `getFunctionStatus`, `setFunctionStatus`, widget ID messages, `GM_VALUE` for grand master.

Chaser speed: QLC documents Speed Dial widget messages (`SPEED_TIME`, etc.). Treat dedicated “set chaser BPM” as **needs a VC widget** until proven against 5.2.x on the Pi.

0.1 uses `MockQLCClient` only.

## Networking (later)

wlan1 = WIZ-LIGHTS AP, NetworkManager shared, 10.42.0.1/24. wlan0 = optional upstream. WiZ must not depend on wlan0. No custom dnsmasq/NAT stack. No automatic AP restart.

## Version plan

| Version | Meaning |
|---------|---------|
| 0.1.0 | Simulator + docs (this) |
| 0.2.0 | Shield XL hardware proof on a **new** SD |
| 0.3.0 | QLC WebSocket |
| 0.4.0 | Network / WiZ / MIDI / DMX status |
| 0.5.0 | Pi standalone prototype |
| 1.0.0 | Show-ready |

## Milestone 0.1 out of scope

Pi deploy, systemd install, GPIO, production `.qxw`, wizbridge changes, network config, AP restart workaround.
