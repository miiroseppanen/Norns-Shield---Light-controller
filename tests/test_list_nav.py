"""Finite menu/list navigation clamps. Circular parameters stay circular."""

from __future__ import annotations

from light_console.controls.encoders import clamp_index
from light_console.display.layout import CONTENT_H, CONTENT_ROWS
from light_console.display.viewport import ListViewport, scrollbar_metrics
from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K1, K2, K3
from light_console.output.fixtures import PatchedFixture
from light_console.output.pages import build_output_pages_from_state
from light_console.state import ScreenId
from light_console.ui.menu import MENU_ITEMS
from light_console.ui.pages import (
    SYSTEM_QLC_TOGGLE,
    SYSTEM_RESTART,
    SYSTEM_ROW_COUNT,
    SYSTEM_VERSION,
    system_visible_count,
)

from tests.conftest import make_controller


def _assert_window(focus: int, offset: int, total: int, visible: int) -> None:
    if total <= 0:
        assert focus == 0
        assert offset == 0
        return
    assert 0 <= focus < total
    max_off = max(0, total - visible)
    assert 0 <= offset <= max_off
    assert offset <= focus < offset + visible
    end = min(total, offset + visible)
    assert end <= total
    if focus == total - 1 and total >= visible:
        assert offset == max_off


def _scrollbar(total: int, visible: int, offset: int):
    return scrollbar_metrics(total, visible, offset, CONTENT_H)


def test_menu_clamps_at_first_and_last():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.MENU
    count = len(MENU_ITEMS)
    assert count == 6
    assert c.state.menu_index == 0
    c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.menu_index == 0
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.menu_index == 1
    c.inject_cooked(EncoderEvent(E1, 20))
    assert c.state.menu_index == count - 1
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.menu_index == count - 1
    c.inject_cooked(EncoderEvent(E1, -20))
    assert c.state.menu_index == 0
    _assert_window(c.state.menu_index, c.state.scroll_offset, count, CONTENT_ROWS)
    assert _scrollbar(count, CONTENT_ROWS, c.state.scroll_offset) is None


def test_system_clamps_at_restart():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.state.system_index == SYSTEM_QLC_TOGGLE
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.system_index == 1
    c.inject_cooked(EncoderEvent(E2, 20))
    assert c.state.system_index == SYSTEM_RESTART
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.system_index == SYSTEM_RESTART
    c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.system_index == SYSTEM_VERSION
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.VERSION
    assert c.power.request_count == 0
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.SYSTEM
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.system_index == SYSTEM_RESTART
    _assert_window(
        c.state.system_index,
        c.state.scroll_offset,
        SYSTEM_ROW_COUNT,
        system_visible_count(c.state),
    )
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.RESTART_CONFIRM
    assert c.power.restart_count == 0


def test_scenes_scroll_clamps_and_scrollbar_tracks_viewport():
    names = tuple(f"S{i:02d}" for i in range(20))
    c = make_controller(scenes=names)
    c.state.screen = ScreenId.SCENES
    c.state.scene_index = 0
    c.state.scroll_offset = 0
    c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.scene_index == 0
    assert c.state.scroll_offset == 0
    top = _scrollbar(20, CONTENT_ROWS, c.state.scroll_offset)
    assert top is not None
    assert top[0] == 0
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.scene_index == 1
    assert c.state.scroll_offset == 0
    for _ in range(CONTENT_ROWS - 2):
        c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.scene_index == CONTENT_ROWS - 1
    assert c.state.scroll_offset == 0
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.scene_index == CONTENT_ROWS
    assert c.state.scroll_offset == 1
    c.inject_cooked(EncoderEvent(E1, 20))
    assert c.state.scene_index == 19
    _assert_window(c.state.scene_index, c.state.scroll_offset, 20, CONTENT_ROWS)
    assert c.state.scroll_offset == 20 - CONTENT_ROWS
    bot = _scrollbar(20, CONTENT_ROWS, c.state.scroll_offset)
    assert bot is not None
    assert bot[0] + bot[1] == CONTENT_H
    window = ListViewport(20, c.state.scene_index, c.state.scroll_offset, CONTENT_ROWS)
    window.reveal()
    assert list(window.window())[-1] == 19
    assert len(list(window.window())) == CONTENT_ROWS
    c.inject_cooked(EncoderEvent(E1, 5))
    assert c.state.scene_index == 19
    assert c.state.scroll_offset == 20 - CONTENT_ROWS
    c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.scene_index == 18
    assert c.state.scroll_offset == 20 - CONTENT_ROWS
    while c.state.scene_index > c.state.scroll_offset:
        c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.scene_index == c.state.scroll_offset
    c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.scene_index == c.state.scroll_offset
    assert c.state.scene_index == 20 - CONTENT_ROWS - 1
    c.inject_cooked(EncoderEvent(E1, -20))
    assert c.state.scene_index == 0
    assert c.state.scroll_offset == 0
    top2 = _scrollbar(20, CONTENT_ROWS, c.state.scroll_offset)
    assert top2 is not None
    assert top2[0] == 0


def test_chasers_clamps_like_scenes():
    names = tuple(f"C{i:02d}" for i in range(12))
    c = make_controller(chasers=names)
    c.state.screen = ScreenId.CHASERS
    c.inject_cooked(EncoderEvent(E1, -3))
    assert c.state.chaser_index == 0
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.chaser_index == 1
    c.inject_cooked(EncoderEvent(E1, 40))
    assert c.state.chaser_index == 11
    _assert_window(c.state.chaser_index, c.state.scroll_offset, 12, CONTENT_ROWS)
    c.inject_cooked(EncoderEvent(E1, -40))
    assert c.state.chaser_index == 0
    assert c.state.scroll_offset == 0


