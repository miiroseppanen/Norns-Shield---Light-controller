"""Navigation encoder fold/scale. Cooked inject stays 1:1; hardware bursts use tick()."""

from __future__ import annotations

from light_console.controls.encoders import (
    bound_index,
    clamp_index,
    fold_encoder_stream,
    is_nav_encoder,
    nav_steps,
)
from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K1
from light_console.output.fixtures import PatchedFixture
from light_console.output.pages import build_output_pages_from_state
from light_console.state import ScreenId
from light_console.display.layout import CONTENT_ROWS
from light_console.display.viewport import ListViewport

from tests.conftest import make_controller


def test_clamp_index_stops_at_ends_and_never_modulos_delta():
    assert clamp_index(0, -1, 5) == 0
    assert clamp_index(4, 1, 5) == 4
    assert clamp_index(0, 1, 5) == 1
    assert clamp_index(3, 1, 5) == 4
    assert clamp_index(4, 20, 10) == 9
    assert clamp_index(4, -20, 10) == 0
    assert clamp_index(0, 1, 1) == 0
    assert clamp_index(0, -3, 1) == 0
    assert clamp_index(7, 1, 0) == 0
    assert bound_index(-4, 5) == 0
    assert bound_index(99, 5) == 4
    assert bound_index(0, 0) == 0


def _burst(encoder: int, n: int, step: int = 1) -> tuple[EncoderEvent, ...]:
    return tuple(EncoderEvent(encoder, step) for _ in range(n))


def test_nav_steps_keeps_isolated_detents_and_halves_bursts():
    assert nav_steps(0) == 0
    assert nav_steps(1) == 1
    assert nav_steps(-1) == -1
    assert nav_steps(2) == 1
    assert nav_steps(3) == 2
    assert nav_steps(10) == 5
    assert nav_steps(-10) == -5
    assert nav_steps(11) == 6


def test_fold_nets_one_poll_and_drops_zero():
    folded = fold_encoder_stream(
        [
            ButtonEvent(K1, "press"),
            EncoderEvent(E2, 1),
            EncoderEvent(E2, 1),
            EncoderEvent(E2, -1),
            ButtonEvent(K1, "release"),
            EncoderEvent(E1, 1),
        ]
    )
    kinds = [(type(ev).__name__, getattr(ev, "encoder", None), getattr(ev, "delta", None), getattr(ev, "action", None)) for ev in folded]
    assert kinds == [
        ("ButtonEvent", None, None, "press"),
        ("EncoderEvent", E2, 1, None),
        ("ButtonEvent", None, None, "release"),
        ("EncoderEvent", E1, 1, None),
    ]
    assert fold_encoder_stream([EncoderEvent(E2, 1), EncoderEvent(E2, -1)]) == []


def test_slow_and_normal_menu_detents_stay_precise():
    c = make_controller()
    c.state.screen = ScreenId.MENU
    c.state.menu_index = 0
    c.hardware.push(EncoderEvent(E1, 1))
    c.tick(now=1.0)
    assert c.state.menu_index == 1
    c.hardware.push(EncoderEvent(E1, 1))
    c.tick(now=1.2)
    assert c.state.menu_index == 2
    c.inject_cooked(EncoderEvent(E1, 2))
    assert c.state.menu_index == 3  # 4 items: 2+2 lands on last


def test_rapid_menu_rotation_is_about_half_as_aggressive():
    c = make_controller(scenes=tuple(f"S{i:02d}" for i in range(20)))
    c.state.screen = ScreenId.SCENES
    c.state.scene_index = 0
    c.hardware.push(*_burst(E1, 10))
    c.tick(now=2.0)
    assert c.state.scene_index == 5
    c.tick(now=2.1)
    assert c.state.scene_index == 5


def test_stop_leaves_no_queued_movement_and_reverse_is_immediate():
    names = tuple(f"S{i:02d}" for i in range(20))
    c = make_controller(scenes=names)
    c.state.screen = ScreenId.SCENES
    c.state.scene_index = 0
    c.hardware.push(*_burst(E1, 10))
    c.tick(now=3.0)
    assert c.state.scene_index == 5
    c.tick(now=3.05)
    assert c.state.scene_index == 5
    c.hardware.push(EncoderEvent(E1, -1))
    c.tick(now=3.1)
    assert c.state.scene_index == 4


def test_in_batch_direction_reverse_nets_before_scale():
    c = make_controller(scenes=tuple(f"S{i:02d}" for i in range(20)))
    c.state.screen = ScreenId.SCENES
    c.hardware.push(*_burst(E1, 10), *_burst(E1, 10, -1))
    c.tick(now=4.0)
    assert c.state.scene_index == 0


def test_parameter_controls_are_not_halved():
    c = make_controller(master_dimmer=80)
    c.state.screen = ScreenId.PLAY
    c.hardware.push(*_burst(E1, 10))
    c.tick(now=5.0)
    assert c.state.master_dimmer == 90
    c.state.screen = ScreenId.PARAMS
    before = c.state.master_dimmer
    c.params.sync_index_to_state(c.state)
    c.state.param_index = 0
    c.hardware.push(*_burst(E3, 10))
    c.tick(now=5.2)
    assert c.state.master_dimmer == min(100, before + 10)


def test_play_sat_is_not_halved():
    c = make_controller()
    c.state.screen = ScreenId.PLAY
    c.hardware.push(*_burst(E2, 10))
    c.tick(now=6.0)
    assert c.state.saturation == 110


def test_is_nav_encoder_excludes_play_live_controls_and_param_value():
    assert is_nav_encoder(ScreenId.PLAY, E1) is False
    assert is_nav_encoder(ScreenId.PLAY, E2) is False
    assert is_nav_encoder(ScreenId.PLAY, E3) is False
    assert is_nav_encoder(ScreenId.PARAMS, E3) is False
    assert is_nav_encoder(ScreenId.MENU, E1) is True
    assert is_nav_encoder(ScreenId.SYSTEM, E2) is True
    assert is_nav_encoder(ScreenId.OUTPUT, E2) is True
    assert is_nav_encoder(ScreenId.PARAMS, E2) is True


def test_fast_output_nav_updates_focus_and_scrollbar_together():
    fixtures = tuple(PatchedFixture(i, f"FIX {i:02d}", 0, i * 8, 4) for i in range(12))
    c = make_controller(fixtures=fixtures)
    c.state.screen = ScreenId.OUTPUT
    pages = build_output_pages_from_state(c.state)
    devices = next(i for i, page in enumerate(pages) if page.kind == "devices")
    c.state.output_page = devices
    c.state.output_focus = 0
    c.state.scroll_offset = 0
    c.hardware.push(*_burst(E2, 10))
    c.tick(now=7.0)
    visible = max(1, CONTENT_ROWS // 2)
    assert c.state.output_focus == 5
    expect = ListViewport(12, 5, 0, visible)
    expect.reveal()
    assert c.state.scroll_offset == expect.offset
    assert c.state.output_focus >= c.state.scroll_offset
    assert c.state.output_focus < c.state.scroll_offset + visible
    c.tick(now=7.1)
    assert c.state.output_focus == 5
    assert c.state.scroll_offset == expect.offset
    c.hardware.push(*_burst(E2, 10, -1))
    c.tick(now=7.2)
    assert c.state.output_focus == 0
    assert c.state.scroll_offset == 0
