from light_console.display.screens import qlc_output_label
from light_console.hardware.events import ButtonEvent, EncoderEvent, SimCommandEvent, E1, K1
from light_console.qlc.client import ConnectionState, MockQLCClient
from light_console.qlc.fake import FakeTransport
from light_console.qlc.ws_client import QlcWebSocketClient
from light_console.state import ScreenId

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
    assert qlc.connection_state() is ConnectionState.ERROR
    qlc.pump(1.0)
    assert qlc.connected() is False
    qlc.set_grand_master(128)
    qlc.set_blackout(True)
    qlc.close()
    assert qlc.connection_state() is ConnectionState.DISCONNECTED


def test_qlc_offline_at_startup_ui_works():
    c = make_controller(qlc_connected=False, qlc_project_loaded=False)
    c.qlc.simulate_link(False)
    c.tick(now=0.1)
    assert c.state.qlc_connected is False
    assert qlc_output_label(c.state) == "OFFLINE"
    before = c.state.master
    c.inject_cooked(EncoderEvent(E1, 3))
    assert c.state.master == before + 3
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.MENU


def test_qlc_successful_connection_and_loss():
    c = make_controller()
    c.tick(now=0.1)
    assert c.state.qlc_connected is True
    assert qlc_output_label(c.state) == "CONNECTED"
    c.qlc.simulate_drop()
    c.tick(now=1.0)
    assert c.state.qlc_connected is False
    assert qlc_output_label(c.state) == "OFFLINE"


def test_parameter_change_offline_then_reconnect_syncs_master():
    c = make_controller(master_dimmer=80)
    c.qlc.simulate_link(False)
    c.tick(now=0.1)
    c.qlc.gm_sends.clear()
    c.inject_cooked(EncoderEvent(E1, 10))
    assert c.state.master == 90
    assert c.qlc.gm_sends == []
    c.qlc.simulate_link(True)
    c.tick(now=1.0)
    expected = int(90 * 255 / 100)
    assert c.qlc.gm_sends[-1] == expected
    assert c.state.qlc_connected is True


def test_duplicate_master_updates_sent_once():
    c = make_controller(master_dimmer=80)
    c.tick(now=0.1)
    c.qlc.gm_sends.clear()
    c.inject_cooked(EncoderEvent(E1, 1))
    sends = list(c.qlc.gm_sends)
    c.tick(now=0.2)
    c.tick(now=0.3)
    assert c.qlc.gm_sends == sends
    assert len(sends) == 1


def test_clean_shutdown_stops_reconnect():
    c = make_controller()
    c.qlc.simulate_drop()
    c.qlc.close()
    attempts = c.qlc.reconnect_attempts
    c.tick(now=10.0)
    assert c.qlc.reconnect_attempts == attempts
    assert c.qlc.connection_state() is ConnectionState.DISCONNECTED


def test_fake_transport_connect_and_gm():
    fake = FakeTransport()
    qlc = QlcWebSocketClient(transport_factory=lambda: fake, reconnect_seconds=0.01)
    qlc.pump(0.0)
    assert qlc.connected() is True
    qlc.pump(0.1)
    assert qlc.project_loaded() is True
    assert "QLC+API|isProjectLoaded" in fake.sent
    qlc.set_grand_master(128)
    assert fake.gm == 128
    assert fake.sent[-1] == "GM_VALUE|128"
    qlc.close()
    assert qlc.connected() is False


def test_fake_transport_reconnect_after_drop():
    fake = FakeTransport()
    qlc = QlcWebSocketClient(transport_factory=lambda: fake, reconnect_seconds=0.5)
    qlc.pump(0.0)
    assert qlc.connected() is True
    fake.drop()
    qlc.pump(0.1)
    assert qlc.connected() is False
    qlc.pump(1.0)
    assert qlc.connected() is True
    assert fake.connect_count >= 2
    qlc.close()


def test_fake_transport_connect_error():
    fake = FakeTransport()
    fake.fail_connect = True
    qlc = QlcWebSocketClient(transport_factory=lambda: fake, reconnect_seconds=0.5)
    qlc.pump(0.0)
    assert qlc.connection_state() is ConnectionState.ERROR
    assert qlc.connected() is False
    qlc.close()


def test_output_screen_connected_and_offline():
    c = make_controller()
    c.state.screen = ScreenId.OUTPUT
    c.tick(now=0.1)
    assert qlc_output_label(c.state) == "CONNECTED"
    assert c.state.qlc_engine == "5.2.2"
    assert c.state.qlc_host == "localhost"
    c.qlc.simulate_link(False)
    c.tick(now=1.0)
    assert qlc_output_label(c.state) == "OFFLINE"
    from light_console.display.renderer import Renderer

    r = Renderer()
    r.render(c.state)
    assert r.fb.digest() != b"\x00" * (128 * 64)


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
