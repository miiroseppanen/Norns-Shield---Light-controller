"""OUTPUT pages. Read-only; no IO or QLC mutation.

Archetypes: universe=map, overview=summary, devices/network/nodes/wiz=list,
live=live data, tech=detail. In-page scrolling uses the shared viewport.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from light_console.output.dmx import nonzero_channels
from light_console.output.fixtures import PatchedFixture, fixture_activity
from light_console.output.netmode import network_page_records
from light_console.output.network import (
    KIND_LOOPBACK,
    NetIface,
    network_list_status,
    oled_iface_lines,
)
from light_console.output.nodes import ArtNetNode
from light_console.output.overview import (
    network_ok,
    node_status,
    overview_facts,
    overview_lines,
    wiz_overview,
)
from light_console.output.routing import (
    OutputRoute,
    ResolvedOutput,
    merge_routes,
    oled_route_lines,
)
from light_console.output.targets import (
    TargetId,
    detect_target,
    label_for_output_ip,
    last_octet,
)
from light_console.output.universe_map import configured_universes
from light_console.ui.vocab import ACTIVE, IDLE, RUNNING

if TYPE_CHECKING:
    from light_console.state import AppState

ROUTING_CONTENT_ROWS = 7


@dataclass(frozen=True)
class OutputItem:
    title: str
    status: str = ""
    subtitle: str = ""
    detail: tuple[str, ...] = ()
    activity: bool = False
    prefix: str = ""
    name: str = ""
    target_id: str = ""
    is_qlc_target: bool = False
    ipv4: str = ""


@dataclass(frozen=True)
class OutputPage:
    kind: str
    title: str
    offset: int = 0
    universe: int | None = None
    window: int = 0
    lines: tuple[str, ...] = ()
    items: tuple[OutputItem, ...] = ()
    archetype: str = "summary"
    empty: str = ""
    universes: tuple[int, ...] = ()


def oled_node_lines(node: ArtNetNode, status: str | None = None) -> tuple[str, ...]:
    lines = [node.name, node.ipv4]
    if node.wire_universe is not None:
        lines.append(f"ARTNET U{node.wire_universe}")
    if status:
        lines.append(status)
    return tuple(lines)


def pack_network_pages(
    ifaces: tuple[NetIface, ...],
    *,
    network_mode: str = "network",
) -> list[OutputPage]:
    shown = tuple(iface for iface in ifaces if iface.kind != KIND_LOOPBACK)
    if not shown:
        shown = ifaces
    if not shown:
        return [OutputPage("network", "NETWORK", archetype="list", empty="NO DEVICES")]
    records = network_page_records(ifaces, network_mode=network_mode)
    if not records:
        items = []
        for iface in shown:
            detail = oled_iface_lines(iface)
            items.append(
                OutputItem(title=iface.name, status=network_list_status(iface), detail=detail)
            )
        lines = tuple(line for iface in shown for line in oled_iface_lines(iface))
        return [
            OutputPage("network", "NETWORK", items=tuple(items), lines=lines, archetype="list")
        ]
    items = tuple(
        OutputItem(title=title, status=status, detail=detail) for title, status, detail in records
    )
    lines = tuple(line for _title, _status, detail in records for line in detail)
    return [OutputPage("network", "NETWORK", items=items, lines=lines, archetype="list")]


def pack_tech_pages(resolved: tuple[ResolvedOutput, ...]) -> list[OutputPage]:
    groups = [
        oled_route_lines(route, remote_name=label_for_output_ip(route.destination))
        for route in resolved
    ]
    if not groups:
        return [OutputPage("tech", "TECH", lines=("NO DATA",), archetype="detail")]
    lines = tuple(line for group in groups for line in group)
    items = tuple(OutputItem(title=line) for line in lines)
    return [OutputPage("tech", "TECH", lines=lines, items=items, archetype="detail")]


def pack_device_pages(
    fixtures: tuple[PatchedFixture, ...],
    dmx: dict[int, tuple[int, ...]],
    seen_ids: set[int],
) -> list[OutputPage]:
    if not fixtures:
        return [OutputPage("devices", "DMX DEVICES", archetype="list", empty="NO DEVICES")]
    items: list[OutputItem] = []
    lines: list[str] = []
    for fixture in fixtures:
        state = fixture_activity(fixture, dmx, seen_ids)
        name = fixture.display_name()
        prefix = f"{fixture.start_1:03d} "
        title = f"{prefix}{name}"
        subtitle = f"{fixture.channels} CH {state}"
        items.append(
            OutputItem(
                title=title,
                subtitle=subtitle,
                status=state,
                activity=state == ACTIVE,
                detail=(title, subtitle),
                prefix=prefix,
                name=name,
            )
        )
        lines.extend((title, subtitle))
    return [
        OutputPage(
            "devices",
            "DMX DEVICES",
            lines=tuple(lines),
            items=tuple(items),
            archetype="list",
        )
    ]


def pack_universe_pages(
    *,
    qlc_universes: tuple[int, ...] = (),
    routes: tuple[OutputRoute, ...] | tuple[ResolvedOutput, ...] = (),
    fixtures: tuple[PatchedFixture, ...] = (),
    view_universe: int = 1,
) -> list[OutputPage]:
    route_unis = tuple(getattr(route, "qlc_universe") for route in routes)
    unis = configured_universes(
        parsed=qlc_universes,
        routes_unis=route_unis,
        fixtures=fixtures,
    )
    view = view_universe if view_universe in unis else unis[0]
    return [
        OutputPage(
            "universe",
            f"UNIVERSE {view}",
            universe=view,
            archetype="map",
            universes=unis,
        )
    ]


def pack_live_pages(
    resolved: tuple[ResolvedOutput, ...],
    dmx: dict[int, tuple[int, ...]] | None,
) -> list[OutputPage]:
    unis = [route.qlc_universe for route in resolved] or [1]
    store = dmx or {}
    pages: list[OutputPage] = []
    for uni in unis:
        buf = store.get(uni - 1, ())
        active = nonzero_channels(buf)
        items = tuple(
            OutputItem(title=f"{channel:03d}", status=f"{value:03d}", activity=False)
            for channel, value in active
        )
        pages.append(
            OutputPage(
                "dmx",
                f"LIVE DMX U{uni}",
                universe=uni,
                window=0,
                items=items,
                lines=tuple(f"{ch:03d} {val:03d}" for ch, val in active),
                archetype="live",
                empty="NO LIVE DMX",
            )
        )
    return pages


def pack_node_pages(
    nodes: tuple[ArtNetNode, ...],
    *,
    net_ok: bool,
    qlc_running: bool,
    dmx_active: bool,
    workspace_routes: tuple[OutputRoute, ...] = (),
) -> list[OutputPage]:
    detected = detect_target(workspace_routes, nodes=nodes)
    by_name = {node.name.upper().replace(" ", ""): node for node in nodes}
    items: list[OutputItem] = [
        OutputItem(
            title="SAFE",
            status="LOOPBACK",
            detail=("SAFE / LOOPBACK", "127.0.0.1"),
            activity=False,
            name="SAFE",
            target_id=TargetId.SAFE.value,
            is_qlc_target=detected.target_id is TargetId.SAFE,
            ipv4="127.0.0.1",
        )
    ]
    for target in (TargetId.AIR2DMX, TargetId.PKNIGHT):
        node = by_name.get(target.value)
        if node is None:
            continue
        status = node_status(node, net_ok=net_ok, qlc_running=qlc_running)
        is_target = detected.target_id is target
        items.append(
            OutputItem(
                title=node.name,
                status=status,
                detail=oled_node_lines(node, status),
                activity=bool(dmx_active and is_target),
                name=node.name,
                target_id=target.value,
                is_qlc_target=is_target,
                ipv4=node.ipv4,
            )
        )
    if detected.target_id is TargetId.CUSTOM:
        ip = detected.output_ip or ""
        items.append(
            OutputItem(
                title="CUSTOM",
                status=last_octet(ip) or IDLE,
                detail=("CUSTOM", ip),
                activity=False,
                name="CUSTOM",
                target_id=TargetId.CUSTOM.value,
                is_qlc_target=True,
                ipv4=ip,
            )
        )
    elif detected.target_id is TargetId.UNKNOWN:
        items.append(
            OutputItem(
                title="UNKNOWN",
                status=IDLE,
                detail=("UNKNOWN",),
                activity=False,
                name="UNKNOWN",
                target_id=TargetId.UNKNOWN.value,
                is_qlc_target=True,
            )
        )
    first = items[0]
    return [
        OutputPage(
            "node",
            "NODES",
            items=tuple(items),
            lines=first.detail,
            archetype="list",
        )
    ]


def pack_wiz_page(
    enabled: bool,
    online: int,
    expected: int,
    *,
    tx_active: bool,
) -> list[OutputPage]:
    if not enabled:
        return []
    label, status = wiz_overview(True, online, expected)
    return [
        OutputPage(
            "wiz",
            "WIZ",
            items=(OutputItem(title=label, status=status, activity=tx_active),),
            lines=(label, status),
            archetype="list",
        )
    ]


def build_output_pages(
    ifaces: tuple[NetIface, ...],
    routes: tuple[OutputRoute, ...] | tuple[ResolvedOutput, ...],
    dmx: dict[int, tuple[int, ...]] | None = None,
    *,
    runtime_routes: tuple[OutputRoute, ...] = (),
    nodes: tuple[ArtNetNode, ...] = (),
    fixtures: tuple[PatchedFixture, ...] = (),
    seen_ids: set[int] | frozenset[int] | None = None,
    qlc_observed: str = RUNNING,
    wiz_enabled: bool = False,
    wiz_online: int = 0,
    wiz_expected: int = 6,
    wiz_tx_active: bool = False,
    qlc_universes: tuple[int, ...] = (),
    view_universe: int = 1,
    network_mode: str = "network",
) -> list[OutputPage]:
    resolved: tuple[ResolvedOutput, ...]
    workspace: tuple[OutputRoute, ...]
    if routes and isinstance(routes[0], ResolvedOutput):
        resolved = routes  # type: ignore[assignment]
        workspace = ()
    else:
        workspace = tuple(routes)  # type: ignore[arg-type]
        resolved = merge_routes(workspace, runtime_routes, ifaces)
    store = dmx or {}
    if seen_ids is None:
        seen: set[int] = set()
    elif isinstance(seen_ids, set):
        seen = seen_ids
    else:
        seen = set(seen_ids)
    net_is_ok = network_ok(ifaces or ())
    qlc_running = qlc_observed == RUNNING
    dmx_active = any(any(buf) for buf in store.values())
    facts = overview_facts(
        ifaces or (),
        nodes,
        fixtures,
        store,
        qlc_observed=qlc_observed,
        wiz_enabled=wiz_enabled,
        wiz_online=wiz_online,
        wiz_expected=wiz_expected,
        wiz_tx_active=wiz_tx_active,
        workspace_routes=workspace,
        network_mode=network_mode,
    )
    overview_items = tuple(
        OutputItem(title=kind, subtitle=name, status=value, activity=active)
        for kind, name, value, active in facts
    )
    pages: list[OutputPage] = []
    pages.extend(
        pack_universe_pages(
            qlc_universes=qlc_universes,
            routes=workspace or routes,
            fixtures=fixtures,
            view_universe=view_universe,
        )
    )
    pages.append(
        OutputPage(
            "overview",
            "OUTPUT",
            lines=overview_lines(
                ifaces or (),
                nodes,
                fixtures,
                store,
                qlc_observed=qlc_observed,
                wiz_enabled=wiz_enabled,
                wiz_online=wiz_online,
                wiz_expected=wiz_expected,
                wiz_tx_active=wiz_tx_active,
                workspace_routes=workspace,
                network_mode=network_mode,
            ),
            items=overview_items,
            archetype="summary",
        )
    )
    pages.extend(pack_device_pages(fixtures, store, seen))
    pages.extend(pack_live_pages(resolved, store))
    pages.extend(pack_network_pages(ifaces or (), network_mode=network_mode))
    pages.extend(
        pack_node_pages(
            nodes,
            net_ok=net_is_ok,
            qlc_running=qlc_running,
            dmx_active=dmx_active,
            workspace_routes=workspace,
        )
    )
    pages.extend(pack_tech_pages(resolved))
    pages.extend(
        pack_wiz_page(wiz_enabled, wiz_online, wiz_expected, tx_active=wiz_tx_active)
    )
    return pages


def build_output_pages_from_state(state: AppState) -> list[OutputPage]:
    return build_output_pages(
        state.network_ifaces,
        state.output_routes,
        state.dmx_by_universe,
        runtime_routes=state.runtime_routes,
        nodes=state.artnet_nodes,
        fixtures=state.fixtures,
        seen_ids=state.dmx_seen_ids,
        qlc_observed=state.qlc_observed,
        wiz_enabled=state.wiz_enabled,
        wiz_online=state.wiz_online,
        wiz_expected=state.wiz_expected,
        wiz_tx_active=state.wiz_tx_active,
        qlc_universes=state.qlc_universes,
        view_universe=state.output_universe,
        network_mode=state.network_mode,
    )
