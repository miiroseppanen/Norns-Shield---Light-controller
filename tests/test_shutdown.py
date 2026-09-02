from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K1, K2, K3
from light_console.power import LinuxPowerService, MockPowerService
from light_console.state import ScreenId
from light_console.ui.pages import SYSTEM_SHUTDOWN_ROW

from tests.conftest import make_controller


def _open_system(c):
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = 4
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SYSTEM


def test_system_shutdown_navigation():
    c = make_controller()
    _open_system(c)
    c.state.system_index = SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHUTDOWN
    assert c.power.request_count == 0


def test_k3_opens_confirmation_not_shutdown():
    c = make_controller()
    _open_system(c)
    c.state.system_index = SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHUTDOWN
    assert c.power.shutdown_requested is False
    assert c.state.shutdown_requested is False


def test_k2_cancels_confirmation():
    c = make_controller()
    _open_system(c)
    c.state.system_index = SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.SYSTEM
    assert c.power.shutdown_requested is False


def test_k1_cancels_to_play():
    c = make_controller()
    _open_system(c)
    c.state.system_index = SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.PLAY
    assert c.power.shutdown_requested is False


def test_k3_confirm_calls_power_once():
    c = make_controller()
    _open_system(c)
    c.state.system_index = SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.power.shutdown_requested is True
    assert c.power.request_count == 1
    assert c.state.shutdown_requested is True
    assert isinstance(c.power, MockPowerService)
    assert c.power.spawn_count == 0


def test_encoder_does_not_confirm_shutdown():
    c = make_controller()
    _open_system(c)
    c.state.system_index = SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(EncoderEvent(E1, 1))
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(EncoderEvent(E3, 1))
    assert c.state.screen == ScreenId.SHUTDOWN
    assert c.power.request_count == 0
    assert c.power.shutdown_requested is False


def test_double_confirm_does_not_request_twice():
    c = make_controller()
    _open_system(c)
    c.state.system_index = SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.power.request_count == 1
    assert c.power.shutdown_requested is True
    assert c.power.spawn_count == 0


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
