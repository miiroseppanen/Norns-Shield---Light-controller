from light_console.hardware.events import EncoderEvent
from light_console.state import ScreenId

from tests.conftest import make_controller


def test_e1_master_dimmer():
    c = make_controller(master_dimmer=80)
    c.inject_cooked(EncoderEvent(1, -10))
    assert c.state.master_dimmer == 70
    c.inject_cooked(EncoderEvent(1, 50))
    assert c.state.master_dimmer == 100
    c.inject_cooked(EncoderEvent(1, -200))
    assert c.state.master_dimmer == 0


def test_e2_select_wraps():
    c = make_controller(selected_index=0)
    names = list(c.state.functions)
    c.inject_cooked(EncoderEvent(2, 1))
    assert c.state.selected_function == names[1]
    c.inject_cooked(EncoderEvent(2, -2))
    assert c.state.selected_function == names[-1]


def test_e3_speed_clamped():
    c = make_controller(bpm=124)
    c.inject_cooked(EncoderEvent(3, 5))
    assert c.state.bpm == 129
    c.inject_cooked(EncoderEvent(3, 1000))
    assert c.state.bpm == 240
    c.inject_cooked(EncoderEvent(3, -1000))
    assert c.state.bpm == 20


def test_menu_e2_navigates_menu_not_scenes():
    c = make_controller(selected_index=0)
    c.state.screen = ScreenId.MENU
    c.state.menu_index = 0
    c.inject_cooked(EncoderEvent(2, 2))
    assert c.state.menu_index == 2
    assert c.state.selected_index == 0
