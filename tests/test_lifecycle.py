from pathlib import Path

from light_console.boot_splash import main as splash_main
from light_console.display.framebuffer import Framebuffer
from light_console.display.lifecycle import (
    STARTING_UP_TEXT,
    SHUTTING_DOWN_TEXT,
    lifecycle_origin,
    render_lifecycle,
)
from light_console.display.marquee import text_width_px
from light_console.display.renderer import Renderer
from light_console.display.widgets import text
from light_console.hardware.events import ButtonEvent, EncoderEvent, E2, K3
from light_console.hardware.oled import Ssd1322
from light_console.state import AppState, ScreenId
from light_console.ui.pages import SYSTEM_NET_TOGGLE, SYSTEM_QLC_TOGGLE, SYSTEM_SHUTDOWN_ROW

from tests.conftest import make_controller
from tests.test_shutdown import _start_shutdown

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ROOT / "light_console/display/screens.py"
OLED = ROOT / "light_console/hardware/oled.py"
SHIELD = ROOT / "light_console/hardware/shieldxl.py"
SPLASH_UNIT = ROOT / "packaging/systemd/shieldxl-oled-starting.service"
LC_UNIT = ROOT / "packaging/systemd/light-console.service"


def _on_pixels(fb: Framebuffer) -> set[tuple[int, int]]:
    return {
        (x, y)
        for y in range(fb.height)
        for x in range(fb.width)
        if fb.get(x, y)
    }


def test_starting_up_renders_exact_centered_text():
    fb = render_lifecycle(STARTING_UP_TEXT)
    expected = Framebuffer()
    x, y = lifecycle_origin(STARTING_UP_TEXT)
    text(expected, x, y, STARTING_UP_TEXT)
    assert STARTING_UP_TEXT == "STARTING UP"
    assert x == (fb.width - text_width_px(STARTING_UP_TEXT)) // 2
    assert fb.digest() == expected.digest()
    assert _on_pixels(fb) == _on_pixels(expected)
    assert fb.digest() != b"\x00" * (128 * 64)


def test_starting_up_is_fullscreen_lifecycle_layout():
    state = AppState(screen=ScreenId.STARTING_UP)
    r = Renderer()
    r.render(state)
    assert r.fb.digest() == render_lifecycle(STARTING_UP_TEXT).digest()
    play = AppState(screen=ScreenId.PLAY, qlc_connected=True)
    r2 = Renderer()
    r2.render(play)
    assert r.fb.digest() != r2.fb.digest()


def test_starting_up_does_not_depend_on_qlc_or_network_or_air2dmx():
    a = AppState(
        screen=ScreenId.STARTING_UP,
        qlc_connected=False,
        qlc_observed="STOPPED",
        network_ifaces=(),
        artnet_nodes=(),
        output_mode="SAFE",
    )
    b = AppState(
        screen=ScreenId.STARTING_UP,
        qlc_connected=True,
        qlc_observed="RUNNING",
        startup_status="RUNNING",
        output_mode="RIG",
    )
    ra, rb = Renderer(), Renderer()
    assert ra.render(a).digest() == rb.render(b).digest()
    assert ra.fb.digest() == render_lifecycle(STARTING_UP_TEXT).digest()


def test_normal_ui_replaces_starting_up_after_init():
    c = make_controller(screen=ScreenId.STARTING_UP)
    assert c.state.screen == ScreenId.PLAY
    r = Renderer()
    r.render(c.state)
    assert r.fb.digest() != render_lifecycle(STARTING_UP_TEXT).digest()


def test_qlc_service_stop_does_not_show_shutting_down():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SYSTEM
    assert c.state.shutdown_requested is False
    assert c.power.request_count == 0
    r = Renderer()
    r.render(c.state)
    assert r.fb.digest() != render_lifecycle(SHUTTING_DOWN_TEXT).digest()


def test_qlc_service_start_does_not_show_starting_up():
    c = make_controller(qlc_desired=False, qlc_observed="STOPPED")
    c.qlc_service.desired_on = False
    c.qlc_service.observed = "STOPPED"
    c.state.qlc_desired = False
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SYSTEM
    assert c.state.screen != ScreenId.STARTING_UP
    r = Renderer()
    r.render(c.state)
    assert r.fb.digest() != render_lifecycle(STARTING_UP_TEXT).digest()


