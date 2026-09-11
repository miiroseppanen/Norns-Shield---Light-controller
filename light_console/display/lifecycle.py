"""Full-screen appliance lifecycle frames. Not QLC function status."""

from __future__ import annotations

from light_console.display.font import GLYPH_H
from light_console.display.framebuffer import Framebuffer
from light_console.display.marquee import text_width_px
from light_console.display.widgets import text

STARTING_UP_TEXT = "STARTING UP"
SHUTTING_DOWN_TEXT = "SHUTTING DOWN"


def lifecycle_origin(
    message: str, width: int = 128, height: int = 64
) -> tuple[int, int]:
    """Pixel origin for centered lifecycle text using font metrics."""
    w = text_width_px(message)
    h = GLYPH_H
    x = max(0, (width - w) // 2)
    y = max(0, (height - h) // 2)
    return x, y


def draw_lifecycle(fb: Framebuffer, message: str) -> None:
    """Black full-screen frame, centered white text, nothing else."""
    fb.clear()
    x, y = lifecycle_origin(message, fb.width, fb.height)
    text(fb, x, y, message)


def render_lifecycle(message: str) -> Framebuffer:
    fb = Framebuffer()
    draw_lifecycle(fb, message)
    return fb
