"""Reusable 128×64 monochrome OLED components.

STATIC CONTROL = what I chose
STATIC STATUS  = what the system is
MOVEMENT       = what is happening now
SCROLLBAR      = where I am
"""

from __future__ import annotations

from light_console.display.activity import FRAMES, SCAN_X, SCAN_Y, SEG_W, activity_frame
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import (
    ACTIVITY_W,
    ACTIVITY_X,
    CONTENT_H,
    CONTENT_RIGHT,
    CONTENT_Y,
    FOCUS_W,
    LABEL_X,
    MIN_THUMB,
    ROW,
    SCROLL_W,
    SCROLL_X,
    TOGGLE_D,
    TOGGLE_LABEL_X,
    TOGGLE_X,
    VALUE_RIGHT,
)
from light_console.display.viewport import scrollbar_metrics
from light_console.display.widgets import CELL_W, clip_text, text, text_center, text_clipped, text_right

WARN_STATES = frozenset({"FAILED", "LOST", "OFFLINE", "AP FAILED", "BRIDGE FAILED"})

_CIRCLE_FILL = (
    0b0011100,
    0b0111110,
    0b1111111,
    0b1111111,
    0b1111111,
    0b0111110,
    0b0011100,
)
_CIRCLE_OUTLINE = (
    0b0011100,
    0b0100010,
    0b1000001,
    0b1000001,
    0b1000001,
    0b0100010,
    0b0011100,
)


def region_on_count(fb: Framebuffer, x: int, y: int, w: int, h: int) -> int:
    total = 0
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            total += fb.get(xx, yy)
    return total


def draw_focus_rail(fb: Framebuffer, y: int, h: int = ROW) -> None:
    fb.fill_rect(0, y, FOCUS_W, h, True)


def draw_separator(fb: Framebuffer, y: int, w: int = CONTENT_RIGHT) -> None:
    fb.hline(0, y, w, True)


def draw_page_header(fb: Framebuffer, title: str) -> None:
    text(fb, 0, 0, clip_text(title, 20))
    draw_separator(fb, ROW - 1)


def draw_empty_state(fb: Framebuffer, message: str) -> None:
    text_center(fb, CONTENT_Y + ROW * 3, clip_text(message, 20))


def draw_scrollbar(
    fb: Framebuffer,
    total: int,
    visible: int,
    offset: int,
    *,
    x: int = SCROLL_X,
    y: int = CONTENT_Y,
    h: int = CONTENT_H,
) -> None:
    metrics = scrollbar_metrics(total, visible, offset, h, min_thumb=MIN_THUMB)
    if metrics is None:
        return
    thumb_y, thumb_h = metrics
    # 1px dotted track so a near-full thumb is not mistaken for a page border.
    for yy in range(y, y + h, 2):
        fb.pixel(x + 1, yy, True)
    fb.fill_rect(x + 1, y + thumb_y, max(1, SCROLL_W - 1), thumb_h, True)


