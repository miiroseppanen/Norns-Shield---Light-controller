from pathlib import Path

from light_console.boot_splash import main as splash_main
from light_console.display.framebuffer import Framebuffer
from light_console.display.lifecycle import (
    STARTING_UP_TEXT,
    SHUTTING_DOWN_TEXT,
    STARTUP_MIN_VISIBLE_S,
    consume_starting_mark,
    hold_starting_up_visible,
    lifecycle_origin,
    remaining_startup_hold_s,
    render_lifecycle,
    write_starting_mark,
)
from light_console.display.marquee import text_width_px
from light_console.display.renderer import Renderer
from light_console.display.widgets import text
from light_console.hardware.events import ButtonEvent, EncoderEvent, E2, K3
from light_console.hardware.oled import Ssd1322
from light_console.state import AppState, ScreenId
from light_console.ui.pages import SYSTEM_NET_TOGGLE, SYSTEM_QLC_TOGGLE

from tests.conftest import make_controller
from tests.test_shutdown import _start_shutdown

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ROOT / "light_console/display/screens.py"
OLED = ROOT / "light_console/hardware/oled.py"
SHIELD = ROOT / "light_console/hardware/shieldxl.py"
SPLASH_PY = ROOT / "light_console/boot_splash.py"
SPLASH_UNIT = ROOT / "packaging/systemd/shieldxl-oled-starting.service"
SHUTDOWN_UNIT = ROOT / "packaging/systemd/shieldxl-oled-shutdown.service"
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
    c.begin_appliance_shutdown()
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
    assert "sleep" not in splash.lower()
    assert not any(ln.startswith("Requires=") for ln in splash.splitlines())
    assert "Wants=shieldxl-oled-starting.service" not in lc
    assert "shieldxl-oled-shutdown.service" in lc
    wants = next(ln for ln in lc.splitlines() if ln.startswith("Wants="))
    assert "shieldxl-oled-starting.service" not in wants
    assert "shieldxl-oled-shutdown.service" in wants
    assert "Requires=shieldxl-oled-starting.service" not in lc
    assert "Requires=shieldxl-oled-shutdown.service" not in lc
    assert (
        "After=local-fs.target shieldxl-oled-starting.service "
        "shieldxl-oled-shutdown.service"
    ) in lc
    exec_start = next(ln for ln in lc.splitlines() if ln.startswith("ExecStart="))
    assert exec_start == "ExecStart=/usr/bin/python3 -u -m light_console.main --shield"
    assert not any(ln.startswith("ExecStop=") for ln in lc.splitlines())
    qlc = (ROOT / "packaging/systemd/qlcplus.service").read_text()
    assert "ExecStart=/usr/bin/qlcplus-qml -w -o /home/light/shows/master.qxw" in qlc


def test_shutting_down_renderer_is_byte_exact():
    fb = render_lifecycle(SHUTTING_DOWN_TEXT)
    expected = Framebuffer()
    x, y = lifecycle_origin(SHUTTING_DOWN_TEXT)
    text(expected, x, y, SHUTTING_DOWN_TEXT)
    assert SHUTTING_DOWN_TEXT == "SHUTTING DOWN"
    assert fb.digest() == expected.digest()
    assert fb.digest() == render_lifecycle("SHUTTING DOWN").digest()
    assert fb.digest() != render_lifecycle(STARTING_UP_TEXT).digest()
    assert fb.digest() != b"\x00" * (128 * 64)


class _FakeOled:
    def __init__(self) -> None:
        self.inited = False
        self.frames: list[bytes] = []
        self.closed = False
        self.blanked = False

    def init(self) -> None:
        self.inited = True

    def show_framebuffer(self, fb: Framebuffer) -> None:
        self.frames.append(bytes(fb.pixels))

    def close(self) -> None:
        self.closed = True

    def cmd(self, code: int, *args: int) -> None:
        if code == 0xAE:
            self.blanked = True


def test_shutdown_helper_paints_shutting_down_then_releases(monkeypatch, tmp_path):
    from light_console.boot_splash import show_shutting_down

    mark = tmp_path / "starting"
    monkeypatch.setattr("light_console.display.lifecycle.STARTING_MARK", mark)
    fake = _FakeOled()

    def factory(*_a, **_k):
        return fake

    monkeypatch.setattr("light_console.hardware.oled.Ssd1322", factory)
    show_shutting_down()
    assert fake.inited is True
    assert fake.frames == [render_lifecycle(SHUTTING_DOWN_TEXT).digest()]
    assert fake.closed is True
    assert fake.blanked is False
    assert not mark.exists()
    assert splash_main(["shutting-down"]) == 0
    assert fake.frames[-1] == render_lifecycle(SHUTTING_DOWN_TEXT).digest()
    assert not mark.exists()
    assert splash_main([]) == 0
    assert fake.frames[-1] == render_lifecycle(STARTING_UP_TEXT).digest()
    assert mark.is_file()


