from light_console.controls.buttons import ButtonTracker
from light_console.hardware.events import ButtonEvent, K1, K2, K3
from light_console.state import ScreenId

from tests.conftest import make_controller


def test_short_press_tracker():
    tracker = ButtonTracker(long_press_s=0.6)
    assert tracker.on_hardware_press(K1, 0.0) == []
    evs = tracker.on_hardware_release(K1, 0.1)
    assert [e.action for e in evs] == ["press", "release"]


def test_long_press_suppresses_short():
    tracker = ButtonTracker(long_press_s=0.5)
    tracker.on_hardware_press(K3, 0.0)
    assert tracker.poll(0.4) == []
    long = tracker.poll(0.51)
    assert long == [ButtonEvent(K3, "long_press")]
    rel = tracker.on_hardware_release(K3, 0.6)
    assert [e.action for e in rel] == ["release"]


def test_k1_toggles_play_menu():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.MENU
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.PLAY
    assert c.state.blackout is False


def test_k2_on_play_is_contextual():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.PLAY
    assert c.state.blackout is False


def test_k3_on_play_is_chaser_go():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.PLAY
    assert c.state.active_function == c.state.current_chaser


def test_hardware_hold_k1_opens_menu():
    c = make_controller()
    c.handle_event(ButtonEvent(K1, "press"), now=10.0)
    c.tick(now=10.1)
    assert c.state.screen == ScreenId.PLAY
    c.tick(now=10.7)
    assert c.state.screen == ScreenId.MENU
