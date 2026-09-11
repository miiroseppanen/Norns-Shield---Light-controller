"""NETWORK / STANDALONE mode. No Wi-Fi secrets in assertions or logs."""

from __future__ import annotations

from light_console.display.components import draw_subordinate_status, draw_toggle
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import ROW, TOGGLE_LABEL_X, TOGGLE_X
from light_console.display.renderer import Renderer
from light_console.hardware.events import ButtonEvent, EncoderEvent, E2, K3
from light_console.output.netmode import (
    AIR2DMX_MAC,
    DHCP_RANGE,
    MODE_NETWORK,
    MODE_STANDALONE,
    PRODUCTION_PI_IP,
    SSID_LIGHT_CONTROL,
    SSID_WIZ_LIGHTS,
    dhcp_range_excludes_reserved,
    light_control_role,
    network_page_records,
    parse_network_mode,
    should_auto_failover,
    toggle_filled,
)
from light_console.output.network import NetIface
from light_console.output.pages import pack_network_pages
from light_console.output.targets import TargetId, detect_target
from light_console.prefs import OperatorPrefs, load_prefs, save_prefs
from light_console.state import ScreenId
from light_console.ui.pages import (
    SYSTEM_NET_TOGGLE,
    SYSTEM_QLC_TOGGLE,
    SYSTEM_ROW_COUNT,
    SYSTEM_SHUTDOWN_ROW,
    SYSTEM_WIZ_TOGGLE,
    system_slots,
)
from light_console.ui.vocab import FAILED, NETWORK, STANDALONE, SWITCHING

from tests.conftest import make_controller


def test_missing_network_mode_pref_is_network(tmp_path):
    path = tmp_path / "prefs.yaml"
    path.write_text("wiz_enabled: false\nqlc_desired: true\n", encoding="utf-8")
    prefs = load_prefs(path)
    assert prefs.network_mode == MODE_NETWORK
    assert parse_network_mode(None) == MODE_NETWORK
    assert parse_network_mode("auto") == MODE_NETWORK


def test_explicit_network_and_standalone_prefs(tmp_path):
    path = tmp_path / "prefs.yaml"
    save_prefs(path, OperatorPrefs(network_mode=MODE_NETWORK))
    text = path.read_text()
    assert "network_mode: network" in text
    assert "psk" not in text.lower()
    assert load_prefs(path).network_mode == MODE_NETWORK
    save_prefs(path, OperatorPrefs(network_mode=MODE_STANDALONE))
    assert load_prefs(path).network_mode == MODE_STANDALONE


def test_failed_switch_keeps_previous_pref(tmp_path):
    path = tmp_path / "prefs.yaml"
    c = make_controller(prefs_path=path)
    assert c.state.network_mode == MODE_NETWORK
    c.net_service.fail_next = True
    c.set_network_mode(MODE_STANDALONE)
    assert c.state.network_mode_observed == SWITCHING
    c.net_service.settle()
    c._sync_network_mode()
    assert c.state.network_mode == MODE_NETWORK
    assert c.state.network_mode_observed == FAILED
    assert load_prefs(path).network_mode == MODE_NETWORK


def test_system_network_mode_is_one_block():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    slots = system_slots(c.state)
    assert [slot.kind for slot in slots] == ["qlc", "wiz", "net", "shutdown"]
    assert slots[2].rows == 2
    assert SYSTEM_ROW_COUNT == 4
    c.state.system_index = SYSTEM_NET_TOGGLE
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.system_index == SYSTEM_SHUTDOWN_ROW


def test_no_network_mode_detail_page():
    names = {item.value for item in ScreenId}
    assert "network_mode" not in names
    assert "net_select" not in names


def test_toggle_filled_network_outline_standalone():
    assert toggle_filled(MODE_NETWORK) is True
    assert toggle_filled(MODE_STANDALONE) is False
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    net = system_slots(c.state)[2]
    r = Renderer()
    r.force_dirty()
    fb = r.render(c.state)
    filled = Framebuffer()
    draw_toggle(filled, TOGGLE_X, net.y, True)
    assert fb.get(TOGGLE_X + 3, net.y + 3) == filled.get(TOGGLE_X + 3, net.y + 3)
    c.state.network_mode = MODE_STANDALONE
    c.state.network_mode_observed = STANDALONE
    r.force_dirty()
    fb = r.render(c.state)
    outline = Framebuffer()
    draw_toggle(outline, TOGGLE_X, net.y, False)
    assert fb.get(TOGGLE_X + 3, net.y + 3) == outline.get(TOGGLE_X + 3, net.y + 3)


def test_subordinate_switching_and_failed():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    net = system_slots(c.state)[2]
    c.state.network_mode_observed = SWITCHING
    r = Renderer()
    r.force_dirty()
    fb = r.render(c.state)
    ref = Framebuffer()
    draw_subordinate_status(ref, net.y + ROW, SWITCHING)
    for dx in range(TOGGLE_LABEL_X, TOGGLE_LABEL_X + 72):
        assert fb.get(dx, net.y + ROW + 2) == ref.get(dx, net.y + ROW + 2)
    c.state.network_mode_observed = FAILED
    r.force_dirty()
    fb = r.render(c.state)
    ref = Framebuffer()
    draw_subordinate_status(ref, net.y + ROW, FAILED)
    assert fb.get(TOGGLE_LABEL_X, net.y + ROW + 2) == ref.get(TOGGLE_LABEL_X, net.y + ROW + 2)


