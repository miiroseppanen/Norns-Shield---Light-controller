# Architecture

Version **0.4.0** — Norns-like UI framework. Control mapping is **per page**, not a global E1=master table. See [`docs/ui-architecture.md`](ui-architecture.md).

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
| `light-console.service` | OLED, encoders, status, QLC WebSocket client (user `light`, boot) | **QLC keeps running.** Last QLC state remains. Restarts on-failure with a 5/60s limit. |

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

## Control model (0.4)

YAML no longer maps E1–E3 / K1–K3 globally. `HomePage` owns the live mapping (E1 master, E2 scene, E3 speed, K1 blackout, K3 menu). Other pages define their own handlers. Hardware only emits events.

## Screens (0.4)

HOME, MENU, SCENES, LIVE, EFFECTS, OUTPUT, SYSTEM. Data-driven `MenuItem` list in `light_console/ui/menu.py`.

Refresh 10–20 fps. Skip SPI/window blit if the 128×64 buffer is unchanged.

## QLC+

Documented API (QLC+ 5 web API): `ws://127.0.0.1:9999/qlcplusWS`, pipe-separated `QLC+API|…`.

Used later: `isProjectLoaded`, `getFunctionsList`, `getFunctionType`, `getFunctionStatus`, `setFunctionStatus`, widget ID messages, `GM_VALUE` for grand master.

Chaser speed: QLC documents Speed Dial widget messages (`SPEED_TIME`, etc.). Treat dedicated “set chaser BPM” as **needs a VC widget** until proven against 5.2.x on the Pi.

0.4 uses `MockQLCClient` in the simulator and `QlcWebSocketClient` on the Shield. The UI does not talk to the socket directly. See [`qlc-integration.md`](qlc-integration.md).

## Networking (later)

wlan1 = WIZ-LIGHTS AP (later, 0.6+). See [`output-architecture.md`](output-architecture.md). No automatic AP restart.

## Version plan

| Version | Meaning |
|---------|---------|
| 0.1.0 | Simulator + docs |
| 0.2.0 | Shield XL hardware proof on a **new** SD |
| 0.3.0 | QLC+ 5.2.2 engine baseline |
| 0.4.0 | Norns-like UI framework |
| 0.4c | Appliance autostart (`light-console.service`) |
| 0.5.0 | QLC+ 5.2.2 systemd + MASTER WebSocket (physically verified) |
| 0.6.0 | WIZ-LIGHTS AP lifecycle, LIGHT-CONTROL network mode, OLED design system |
| 1.0.0 | Show-ready |

## Milestone 0.1 out of scope

Production `.qxw`, wizbridge changes, network config, AP restart workaround. GPIO and OLED autostart are 0.2 / 0.4c.
