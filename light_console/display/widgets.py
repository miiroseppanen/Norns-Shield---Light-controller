from __future__ import annotations

from light_console.display.font import CELL_H, CELL_W, GLYPH_H, glyph
from light_console.display.framebuffer import Framebuffer


def text(fb: Framebuffer, x: int, y: int, s: str, on: bool = True) -> None:
    text_clipped(fb, x, y, s, x0=None, x1=None, on=on)


def text_clipped(
    fb: Framebuffer,
    x: int,
    y: int,
    s: str,
    x0: int | None = None,
    x1: int | None = None,
    on: bool = True,
) -> None:
    """Draw text starting at x. Only pixels in [x0, x1) are written when bounds set."""
    cx = x
    left = 0 if x0 is None else x0
    right = fb.width if x1 is None else x1
    for ch in s:
        rows = glyph(ch)
        for row, bits in enumerate(rows):
            for col in range(5):
                px = cx + col
                if px < left or px >= right:
                    continue
                if bits & (0x10 >> col):
                    fb.pixel(px, y + row, on)
        cx += CELL_W


def text_right(fb: Framebuffer, right: int, y: int, s: str, on: bool = True) -> None:
    width = len(s) * CELL_W
    text(fb, right - width, y, s, on)


def text_center(fb: Framebuffer, y: int, s: str, on: bool = True) -> None:
    width = len(s) * CELL_W
    text(fb, max(0, (fb.width - width) // 2), y, s, on)


def clip_text(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    if max_chars <= 1:
        return s[:max_chars]
    return s[: max_chars - 1] + "."


def status_pair(fb: Framebuffer, y: int, left: str, right: str) -> None:
    text(fb, 0, y, clip_text(left, 12))
    text_right(fb, fb.width, y, clip_text(right, 9))


def invert_bar(fb: Framebuffer, y: int, h: int = CELL_H) -> None:
    for yy in range(y, min(fb.height, y + h)):
        for x in range(fb.width):
            fb.pixel(x, yy, not fb.get(x, yy))


ROW = CELL_H
__all__ = [
    "text",
    "text_clipped",
    "text_right",
    "text_center",
    "clip_text",
    "status_pair",
    "invert_bar",
    "ROW",
    "CELL_W",
    "CELL_H",
    "GLYPH_H",
]
