from pathlib import Path

from light_console.hardware.events import ButtonEvent, EncoderEvent, E2, K3
from light_console.output.apply import RouteApplyError, apply_managed_target, wait_qlc
from light_console.output.mutate import (
    RoutePatchError,
    patch_managed_artnet,
    universe_block,
    validate_managed_patch,
    write_temp_and_validate,
)
from light_console.output.network import NetIface
from light_console.output.nodes import KNOWN_ARTNET_NODES
from light_console.output.pages import build_output_pages
from light_console.output.routing import (
    KIND_UNICAST,
    OutputRoute,
    oled_route_lines,
    parse_output_routes,
    resolve_route,
)
from light_console.output.targets import (
    AIR2DMX_FALLBACK_IP,
    AIR2DMX_MAC,
    LAN_ARTNET_LINE,
    MANAGED_QLC_UNIVERSE,
    PKNIGHT_FALLBACK_IP,
    SAFE_LINE,
    SAFE_LINE_UID,
    SAFE_OUTPUT_IP,
    TargetId,
    TargetUnavailable,
    apply_plan_for,
    detect_target,
    last_octet,
    read_arp_table,
    resolve_apply_ipv4,
)
from light_console.qlc.service import MockQlcService
from light_console.state import ScreenId
from light_console.ui.vocab import ACTIVE, FAILED, IDLE, RUNNING, SEEN, STOPPED

from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]
SHIELD = ROOT / "qlc/projects/siirtyma-shield.qxw"
IFACES = (NetIface("wlan0", True, "192.168.88.246", "LIGHT-CONTROL", 24),)
AIR_ARP = {AIR2DMX_FALLBACK_IP: AIR2DMX_MAC}


def _routes(text: str | None = None):
    return parse_output_routes(text or SHIELD.read_text(encoding="utf-8"))


def _patch_u2_ip(text: str, ip: str, *, uid: str = "192.168.88.246") -> str:
    from light_console.output.targets import ApplyPlan

    if ip.startswith("127."):
        plan = apply_plan_for(TargetId.SAFE, ip, lan_uid=SAFE_LINE_UID)
    elif ip == AIR2DMX_FALLBACK_IP:
        plan = apply_plan_for(TargetId.AIR2DMX, ip, lan_uid=uid)
    elif ip == PKNIGHT_FALLBACK_IP:
        plan = apply_plan_for(TargetId.PKNIGHT, ip, lan_uid=uid)
    else:
        plan = ApplyPlan(TargetId.CUSTOM, ip, LAN_ARTNET_LINE, uid, uid)
    return patch_managed_artnet(text, plan)


def _join(c, timeout: float = 2.0) -> None:
    thread = getattr(c, "_route_thread", None)
    if thread is not None:
        thread.join(timeout)
        assert not thread.is_alive()


