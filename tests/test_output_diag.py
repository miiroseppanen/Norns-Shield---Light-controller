from pathlib import Path

from light_console.display.renderer import Renderer
from light_console.display.screens import draw_output, draw_play
from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K1, K3
from light_console.output.dmx import (
    apply_channel_pairs,
    dmx_windows,
    empty_universe,
    nonzero_channels,
    parse_get_channels_values,
    DmxCache,
)
from light_console.output.network import NetIface, collect_network, parse_ip_br
from light_console.output.pages import build_output_pages
from light_console.output.routing import parse_output_routes, routing_mode
from light_console.qlc.fake import FakeTransport
from light_console.qlc.ws_client import QlcWebSocketClient
from light_console.state import ScreenId
from light_console.ui.menu import DEFERRED_MENU_ITEMS, MENU_ITEMS, menu_index_of

from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]
SHIELD = ROOT / "qlc/projects/siirtyma-shield.qxw"
REACHABLE_PY = (
    ROOT / "light_console/ui/menu.py",
    ROOT / "light_console/display/screens.py",
)


def test_production_menu_is_status_output_system():
    assert [item.label for item in MENU_ITEMS] == ["STATUS", "OUTPUT", "SYSTEM"]
    assert {item.label for item in DEFERRED_MENU_ITEMS} == {
        "SHOWS",
        "SCENES",
        "CHASERS",
        "PARAMS",
    }
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert [item.label for item in c.nav.current_items()] == ["STATUS", "OUTPUT", "SYSTEM"]
    c.state.menu_index = menu_index_of("OUTPUT")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.OUTPUT


def test_no_placeholder_strings_in_reachable_ui():
    forbidden = (
        "NYI",
        "TODO",
        "FIXME",
        "PLACEHOLDER",
        "AUTO LOAD",
        "LOAD IN QLC WEB",
        "WEB LOAD",
    )
    blobs = "\n".join(path.read_text(encoding="utf-8") for path in REACHABLE_PY)
    for needle in forbidden:
        assert needle not in blobs
    labels = " ".join(item.label for item in MENU_ITEMS)
    for needle in forbidden:
        assert needle not in labels


def test_network_model_wlan0_wlan1_and_missing():
    text = (
        "wlan0            UP             192.168.88.246/24\n"
        "eth0             UP             192.168.1.2/24\n"
    )
    parsed = parse_ip_br(text)
    assert parsed["wlan0"] == (True, "192.168.88.246")
    assert "wlan1" not in parsed
    ifaces = collect_network(
        ip_text=text,
        ssid_for=lambda name: "LIGHT-CONTROL" if name == "wlan0" else "",
    )
    by_name = {iface.name: iface for iface in ifaces}
    assert by_name["wlan0"] == NetIface("wlan0", True, "192.168.88.246", "LIGHT-CONTROL")
    assert by_name["wlan1"] == NetIface("wlan1", False, "", "")
    assert by_name["eth0"].up is True


def test_routing_from_loopback_master():
    routes = parse_output_routes(SHIELD.read_text(encoding="utf-8"))
    assert len(routes) == 2
    assert routes[0].qlc_universe == 1
    assert routes[0].plugin == "ARTNET"
    assert routes[0].destination == "127.0.0.1"
    assert routes[0].wire_universe == 0
    assert routes[0].mode == "SAFE"
    assert routes[1].qlc_universe == 2
    assert routes[1].destination == "127.0.0.1"
    assert routes[1].wire_universe == 1
    assert routing_mode(routes) == "SAFE"


def test_routing_marks_pknight_as_rig():
    text = SHIELD.read_text(encoding="utf-8").replace(
        'outputIP="127.0.0.1"', 'outputIP="192.168.88.201"', 1
    )
    routes = parse_output_routes(text)
    assert routes[0].destination == "192.168.88.201"
    assert routes[0].mode == "RIG"
    assert routing_mode(routes) == "RIG"


def test_live_dmx_nonzero_and_zero_removal():
    msg = "QLC+API|getChannelsValues|1|255|Intensity|0|2|0|Intensity|0|7|64|Intensity|0"
    pairs = parse_get_channels_values(msg)
    buf = empty_universe()
    apply_channel_pairs(buf, pairs)
    assert nonzero_channels(buf) == [(1, 255), (7, 64)]
    buf[0] = 0
    assert nonzero_channels(buf) == [(7, 64)]


def test_dmx_cache_and_reconnect_reset():
    cache = DmxCache()
    cache.begin_request(0)
    cache.ingest("QLC+API|getChannelsValues|1|10|t|0|2|20|t|0")
    assert cache.snapshot(0)[0] == 10
    cache.clear()
    assert cache.snapshot(0) is None
    assert cache.ready is False