def test_params_list_clamps_values_unchanged():
    c = make_controller(master_dimmer=40)
    c.state.screen = ScreenId.PARAMS
    c.state.param_index = 0
    c.params.index = 0
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.params.selected.id == "master"
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.params.selected.id == "sat"
    last = len(c.params) - 1
    c.inject_cooked(EncoderEvent(E2, 20))
    assert c.params.index == last
    assert c.state.param_index == last
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.params.index == last
    c.inject_cooked(EncoderEvent(E2, -20))
    assert c.params.index == 0
    _assert_window(c.state.param_index, c.state.scroll_offset, len(c.params), CONTENT_ROWS)
    assert c.state.master == 40


def test_output_pages_and_device_list_clamp():
    fixtures = tuple(PatchedFixture(i, f"FIX {i:02d}", 0, i * 8, 4) for i in range(12))
    c = make_controller(fixtures=fixtures)
    c.state.screen = ScreenId.OUTPUT
    pages = build_output_pages_from_state(c.state)
    assert pages
    last_page = len(pages) - 1
    c.state.output_page = 0
    c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.output_page == 0
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.output_page == 1
    c.state.output_page = last_page
    c.inject_cooked(EncoderEvent(E1, 8))
    assert c.state.output_page == last_page

    devices = next(i for i, page in enumerate(pages) if page.kind == "devices")
    c.state.output_page = devices
    c.state.output_focus = 0
    c.state.scroll_offset = 0
    visible = max(1, CONTENT_ROWS // 2)
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.state.output_focus == 0
    assert c.state.scroll_offset == 0
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.output_focus == 1
    c.inject_cooked(EncoderEvent(E2, 20))
    assert c.state.output_focus == 11
    _assert_window(c.state.output_focus, c.state.scroll_offset, 12, visible)
    assert c.state.scroll_offset == 12 - visible
    bot = _scrollbar(12, visible, c.state.scroll_offset)
    assert bot is not None
    assert bot[0] + bot[1] == CONTENT_H
    c.inject_cooked(EncoderEvent(E2, -20))
    assert c.state.output_focus == 0
    assert c.state.scroll_offset == 0


def test_one_item_and_short_lists_stay_stable():
    c = make_controller(scenes=("ONLY",), chasers=("ONE",))
    c.state.screen = ScreenId.SCENES
    c.inject_cooked(EncoderEvent(E1, 5))
    assert c.state.scene_index == 0
    assert c.state.scroll_offset == 0
    c.inject_cooked(EncoderEvent(E1, -5))
    assert c.state.scene_index == 0
    _assert_window(0, c.state.scroll_offset, 1, CONTENT_ROWS)
    assert _scrollbar(1, CONTENT_ROWS, 0) is None
    c.state.screen = ScreenId.CHASERS
    c.inject_cooked(EncoderEvent(E1, 3))
    assert c.state.chaser_index == 0
    c = make_controller()
    c.state.screen = ScreenId.SCENES
    assert len(c.state.scenes) < CONTENT_ROWS
    c.inject_cooked(EncoderEvent(E1, 8))
    assert c.state.scene_index == len(c.state.scenes) - 1
    assert c.state.scroll_offset == 0
    _assert_window(
        c.state.scene_index,
        c.state.scroll_offset,
        len(c.state.scenes),
        CONTENT_ROWS,
    )


def test_shows_list_clamps():
    c = make_controller()
    c.state.screen = ScreenId.SHOWS
    c.state.show_files = tuple(f"SHOW {i:02d}" for i in range(10))
    c.state.show_ids = c.state.show_files
    c.state.show_index = 4
    c.inject_cooked(EncoderEvent(E1, 20))
    assert c.state.show_index == 9
    c.inject_cooked(EncoderEvent(E2, -20))
    assert c.state.show_index == 0
    _assert_window(c.state.show_index, c.state.scroll_offset, 10, CONTENT_ROWS)


def test_play_master_sat_clamp_and_hue_wraps():
    c = make_controller()
    c.inject_cooked(EncoderEvent(E1, 50))
    assert c.state.master == 100
    c.inject_cooked(EncoderEvent(E1, -10))
    assert c.state.master == 90
    c.inject_cooked(EncoderEvent(E2, 5))
    assert c.state.saturation == 105
    c.inject_cooked(EncoderEvent(E2, 200))
    assert c.state.saturation == 200
    c.inject_cooked(EncoderEvent(E3, 181))
    assert c.state.hue_shift == -179
    c.inject_cooked(EncoderEvent(E3, -2))
    assert c.state.hue_shift == 179


def test_universe_e2_still_clamps():
    c = make_controller()
    c.state.screen = ScreenId.OUTPUT
    c.state.qlc_universes = (1, 2, 3, 4, 5, 6)
    c.state.output_universe = 1
    pages = build_output_pages_from_state(c.state)
    uni = next(i for i, page in enumerate(pages) if page.kind == "universe")
    c.state.output_page = uni
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.state.output_universe == 1
    c.inject_cooked(EncoderEvent(E2, 20))
    assert c.state.output_universe == 4
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.output_universe == 4


def test_clamp_index_matches_specified_burst_examples():
    assert clamp_index(4, 20, 10) == 9
    assert clamp_index(4, -20, 10) == 0