def _master(tmp_path: Path) -> Path:
    shows = tmp_path / "shows"
    shows.mkdir()
    dest = shows / "master.qxw"
    dest.write_text(SHIELD.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def test_detect_safe_air2dmx_pknight_custom_unknown():
    safe = detect_target(_routes())
    assert safe.target_id is TargetId.SAFE
    assert safe.output_ip == SAFE_OUTPUT_IP
    air = detect_target(_routes(_patch_u2_ip(SHIELD.read_text(encoding="utf-8"), AIR2DMX_FALLBACK_IP)))
    assert air.target_id is TargetId.AIR2DMX
    pkn = detect_target(_routes(_patch_u2_ip(SHIELD.read_text(encoding="utf-8"), PKNIGHT_FALLBACK_IP)))
    assert pkn.target_id is TargetId.PKNIGHT
    custom_xml = _patch_u2_ip(SHIELD.read_text(encoding="utf-8"), "192.168.88.123")
    custom = detect_target(_routes(custom_xml))
    assert custom.target_id is TargetId.CUSTOM
    assert last_octet(custom.output_ip or "") == ".123"
    unknown = detect_target(())
    assert unknown.target_id is TargetId.UNKNOWN


def test_local_artnet_line_is_not_remote_destination():
    route = OutputRoute(
        qlc_universe=2,
        name="Universe 2",
        plugin="ARTNET",
        line=1,
        line_uid="192.168.88.246",
        output_ip="127.0.0.1",
        wire_universe=1,
    )
    detected = detect_target((route,))
    assert detected.target_id is TargetId.SAFE
    resolved = resolve_route(route, IFACES)
    assert resolved.line_uid == "192.168.88.246"
    assert resolved.destination == "127.0.0.1"
    assert resolved.destination != resolved.line_uid


def test_explicit_unicast_tech_splits_local_and_remote():
    route = OutputRoute(
        qlc_universe=2,
        name="Universe 2",
        plugin="ARTNET",
        line=1,
        line_uid="192.168.88.246",
        output_ip=AIR2DMX_FALLBACK_IP,
        wire_universe=1,
    )
    resolved = resolve_route(route, IFACES)
    assert resolved.dest_kind == KIND_UNICAST
    assert oled_route_lines(resolved, remote_name="AIR2DMX") == (
        "QLC U2",
        "ARTNET U1",
        "LOCAL wlan0",
        "192.168.88.246",
        "REMOTE AIR2DMX",
        AIR2DMX_FALLBACK_IP,
    )


def test_patch_only_managed_universe_preserves_unrelated_xml():
    original = SHIELD.read_text(encoding="utf-8")
    plan = apply_plan_for(TargetId.AIR2DMX, AIR2DMX_FALLBACK_IP, lan_uid="192.168.88.246")
    patched = patch_managed_artnet(original, plan)
    validate_managed_patch(original, patched, plan)
    assert universe_block(original, 0) == universe_block(patched, 0)
    before = parse_output_routes(original)
    after = parse_output_routes(patched)
    assert before[0].output_ip == after[0].output_ip == "127.0.0.1"
    assert after[1].qlc_universe == MANAGED_QLC_UNIVERSE
    assert after[1].output_ip == AIR2DMX_FALLBACK_IP
    assert after[1].line == LAN_ARTNET_LINE
    assert after[1].line_uid == "192.168.88.246"
    assert original.replace(universe_block(original, 1) or "", "X") == patched.replace(
        universe_block(patched, 1) or "", "X"
    )
    safe = apply_plan_for(TargetId.SAFE, SAFE_OUTPUT_IP, lan_uid=SAFE_LINE_UID)
    restored = patch_managed_artnet(patched, safe)
    assert restored == original


def test_temp_file_validation_rejects_invalid_xml(tmp_path):
    dest = tmp_path / "master.qxw"
    original = SHIELD.read_text(encoding="utf-8")
    dest.write_text(original)
    plan = apply_plan_for(TargetId.SAFE, SAFE_OUTPUT_IP, lan_uid=SAFE_LINE_UID)
    try:
        write_temp_and_validate(dest, original, "<not-a-workspace/>", plan)
        raise AssertionError("expected invalid XML")
    except RoutePatchError:
        pass
    assert not list(tmp_path.glob(".master.qxw.next"))
    assert dest.read_text(encoding="utf-8") == original


def test_atomic_replace_and_rollback_on_invalid_start(tmp_path):
    dest = _master(tmp_path)
    original = dest.read_bytes()
    plan = apply_plan_for(TargetId.AIR2DMX, AIR2DMX_FALLBACK_IP, lan_uid="192.168.88.246")

    class FailStart(MockQlcService):
        def set_desired(self, on: bool) -> None:
            super().set_desired(on)
            if on:
                self.observed = FAILED

        def settle(self) -> str:
            if self.observed == "STOPPING":
                self.observed = STOPPED
            return self.observed

    svc = FailStart(observed=RUNNING)
    try:
        apply_managed_target(dest, TargetId.AIR2DMX, plan, qlc_service=svc, connected=lambda: True)
        raise AssertionError("expected start failure")
    except RouteApplyError as exc:
        assert exc.restored is True
    assert dest.read_bytes() == original
    assert svc.commands[0] == "stop"
    assert "start" in svc.commands


def test_qlc_stop_start_sequence_and_no_concurrent(tmp_path):
    dest = _master(tmp_path)
    plan = apply_plan_for(TargetId.AIR2DMX, AIR2DMX_FALLBACK_IP, lan_uid="192.168.88.246")
    svc = MockQlcService(observed=RUNNING)
    stages: list[str] = []
    apply_managed_target(
        dest,
        TargetId.AIR2DMX,
        plan,
        qlc_service=svc,
        progress=stages.append,
        connected=lambda: True,
    )
    assert svc.commands == ["stop", "start"]
    assert "QLC STOPPING" in stages
    assert "QLC STARTING" in stages
    routes = parse_output_routes(dest.read_text(encoding="utf-8"))
    assert detect_target(routes).target_id is TargetId.AIR2DMX

    c = make_controller(shows_dir=dest.parent)
    c._route_arp = AIR_ARP
    c._route_ping = lambda ip: True
    c.state.route_busy = True
    before = dest.read_bytes()
    c.apply_route_target("AIR2DMX")
    assert dest.read_bytes() == before
    assert c.state.route_busy is True


def test_air2dmx_unavailable_does_not_apply_stale(tmp_path):
    dest = _master(tmp_path)
    original = dest.read_bytes()
    c = make_controller(shows_dir=dest.parent)
    c._route_arp = {}
    c._route_ping = lambda ip: True
    c.apply_route_target("AIR2DMX")
    _join(c)
    assert dest.read_bytes() == original
    assert c.state.route_op == FAILED
    assert detect_target(_routes(dest.read_text(encoding="utf-8"))).target_id is TargetId.SAFE


def test_resolve_air2dmx_requires_mac():
    try:
        resolve_apply_ipv4(TargetId.AIR2DMX, nodes=KNOWN_ARTNET_NODES, arp={}, ping=lambda ip: True)
        raise AssertionError("expected unavailable")
    except TargetUnavailable:
        pass
    ip = resolve_apply_ipv4(TargetId.AIR2DMX, nodes=KNOWN_ARTNET_NODES, arp=AIR_ARP, ping=lambda ip: True)
    assert ip == AIR2DMX_FALLBACK_IP
    ip = resolve_apply_ipv4(
        TargetId.PKNIGHT, nodes=KNOWN_ARTNET_NODES, arp={}, ping=lambda ip: ip == PKNIGHT_FALLBACK_IP
    )
    assert ip == PKNIGHT_FALLBACK_IP


def test_node_nav_and_detail_do_not_mutate_explicit_set_target_does(tmp_path):
    dest = _master(tmp_path)
    c = make_controller(shows_dir=dest.parent)
    c._route_arp = AIR_ARP
    c._route_ping = lambda ip: True
    c.state.network_ifaces = IFACES
    c.state.artnet_nodes = KNOWN_ARTNET_NODES
    c.state.screen = ScreenId.OUTPUT
    pages = build_output_pages_from_controller(c)
    node_i = next(i for i, page in enumerate(pages) if page.kind == "node")
    c.state.output_page = node_i
    before = dest.read_bytes()
    c.inject_cooked(EncoderEvent(E2, 1))
    assert dest.read_bytes() == before
    pages = build_output_pages_from_controller(c)
    focused = pages[node_i].items[c.state.output_focus]
    assert focused.target_id == TargetId.AIR2DMX.value
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.output_detail is True
    assert dest.read_bytes() == before
    c.inject_cooked(ButtonEvent(K3, "press"))
    _join(c)
    after = dest.read_text(encoding="utf-8")
    assert dest.read_bytes() != before
    detected = detect_target(parse_output_routes(after))
    assert detected.target_id is TargetId.AIR2DMX
    assert universe_block(before.decode("utf-8"), 0) == universe_block(after, 0)
    c.apply_route_target("SAFE")
    _join(c)
    safe = detect_target(parse_output_routes(dest.read_text(encoding="utf-8")))
    assert safe.target_id is TargetId.SAFE
    assert parse_output_routes(dest.read_text(encoding="utf-8"))[1].line == SAFE_LINE
    assert parse_output_routes(dest.read_text(encoding="utf-8"))[1].line_uid == SAFE_LINE_UID


def build_output_pages_from_controller(c):
    return build_output_pages(
        c.state.network_ifaces,
        c.state.output_routes,
        c.state.dmx_by_universe,
        runtime_routes=c.state.runtime_routes,
        nodes=c.state.artnet_nodes,
        qlc_observed=c.state.qlc_observed,
    )


def test_node_status_independent_from_target_and_activity(tmp_path):
    dest = _master(tmp_path)
    c = make_controller(shows_dir=dest.parent)
    c.state.network_ifaces = IFACES
    pages = build_output_pages_from_controller(c)
    nodes = next(page for page in pages if page.kind == "node")
    by_title = {item.title: item for item in nodes.items}
    assert by_title["SAFE"].is_qlc_target is True
    assert by_title["AIR2DMX"].is_qlc_target is False
    assert by_title["AIR2DMX"].status == SEEN
    assert by_title["AIR2DMX"].activity is False
    assert by_title["PKNight"].status == IDLE
    overview = next(page for page in pages if page.kind == "overview")
    dmx = next(item for item in overview.items if item.title == "DMX")
    assert dmx.subtitle == "SAFE"
    assert dmx.status == IDLE
    assert dmx.activity is False


def test_overview_follows_persisted_route_not_discovery(tmp_path):
    dest = _master(tmp_path)
    plan = apply_plan_for(TargetId.PKNIGHT, PKNIGHT_FALLBACK_IP, lan_uid="192.168.88.246")
    dest.write_text(patch_managed_artnet(dest.read_text(encoding="utf-8"), plan), encoding="utf-8")
    pages = build_output_pages(
        IFACES,
        parse_output_routes(dest.read_text(encoding="utf-8")),
        nodes=KNOWN_ARTNET_NODES,
        qlc_observed=RUNNING,
    )
    overview = next(item for item in pages if item.kind == "overview")
    dmx = next(item for item in overview.items if item.title == "DMX")
    assert dmx.subtitle == "PKNIGHT"
    assert "AIR2DMX" not in " ".join(overview.lines)
    live = {1: tuple([10] + [0] * 511)}
    pages_live = build_output_pages(
        IFACES,
        parse_output_routes(dest.read_text(encoding="utf-8")),
        live,
        nodes=KNOWN_ARTNET_NODES,
        qlc_observed=RUNNING,
    )
    dmx_live = next(
        item
        for item in next(p for p in pages_live if p.kind == "overview").items
        if item.title == "DMX"
    )
    assert dmx_live.status == ACTIVE
    nodes = next(page for page in pages_live if page.kind == "node")
    air = next(item for item in nodes.items if item.title == "AIR2DMX")
    pkn = next(item for item in nodes.items if item.title == "PKNight")
    assert air.activity is False
    assert pkn.activity is True
    assert air.status == SEEN
    assert pkn.is_qlc_target is True


def test_app_restart_derives_target_from_qxw(tmp_path):
    dest = _master(tmp_path)
    plan = apply_plan_for(TargetId.AIR2DMX, AIR2DMX_FALLBACK_IP, lan_uid="192.168.88.246")
    dest.write_text(patch_managed_artnet(dest.read_text(encoding="utf-8"), plan), encoding="utf-8")
    c = make_controller(shows_dir=dest.parent)
    detected = detect_target(c.state.output_routes)
    assert detected.target_id is TargetId.AIR2DMX
    pages = build_output_pages_from_controller(c)
    dmx = next(
        item
        for item in next(p for p in pages if p.kind == "overview").items
        if item.title == "DMX"
    )
    assert dmx.subtitle == "AIR2DMX"


def test_read_arp_and_wait_qlc():
    table = read_arp_table(
        "IP address       HW type     Flags       HW address            Mask     Device\n"
        "192.168.88.242   0x1         0x2         3c:61:05:97:e1:93     *        wlan0\n"
        "192.168.88.1     0x1         0x0         00:00:00:00:00:00     *        wlan0\n"
    )
    assert table[AIR2DMX_FALLBACK_IP] == AIR2DMX_MAC
    assert "192.168.88.1" not in table
    svc = MockQlcService(observed=RUNNING)
    svc.set_desired(False)
    assert wait_qlc(svc, STOPPED, timeout=1.0)
