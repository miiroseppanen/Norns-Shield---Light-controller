"""Clipped-field marquee for overflowing focused names. Not an activity indicator."""

from __future__ import annotations

from light_console.display.font import CELL_W
from light_console.state import AppState

START_PAUSE_S = 1.2
END_PAUSE_S = 0.75
PX_PER_S = 16.0


def text_width_px(text: str) -> int:
    return len(text) * CELL_W


def max_offset_px(text: str, field_w: int) -> int:
    return max(0, text_width_px(text) - max(0, int(field_w)))


def marquee_offset_px(elapsed: float, text: str, field_w: int) -> int:
    """Pixel offset: start pause, scroll to full suffix, end pause, snap, repeat."""
    travel = max_offset_px(text, field_w)
    if travel <= 0 or elapsed <= 0:
        return 0
    scroll_s = travel / PX_PER_S
    period = START_PAUSE_S + scroll_s + END_PAUSE_S
    t = elapsed % period
    if t < START_PAUSE_S:
        return 0
    t -= START_PAUSE_S
    if t >= scroll_s:
        return travel
    return min(travel, int(t * PX_PER_S))


def bind_marquee(state: AppState, key: str, now: float) -> None:
    if state.marquee_key != key:
        state.marquee_key = key
        state.marquee_t0 = now


def clear_marquee(state: AppState) -> None:
    state.marquee_key = ""
    state.marquee_t0 = 0.0


def field_offset(state: AppState, key: str, now: float, text: str, field_w: int) -> int:
    """Offset for the single active marquee field. Resets when key changes."""
    if max_offset_px(text, field_w) <= 0:
        if state.marquee_key == key:
            state.marquee_key = ""
        return 0
    bind_marquee(state, key, now)
    return marquee_offset_px(now - state.marquee_t0, text, field_w)