def test_lifecycle_helper_has_no_network_or_production_pi():
    src = SPLASH_PY.read_text(encoding="utf-8")
    unit = SHUTDOWN_UNIT.read_text()
    for blob in (src, unit):
        assert "192.168.88.248" not in blob
        assert "nmcli" not in blob
        assert "subprocess" not in blob
        assert "socket" not in blob
        assert "urllib" not in blob
        assert "qlcplus" not in blob
        assert "artnet" not in blob.lower()
    assert "show_framebuffer(render_lifecycle" in src
    close_fn = OLED.read_text(encoding="utf-8").split("def close", 1)[1].split("def ", 1)[0]
    assert "0xAE" not in close_fn
    assert "show_framebuffer" not in close_fn


def test_machine_shutdown_unit_is_not_tied_to_app_restart():
    stop = SHUTDOWN_UNIT.read_text()
    lc = LC_UNIT.read_text()
    qlc = (ROOT / "packaging/systemd/qlcplus.service").read_text()
    assert "ExecStop=/usr/bin/python3 -m light_console.boot_splash shutting-down" in stop
    assert "ExecStart=/usr/bin/true" in stop
    assert "RemainAfterExit=yes" in stop
    assert "Type=oneshot" in stop
    assert "PartOf=light-console.service" not in stop
    assert "BindsTo=light-console.service" not in stop
    assert "PartOf=qlcplus.service" not in stop
    assert "Before=light-console.service" in stop
    assert "Before=light-console.service shutdown.target reboot.target halt.target poweroff.target" in stop
    assert "WantedBy=multi-user.target" in stop
    assert "network-online" not in stop
    assert "qlcplus" not in stop
    assert not any(ln.startswith("ExecStop=") for ln in lc.splitlines())
    assert "boot_splash shutting-down" not in lc
    assert "boot_splash shutting-down" not in qlc
    assert "shieldxl-oled-shutdown.service" in (ROOT / "packaging/install-appliance.sh").read_text()


def test_helper_records_paint_only_after_framebuffer_flush():
    src = SPLASH_PY.read_text(encoding="utf-8")
    paint = src.index("oled.show_framebuffer(render_lifecycle(message))")
    log = src.index('LOG.info("painted %s", message)')
    stamp = src.index("_stamp(message)")
    mark = src.index("write_starting_mark()")
    assert paint < log < stamp < mark
    assert "time.sleep" not in src


def test_service_restart_unit_text_does_not_invoke_shutdown_painter():
    lc = LC_UNIT.read_text()
    assert "Restart=on-failure" in lc
    assert not any(ln.startswith("ExecStop=") for ln in lc.splitlines())
    stop = SHUTDOWN_UNIT.read_text()
    assert "PartOf=light-console.service" not in stop
    wants = next(ln for ln in lc.splitlines() if ln.startswith("Wants="))
    assert "shieldxl-oled-starting.service" not in wants


def test_startup_min_visible_is_in_target_range():
    assert 2.0 <= STARTUP_MIN_VISIBLE_S <= 2.5
    assert STARTUP_MIN_VISIBLE_S == 2.25


def test_remaining_startup_hold_uses_monotonic_delta():
    t0 = 10.0
    assert remaining_startup_hold_s(t0, t0) == STARTUP_MIN_VISIBLE_S
    assert remaining_startup_hold_s(t0, t0 + STARTUP_MIN_VISIBLE_S) == 0.0
    assert remaining_startup_hold_s(t0, t0 + STARTUP_MIN_VISIBLE_S + 3.0) == 0.0
    assert remaining_startup_hold_s(t0, t0 + 0.5) == STARTUP_MIN_VISIBLE_S - 0.5
    src = (ROOT / "light_console/display/lifecycle.py").read_text(encoding="utf-8")
    hold = src.split("def hold_starting_up_visible", 1)[1].split("def ", 1)[0]
    assert "time.monotonic" in hold
    assert "time.time(" not in hold
    assert "datetime" not in hold
    assert "qlc" not in hold.lower()
    assert "nmcli" not in hold
    assert "network" not in hold.lower()
    assert "artnet" not in hold.lower()
    assert "discover" not in hold.lower()


