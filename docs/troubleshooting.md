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
| Black OLED after boot | `systemctl status light-console`; `journalctl -u light-console -b`. Pending `dev-spidev0.0.device` job means the unit still has `After=`/`Wants=` on that device — remove them. |
| Black OLED while running | SPI overlay, RESET/DC wiring, HDMI stealing fb numbering — see research U3/U4 |
| `light-console --shield` from SSH fails | Another instance holds `/tmp/light-console.instance.lock`. `sudo systemctl stop light-console` if you need the foreground. |
| No encoder events | Overlay pin overrides, `evtest`, E2/E3 identity (U1) |
| Keys inverted | Active low; overlay flags |
| Show dead when UI dies | QLC/wizbridge still running? If not, that is a systemd issue, not OLED |

## Appliance (read-only)

```
cd /home/light/light-console
python3 -m light_console.appliance_check
```

Does not start, stop, or restart services. Cold-boot sequence: [`docs/cold-boot.md`](cold-boot.md).

## QLC

`QLC LOST` = WebSocket down. Do not restart QLC from the UI. Check `qlcplus.service` separately.

## WiZ

`WiZ 0/m WAIT` after simultaneous power-on can be normal for minutes. Do not bounce the AP in a loop.

## MIDI

Launchpad Mini USB `1235:0036`. OLED `MIDI LP --` means the pad is missing; QLC can still run from the console.

## DMX

`DMX NET OK` ≠ node alive. `DMX NODE --` if PKNight `192.168.88.201` is unreachable. WiZ continues.
