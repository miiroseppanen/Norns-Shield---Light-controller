"""QLC function runtime is invalid once QLC is disconnected or stopped."""

from __future__ import annotations

from light_console.display.renderer import Renderer
from light_console.display.screens import draw_play, startup_oled_word
from light_console.hardware.events import ButtonEvent, K3
from light_console.qlc.client import ConnectionState
from light_console.qlc.fake import FakeTransport
from light_console.qlc.functions import QlcFunction
from light_console.qlc.runtime import (
    WAIT,
    apply_live_startup_runtime,
    function_runtime_available,
    invalidate_function_runtime,
    parse_startup_status_file,
)
from light_console.qlc.ws_client import QlcWebSocketClient
from light_console.state import AppState, ScreenId
from light_console.ui.pages import SYSTEM_QLC_TOGGLE
from light_console.ui.vocab import FAILED, RUNNING, STARTING, STOPPED, STOPPING

from tests.conftest import make_controller


def _write_startup_file(path, status: str = RUNNING) -> None:
    path.write_text(f"status={status}\nid=0\nname=startup\n", encoding="utf-8")


def _arm_startup(c, *, running: bool = True) -> QlcFunction:
    fns = list(c.qlc.list_functions())
    fn = QlcFunction(42, "startup", "Chaser", running=running)
    fns.append(fn)
    c.qlc.replace_functions(fns)
    return c.qlc.function_by_name("startup")


def _controller_with_startup_running(tmp_path, monkeypatch):
    path = tmp_path / "qlc-startup.status"
    monkeypatch.setattr("light_console.ui.controller.STARTUP_STATUS_PATH", path)
    _write_startup_file(path, RUNNING)
    c = make_controller()
    _arm_startup(c, running=True)
    c._finish()
    return c, path


def play_qlc_and_startup(c) -> tuple[str, str]:
    from light_console.display.screens import play_qlc_word

    return play_qlc_word(c.state), startup_oled_word(c.state)


def test_parse_startup_status_file():
    assert parse_startup_status_file("status=RUNNING\nid=0\n") == "RUNNING"
    assert parse_startup_status_file("note=x\n") == ""


def test_function_runtime_available_matrix():
    assert function_runtime_available(True, RUNNING) is True
    assert function_runtime_available(True, STARTING) is True
    assert function_runtime_available(True, STOPPING) is False
    assert function_runtime_available(True, STOPPED) is False
    assert function_runtime_available(True, FAILED) is False
    assert function_runtime_available(False, RUNNING) is False
    assert function_runtime_available(False, STOPPED) is False


def test_stale_file_running_is_not_live_evidence():
    state = AppState(qlc_connected=True, qlc_observed=RUNNING)
    apply_live_startup_runtime(state, live_running=False, file_status=RUNNING)
    assert state.startup_status == STOPPED
    assert state.startup_running is False
    apply_live_startup_runtime(state, live_running=True, file_status=RUNNING)
    assert state.startup_status == RUNNING
    assert state.startup_running is True


def test_connected_startup_running_shows_running(tmp_path, monkeypatch):
    c, _path = _controller_with_startup_running(tmp_path, monkeypatch)
    assert c.state.qlc_connected is True
    assert c.state.qlc_observed == RUNNING
    assert c.state.startup_status == RUNNING
    assert c.state.startup_running is True
    assert startup_oled_word(c.state) == RUNNING


def test_qlc_stop_invalidates_startup_immediately(tmp_path, monkeypatch):
    c, path = _controller_with_startup_running(tmp_path, monkeypatch)
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.qlc_desired is False
    assert c.state.qlc_observed == STOPPING
    assert c.state.startup_status == STOPPED
    assert c.state.startup_running is False
    assert startup_oled_word(c.state) == STOPPED
    assert "status=RUNNING" in path.read_text()


def test_stopped_qlc_cannot_display_startup_running(tmp_path, monkeypatch):
    c, _path = _controller_with_startup_running(tmp_path, monkeypatch)
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.qlc_service.settle()
    c.qlc.simulate_link(False)
    c.tick(now=1.0)
    assert c.state.qlc_observed == STOPPED
    assert c.state.startup_status != RUNNING
    assert startup_oled_word(c.state) == STOPPED
    c.state.screen = ScreenId.PLAY
    r = Renderer()
    r.force_dirty()
    r.render(c.state)
    assert play_qlc_and_startup(c) == (STOPPED, STOPPED)


def test_websocket_disconnect_invalidates_cached_function_state(tmp_path, monkeypatch):
    c, path = _controller_with_startup_running(tmp_path, monkeypatch)
    desired = c.state.qlc_desired
    c.qlc.simulate_drop()
    c.tick(now=1.0)
    assert c.state.qlc_connected is False
    assert c.state.startup_status == STOPPED
    assert c.state.startup_running is False
    assert c.qlc.function_by_name("startup").running is False
    assert c.state.qlc_desired is desired
    assert "status=RUNNING" in path.read_text()


def test_reconnect_does_not_reuse_stale_running(tmp_path, monkeypatch):
    c, path = _controller_with_startup_running(tmp_path, monkeypatch)
    c.qlc.simulate_drop()
    c.tick(now=1.0)
    c.qlc.simulate_link(True)
    c.tick(now=2.0)
    assert c.state.qlc_connected is True
    assert c.state.qlc_observed == RUNNING
    assert "status=RUNNING" in path.read_text()
    assert c.state.startup_status != RUNNING
    assert c.state.startup_running is False
    assert startup_oled_word(c.state) != RUNNING


