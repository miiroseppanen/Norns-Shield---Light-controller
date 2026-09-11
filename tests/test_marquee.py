"""Deterministic clipped-field marquee. No wall-clock sleeps."""

from __future__ import annotations

from light_console.display.activity import activity_frame
from light_console.display.components import (
    draw_prefixed_name,
    draw_scrollbar,
    draw_status_row,
    region_on_count,
)
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import (
    ACTIVITY_W,
    ACTIVITY_X,
    CONTENT_H,
    CONTENT_RIGHT,
    CONTENT_Y,
    FOCUS_W,
    LABEL_X,
    ROW,
    SCROLL_X,
)
from light_console.display.marquee import (
    END_PAUSE_S,
    PX_PER_S,
    START_PAUSE_S,
    field_offset,
    marquee_offset_px,
    max_offset_px,
)
from light_console.display.renderer import Renderer
from light_console.display.screens import draw_list
from light_console.display.widgets import CELL_W, text_clipped
from light_console.hardware.events import EncoderEvent, E1
from light_console.output.fixtures import PatchedFixture
from light_console.output.pages import build_output_pages_from_state
from light_console.state import AppState, ScreenId
from light_console.ui.vocab import ACTIVE

from tests.conftest import make_controller

LONG = "60 W BATTERY LED PAR CAN EXTRA"


def _region(fb: Framebuffer, x: int, y: int, w: int, h: int) -> bytes:
    return bytes(fb.get(x + dx, y + dy) for dy in range(h) for dx in range(w))


def test_fitting_text_never_scrolls():
    assert max_offset_px("WASH", 40) == 0
    assert marquee_offset_px(10.0, "WASH", 40) == 0
    state = AppState()
    assert field_offset(state, "a", 5.0, "WASH", 40) == 0
    assert state.marquee_key == ""


def test_overflow_starts_at_zero_and_waits_for_delay():
    field_w = 24
    travel = max_offset_px(LONG, field_w)
    assert travel > 0
    assert marquee_offset_px(0.0, LONG, field_w) == 0
    assert marquee_offset_px(START_PAUSE_S - 0.01, LONG, field_w) == 0
    assert marquee_offset_px(START_PAUSE_S, LONG, field_w) == 0
    moved = marquee_offset_px(START_PAUSE_S + 0.5, LONG, field_w)
    assert 0 < moved < travel
    assert moved == min(travel, int(0.5 * PX_PER_S))


def test_max_offset_reveals_complete_suffix_then_pauses_and_resets():
    field_w = 24
    travel = max_offset_px(LONG, field_w)
    scroll_s = travel / PX_PER_S
    assert marquee_offset_px(START_PAUSE_S + scroll_s, LONG, field_w) == travel
    assert marquee_offset_px(START_PAUSE_S + scroll_s + END_PAUSE_S - 0.01, LONG, field_w) == travel
    period = START_PAUSE_S + scroll_s + END_PAUSE_S
    assert marquee_offset_px(period, LONG, field_w) == 0
    repeated = marquee_offset_px(period + START_PAUSE_S + 1.0, LONG, field_w)
    assert 0 < repeated < travel


def test_focus_and_page_change_reset_offset():
    field_w = 24
    state = AppState(ui_now=0.0)
    assert field_offset(state, "row:0", 0.0, LONG, field_w) == 0
    later = START_PAUSE_S + 0.8
    assert field_offset(state, "row:0", later, LONG, field_w) > 0
    assert field_offset(state, "row:1", later, LONG, field_w) == 0
    assert state.marquee_key == "row:1"
    state.reset_list_window()
    assert state.marquee_key == ""
    assert state.marquee_t0 == 0.0


def test_rapid_navigation_does_not_create_timer_backlog():
    state = AppState()
    field_w = 24
    for i in range(40):
        field_offset(state, f"row:{i}", 8.0 + i * 0.01, LONG, field_w)
    assert state.marquee_key == "row:39"
    assert field_offset(state, "row:39", 8.0 + 39 * 0.01, LONG, field_w) == 0


def test_non_focused_overflow_stays_static():
    labels = ["SHORT", LONG, "OTHER"]
    unfocused_a = Framebuffer()
    unfocused_b = Framebuffer()
    still = AppState(ui_now=0.0)
    draw_list(unfocused_a, labels, 0, state=still, list_id="t")
    still.ui_now = START_PAUSE_S + 1.0
    draw_list(unfocused_b, labels, 0, state=still, list_id="t")
    y = CONTENT_Y + ROW
    assert _region(unfocused_a, LABEL_X, y, CONTENT_RIGHT - LABEL_X, ROW) == _region(
        unfocused_b, LABEL_X, y, CONTENT_RIGHT - LABEL_X, ROW
    )
    moving = AppState(ui_now=0.0)
    paused = Framebuffer()
    draw_list(paused, labels, 1, state=moving, list_id="t")
    moving.ui_now = START_PAUSE_S + 1.0
    live = Framebuffer()
    draw_list(live, labels, 1, state=moving, list_id="t")
    assert _region(live, LABEL_X, CONTENT_Y + ROW, 36, ROW) != _region(
        paused, LABEL_X, CONTENT_Y + ROW, 36, ROW
    )