def test_hold_sleeps_only_remaining_time(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(
        "light_console.display.lifecycle.time.monotonic",
        lambda: 100.4,
    )
    monkeypatch.setattr(
        "light_console.display.lifecycle.time.sleep",
        lambda s: slept.append(s),
    )
    n = hold_starting_up_visible(100.0, enabled=True)
    assert abs(n - (STARTUP_MIN_VISIBLE_S - 0.4)) < 1e-9
    assert len(slept) == 1
    assert abs(slept[0] - (STARTUP_MIN_VISIBLE_S - 0.4)) < 1e-9


def test_hold_skips_when_init_already_exceeded_minimum(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(
        "light_console.display.lifecycle.time.monotonic",
        lambda: 50.0 + STARTUP_MIN_VISIBLE_S + 1.0,
    )
    monkeypatch.setattr(
        "light_console.display.lifecycle.time.sleep",
        lambda s: slept.append(s),
    )
    n = hold_starting_up_visible(50.0, enabled=True)
    assert n == 0.0
    assert slept == []


def test_hold_skipped_without_boot_mark_or_t0(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(
        "light_console.display.lifecycle.time.sleep",
        lambda s: slept.append(s),
    )
    assert hold_starting_up_visible(10.0, enabled=False) == 0.0
    assert hold_starting_up_visible(None, enabled=True) == 0.0
    assert slept == []


def test_reveal_holds_only_when_boot_mark_present(monkeypatch, tmp_path):
    mark = tmp_path / "starting"
    monkeypatch.setattr("light_console.display.lifecycle.STARTING_MARK", mark)
    slept: list[float] = []
    monkeypatch.setattr(
        "light_console.display.lifecycle.time.sleep",
        lambda s: slept.append(s),
    )
    clock = {"now": 20.0}

    def fake_mono() -> float:
        return clock["now"]

    monkeypatch.setattr("light_console.display.lifecycle.time.monotonic", fake_mono)
    monkeypatch.setattr("light_console.ui.controller.time.monotonic", fake_mono)

    c = make_controller(screen=ScreenId.STARTING_UP)
    assert c.state.screen == ScreenId.PLAY
    assert slept == []

    c.state.screen = ScreenId.STARTING_UP
    c.hardware.starting_up_at = 19.5
    c.reveal_normal_ui()
    assert c.state.screen == ScreenId.PLAY
    assert slept == []
    assert not mark.exists()

    c.state.screen = ScreenId.STARTING_UP
    c.hardware.starting_up_at = 19.5
    write_starting_mark(mark)
    clock["now"] = 19.7
    c.reveal_normal_ui()
    assert c.state.screen == ScreenId.PLAY
    assert len(slept) == 1
    assert abs(slept[0] - (STARTUP_MIN_VISIBLE_S - 0.2)) < 1e-9
    assert not mark.exists()
    assert consume_starting_mark(mark) is False


def test_reveal_does_not_wait_for_qlc_or_network(monkeypatch, tmp_path):
    mark = tmp_path / "starting"
    monkeypatch.setattr("light_console.display.lifecycle.STARTING_MARK", mark)
    slept: list[float] = []
    monkeypatch.setattr(
        "light_console.display.lifecycle.time.sleep",
        lambda s: slept.append(s),
    )
    monkeypatch.setattr(
        "light_console.display.lifecycle.time.monotonic",
        lambda: 5.0 + STARTUP_MIN_VISIBLE_S,
    )
    c = make_controller(
        screen=ScreenId.STARTING_UP,
        qlc_connected=False,
        qlc_observed="STOPPED",
        network_mode="network",
        network_mode_observed="OFFLINE",
    )
    c.state.artnet_nodes = ()
    c.state.screen = ScreenId.STARTING_UP
    c.hardware.starting_up_at = 5.0
    write_starting_mark(mark)
    c.reveal_normal_ui()
    assert c.state.screen == ScreenId.PLAY
    assert slept == []
    r = Renderer()
    r.render(c.state)
    assert r.fb.digest() != render_lifecycle(STARTING_UP_TEXT).digest()


def test_tick_and_render_do_not_sleep_for_startup_hold(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(
        "light_console.display.lifecycle.time.sleep",
        lambda s: slept.append(s),
    )
    c = make_controller()
    c.tick()
    assert slept == []
    tick_src = (ROOT / "light_console/ui/controller.py").read_text(encoding="utf-8")
    tick_fn = tick_src.split("def tick(", 1)[1].split("def ", 1)[0]
    assert "hold_starting_up_visible" not in tick_fn
    assert "time.sleep" not in tick_fn
    render_src = (ROOT / "light_console/display/renderer.py").read_text(encoding="utf-8")
    assert "hold_starting_up_visible" not in render_src
    assert "time.sleep" not in render_src


def test_starting_up_painted_before_controller_reveal():
    shield = SHIELD.read_text(encoding="utf-8")
    main = (ROOT / "light_console/main.py").read_text(encoding="utf-8")
    ctrl = (ROOT / "light_console/ui/controller.py").read_text(encoding="utf-8")
    paint = shield.index("show_framebuffer(render_lifecycle(STARTING_UP_TEXT))")
    t0 = shield.index("starting_up_at = time.monotonic()")
    assert paint < t0
    assert "state.screen = ScreenId.STARTING_UP" in main
    assert main.index("hardware: HardwareBackend = ShieldXLBackend()") < main.index(
        "controller = Controller("
    )
    assert "self.reveal_normal_ui()" in ctrl
    assert ctrl.index("self.reveal_normal_ui()") > ctrl.index("self._load_routes()")
    assert "hold_starting_up_visible" in ctrl.split("def reveal_normal_ui", 1)[1].split(
        "def ", 1
    )[0]