def test_network_mode_toggle_does_not_show_lifecycle_screens():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_NET_TOGGLE
    before = c.state.network_mode
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SYSTEM
    assert c.state.screen not in {ScreenId.STARTING_UP, ScreenId.SHUTTING_DOWN}
    assert c.power.request_count == 0
    assert c.state.network_mode != before or c.state.network_mode_busy
    r = Renderer()
    r.render(c.state)
    digest = r.fb.digest()
    assert digest != render_lifecycle(STARTING_UP_TEXT).digest()
    assert digest != render_lifecycle(SHUTTING_DOWN_TEXT).digest()


def test_service_restart_is_not_appliance_shutdown():
    first = make_controller()
    first.hardware.close()
    assert first.state.screen == ScreenId.PLAY
    assert first.state.shutdown_requested is False
    second = make_controller()
    assert second.state.screen == ScreenId.PLAY
    assert second.state.shutdown_requested is False
    assert second.power.request_count == 0
    unit = SPLASH_UNIT.read_text()
    assert "Restart=" not in unit
    assert "Type=oneshot" in unit


def test_shutting_down_is_centered_lifecycle_text():
    c = make_controller()
    _start_shutdown(c)
    r = Renderer()
    r.force_dirty()
    fb = r.render(c.state)
    assert fb.digest() == render_lifecycle(SHUTTING_DOWN_TEXT).digest()
    x, _y = lifecycle_origin(SHUTTING_DOWN_TEXT)
    assert x == (128 - text_width_px(SHUTTING_DOWN_TEXT)) // 2
    assert "SAFE TO UNPLUG" not in SCREENS.read_text()
    assert "GREEN LED STOPS" not in SCREENS.read_text()


def test_shutting_down_flushed_before_shutdown_backend():
    c = make_controller()
    order: list[str] = []
    hw = c.hardware
    power = c.power
    real_set = hw.set_display
    real_req = power.request_shutdown

    def wrapped_set(fb):
        order.append("display")
        real_set(fb)
        assert bytes(fb.pixels) == render_lifecycle(SHUTTING_DOWN_TEXT).digest()

    def wrapped_req():
        order.append("shutdown")
        return real_req()

    hw.set_display = wrapped_set  # type: ignore[method-assign]
    power.request_shutdown = wrapped_req  # type: ignore[method-assign]
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert order == ["display", "shutdown"]
    assert c.state.screen == ScreenId.SHUTTING_DOWN
    assert c.power.request_count == 1


def test_inputs_locked_after_shutdown_begins():
    c = make_controller()
    _start_shutdown(c)
    master = c.state.master
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHUTTING_DOWN
    assert c.state.master == master
    assert c.power.request_count == 1


def test_oled_failure_in_early_startup_does_not_block_boot(monkeypatch):
    def boom():
        raise OSError("spidev missing")

    monkeypatch.setattr("light_console.boot_splash.show_starting_up", boom)
    assert splash_main([]) == 0


def test_shutdown_teardown_does_not_clear_oled():
    close_src = Ssd1322.close.__doc__ or ""
    oled = OLED.read_text(encoding="utf-8")
    shield = SHIELD.read_text(encoding="utf-8")
    close_fn = oled.split("def close", 1)[1].split("def ", 1)[0]
    assert "0xAE" not in close_fn
    assert "show_framebuffer" not in close_fn
    assert "Never paint a blank frame" in shield
    assert "blank the SSD1322" in close_src or "Do not blank" in close_src
    c = make_controller()
    _start_shutdown(c)
    frame = c.hardware.last_frame
    c.hardware.close()
    assert c.hardware.closed is True
    assert c.hardware.cleared_on_close is False
    assert c.hardware.last_frame == frame
    assert c.hardware.last_frame == render_lifecycle(SHUTTING_DOWN_TEXT).digest()


def test_splash_unit_is_early_and_nonblocking():
    splash = SPLASH_UNIT.read_text()
    lc = LC_UNIT.read_text()
    assert "python3 -m light_console.boot_splash" in splash
    assert "After=local-fs.target" in splash
    assert "Before=light-console.service" in splash
    assert "network-online" not in splash
    assert "qlcplus" not in splash
    assert not any(ln.startswith("Requires=") for ln in splash.splitlines())
    assert "Wants=shieldxl-oled-starting.service" in lc
    assert "Requires=shieldxl-oled-starting.service" not in lc
    assert "After=local-fs.target shieldxl-oled-starting.service" in lc
    exec_start = next(ln for ln in lc.splitlines() if ln.startswith("ExecStart="))
    assert exec_start == "ExecStart=/usr/bin/python3 -u -m light_console.main --shield"
    qlc = (ROOT / "packaging/systemd/qlcplus.service").read_text()
    assert "ExecStart=/usr/bin/qlcplus-qml -w -o /home/light/shows/master.qxw" in qlc