def test_fresh_function_query_restores_running(tmp_path, monkeypatch):
    c, _path = _controller_with_startup_running(tmp_path, monkeypatch)
    c.qlc.simulate_drop()
    c.tick(now=1.0)
    c.qlc.simulate_link(True)
    c.tick(now=2.0)
    assert c.state.startup_status != RUNNING
    c.qlc.function_by_name("startup").running = True
    c._finish()
    assert c.state.startup_status == RUNNING
    assert c.state.startup_running is True
    assert startup_oled_word(c.state) == RUNNING


def test_ui_stop_then_start_rebuilds_from_fresh_evidence(tmp_path, monkeypatch):
    c, path = _controller_with_startup_running(tmp_path, monkeypatch)
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.qlc_service.settle()
    c.qlc.simulate_link(False)
    c.tick(now=1.0)
    assert c.state.qlc_desired is False
    assert c.state.qlc_observed == STOPPED
    assert startup_oled_word(c.state) == STOPPED
    c.set_qlc_desired(True)
    c.qlc_service.settle()
    c.qlc.simulate_link(True)
    c.tick(now=2.0)
    assert c.state.qlc_desired is True
    assert c.state.qlc_observed == RUNNING
    assert "status=RUNNING" in path.read_text()
    assert c.state.startup_status != RUNNING
    c.qlc.function_by_name("startup").running = True
    c._finish()
    assert c.state.startup_status == RUNNING


def test_unexpected_crash_keeps_desired_and_clears_startup(tmp_path, monkeypatch):
    c, _path = _controller_with_startup_running(tmp_path, monkeypatch)
    assert c.state.qlc_desired is True
    c.qlc.simulate_drop()
    c.qlc_service.fail()
    c.state.qlc_observed = FAILED
    c.tick(now=1.0)
    assert c.state.qlc_desired is True
    assert c.state.qlc_observed == FAILED
    assert c.state.startup_status == STOPPED
    assert c.qlc_service.commands == []


def test_self_heal_reconnects_without_restarting_qlc_process(tmp_path, monkeypatch):
    c, _path = _controller_with_startup_running(tmp_path, monkeypatch)
    c.qlc.simulate_drop()
    c.tick(now=1.0)
    attempts = c.qlc.reconnect_attempts
    c.tick(now=4.0)
    assert c.qlc.reconnect_attempts > attempts
    assert c.qlc.connected() is False
    assert c.qlc_service.commands == []
    assert c.state.qlc_desired is True
    c.qlc.simulate_link(True)
    c.tick(now=5.0)
    assert c.state.qlc_connected is True
    assert c.state.startup_status != RUNNING


def test_regression_shield_ui_stop_oled(tmp_path, monkeypatch):
    """QLC RUNNING + startup RUNNING, stop from Shield UI → no startup RUNNING."""
    c, path = _controller_with_startup_running(tmp_path, monkeypatch)
    c.state.screen = ScreenId.PLAY
    assert play_qlc_and_startup(c) == (RUNNING, RUNNING)
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.qlc_observed == STOPPING
    assert startup_oled_word(c.state) != RUNNING
    c.qlc_service.settle()
    c.qlc.simulate_link(False)
    c.nav.go_play(c.state)
    c.tick(now=1.0)
    assert c.state.qlc_observed == STOPPED
    assert play_qlc_and_startup(c) == (STOPPED, STOPPED)
    assert "status=RUNNING" in path.read_text()


def test_ws_drop_clears_running_reconnect_queries_fresh():
    fake = FakeTransport()
    fake.functions = [(0, "startup")]
    fake.function_running = {0: "Running"}
    qlc = QlcWebSocketClient(transport_factory=lambda: fake, reconnect_seconds=0.5)
    qlc.pump(0.0)
    qlc.pump(0.1)
    assert qlc.connected() is True
    assert qlc.function_by_name("startup").running is True
    assert "QLC+API|getFunctionStatus|0" in fake.sent
    fake.drop()
    qlc.pump(0.2)
    assert qlc.connected() is False
    assert qlc.connection_state() is not ConnectionState.CONNECTED
    assert qlc.function_by_name("startup").running is False
    fake.function_running[0] = "Stopped"
    qlc.pump(1.0)
    qlc.pump(1.1)
    assert qlc.connected() is True
    assert qlc.function_by_name("startup").running is False
    fake.function_running[0] = "Running"
    qlc.request_function_status(0)
    qlc.pump(1.2)
    assert qlc.function_by_name("startup").running is True
    qlc.close()


def test_wait_file_while_connected_before_live_running(tmp_path, monkeypatch):
    path = tmp_path / "qlc-startup.status"
    monkeypatch.setattr("light_console.ui.controller.STARTUP_STATUS_PATH", path)
    _write_startup_file(path, WAIT)
    c = make_controller()
    _arm_startup(c, running=False)
    c._finish()
    assert c.state.startup_status == WAIT
    assert c.state.startup_running is False
    invalidate_function_runtime(c.state)
    assert c.state.startup_status == STOPPED
