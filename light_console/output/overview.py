"""OUTPUT overview: operator facts, not routing debug."""

from __future__ import annotations

from light_console.output.dmx import nonzero_channels
from light_console.output.fixtures import PatchedFixture
from light_console.output.network import KIND_LOOPBACK, NetIface
from light_console.output.nodes import ArtNetNode
from light_console.ui.vocab import ACTIVE, DISCONNECTED, IDLE, LOST, OFF, OK, SEEN
from light_console.display.activity import dmx_output_active


def primary_network(ifaces: tuple[NetIface, ...]) -> tuple[str, str]:
    usable = tuple(iface for iface in ifaces if iface.kind != KIND_LOOPBACK)
    with_ssid = tuple(iface for iface in usable if iface.ssid)
    if with_ssid:
        iface = with_ssid[0]
        return iface.ssid, OK if iface.ipv4 else DISCONNECTED
    with_ip = tuple(iface for iface in usable if iface.ipv4)
    if with_ip:
        return with_ip[0].name, OK
    if usable:
        return usable[0].name, DISCONNECTED
    return "--", DISCONNECTED


def network_ok(ifaces: tuple[NetIface, ...]) -> bool:
    return primary_network(ifaces)[1] == OK


def node_status(node: ArtNetNode, *, net_ok: bool, qlc_running: bool) -> str:
    del qlc_running
    if node.wire_universe is None:
        return IDLE
    if not net_ok:
        return LOST
    return SEEN


def relevant_dmx_node(nodes: tuple[ArtNetNode, ...]) -> ArtNetNode | None:
    for node in nodes:
        if node.wire_universe is not None:
            return node
    return nodes[0] if nodes else None


def _fixture_live(fixture: PatchedFixture, dmx: dict[int, tuple[int, ...]]) -> bool:
    buf = dmx.get(fixture.universe_id, ())
    start = fixture.address
    end = start + fixture.channels
    if not buf or start >= len(buf):
        return False
    return any(buf[start:end])


def live_counts(
    fixtures: tuple[PatchedFixture, ...],
    dmx: dict[int, tuple[int, ...]],
) -> tuple[int, int, int, int]:
    patched = len(fixtures)
    channels = sum(fx.channels for fx in fixtures)
    active_fixtures = sum(1 for fx in fixtures if _fixture_live(fx, dmx))
    live_channels = sum(len(nonzero_channels(buf)) for buf in dmx.values())
    return patched, channels, active_fixtures, live_channels


def wiz_overview(enabled: bool, online: int, expected: int) -> tuple[str, str]:
    if not enabled:
        return "WIZ", OFF
    status = OK if online >= expected and expected > 0 else LOST
    return f"WIZ {online}/{expected}", status


def overview_facts(
    ifaces: tuple[NetIface, ...],
    nodes: tuple[ArtNetNode, ...],
    fixtures: tuple[PatchedFixture, ...],
    dmx: dict[int, tuple[int, ...]],
    *,
    qlc_observed: str,
    wiz_enabled: bool,
    wiz_online: int,
    wiz_expected: int,
    wiz_tx_active: bool = False,
    workspace_routes: tuple = (),
    network_mode: str = "network",
) -> tuple[tuple[str, str, str, bool], ...]:
    """(kind, name, status, activity). Activity is live output, not availability."""
    from light_console.output.netmode import oled_mode_word
    from light_console.output.targets import detect_target

    net_name, net_status = primary_network(ifaces)
    del net_name
    live_now = dmx_output_active(dmx)
    detected = detect_target(workspace_routes, nodes=nodes)
    dmx_name = detected.oled_name
    dmx_status = ACTIVE if live_now else IDLE
    node_active = live_now
    patched, ch, live_fx, live_ch = live_counts(fixtures, dmx)
    wiz_label, wiz_status = wiz_overview(wiz_enabled, wiz_online, wiz_expected)
    wiz_active = bool(wiz_enabled and wiz_tx_active)
    if wiz_label.startswith("WIZ "):
        wiz_kind, wiz_name = "WIZ", wiz_label[4:]
    else:
        wiz_kind, wiz_name = "WIZ", ""
    return (
        ("NET", oled_mode_word(network_mode), net_status, False),
        ("DMX", dmx_name, dmx_status, node_active),
        ("DEV", "", f"{patched} / {ch} CH", False),
        ("LIVE", "", f"{live_fx} / {live_ch} CH", live_now),
        (wiz_kind, wiz_name, wiz_status, wiz_active),
    )


def overview_lines(
    ifaces: tuple[NetIface, ...],
    nodes: tuple[ArtNetNode, ...],
    fixtures: tuple[PatchedFixture, ...],
    dmx: dict[int, tuple[int, ...]],
    *,
    qlc_observed: str,
    wiz_enabled: bool,
    wiz_online: int,
    wiz_expected: int,
    wiz_tx_active: bool = False,
    workspace_routes: tuple = (),
    network_mode: str = "network",
) -> tuple[str, ...]:
    facts = overview_facts(
        ifaces,
        nodes,
        fixtures,
        dmx,
        qlc_observed=qlc_observed,
        wiz_enabled=wiz_enabled,
        wiz_online=wiz_online,
        wiz_expected=wiz_expected,
        wiz_tx_active=wiz_tx_active,
        workspace_routes=workspace_routes,
        network_mode=network_mode,
    )
    lines: list[str] = []
    for kind, name, value, _active in facts:
        parts = [kind, name, value] if name else [kind, value]
        lines.append(" ".join(part for part in parts if part).strip())
    return tuple(lines)
