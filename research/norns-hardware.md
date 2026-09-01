# Norns hardware notes (reference only)

This project is **not** a norns. The Norns Shield SD card must not be modified. This file exists so we do not mix CM3 norns, norns shield, Fates, and shieldXL.

## Three hardware families

| Family | CPU board | Display | Keys/encoders GPIO | Audio |
|--------|-----------|---------|--------------------|-------|
| norns (standard) | Compute Module 3 | NHD-2.7-12864WDW3, SSD1322 SPI, DC=GPIO5, RESET=GPIO6 | GPIO 28–39 (CM3 SODIMM) | CS4270, I2S GPIO17–21 |
| norns shield | Pi 3B+/4 40-pin | Same panel family | Overlay **overrides** to GPIOs on the 40-pin header | CS4270 (210330) or CS4271 (211028) |
| shieldXL | Pi 3/4 | NHD-2.7-12864WDW3-M | Same overlay overrides as shield 210330 | CS4270 + extra TRS MIDI UART |
| Fates | Pi 3/4 | Often same OLED, **different GPIOs** | Do not use Fates overlays on shieldXL | Different |

## Software stack we will not run

matron (Lua UI + cairo → framebuffer), crone, SuperCollider, maiden, norns systemd target, norns realtime kernel image.

## Software ideas we may reuse later

- Read encoders/keys as Linux input events.
- Draw 128×64 into a framebuffer or SPI.
- Keep UI in a process that is **not** the show engine.

## matron input (for later driver design)

norns overlay `gpio-keys` uses `linux,code` 1, 2, 3. Encoders are `rotary-encoder` relative axes. matron watches `/dev/input`. light-console should do the same on Pi, not copy matron C.

## Disk images (do not flash for this project)

norns-image 231114 still publishes `norns231114-shield-pi4-cs4720.tgz` for pre-211028 / CS4270 shields. That image is for **norns**, not light-console.
