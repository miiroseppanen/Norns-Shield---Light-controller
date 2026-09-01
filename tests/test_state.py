from light_console.controls.buttons import ButtonTracker
from light_console.hardware.events import ButtonEvent
from light_console.state import ScreenId

from tests.conftest import make_controller


def test_short_press_blackout_toggle():
    tracker = ButtonTracker(long_press_s=0.6)
    assert tracker.on_hardware_press(1, 0.0) == []
    evs = tracker.on_hardware_release(1, 0.1)
    assert [e.action for e in evs] == ["press", "release"]


def test_long_press_suppresses_short():
    tracker = ButtonTracker(long_press_s=0.5)
    tracker.on_hardware_press(3, 0.0)
    assert tracker.poll(0.4) == []
    long = tracker.poll(0.51)
    assert long == [ButtonEvent(3, "long_press")]
    rel = tracker.on_hardware_release(3, 0.6)
    assert [e.action for e in rel] == ["release"]


def test_k1_short_toggles_blackout_via_controller():
    c = make_controller()
    c.inject_cooked(ButtonEvent(1, "press"))
    assert c.state.blackout is True
    c.inject_cooked(ButtonEvent(1, "press"))
    assert c.state.blackout is False


def test_k1_long_all_off():
    c = make_controller(active_function="SININEN")
    c.inject_cooked(ButtonEvent(1, "long_press"))
    assert c.state.blackout is True
    assert c.state.active_function is None


def test_k2_go_and_k2_long_home():
    c = make_controller(selected_index=1)
    c.inject_cooked(ButtonEvent(2, "press"))
    assert c.state.active_function == c.state.functions[1]
    c.state.screen = ScreenId.WIZ
    c.inject_cooked(ButtonEvent(2, "long_press"))
    assert c.state.screen == ScreenId.HOME


def test_k3_special_and_menu():
    c = make_controller()
    c.inject_cooked(ButtonEvent(3, "press"))
    assert c.state.special_armed is True
    c.inject_cooked(ButtonEvent(3, "long_press"))
    assert c.state.screen == ScreenId.MENU


def test_hardware_hold_becomes_long_press():
    c = make_controller()
    c.handle_event(ButtonEvent(1, "press"), now=10.0)
    c.tick(now=10.1)
    assert c.state.blackout is False
    c.tick(now=10.7)
    assert c.state.blackout is True
    assert c.state.active_function is None
