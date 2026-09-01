# Boot

Deterministic, diagnosable, no restart loops that flash the show.

## Intended order (later Pi)

1. NetworkManager: WIZ-LIGHTS AP (wlan1) comes up locally — no internet required
2. wizbridge.service
3. qlcplus.service (after MIDI wait helper if used — same idea as production `wait-qlc-launchpad`)
4. light-console.service — OLED boot screen, then home

light-console **After=** QLC is allowed as a weak ordering hint, not a hard requirement to draw the boot checklist.

## Boot screen

```
LIGHT CONSOLE
QLC       WAIT|OK|LOST
WIZ AP    WAIT|OK
WiZ       n/m
MIDI LP   OK|--
DMX NODE  OK|--
```

When QLC is connected and project loaded, switch to HOME.

## Forbidden

- Restart QLC because OLED failed
- Restart WIZ-LIGHTS in a loop because WiZ count is 0
- Require wlan0 before starting the show path
