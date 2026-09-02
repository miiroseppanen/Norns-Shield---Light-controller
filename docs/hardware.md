# Hardware

Authoritative pin research: [`research/shieldxl.md`](../research/shieldxl.md).

## Device

Raspberry Pi 4 + Denki Oto shieldXL (norns shield 210330 remix). OLED 128×64 SSD1322, three encoders, three keys.

## Software rule

`light_console` never imports `RPi.GPIO` / `gpiozero` / `spidev` outside `light_console.hardware` (`shieldxl.py`, `oled.py`).

## Pin table (BCM) — verified for 210330 / shieldXL overlay

| Function | GPIO | Notes |
|----------|------|-------|
| OLED D/C | 5 | |
| OLED RESET | 6 | active low |
| OLED CS | 8 | SPI0 CE0 |
| OLED MOSI | 10 | SPI0 |
| OLED SCLK | 11 | SPI0 |
| K3 | 13 | active low |
| UART TX (MIDI) | 14 | unused by this app |
| UART RX (MIDI) | 15 | unused by this app |
| Codec reset | 17 | do not reuse |
| I2S | 18–21 | do not reuse |
| K1 | 22 | active low |
| E3 B (physical E3 / overlay e3_pin_b; schematic E2 B) | 23 | A-leads-B = CW |
| E3 A (physical E3 / overlay e3_pin_a; schematic E2 A) | 24 | |
| E2 B (physical E2 / overlay e2_pin_b; schematic E3 B) | 25 | |
| K2 | 26 | active low |
| E1 B | 27 | |
| E1 A | 4 | |
| E2 A (physical E2 / overlay e2_pin_a; schematic E3 A) | 12 | |

Physical E2 = GPIO12/25 (overlay e2, schematic part E3). Physical E3 = GPIO24/23 (overlay e3, schematic part E2). See `research/phase-4b-encoders-e2-e3.md`.

## Backends

- `SimulatorBackend` — pygame 128×64 window + keyboard (same UI code as Shield)
- `ShieldXLBackend` — gpiod + SSD1322 SPI (Milestone 0.4 prototype)
