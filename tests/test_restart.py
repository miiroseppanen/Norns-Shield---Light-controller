from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import CONTENT_Y, LABEL_X, ROW
from light_console.display.lifecycle import RESTARTING_TEXT, render_lifecycle
from light_console.display.renderer import Renderer
from light_console.display.screens import RESTART_CONFIRM_LINES, RESTARTING_LINES
from light_console.display.widgets import text
from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K1, K2, K3
from light_console.power import LinuxPowerService, MockPowerService
from light_console.state import ScreenId
from light_console.ui.menu import MENU_ITEMS, menu_index_of

from tests.conftest import make_controller


def _open_restart_confirm(c):
    if c.state.screen != ScreenId.PLAY:
        c.inject_cooked(ButtonEvent(K1, "press"))
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.MENU
    c.state.menu_index = menu_index_of("RESTART")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.RESTART_CONFIRM


def _start_restart(c):
    _open_restart_confirm(c)
    c.inject_cooked(ButtonEvent(K3, "press"))


def test_menu_restart_sits_under_system():
    labels = [item.label for item in MENU_ITEMS]
    assert labels[-3:] == ["SYSTEM", "RESTART", "SHUTDOWN"]
    c = make_controller()
    _open_restart_confirm(c)
    assert c.power.restart_count == 0
    assert c.state.restart_requested is False
    fb = Renderer().render(c.state)
    want = Framebuffer()
    for i, line in enumerate(RESTART_CONFIRM_LINES):
        text(want, LABEL_X, CONTENT_Y + ROW * (i + 1), line)
    for y in range(fb.height):
        for x in range(fb.width):
            if not want.get(x, y):
                continue
            if fb.get(x, y) != 1:
                raise AssertionError("restart confirm copy missing")
    assert RESTART_CONFIRM_LINES == ("PRESS RIGHT BUTTON", "TO RESTART")
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    assert c.power.restart_count == 0


def test_k3_on_restart_confirm_starts_restart():
    c = make_controller()
    _start_restart(c)
    assert c.state.screen == ScreenId.RESTARTING
    assert c.state.restart_requested is True
    assert c.power.restart_requested is True
    assert c.power.restart_count == 1
    assert c.power.request_count == 0
    assert isinstance(c.power, MockPowerService)
    assert c.power.restart_spawn_count == 0
    assert c.power.spawn_count == 0


def test_k2_does_not_cancel_restart():
    c = make_controller()
    _start_restart(c)
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.RESTARTING
    assert c.power.restart_count == 1


def test_keys_and_encoders_ignored_after_restart():
    c = make_controller()
    _start_restart(c)
    master = c.state.master
    for ev in (
        ButtonEvent(K1, "press"),
        ButtonEvent(K2, "press"),
        ButtonEvent(K3, "press"),
        EncoderEvent(E1, 5),
        EncoderEvent(E2, 1),
        EncoderEvent(E3, -1),
    ):
        c.inject_cooked(ev)
    assert c.state.screen == ScreenId.RESTARTING
    assert c.power.restart_count == 1
    assert c.state.master == master


def test_restart_backend_called_exactly_once():
    c = make_controller()
    _start_restart(c)
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.power.restart_count == 1
    assert c.power.restart_requested is True


def test_renderer_restarting_guidance():
    c = make_controller()
    _start_restart(c)
    r = Renderer()
    r.force_dirty()
    fb = r.render(c.state)
    assert RESTARTING_LINES == ("RESTARTING",)
    assert fb.digest() == render_lifecycle(RESTARTING_TEXT).digest()


def test_restart_does_not_halt():
    c = make_controller()
    _start_restart(c)
    assert c.power.shutdown_requested is False
    assert c.state.shutdown_requested is False
    assert c.power.request_count == 0


def test_halt_blocks_restart():
    from tests.test_shutdown import _start_shutdown

    c = make_controller()
    _start_shutdown(c)
    c.begin_appliance_restart()
    assert c.state.screen == ScreenId.SHUTTING_DOWN
    assert c.power.restart_count == 0
    assert c.power.request_count == 1


def test_linux_power_spawns_restart_argv_once():
    true = "/usr/bin/true"
    svc = LinuxPowerService(argv=(true,), restart_cmd=(true,))
    assert svc.request_restart() is True
    assert svc.restart_spawn_count == 1
    assert svc.restart_count == 1
    assert svc.spawn_count == 0
    assert svc.request_restart() is False
    assert svc.request_shutdown() is False
    assert svc.restart_cmd == (true,)
