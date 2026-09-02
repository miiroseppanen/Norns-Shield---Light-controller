from light_console.hardware.events import SimCommandEvent
from light_console.qlc.client import MockQLCClient
from light_console.qlc.ws_client import QlcWebSocketClient

from tests.conftest import make_controller


def test_qlc_disconnect_shows_lost_and_does_not_restart_process():
    c = make_controller()
    c.qlc.simulate_drop()
    c.tick(now=1.0)
    assert c.state.qlc_connected is False
    assert "QLC LOST" in c.state.warnings
    attempts = c.qlc.reconnect_attempts
    c.tick(now=4.0)
    assert c.qlc.reconnect_attempts > attempts
    assert c.qlc.connected() is False


def test_qlc_reconnect_clears_lost():
    c = make_controller()
    c.qlc.simulate_link(False)
    c.tick(now=1.0)
    c.qlc.simulate_link(True)
    c.tick(now=2.0)
    assert c.state.qlc_connected is True
    assert "QLC LOST" not in c.state.warnings


def test_mock_start_stop_function():
    qlc = MockQLCClient(("WASH", "SPOT"))
    qlc.simulate_link(True)
    assert qlc.start_function_by_name("WASH")
    assert qlc.function_by_name("WASH").running
    qlc.toggle_function_by_name("WASH")
    assert not qlc.function_by_name("WASH").running


def test_sim_f1_toggles_qlc():
    c = make_controller()
    c.inject_cooked(SimCommandEvent("toggle_qlc"))
    c._sync_qlc()
    c._finish()
    assert c.state.qlc_connected is False


def test_ws_client_offline_does_not_raise():
    qlc = QlcWebSocketClient("ws://127.0.0.1:1/qlcplusWS", reconnect_seconds=0.01)
    qlc.pump(0.0)
    assert qlc.connected() is False
    qlc.pump(1.0)
    assert qlc.connected() is False
    qlc.set_grand_master(128)
    qlc.set_blackout(True)
    qlc.close()
