# Norns UI model (Shield XL Light Console)

This is **not** Norns OS. It is the Norns interaction model on Raspberry Pi OS + Python.

See also [`ui-architecture.md`](ui-architecture.md).

## Controls

Physical names everywhere: **K1 K2 K3** and **E1 E2 E3**.

K1 is the shell PLAY ↔ MENU toggle. Show functions are not wired in the hardware layer.

### PLAY

- **E1** — MASTER
- **E2** — selected scene (shared with SCENES)
- **K2** — SCENE GO
- **E3** — selected chaser (shared with CHASERS)
- **K3** — CHASER GO
- **K1** — MENU

### MENU

- **E1 / E2** — selection
- **E3** — no-op (does not move the cursor)
- **K3** — forward / enter
- **K2** — back (no-op at root)
- **K1** — PLAY, from any menu depth

Stack: `root → submenu → page`. K2 pops.

Root:

```
HOME
SHOWS
SCENES
CHASERS
PARAMS
OUTPUT
SYSTEM
```

HOME enters PLAY. SHOWS / SCENES / CHASERS / PARAMS / OUTPUT / SYSTEM are screens.

SHOWS lists named `.qxw` files on the appliance. K3 opens a confirm page (`LOAD` or `OPEN`). Confirming copies that file onto `master.qxw` and restarts QLC via systemd start/stop. Already-open files stay `OPEN` and do not bounce QLC. See [`docs/show-ui.md`](show-ui.md).

SYSTEM list: QLC SERVICE, NETWORK MODE, VERSION, RESTART.

WIZ submenu: DEVICES, CONTROL, INFO.

MENU after SYSTEM is SHUTDOWN last. SYSTEM → RESTART → K3, or MENU → SHUTDOWN → K3, opens a confirm page (`PRESS RIGHT BUTTON` / `TO RESTART` or `TO SHUT DOWN`). K2 back (RESTART confirm returns to SYSTEM). K3 on the confirm page begins reboot or halt. OLED stays on RESTARTING or SHUTTING DOWN until Linux stops. After that K1/K2/K3 and E1/E2/E3 do nothing; `PowerService.request_restart()` or `request_shutdown()` runs once. The Shield backend may run `sudo /usr/sbin/shutdown -r now` or `-h now`. The simulator only sets a flag.

## Screens vs parameters

A **PLAY screen** is for live performance. **PARAMS** lists every adjustable value.

The same `Parameter` objects back both. AppState holds the values once.

## Parameter types

`Parameter`, `NumberParameter`, `OptionParameter`, `ToggleParameter`, `ActionParameter`

Metadata: id, name, type, value, min/max/step, options, formatter.

PARAMS: E2 select, E3 change, K3 trigger, K2 back.

Encoder path: `E3 → Parameter.delta → AppState → QlcBinding`. Never GPIO → QLC.

## Screen API

Python equivalent of norns `enc` / `key` / `redraw`:

```python
screen.enc(n, delta)   # n is E1/E2/E3
screen.key(n, z)       # n is K1/K2/K3; z=1 tap, z=0 up
screen.redraw(fb)
```

`NornsUIShell` consumes K1 globally, MENU E1/K2/K3, then dispatches to the active screen. PARAMS still uses E2/E3.

## Event flow

```
GPIO → HardwareEvent → NornsUIShell → Screen → Parameter/Action
     → AppState → QLC client

AppState → 128×64 framebuffer → OLED
```

OLED driver does not know QLC. QLC client does not know GPIO numbers.

## Rendering

128×64, sparse, header + list, `>` and inverted selected row, no per-widget boxes.