def test_clipping_keeps_prefix_status_activity_scrollbar_fixed():
    prefix = "025 "
    name = LONG
    field_w = 48
    y = CONTENT_Y
    start = Framebuffer()
    draw_prefixed_name(start, y, prefix, name, focused=True, offset=0, field_right=LABEL_X + 24 + field_w)
    moved = Framebuffer()
    draw_prefixed_name(
        moved,
        y,
        prefix,
        name,
        focused=True,
        offset=18,
        field_right=LABEL_X + 24 + field_w,
    )
    prefix_w = len(prefix) * CELL_W
    assert _region(start, LABEL_X, y, prefix_w, ROW) == _region(moved, LABEL_X, y, prefix_w, ROW)
    assert region_on_count(start, 0, y, FOCUS_W, ROW) == region_on_count(moved, 0, y, FOCUS_W, ROW)

    status_a = Framebuffer()
    status_b = Framebuffer()
    draw_status_row(status_a, y + ROW, "14 CH", ACTIVE, activity=True, now=0.0)
    draw_status_row(status_b, y + ROW, "14 CH", ACTIVE, activity=True, now=0.0, label_offset=20)
    # Structured status/value stay put; label here is short so offset is clipped away.
    right = ACTIVITY_X
    assert _region(status_a, right - 36, y + ROW, 36, ROW) == _region(
        status_b, right - 36, y + ROW, 36, ROW
    )
    assert _region(status_a, ACTIVITY_X, y + ROW, ACTIVITY_W, ROW) == _region(
        status_b, ACTIVITY_X, y + ROW, ACTIVITY_W, ROW
    )

    bar_a = Framebuffer()
    bar_b = Framebuffer()
    draw_scrollbar(bar_a, 12, 3, 2)
    draw_scrollbar(bar_b, 12, 3, 2)
    assert _region(bar_a, SCROLL_X, CONTENT_Y, 3, CONTENT_H) == _region(
        bar_b, SCROLL_X, CONTENT_Y, 3, CONTENT_H
    )


def test_clipping_prevents_drawing_outside_name_field():
    fb = Framebuffer()
    x = 20
    field_w = 30
    text_clipped(fb, x - 40, 16, LONG, x, x + field_w)
    for yy in range(16, 16 + ROW):
        for px in range(0, x):
            assert fb.get(px, yy) == 0
        for px in range(x + field_w, 128):
            assert fb.get(px, yy) == 0
    assert region_on_count(fb, x, 16, field_w, ROW) > 0


def test_device_row_marquees_only_the_name_field():
    fx = PatchedFixture(1, LONG, 0, 24, 14)
    c = make_controller(fixtures=(fx,), dmx_ready=True)
    c.state.screen = ScreenId.OUTPUT
    built = build_output_pages_from_state(c.state)
    c.state.output_page = next(i for i, page in enumerate(built) if page.kind == "devices")
    c.state.output_focus = 0
    c.state.ui_now = 0.0
    r = Renderer()
    start = r.render(c.state)
    start_prefix = _region(start, LABEL_X, CONTENT_Y, 4 * CELL_W, ROW)
    start_status = _region(start, ACTIVITY_X - 36, CONTENT_Y + ROW, 36, ROW)
    start_bar = _region(start, SCROLL_X, CONTENT_Y, 3, CONTENT_H)
    name_x = LABEL_X + 4 * CELL_W
    start_name = _region(start, name_x, CONTENT_Y, 36, ROW)
    c.state.ui_now = START_PAUSE_S + 1.0
    r.force_dirty()
    moved = r.render(c.state)
    assert _region(moved, LABEL_X, CONTENT_Y, 4 * CELL_W, ROW) == start_prefix
    assert _region(moved, ACTIVITY_X - 36, CONTENT_Y + ROW, 36, ROW) == start_status
    assert _region(moved, SCROLL_X, CONTENT_Y, 3, CONTENT_H) == start_bar
    assert _region(moved, name_x, CONTENT_Y, 36, ROW) != start_name


def test_activity_state_independent_of_marquee():
    assert activity_frame(0.0, True) == 0
    assert marquee_offset_px(0.0, LONG, 24) == 0
    assert activity_frame(START_PAUSE_S + 0.5, False) is None
    assert marquee_offset_px(START_PAUSE_S + 0.5, LONG, 24) > 0
    assert activity_frame(0.3, True) == 1
    assert marquee_offset_px(0.3, LONG, 24) == 0


def test_navigation_is_never_blocked_by_marquee():
    c = make_controller(scenes=tuple(f"SCENE {i} WITH A VERY LONG NAME" for i in range(8)))
    c.state.screen = ScreenId.SCENES
    c.state.ui_now = START_PAUSE_S + 1.0
    Renderer().render(c.state)
    c.hardware.push(EncoderEvent(E1, 1))
    c.tick(now=START_PAUSE_S + 1.01)
    assert c.state.scene_index == 1
    assert c.state.marquee_key in ("", "scenes:1")


def test_empty_state_has_no_marquee_or_scrollbar():
    c = make_controller(fixtures=(), dmx_ready=True, qlc_connected=True)
    c.state.screen = ScreenId.OUTPUT
    built = build_output_pages_from_state(c.state)
    c.state.output_page = next(i for i, page in enumerate(built) if page.kind == "devices")
    r = Renderer()
    fb = r.render(c.state)
    assert region_on_count(fb, SCROLL_X, CONTENT_Y, 3, CONTENT_H) == 0
    assert c.state.marquee_key == ""