def test_dmx_windows_paginate():
    active = [(i, 255) for i in range(1, 19)]
    windows = dmx_windows(active, 6)
    assert len(windows) == 3
    assert windows[0][0] == (1, 255)
    assert windows[-1][-1] == (18, 255)


def test_output_pages_include_network_routing_and_universes():
    ifaces = (NetIface("wlan0", True, "192.168.88.246", "LIGHT-CONTROL"),)
    routes = parse_output_routes(SHIELD.read_text(encoding="utf-8"))
    buf = empty_universe()
    buf[0] = 1
    for i in range(10):
        buf[i] = 10
    pages = build_output_pages(ifaces, routes, {0: tuple(buf), 1: tuple(empty_universe())})
    kinds = [p.kind for p in pages]
    assert kinds[0] == "network"
    assert "routing" in kinds
    dmx_pages = [p for p in pages if p.kind == "dmx"]
    assert [p.universe for p in dmx_pages][:2] == [1, 1]
    assert any(p.universe == 2 for p in dmx_pages)


def test_output_e1_cycles_and_e2_e3_k3_do_not_mutate():
    c = make_controller()
    routes = parse_output_routes(SHIELD.read_text(encoding="utf-8"))
    c.state.output_routes = routes
    c.state.network_ifaces = (
        NetIface("wlan0", True, "192.168.88.246", "LIGHT-CONTROL"),
        NetIface("wlan1", False, "", ""),
    )
    c.state.screen = ScreenId.OUTPUT
    before = list(c.qlc.channel_requests)
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.output_page == 1
    c.inject_cooked(EncoderEvent(E2, 3))
    c.inject_cooked(EncoderEvent(E3, 3))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.output_page == 1
    assert c.qlc.channel_requests == before
    assert not hasattr(c.qlc, "io") or getattr(c.qlc, "io", []) == []
    r = Renderer()
    r.render(c.state)
    assert r.fb.digest() != b"\x00" * (128 * 64)


def test_output_never_sends_desk_or_patch():
    output_py = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (ROOT / "light_console/output").glob("*.py")
    )
    output_py += (ROOT / "light_console/ui/pages.py").read_text(encoding="utf-8")
    output_py += (ROOT / "light_console/display/screens.py").read_text(encoding="utf-8")
    assert "set_simple_desk_channel" not in output_py
    assert "patch_output" not in output_py
    assert 'f"CH|' not in output_py
    assert "QLC+IO" not in output_py


def test_controller_dmx_poll_and_reconnect(tmp_path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shows.joinpath("master.qxw").write_text(SHIELD.read_text(encoding="utf-8"))
    c = make_controller(shows_dir=shows)
    assert c.state.output_routes[0].destination == "127.0.0.1"
    c.qlc.set_dmx_universe(0, {1: 255, 12: 40})
    c.qlc.set_dmx_universe(1, {33: 200})
    c.tick(now=0.0)
    assert c.state.dmx_ready is True
    assert nonzero_channels(c.state.dmx_by_universe[0]) == [(1, 255), (12, 40)]
    assert c.qlc.channel_requests[-1].startswith("QLC+API|getChannelsValues|")
    c.qlc.simulate_link(False)
    c.tick(now=3.0)
    assert c.state.dmx_ready is False
    assert c.state.dmx_by_universe == {}
    c.qlc.simulate_link(True)
    c.qlc.set_dmx_universe(0, {2: 9})
    c.tick(now=6.0)
    assert c.state.dmx_ready is True
    assert nonzero_channels(c.state.dmx_by_universe[0]) == [(2, 9)]


def test_status_screen_appliance_copy():
    c = make_controller()
    c.state.startup_status = "RUNNING"
    c.state.output_mode = "SAFE"
    r = Renderer()
    r.render(c.state)
    assert c.state.screen == ScreenId.PLAY
    draw_play(r.fb, c.state)


def test_ws_get_channels_values_roundtrip():
    fake = FakeTransport()
    fake.dmx[0] = {1: 128, 5: 7}
    qlc = QlcWebSocketClient(transport_factory=lambda: fake)
    qlc.pump(0.0)
    qlc.request_channels_values(1, 1, 8)
    qlc.pump(0.1)
    snap = qlc.dmx_snapshot(0)
    assert snap is not None
    assert snap[0] == 128
    assert snap[4] == 7
    assert fake.sent[-1] == "QLC+API|getChannelsValues|1|1|8"
    qlc.close()
    assert qlc.dmx_snapshot(0) is None


def test_offline_output_pages_do_not_crash():
    c = make_controller()
    c.qlc.simulate_link(False)
    c.tick(now=1.0)
    c.state.screen = ScreenId.OUTPUT
    r = Renderer()
    r.force_dirty()
    draw_output(r.fb, c.state)
    r.render(c.state)
