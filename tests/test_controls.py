from light_console.display.components import draw_status_row
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import ROW
from light_console.display.wordmark import MASTER_Y
from light_console.display.renderer import Renderer
from light_console.hardware.events import EncoderEvent, E1, E2, E3
from light_console.state import AppState, ScreenId, demo_live_state

from tests.conftest import make_controller


def test_e1_master_dimmer():
    c = make_controller(master_dimmer=80)
    c.inject_cooked(EncoderEvent(E1, -10))
    assert c.state.master_dimmer == 70
    c.inject_cooked(EncoderEvent(E1, 50))
    assert c.state.master_dimmer == 100
    c.inject_cooked(EncoderEvent(E1, -200))
    assert c.state.master_dimmer == 0


def test_e2_sat_on_play():
    c = make_controller()
    assert c.state.saturation == 100
    c.inject_cooked(EncoderEvent(E2, -10))
    assert c.state.saturation == 90
    c.inject_cooked(EncoderEvent(E2, 200))
    assert c.state.saturation == 200
    c.inject_cooked(EncoderEvent(E2, 10))
    assert c.state.saturation == 200
    c.inject_cooked(EncoderEvent(E2, -300))
    assert c.state.saturation == 0


def test_e3_hue_on_play():
    c = make_controller()
    assert c.state.hue_shift == 0
    c.inject_cooked(EncoderEvent(E3, 24))
    assert c.state.hue_shift == 24
    c.inject_cooked(EncoderEvent(E3, -39))
    assert c.state.hue_shift == -15
    c.inject_cooked(EncoderEvent(E3, -180))
    assert c.state.hue_shift == 165


def test_menu_e1_navigates_menu_not_live_controls():
    c = make_controller(scene_index=0, current_scene="WASH")
    c.state.screen = ScreenId.MENU
    c.state.menu_index = 0
    c.inject_cooked(EncoderEvent(E1, 2))
    assert c.state.menu_index == 2
    assert c.state.current_scene == "WASH"
    assert c.state.scene_index == 0
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.menu_index == 3
    c.inject_cooked(EncoderEvent(E3, 1))
    assert c.state.menu_index == 3
    assert c.state.current_scene == "WASH"


def test_default_master_is_100_percent():
    state = AppState()
    assert state.master_dimmer == 100
    assert state.master == 100
    assert int(state.master * 255 / 100) == 255
    live = demo_live_state()
    assert live.master == 100
    c = make_controller()
    assert c.state.master == 100
    c.state.clamp_indices()
    assert c.state.master == 100
    r = Renderer()
    fb = r.render(c.state)
    expected = Framebuffer()
    draw_status_row(expected, MASTER_Y, "MASTER", "100%", warn=False)
    for dy in range(ROW):
        for x in range(fb.width):
            assert fb.get(x, MASTER_Y + dy) == expected.get(x, MASTER_Y + dy)
    c.inject_cooked(EncoderEvent(E1, -25))
    assert c.state.master == 75
    c.inject_cooked(EncoderEvent(E1, 25))
    assert c.state.master == 100
    c.inject_cooked(EncoderEvent(E1, 40))
    assert c.state.master == 100
    c.inject_cooked(EncoderEvent(E1, -200))
    assert c.state.master == 0
    c.inject_cooked(EncoderEvent(E1, 100))
    assert c.state.master == 100
