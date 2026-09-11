"""Userspace SSD1322 (NHD-2.7-12864WDW3). Proven packing from Milestone 0.2.

128 bytes/row, 8192/frame, remap 0x04,0x11 (enclosure 180°).
"""

from __future__ import annotations

import time
from pathlib import Path

from light_console.display.framebuffer import Framebuffer
from light_console.hardware.pinout import OLED_CS, OLED_DC, OLED_MOSI, OLED_RESET, OLED_SCLK

CHIP_PATH = "/dev/gpiochip0"
SPI_DEV = "/dev/spidev0.0"
WIDTH = 128
HEIGHT = 64
COL_START = 0x1C
COL_END = 0x5B
BYTES_PER_ROW = 128
REMAP_180 = (0x04, 0x11)


def pack_framebuffer(fb: Framebuffer) -> list[bytes]:
    rows: list[bytes] = []
    for y in range(fb.height):
        rows.append(bytes(0xFF if fb.get(x, y) else 0x00 for x in range(fb.width)))
    return rows


class Ssd1322:
    def __init__(self, hz: int = 8_000_000, remap: tuple[int, int] = REMAP_180) -> None:
        import gpiod
        import spidev
        from gpiod.line import Direction, Value

        if not Path(SPI_DEV).exists():
            raise FileNotFoundError(f"{SPI_DEV} missing — enable dtparam=spi=on")
        self._gpiod = gpiod
        self._Value = Value
        self.remap = remap
        self.gpio = gpiod.request_lines(
            CHIP_PATH,
            consumer="light-console-oled",
            config={
                OLED_DC.bcm: gpiod.LineSettings(
                    direction=Direction.OUTPUT, output_value=Value.ACTIVE
                ),
                OLED_RESET.bcm: gpiod.LineSettings(
                    direction=Direction.OUTPUT, output_value=Value.ACTIVE
                ),
            },
        )
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)  # SPI0 CE0 (GPIO8)
        self.spi.mode = 0
        self.spi.max_speed_hz = hz
        _ = (OLED_CS, OLED_MOSI, OLED_SCLK)

    def close(self) -> None:
        """Release SPI/GPIO. Do not blank the SSD1322; last pixels stay."""
        try:
            self.spi.close()
        except Exception:
            pass
        try:
            self.gpio.release()
        except Exception:
            pass

    def _dc(self, data: bool) -> None:
        self.gpio.set_value(OLED_DC.bcm, self._Value.ACTIVE if data else self._Value.INACTIVE)

    def cmd(self, code: int, *args: int) -> None:
        self._dc(False)
        self.spi.writebytes([code & 0xFF])
        if args:
            self._dc(True)
            self.spi.writebytes([a & 0xFF for a in args])

    def data(self, payload: bytes) -> None:
        self._dc(True)
        self.spi.writebytes(list(payload))

    def reset(self) -> None:
        self.gpio.set_value(OLED_RESET.bcm, self._Value.INACTIVE)
        time.sleep(0.001)
        self.gpio.set_value(OLED_RESET.bcm, self._Value.ACTIVE)
        time.sleep(0.001)

    def init(self) -> None:
        self.reset()
        self.cmd(0xFD, 0x12)
        self.cmd(0xAE)
        self.cmd(0xB3, 0x91)
        self.cmd(0xCA, 0x3F)
        self.cmd(0xA2, 0x00)
        self.cmd(0xA1, 0x00)
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
        for y, row in enumerate(rows):
            self.cmd(0x15, COL_START, COL_END)
            self.cmd(0x75, y, y)
            self.cmd(0x5C)
            self.data(row)

    def show_framebuffer(self, fb: Framebuffer) -> None:
        self.show_rows(pack_framebuffer(fb))
