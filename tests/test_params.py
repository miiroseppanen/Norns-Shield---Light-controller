from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K3
from light_console.state import AppState, ScreenId
from light_console.ui.params import (
    ActionParameter,
    NumberParameter,
    OptionParameter,
    ToggleParameter,
    bind_console_params,
)

from tests.conftest import make_controller


def test_number_set_and_wrap_hue_set():
    box = {"v": 40}
    p = NumberParameter("n", "N", lambda: box["v"], lambda v: box.__setitem__("v", v), 0, 200)
    p.set(100)
    assert p.get() == 100
    p.set(999)
    assert p.get() == 200
    from light_console.ui.params import WrapNumberParameter

    hue = {"v": 90}
    w = WrapNumberParameter("h", "H", lambda: hue["v"], lambda v: hue.__setitem__("v", v), -180, 180)
    w.set(0)
    assert w.get() == 0
    w.set(181)
    assert w.get() == -179
    box = {"v": 50}
    p = NumberParameter("n", "N", lambda: box["v"], lambda v: box.__setitem__("v", v), 0, 100)
    p.delta(80)
    assert p.get() == 100
    p.delta(-1000)
    assert p.get() == 0
    assert p.formatted() == "0"


def test_option_clamps():
    box = {"v": "A"}
    p = OptionParameter("o", "O", lambda: box["v"], lambda v: box.__setitem__("v", v), ("A", "B", "C"))
    p.delta(1)
    assert p.get() == "B"
    p.delta(1)
    assert p.get() == "C"
    p.delta(1)
    assert p.get() == "C"
    p.delta(20)
    assert p.get() == "C"
    p.delta(-2)
    assert p.get() == "A"
    p.delta(-1)
    assert p.get() == "A"


def test_toggle_delta_and_trigger():
    box = {"v": False}
    p = ToggleParameter("t", "T", lambda: box["v"], lambda v: box.__setitem__("v", v))
    assert p.formatted() == "Off"
    p.delta(1)
    assert p.get() is True
    p.delta(-1)
    assert p.get() is False
    p.trigger()
    assert p.get() is True


def test_action_parameter():
    hits = []
    p = ActionParameter("a", "Go", lambda: hits.append(1))
    p.delta(3)
    assert hits == []
    p.trigger()
    assert hits == [1]


def test_params_select_and_change():
    state = AppState(master_dimmer=80, bpm=124, blackout=False, current_scene="WASH")
    params = bind_console_params(state)
    assert params.selected.id == "master"
    params.select_delta(1)
    assert params.selected.id == "sat"
    params.select_delta(2)
    assert params.selected.id == "speed"
    params.selected.delta(6)
    assert state.speed == 130
    params.select_delta(1)
    params.selected.trigger()
    assert state.blackout is True


def test_params_screen_e2_e3():
    c = make_controller(master_dimmer=40)
    c.state.screen = ScreenId.PARAMS
    assert c.state.screen == ScreenId.PARAMS
    c.state.param_index = 0
    c.params.index = 0
    c.inject_cooked(EncoderEvent(E3, 5))
    assert c.state.master == 45
    c.inject_cooked(EncoderEvent(E1, 2))
    assert c.params.selected.id == "hue"
    c.inject_cooked(EncoderEvent(E2, 2))
    assert c.params.selected.id == "blackout"
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.blackout is True


def test_qlc_offline_params_still_work():
    c = make_controller(master_dimmer=80)
    c.qlc.simulate_link(False)
    c.tick(now=1.0)
    c.state.screen = ScreenId.PARAMS
    c.state.param_index = 0
    c.params.index = 0
    c.inject_cooked(EncoderEvent(E3, 1))
    assert c.state.master == 81
    assert c.state.screen == ScreenId.PARAMS
