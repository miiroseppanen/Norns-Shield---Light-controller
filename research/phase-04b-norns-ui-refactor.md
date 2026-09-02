# Milestone 0.4b — Norns UI semantics

Date: 2026-09-02

Mac: `python3.11 -m pytest` — **46 passed**.

## What changed

- `NornsUIShell`: K1 is PLAY ↔ MENU globally
- PLAY screen (was HOME); K1 no longer blackout
- Menu root: HOME PARAMS SCENES OUTPUT SYSTEM
- Navigation stack; K2 pop; root K2 is a no-op
- Parameter system: Number / Option / Toggle / Action, shared by PLAY and PARAMS
- Screen API: `enc(n, delta)`, `key(n, z)`, `redraw(fb)`
- QLC still only via `QlcBinding` after AppState changes

## Deploy

Copy to `/home/light/light-console`. Previous `--shield` process was stopped so GPIO/SPI could bind. OLED PLAY frame written (0.4.0).

1. PLAY
2. K1 → MENU
3. E2 browse
4. K3 → PARAMS
5. E2 select parameter
6. E3 change value
7. K2 back
8. K1 → PLAY
9. PLAY shows the same value
