# Shield XL Light Console

Standalone lighting console UI for **Raspberry Pi 4 + Denki Oto shieldXL**. QLC+ is the show engine. This repository is **new and separate** from the production wiz-bridge Pi and from the Norns Shield SD card.

**Milestone 0.4.0** — Norns UI model (PLAY / MENU / PARAMS). Same code on Mac simulator and Shield.

## Mac simulator

```bash
cd shieldxl-light-console
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[sim,dev]"
python -m simulator.run
```

The window is a scaled **128×64** copy of the same framebuffer the OLED uses. There is no separate fake UI.

| Input | Action |
|-------|--------|
| Q / A or ← → | Encoder E1 |
| W / S or ↑ ↓ | Encoder E2 |
| E / D or `,` `.` | Encoder E3 |
| Z or 1 | K1 |
| X or 2 | K2 |
| C or 3 | K3 |
| F1 | QLC connected / offline |
| ESC | quit |

K1 = PLAY/MENU. PLAY: E1 master, E2 scene, E3 speed, K3 GO. MENU: E2 select, K3 enter, K2 back. PARAMS: E2 select, E3 value.

Headless dump (no pygame window):

```bash
python -m light_console.main --headless --dump-screen /tmp/oled.txt --screenshot /tmp/oled.ppm
```

Tests:

```bash
python -m pytest
```

UI model: [`docs/norns-ui-model.md`](docs/norns-ui-model.md). Architecture: [`docs/ui-architecture.md`](docs/ui-architecture.md).

## What this is not

- Not a replacement for QLC+ or wizbridge
- Not a Norns image
- Not a deploy onto `valot.local` or the existing Norns microSD

Hardware facts: [`research/shieldxl.md`](research/shieldxl.md).

## Version

| Ver | Meaning |
|-----|---------|
| 0.1.0 | Simulator + docs |
| 0.2.0 | Shield XL hardware proof |
| 0.3.0 | QLC+ 5.2.2 engine baseline |
| 0.4.0 | Norns-like UI framework (now) |
| 1.0.0 | Show-ready |
