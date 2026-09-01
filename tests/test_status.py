from light_console.hardware.events import ButtonEvent, SimCommandEvent
from light_console.state import ScreenId
from light_console.status.dmx import apply_dmx
from light_console.status.midi import apply_launchpad
from light_console.status.network import apply_upstream
from light_console.status.wiz import apply_wiz_online

from tests.conftest import make_controller


def test_wiz_count_not_hardcoded_six():
    c = make_controller(wiz_expected=9, wiz_online=0)
    apply_wiz_online(c.state, 4)
    c._finish()
    assert c.state.wiz_online == 4
    assert c.state.wiz_expected == 9
    assert any("WIZ 4/9" in w for w in c.state.warnings)


def test_wiz_zero_wait():
    c = make_controller(wiz_ap_up=True, wiz_online=0, wiz_expected=6)
    c._finish()
    assert c.state.wiz_waiting
    assert any("WAIT" in w for w in c.state.warnings)


def test_missing_launchpad_warning_show_continues():
    c = make_controller()
    apply_launchpad(c.state, False)
    c.state.active_function = "SININEN"
    c._finish()
    assert "MIDI LP --" in c.state.warnings
    assert c.state.active_function == "SININEN"


def test_missing_pknight_does_not_claim_dmx_ok():
    c = make_controller()
    apply_dmx(c.state, net_ok=True, node_ok=False)
    c._finish()
    assert c.state.dmx_node_reachable is False
    assert "DMX NODE --" in c.state.warnings


def test_missing_upstream_is_ok_for_wiz():
    c = make_controller(wiz_ap_up=True, wiz_online=6)
    apply_upstream(c.state, False)
    c._finish()
    assert c.state.upstream_connected is False
    assert c.state.wiz_online == 6
    assert not any("UPSTREAM" in w for w in c.state.warnings)


def test_sim_toggles():
    c = make_controller()
    c.inject_cooked(SimCommandEvent("toggle_launchpad"))
    assert c.state.launchpad_connected is False
    c.inject_cooked(SimCommandEvent("toggle_pknight"))
    assert c.state.dmx_node_reachable is True
    c.inject_cooked(SimCommandEvent("toggle_pknight"))
    assert c.state.dmx_node_reachable is False
    c.inject_cooked(SimCommandEvent("toggle_upstream"))
    assert c.state.upstream_ssid == "LIGHT-CONTROL"
    c.inject_cooked(SimCommandEvent("wiz_set", 0))
    assert c.state.wiz_online == 0
    c.inject_cooked(SimCommandEvent("wiz_delta", 1))
    assert c.state.wiz_online == 1


def test_menu_go_opens_page():
    c = make_controller()
    c.inject_cooked(ButtonEvent(3, "long_press"))
    assert c.state.screen == ScreenId.MENU
    c.state.menu_index = 2  # WIZ
    c.inject_cooked(ButtonEvent(2, "press"))
    assert c.state.screen == ScreenId.WIZ


def test_blackout_is_local_state_not_a_stuck_output_loop():
    c = make_controller()
    c.inject_cooked(ButtonEvent(1, "press"))
    assert c.state.blackout is True
    # Dropping the UI process would drop this flag; QLC mock blackout is a separate field
    # that production must map to GM/VC so Launchpad can clear it.
    assert c.qlc.blackout is True
