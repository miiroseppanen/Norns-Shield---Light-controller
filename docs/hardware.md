# Hardware

Authoritative pin research: [`research/shieldxl.md`](../research/shieldxl.md).

## Device

Raspberry Pi 4 + Denki Oto shieldXL (norns shield 210330 remix). OLED 128×64 SSD1322, three encoders, three keys.

## Software rule

`light_console` never imports `RPi.GPIO` / `gpiozero` / `spidev` outside `light_console.hardware.shieldxl`. Milestone 0.1 does not open those devices.

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
| E3 B (schematic E2 B) / overlay e3_pin_b | 23 | confirm knob in 0.2 |
| overlay e3_pin_a | 24 | confirm knob in 0.2 |
| overlay e2_pin_b | 25 | confirm knob in 0.2 |
| K2 | 26 | active low |
| E1 B | 27 | |
| E1 A | 4 | |
| overlay e2_pin_a | 12 | confirm knob in 0.2 |

E2 vs E3 physical identity: UNKNOWN until `evtest` (research U1).

## Backends

- `SimulatorBackend` — pygame 128×64 window + keyboard/mouse (0.1)
- `ShieldXLBackend` — raises until Milestone 0.2
