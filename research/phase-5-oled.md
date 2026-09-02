# Phase 5 — OLED proof

Date: 2026-09-01. Host: `light@shieldxl-light.local`.  
Tool: `scripts/test-oled.py`. Path: userspace SSD1322 on `/dev/spidev0.0` after stock `dtparam=spi=on`. No ssd13xx overlay.

## Geometry (operator: “näyttää oikealta”)

Packing that failed: 64 bytes/row (2 pixels/byte 4bpp) → ~1/4 image, repeat, bottom noise.

Packing that works (NHD-2.7-12864WDW3 / Dual COM):

| Item | Value |
|------|--------|
| Column window | `0x15` start `0x1C` end `0x5B` (64 column addresses) |
| Row window | `0x75` 0..63 |
| Bytes per column address | 2 (`0x00`/`0xFF` per visible pixel) |
| Bytes per row | **128** |
| Frame | **8192** |
| Remap | `0xA0` = `0x16,0x11` (rotate 0) |
| Dual COM | enabled (B[4]=1); COM-split A[5]=0 |
| Multiplex | `0xCA` = `0x3F` (64 rows) |
| Offset / start line | 0 / 0 |

Pattern: white rows 0, 16, 32, 48, 63; black row 1; 8 px left and right bars. Full 128×64, no repeat, no noise.

## Text

Operator: text is **clear**. First draw with remap `0x16,0x11` was **180°** vs enclosure.

Working remap: `0x04,0x11` (`--rotate 180`). Matches norns `dtparam=rotate=180`.

**OLED PASS** — full 128×64, readable `LIGHT CONSOLE` / `OLED PASS`, userspace SPI, no kernel overlay.

## Notes

GPIO pins unchanged (DC=5, RESET=6, SPI0 CE0/MOSI/SCLK). Codec pins untouched.
