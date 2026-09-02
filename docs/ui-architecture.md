# UI architecture (Milestone 0.4)

Norns interaction model on Pi OS + Python. Details: [`norns-ui-model.md`](norns-ui-model.md).

Hardware events never call QLC. They go through `NornsUIShell` → screen → parameter → `AppState`. `QlcBinding` pushes state to QLC when the socket is up.

## Layers

```
hardware          K1–K3, E1–E3, SSD1322 (or Mac simulator)
     │
HardwareEvent     encoder / key (named K1–K3, E1–E3)
     │
NornsUIShell      K1 PLAY↔MENU, menu stack
     │
Screen            enc(n, delta) / key(n, z) / redraw(fb)
     │
Parameter         Number / Option / Toggle / Action
     │
AppState          master, speed, blackout, current_scene, qlc_connected, …
     │
QlcBinding        pull connection, push GM / blackout / speed
     │
QLCClient         MockQLCClient  |  QlcWebSocketClient
     │
Renderer          AppState → 128×64 framebuffer
```

| Layer | Owns | Must not |
|-------|------|----------|
| `hardware/` | GPIO, SPI, pygame window | QLC, menu, master |
| `ui/shell.py` | K1 PLAY↔MENU, stack | SPI, WebSocket |
| `ui/pages.py` | PLAY/PARAMS/… `enc`/`key`/`redraw` | GPIO numbers as “button1” |
| `ui/params.py` | Shared parameters | Hardware |
| `display/` | Drawing from `AppState` | Input, QLC |
| `qlc/` | WebSocket client + binding | GPIO, framebuffer |

## Two modes

1. **PLAY** — live. E1/E2/E3 and K2/K3 belong to the play screen. K1 opens MENU.
2. **MENU** — E2 select, K3 forward, K2 back (no-op at root), K1 returns PLAY.

## PLAY mapping (screen-local)

| Control | PLAY |
|---------|------|
| E1 | master (parameter) |
| E2 | scene (parameter) |
| E3 | speed (parameter) |
| K1 | MENU (shell) |
| K2 | contextual |
| K3 | GO |

Blackout is a PARAMS toggle, not K1.

## Menu

```
HOME    → PLAY
PARAMS  → parameter list
SCENES
OUTPUT
SYSTEM
```

## PARAMS

E2 select, E3 change, K3 trigger. Same `Params` objects as PLAY.

## Simulator

Same `NornsUIShell`, screens, parameters, renderer as the Shield.

| Key | Hardware |
|-----|----------|
| Q/A or ←/→ | E1 |
| W/S or ↑/↓ | E2 |
| E/D or `,` `.` | E3 |
| Z or 1 | K1 |
| X or 2 | K2 |
| C or 3 | K3 |
| F1 | QLC online / offline |
