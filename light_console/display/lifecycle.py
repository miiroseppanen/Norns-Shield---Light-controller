"""Full-screen appliance lifecycle frames. Not QLC function status."""

from __future__ import annotations

import time
from pathlib import Path

from light_console.display.font import GLYPH_H
from light_console.display.framebuffer import Framebuffer
from light_console.display.marquee import text_width_px
from light_console.display.widgets import text

STARTING_UP_TEXT = "STARTING UP"
SHUTTING_DOWN_TEXT = "SHUTTING DOWN"
RESTARTING_TEXT = "RESTARTING"
STARTUP_MIN_VISIBLE_S = 2.25
# Written by the early boot helper; consumed once by Light Console.
# Ordinary systemctl restart does not recreate this, so it must not hold.
STARTING_MARK = Path("/tmp/shieldxl-oled-starting")


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


def remaining_startup_hold_s(
    t0: float,
    now: float,
    minimum_s: float = STARTUP_MIN_VISIBLE_S,
) -> float:
    """Seconds still needed so STARTING UP has been visible for minimum_s."""
    return max(0.0, minimum_s - (now - t0))


def write_starting_mark(path: Path | None = None) -> None:
    target = STARTING_MARK if path is None else path
    try:
        target.write_text("1\n", encoding="utf-8")
    except OSError:
        pass


def consume_starting_mark(path: Path | None = None) -> bool:
    target = STARTING_MARK if path is None else path
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def hold_starting_up_visible(
    t0: float | None,
    *,
    enabled: bool,
    minimum_s: float = STARTUP_MIN_VISIBLE_S,
) -> float:
    """Sleep only leftover STARTING UP time. Local UI policy."""
    if t0 is None or not enabled:
        return 0.0
    rem = remaining_startup_hold_s(t0, time.monotonic(), minimum_s)
    if rem <= 0:
        return 0.0
    time.sleep(rem)
    return rem
