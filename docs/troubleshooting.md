# Troubleshooting

## Simulator (Mac)

| Symptom | Check |
|---------|--------|
| `python -m simulator.run` ImportError pygame | `pip install -e ".[sim]"` |
| Window opens but keys do nothing | Focus the OLED window; see on-screen legend |
| Tests fail | `python -m pytest` from repo root with `pip install -e ".[dev]"` |

## Hardware (Milestone 0.2+)

| Symptom | Check |
|---------|--------|
| Black OLED | SPI overlay, RESET/DC wiring, HDMI stealing fb numbering — see research U3/U4 |
| No encoder events | Overlay pin overrides, `evtest`, E2/E3 identity (U1) |
| Keys inverted | Active low; overlay flags |
| Show dead when UI dies | QLC/wizbridge still running? If not, that is a systemd issue, not OLED |

## QLC

`QLC LOST` = WebSocket down. Do not restart QLC from the UI. Check `qlcplus.service` separately.

## WiZ

`WiZ 0/m WAIT` after simultaneous power-on can be normal for minutes. Do not bounce the AP in a loop.

## MIDI

Launchpad Mini USB `1235:0036`. OLED `MIDI LP --` means the pad is missing; QLC can still run from the console.

## DMX

`DMX NET OK` ≠ node alive. `DMX NODE --` if PKNight `192.168.88.201` is unreachable. WiZ continues.