def test_k3_starts_one_switch_and_ignores_repeats():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_NET_TOGGLE
    wiz_before = c.state.wiz_enabled
    routes_before = c.state.output_routes
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.net_service.commands == [MODE_STANDALONE]
    assert c.state.network_mode_observed == SWITCHING
    assert c.state.network_mode == MODE_NETWORK
    assert c.state.network_mode_busy is True
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.net_service.commands == [MODE_STANDALONE]
    assert c.state.wiz_enabled is wiz_before
    assert c.state.output_routes == routes_before
    c.net_service.settle()
    c._sync_network_mode()
    assert c.state.network_mode == MODE_STANDALONE
    assert c.state.network_mode_observed == STANDALONE
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.net_service.commands[-1] == MODE_NETWORK


def test_e2_does_not_mutate_network_mode():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_NET_TOGGLE
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.net_service.commands == []
    assert c.state.network_mode == MODE_NETWORK
    assert c.state.system_index == SYSTEM_SHUTDOWN_ROW


def test_standalone_and_network_page_roles():
    ifaces = (
        NetIface("wlan0", True, "192.168.88.246", SSID_LIGHT_CONTROL, 24, kind="onboard"),
        NetIface("wlan1", False, "", "", kind="usb"),
        NetIface("lo", True, "127.0.0.1", "", kind="loopback"),
    )
    net = pack_network_pages(ifaces, network_mode=MODE_NETWORK)
    titles = [item.title for item in net[0].items]
    assert titles[0] == SSID_LIGHT_CONTROL
    assert net[0].items[0].status == "CLIENT"
    assert "CLIENT" in net[0].lines
    assert "wlan0" in net[0].lines
    assert "192.168.88.246" in net[0].lines
    assert SSID_WIZ_LIGHTS not in titles
    assert "lo" not in titles
    standalone = pack_network_pages(ifaces, network_mode=MODE_STANDALONE)
    assert standalone[0].items[0].status == "AP"
    assert "AP" in standalone[0].lines
    wiz_ifaces = (
        NetIface("wlan0", True, "192.168.88.246", SSID_LIGHT_CONTROL, 24, kind="onboard"),
        NetIface("wlan1", True, "10.42.0.5", SSID_WIZ_LIGHTS, 24, kind="usb"),
    )
    wiz_page = pack_network_pages(wiz_ifaces, network_mode=MODE_STANDALONE)
    titles = [item.title for item in wiz_page[0].items]
    assert SSID_WIZ_LIGHTS in titles
    assert SSID_LIGHT_CONTROL in titles
    assert light_control_role(MODE_STANDALONE) == "AP"


def test_busy_lock_and_rollback_standalone_to_network():
    c = make_controller(network_mode=MODE_STANDALONE)
    c.net_service.mode = MODE_STANDALONE
    c.state.network_mode = MODE_STANDALONE
    c.state.network_mode_observed = STANDALONE
    c.net_service.fail_next = True
    c.set_network_mode(MODE_NETWORK)
    assert c.state.network_mode_observed == SWITCHING
    c.net_service.settle()
    c._sync_network_mode()
    assert c.state.network_mode == MODE_STANDALONE
    assert c.state.network_mode_observed == FAILED


def test_boot_respects_persisted_mode(tmp_path):
    path = tmp_path / "prefs.yaml"
    save_prefs(path, OperatorPrefs(network_mode=MODE_STANDALONE, qlc_desired=True))
    c = make_controller(prefs_path=path)
    assert c.state.network_mode == MODE_STANDALONE
    assert c.state.network_mode_observed == STANDALONE
    assert should_auto_failover() is False


def test_mode_independent_of_qlc_target():
    c = make_controller()
    c.state.output_mode = "SAFE"
    before = c.state.output_routes
    c.set_network_mode(MODE_STANDALONE)
    c.net_service.settle()
    c._sync_network_mode()
    assert c.state.output_mode == "SAFE"
    assert c.state.output_routes == before
    assert c.net_service.workspace_writes == 0
    detected = detect_target(before)
    assert detected.target_id is TargetId.SAFE or before == ()


def test_air2dmx_not_inferred_from_242_and_production_excluded():
    assert dhcp_range_excludes_reserved(DHCP_RANGE)
    assert PRODUCTION_PI_IP not in DHCP_RANGE
    assert "192.168.88.248" not in DHCP_RANGE
    assert AIR2DMX_MAC == "3c:61:05:97:e1:93"
    records = network_page_records(
        (NetIface("wlan0", True, "192.168.88.242", SSID_LIGHT_CONTROL, 24, kind="onboard"),),
        network_mode=MODE_NETWORK,
    )
    assert records[0][0] == SSID_LIGHT_CONTROL
    assert "AIR2DMX" not in str(records)


def test_mode_switch_does_not_toggle_wiz():
    c = make_controller(wiz_enabled=False)
    c.set_network_mode(MODE_STANDALONE)
    c.net_service.settle()
    c._sync_network_mode()
    assert c.state.wiz_enabled is False
    assert c.net_service.wiz_toggles == 0
    assert PRODUCTION_PI_IP not in c.net_service.probed_hosts


def test_qlc_wiz_shutdown_still_work():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.qlc_service.commands[-1] == "stop"
    c.state.system_index = SYSTEM_WIZ_TOGGLE
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_enabled is True
    c.state.system_index = SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHUTTING_DOWN
