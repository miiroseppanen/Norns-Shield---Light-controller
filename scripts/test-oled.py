#!/usr/bin/env python3
"""Shield XL OLED proof — userspace SSD1322 on SPI0, no kernel overlay.

NHD-2.7-12864WDW3-M / SSD1322: controller RAM is wider than 128 px.
Visible window is column 0x1C..0x5B (64 column addresses). Dual COM
(remap second byte 0x11) plus segment wiring means **every second
nibble/pixel is unused**: each visible pixel is one full byte 0x00 or
0xFF, two bytes per column address.

  bytes_per_row = 128
  frame_bytes   = 128 * 64 = 8192

Sending 64 bytes/row (2px-per-byte 4bpp) fills only half a RAM row, so
the next software row continues on the same COM line: ~1/4 image in the
top-left, a repeat in the upper half, noise below.

Pins unchanged: MOSI=10 SCLK=11 CE0=8 DC=5 RESET=6. No extra overlays.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import gpiod
import spidev
from gpiod.line import Direction, Value

CHIP_PATH = "/dev/gpiochip0"
SPI_DEV = "/dev/spidev0.0"
GPIO_DC = 5
GPIO_RESET = 6
WIDTH = 128
HEIGHT = 64
COL_START = 0x1C
COL_END = 0x5B
COL_COUNT = COL_END - COL_START + 1  # 64
BYTES_PER_PIXEL = 1  # 0x00 or 0xFF per visible pixel
BYTES_PER_COL = 2  # Newhaven write2Pixels: two bytes per column address
BYTES_PER_ROW = COL_COUNT * BYTES_PER_COL  # 128
FRAME_BYTES = BYTES_PER_ROW * HEIGHT  # 8192
MUX = 0x3F
OFFSET = 0x00
START_LINE = 0x00
REMAP_0 = (0x16, 0x11)  # NHD datasheet / u8g2 nhd_128x64
REMAP_180 = (0x04, 0x11)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


class Ssd1322:
    def __init__(self, remap: tuple[int, int], hz: int) -> None:
        if not Path(SPI_DEV).exists():
            fail(f"{SPI_DEV} missing — enable dtparam=spi=on and reboot")
        self.remap = remap
        self.gpio = gpiod.request_lines(
            CHIP_PATH,
            consumer="shieldxl-oled-test",
            config={
                GPIO_DC: gpiod.LineSettings(
                    direction=Direction.OUTPUT, output_value=Value.ACTIVE
                ),
                GPIO_RESET: gpiod.LineSettings(
                    direction=Direction.OUTPUT, output_value=Value.ACTIVE
                ),
            },
        )
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.mode = 0
        self.spi.max_speed_hz = hz
        self.spi.no_cs = False

    def close(self) -> None:
        try:
            self.spi.close()
        except Exception:
            pass
        try:
            self.gpio.release()
        except Exception:
            pass

    def _dc(self, data: bool) -> None:
        self.gpio.set_value(GPIO_DC, Value.ACTIVE if data else Value.INACTIVE)

    def cmd(self, code: int, *args: int) -> None:
        self._dc(False)
        self.spi.writebytes([code & 0xFF])
        if args:
            self._dc(True)
            self.spi.writebytes([a & 0xFF for a in args])

    def data(self, payload: bytes | bytearray | list[int]) -> None:
        self._dc(True)
        buf = bytes(payload)
        # Keep transfers small so CS is per-row, never mid-row (spidev bufsiz).
        self.spi.writebytes(list(buf))

    def reset(self) -> None:
        self.gpio.set_value(GPIO_RESET, Value.INACTIVE)
        time.sleep(0.001)
        self.gpio.set_value(GPIO_RESET, Value.ACTIVE)
        time.sleep(0.001)

    def init(self) -> None:
        self.reset()
        self.cmd(0xFD, 0x12)
        self.cmd(0xAE)
        self.cmd(0xB3, 0x91)
        self.cmd(0xCA, MUX)
        self.cmd(0xA2, OFFSET)
        self.cmd(0xA1, START_LINE)
        self.cmd(0xAB, 0x01)
        self.cmd(0xA0, self.remap[0], self.remap[1])
        self.cmd(0xC7, 0x0F)
        self.cmd(0xC1, 0x9F)
        self.cmd(0xB1, 0xF2)
        self.cmd(0xBB, 0x1F)
        self.cmd(0xB4, 0xA0, 0xFD)
        self.cmd(0xBE, 0x04)
        self.cmd(0xB9)
        self.cmd(0xA6)
        self.cmd(0xA9)
        self.cmd(0xAF)
        time.sleep(0.01)

    def show_rows(self, rows: list[bytes]) -> None:
        if len(rows) != HEIGHT:
            fail(f"need {HEIGHT} rows, got {len(rows)}")
        for y, row in enumerate(rows):
            if len(row) != BYTES_PER_ROW:
                fail(f"row {y} is {len(row)} bytes, expected {BYTES_PER_ROW}")
            self.cmd(0x15, COL_START, COL_END)
            self.cmd(0x75, y, y)
            self.cmd(0x5C)
            self.data(row)


def pack_row(pixels: list[int]) -> bytes:
    """128 visible pixels → 128 bytes 0x00/0xFF (2 bytes per column address)."""
    if len(pixels) != WIDTH:
        fail(f"pack_row got {len(pixels)} pixels")
    return bytes(0xFF if p else 0x00 for p in pixels)


def geometry_rows() -> list[bytes]:
    rows: list[bytes] = []
    white_rows = {0, 16, 32, 48, 63}
    for y in range(HEIGHT):
        pix = [0] * WIDTH
        if y in white_rows:
            pix = [1] * WIDTH
        for x in range(8):
            pix[x] = 1
            pix[WIDTH - 1 - x] = 1
        rows.append(pack_row(pix))
    return rows


# 5×7 from light_console.display.font — packed 7 rows, bits 4..0.
_RAW = {
    " ": 0x00000000000000,
    "A": 0x0E11111F111100,
    "C": 0x0E111010110E00,
    "D": 0x1C121111121C00,
    "E": 0x1F101E10101F00,
    "G": 0x0E111017110E00,
    "H": 0x11111F11111100,
    "I": 0x0E040404040E00,
    "L": 0x10101010101F00,
    "N": 0x11191513111100,
    "O": 0x0E111111110E00,
    "P": 0x1E11111E101000,
    "S": 0x0E11100E110E00,
    "T": 0x1F040404040400,
}
CELL_W = 6


def glyph(ch: str) -> tuple[int, ...]:
    packed = _RAW.get(ch.upper() if ch.isalpha() else ch, _RAW[" "])
    return tuple((packed >> (8 * (6 - i))) & 0x1F for i in range(7))


def blit_text(fb: list[list[int]], text: str, y0: int) -> None:
    x = max(0, (WIDTH - len(text) * CELL_W) // 2)
    for ch in text:
        rows = glyph(ch)
        for row, bits in enumerate(rows):
            yy = y0 + row
            if not (0 <= yy < HEIGHT):
                continue
            for col in range(5):
                if bits & (0x10 >> col):
                    xx = x + col
                    if 0 <= xx < WIDTH:
                        fb[yy][xx] = 1
        x += CELL_W


def text_rows() -> list[bytes]:
    fb = [[0] * WIDTH for _ in range(HEIGHT)]
    blit_text(fb, "LIGHT CONSOLE", 18)
    blit_text(fb, "OLED PASS", 36)
    return [pack_row(row) for row in fb]


def print_debug(remap: tuple[int, int]) -> None:
    dual = (remap[1] >> 4) & 1
    print(
        f"column_start=0x{COL_START:02X} ({COL_START})  "
        f"column_end=0x{COL_END:02X} ({COL_END})  "
        f"column_count={COL_COUNT}",
        flush=True,
    )
    print("row_start=0  row_end=63  row_count=64", flush=True)
    print(
        f"bytes_per_row={BYTES_PER_ROW}  "
        f"(col_count {COL_COUNT} × {BYTES_PER_COL} bytes/col)",
        flush=True,
    )
    print(f"total_frame_bytes={FRAME_BYTES}", flush=True)
    print(
        f"remap=0x{remap[0]:02X},0x{remap[1]:02X}  "
        f"dual_com={dual}  (A[5] COM-split must be 0 when dual=1)",
        flush=True,
    )
    print(f"multiplex=0x{MUX:02X} ({MUX + 1} rows)", flush=True)
    print(f"display_offset=0x{OFFSET:02X}  start_line=0x{START_LINE:02X}", flush=True)
    print(
        "packing=1 byte/visible pixel (0x00/0xFF); not 2px-per-byte 4bpp",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotate", type=int, choices=(0, 180), default=180)
    parser.add_argument("--hz", type=int, default=8_000_000)
    parser.add_argument(
        "--geometry",
        action="store_true",
        help="draw the row/bar geometry pattern instead of text",
    )
    args = parser.parse_args()
    remap = REMAP_180 if args.rotate == 180 else REMAP_0

    mode = "geometry" if args.geometry else "text"
    print(
        f"SSD1322 {mode}  {SPI_DEV}  DC=GPIO{GPIO_DC} RESET=GPIO{GPIO_RESET}  "
        f"rotate={args.rotate} hz={args.hz}",
        flush=True,
    )
    print_debug(remap)
    print(
        "pattern=geometry bars" if args.geometry else "pattern=LIGHT CONSOLE / OLED PASS",
        flush=True,
    )

    oled = Ssd1322(remap=remap, hz=args.hz)
    try:
        oled.init()
        oled.show_rows(geometry_rows() if args.geometry else text_rows())
        print("frame written; look at the panel (image stays in SSD1322 RAM)", flush=True)
    finally:
        oled.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