def draw_toggle(fb: Framebuffer, x: int, y: int, on: bool) -> None:
    """Filled circle = enabled choice. Outline = disabled choice."""
    pattern = _CIRCLE_FILL if on else _CIRCLE_OUTLINE
    cy = y + max(0, (ROW - TOGGLE_D) // 2)
    for row, bits in enumerate(pattern):
        for col in range(TOGGLE_D):
            if bits & (1 << (TOGGLE_D - 1 - col)):
                fb.pixel(x + col, cy + row, True)


def draw_activity(fb: Framebuffer, x: int, y: int, frame: int) -> None:
    """1px-high LTR scan in the activity slot. Idle callers must not draw this."""
    slot = max(0, min(FRAMES - 1, int(frame)))
    fb.hline(x + SCAN_X[slot], y + SCAN_Y, SEG_W, True)


def maybe_activity(fb: Framebuffer, y: int, now: float, active: bool) -> None:
    frame = activity_frame(now, active)
    if frame is None:
        return
    draw_activity(fb, ACTIVITY_X, y, frame)


def draw_toggle_row(
    fb: Framebuffer,
    y: int,
    label: str,
    on: bool,
    *,
    focused: bool = False,
    rail_h: int | None = None,
) -> None:
    if focused:
        draw_focus_rail(fb, y, rail_h or ROW)
    draw_toggle(fb, TOGGLE_X, y, on)
    max_chars = max(1, (CONTENT_RIGHT - TOGGLE_LABEL_X) // CELL_W)
    text(fb, TOGGLE_LABEL_X, y, clip_text(label, max_chars))


def draw_subordinate_status(
    fb: Framebuffer,
    y: int,
    word: str,
    *,
    warn: bool | None = None,
) -> None:
    """Observed state under an editable setting. Not a focus target."""
    text_word = clip_text(word, 13)
    if warn is None:
        warn = text_word in WARN_STATES
    x = TOGGLE_LABEL_X
    if warn:
        fb.fill_rect(x, y + 2, 3, 3, True)
        x += 5
    text(fb, x, y, text_word)


def _status_right(activity: bool) -> int:
    return ACTIVITY_X if activity else CONTENT_RIGHT


def status_label_field_w(value: str, *, warn: bool | None = None) -> int:
    word = clip_text(value, 12)
    if warn is None:
        warn = word in WARN_STATES
    warn_gap = 5 if warn else 0
    word_w = len(word) * CELL_W
    return max(CELL_W, VALUE_RIGHT - warn_gap - word_w - CELL_W - LABEL_X)


def draw_status_row(
    fb: Framebuffer,
    y: int,
    label: str,
    value: str,
    *,
    focused: bool = False,
    warn: bool | None = None,
    activity: bool = False,
    now: float = 0.0,
    label_offset: int = 0,
) -> None:
    if focused:
        draw_focus_rail(fb, y)
    # Keep the activity/toggle gutter clear; vocab words up to 12 chars still fit.
    right = VALUE_RIGHT
    word = clip_text(value, 12)
    if warn is None:
        warn = word in WARN_STATES
    warn_gap = 5 if warn else 0
    word_w = len(word) * CELL_W
    field_w = status_label_field_w(value, warn=warn)
    draw_name_field(fb, LABEL_X, y, label, field_w, offset=label_offset)
    if warn:
        fb.fill_rect(right - word_w - warn_gap, y + 2, 3, 3, True)
    text_right(fb, right, y, word)
    maybe_activity(fb, y, now, activity)


def draw_named_status_row(
    fb: Framebuffer,
    y: int,
    kind: str,
    name: str,
    status: str,
    *,
    focused: bool = False,
    warn: bool | None = None,
    activity: bool = False,
    now: float = 0.0,
) -> None:
    """Kind left, name middle, status right. Used for NET LIGHT-CONTROL OK."""
    if focused:
        draw_focus_rail(fb, y)
    right = _status_right(activity)
    kind_text = clip_text(kind, 4)
    word = clip_text(status, 12)
    if warn is None:
        warn = word in WARN_STATES
    warn_gap = 5 if warn else 0
    word_w = len(word) * CELL_W
    text(fb, LABEL_X, y, kind_text)
    text_right(fb, right, y, word)
    if warn:
        fb.fill_rect(right - word_w - warn_gap, y + 2, 3, 3, True)
    name_x = LABEL_X + (len(kind_text) + 1) * CELL_W
    name_right = right - word_w - warn_gap - CELL_W
    max_name = max(0, (name_right - name_x) // CELL_W)
    if name and max_name:
        text(fb, name_x, y, clip_text(name, max_name))
    maybe_activity(fb, y, now, activity)


def draw_action_row(
    fb: Framebuffer,
    y: int,
    label: str,
    *,
    focused: bool = False,
    x: int | None = None,
) -> None:
    if focused:
        draw_focus_rail(fb, y)
    origin = LABEL_X if x is None else x
    max_chars = max(1, (CONTENT_RIGHT - origin) // CELL_W)
    text(fb, origin, y, clip_text(label, max_chars))


def draw_text_row(
    fb: Framebuffer,
    y: int,
    line: str,
    *,
    focused: bool = False,
    offset: int = 0,
    field_right: int = CONTENT_RIGHT,
) -> None:
    if focused:
        draw_focus_rail(fb, y)
    draw_name_field(fb, LABEL_X, y, line, field_right - LABEL_X, offset=offset)


def draw_name_field(
    fb: Framebuffer,
    x: int,
    y: int,
    value: str,
    field_w: int,
    *,
    offset: int = 0,
) -> None:
    """Human-readable name inside a clipped viewport. Status/prefix stay outside."""
    if field_w <= 0 or not value:
        return
    width = len(value) * CELL_W
    if width <= field_w and offset <= 0:
        text(fb, x, y, value)
        return
    off = max(0, int(offset))
    text_clipped(fb, x - off, y, value, x, x + field_w)


def draw_prefixed_name(
    fb: Framebuffer,
    y: int,
    prefix: str,
    name: str,
    *,
    focused: bool = False,
    offset: int = 0,
    field_right: int = CONTENT_RIGHT,
) -> None:
    if focused:
        draw_focus_rail(fb, y)
    text(fb, LABEL_X, y, prefix)
    name_x = LABEL_X + len(prefix) * CELL_W
    draw_name_field(fb, name_x, y, name, field_right - name_x, offset=offset)
