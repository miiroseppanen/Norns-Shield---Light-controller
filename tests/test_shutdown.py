from pathlib import Path

from light_console.display.renderer import Renderer
from light_console.display.screens import SHUTTING_DOWN_LINES
from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K1, K2, K3
from light_console.power import LinuxPowerService, MockPowerService
from light_console.state import ScreenId
from light_console.ui.menu import menu_index_of
from light_console.ui.pages import SYSTEM_SHUTDOWN_ROW

from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ROOT / "light_console/display/screens.py"


def _open_system(c):
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("SYSTEM")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SYSTEM


def _start_shutdown(c):
    _open_system(c)
    c.state.system_index = SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))


def test_system_k3_starts_shutdown_immediately():
    c = make_controller()
    _start_shutdown(c)
    assert c.state.screen == ScreenId.SHUTTING_DOWN
    assert c.state.shutdown_requested is True
    assert c.power.shutdown_requested is True
    assert c.power.request_count == 1
    assert isinstance(c.power, MockPowerService)
    assert c.power.spawn_count == 0


def test_no_shutdown_confirmation_state():
    assert not hasattr(ScreenId, "SHUTDOWN")
    text = SCREENS.read_text(encoding="utf-8")
    assert "SHUTDOWN?" not in text
    assert "K2  CANCEL" not in text
    assert "K3  CONFIRM" not in text
    for line in SHUTTING_DOWN_LINES:
        assert line in text


def test_k2_does_not_cancel_shutdown():
    c = make_controller()
    _start_shutdown(c)
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.SHUTTING_DOWN
    assert c.power.request_count == 1
    assert c.power.shutdown_requested is True


def test_k1_does_not_leave_shutdown():
    c = make_controller()
    _start_shutdown(c)
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.SHUTTING_DOWN
    assert c.power.request_count == 1


def test_keys_and_encoders_ignored_after_shutdown():
    c = make_controller()
    _start_shutdown(c)
    master = c.state.master
    system_index = c.state.system_index
    for ev in (
        ButtonEvent(K1, "press"),
        ButtonEvent(K2, "press"),
        ButtonEvent(K3, "press"),
        EncoderEvent(E1, 5),
        EncoderEvent(E2, 1),
        EncoderEvent(E3, -1),
    ):
        c.inject_cooked(ev)
    assert c.state.screen == ScreenId.SHUTTING_DOWN
    assert c.power.request_count == 1
    assert c.power.shutdown_requested is True
    assert c.state.master == master
    assert c.state.system_index == system_index


def test_shutdown_backend_called_exactly_once():
    c = make_controller()
    _start_shutdown(c)
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.power.request_count == 1
    assert c.power.shutdown_requested is True
    assert c.power.spawn_count == 0


def test_renderer_shutdown_guidance():
    c = make_controller()
    _start_shutdown(c)
    r = Renderer()
    r.force_dirty()
    fb = r.render(c.state)
    assert fb.width == 128
    assert fb.height == 64
    assert fb.digest() != b"\x00" * (128 * 64)
    assert SHUTTING_DOWN_LINES == (
        "SHUTTING DOWN",
        "WAIT",
        "GREEN LED STOPS",
        "SAFE TO UNPLUG",
    )


def test_play_status_unaffected_without_shutdown():
    c = make_controller()
    assert c.state.screen == ScreenId.PLAY
    assert c.state.qlc_connected is True
    c.inject_cooked(EncoderEvent(E1, 2))
    assert c.state.screen == ScreenId.PLAY
    assert c.power.request_count == 0
    r = Renderer()
    r.render(c.state)
    assert r.fb.digest() != b"\x00" * (128 * 64)


def test_mock_does_not_spawn_host_shutdown():
    power = MockPowerService()
    assert power.request_shutdown() is True
    assert power.spawn_count == 0
    assert power.request_shutdown() is False


def test_linux_power_spawns_argv_once():
    true = "/usr/bin/true"
    svc = LinuxPowerService(argv=(true,))
    assert svc.request_shutdown() is True
    assert svc.spawn_count == 1
    assert svc.request_count == 1
    assert svc.request_shutdown() is False
    assert svc.spawn_count == 1
    assert svc.request_count == 1
    assert svc.argv == (true,)
