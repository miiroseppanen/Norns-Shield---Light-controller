"""Read-only QLC output routing. Never patches IO.

Keeps these facts separate:

1. QLC universe (1-based UI)
2. local Art-Net interface / line
3. local interface IP (Line UID)
4. Art-Net destination (explicit outputIP, else derived broadcast)
5. Art-Net wire universe
6. discovered node identity (elsewhere; never copied into destination)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ipaddress
import xml.etree.ElementTree as ET

from light_console.artnet.destinations import LOOPBACK_HOSTS
from light_console.output.network import NetIface
from light_console.qxw import QxwError, _DOCTYPE

SOURCE_WORKSPACE = "workspace"
SOURCE_RUNTIME = "runtime"
KIND_LOOPBACK = "LOOPBACK"
KIND_BCAST = "BCAST"
KIND_UNICAST = "UNICAST"
KIND_UNKNOWN = "--"


def is_loopback_ip(host: str) -> bool:
    h = host.strip().lower()
    return h in LOOPBACK_HOSTS or h.startswith("127.")


def ipv4_broadcast(ip: str, prefix: int | None) -> str:
    text = ip.strip()
    if not text or is_loopback_ip(text):
        return "127.0.0.1" if is_loopback_ip(text) else ""
    pfx = 24 if prefix is None else prefix
    try:
        net = ipaddress.IPv4Network(f"{text}/{pfx}", strict=False)
    except ValueError:
        return ""
    return str(net.broadcast_address)


def dest_kind_for(ip: str) -> str:
    text = ip.strip()
    if not text or text == "--":
        return KIND_UNKNOWN
    if is_loopback_ip(text):
        return KIND_LOOPBACK
    if text == "255.255.255.255" or text.endswith(".255"):
        return KIND_BCAST
    if text.count(".") == 3:
        return KIND_UNICAST
    return KIND_UNKNOWN


@dataclass(frozen=True)
class OutputRoute:
    """One patched QLC output, from workspace XML or runtime /config."""

    qlc_universe: int
    name: str
    plugin: str
    line: int | None
    line_uid: str
    output_ip: str | None
    wire_universe: int | None
    source: str = SOURCE_WORKSPACE

    @property
    def destination(self) -> str:
        return resolve_route(self).destination

    @property
    def mode(self) -> str:
        return resolve_route(self).mode

    @property
    def safe(self) -> bool:
        return self.mode == "SAFE"


@dataclass(frozen=True)
class ResolvedOutput:
    qlc_universe: int
    name: str
    plugin: str
    line: int | None
    line_uid: str
    tx_iface: str
    output_ip: str | None
    destination: str
    dest_kind: str
    wire_universe: int | None
    source: str
    file_loopback: bool
    mode: str

    @property
    def safe(self) -> bool:
        return self.mode == "SAFE"


def _iface_for_uid(uid: str, ifaces: tuple[NetIface, ...]) -> NetIface | None:
    target = uid.strip()
    if not target:
        return None
    if is_loopback_ip(target):
        return NetIface("lo", True, "127.0.0.1", "", 8)
    for iface in ifaces:
        if iface.ipv4 == target:
            return iface
    return None


def resolve_route(
    route: OutputRoute,
    ifaces: tuple[NetIface, ...] = (),
    *,
    file_loopback: bool = False,
) -> ResolvedOutput:
    iface = _iface_for_uid(route.line_uid, ifaces)
    tx = ""
    if is_loopback_ip(route.line_uid):
        tx = "lo"
    elif iface is not None:
        tx = iface.name

    explicit = (route.output_ip or "").strip() or None
    if explicit:
        dest = explicit
    elif is_loopback_ip(route.line_uid):
        dest = route.line_uid or "127.0.0.1"
        tx = tx or "lo"
    elif route.line_uid.count(".") == 3:
        prefix = iface.prefix if iface is not None else None
        dest = ipv4_broadcast(route.line_uid, prefix) or "--"
    else:
        dest = "--"

    kind = dest_kind_for(dest)
    mode = "SAFE" if kind == KIND_LOOPBACK else "RIG"
    if kind == KIND_LOOPBACK and is_loopback_ip(route.line_uid):
        tx = tx or "lo"
    return ResolvedOutput(
        qlc_universe=route.qlc_universe,
        name=route.name,
        plugin=route.plugin,
        line=route.line,
        line_uid=route.line_uid,
        tx_iface=tx,
        output_ip=explicit,
        destination=dest,
        dest_kind=kind,
        wire_universe=route.wire_universe,
        source=route.source,
        file_loopback=file_loopback,
        mode=mode,
    )


def merge_routes(
    workspace: tuple[OutputRoute, ...],
    runtime: tuple[OutputRoute, ...],
    ifaces: tuple[NetIface, ...] = (),
) -> tuple[ResolvedOutput, ...]:
    file_by_uni = {route.qlc_universe: route for route in workspace}
    live_by_uni = {route.qlc_universe: route for route in runtime}
    order: list[int] = []
    for route in workspace + runtime:
        if route.qlc_universe not in order:
            order.append(route.qlc_universe)
    out: list[ResolvedOutput] = []
    for uni in order:
        live = live_by_uni.get(uni)
        stored = file_by_uni.get(uni)
        if stored is not None and live is not None:
            combined = OutputRoute(
                qlc_universe=stored.qlc_universe,
                name=stored.name or live.name,
                plugin=live.plugin or stored.plugin,
                line=live.line if live.line is not None else stored.line,
                line_uid=live.line_uid or stored.line_uid,
                output_ip=stored.output_ip,
                wire_universe=(
                    stored.wire_universe
                    if stored.wire_universe is not None
                    else live.wire_universe
                ),
                source=SOURCE_WORKSPACE,
            )
            file_mismatch = stored.safe and not is_loopback_ip(combined.line_uid)
            out.append(resolve_route(combined, ifaces, file_loopback=file_mismatch))
            continue
        chosen = live if live is not None else stored
        if chosen is None:
            continue
        out.append(resolve_route(chosen, ifaces))
    return tuple(out)


def routing_mode(routes: tuple[OutputRoute, ...] | tuple[ResolvedOutput, ...]) -> str:
    if not routes:
        return "SAFE"
    if all(route.safe for route in routes):
        return "SAFE"
    return "RIG"


def oled_route_lines(route: ResolvedOutput, *, remote_name: str = "") -> tuple[str, ...]:
    uni = f"QLC U{route.qlc_universe}"
    if route.dest_kind == KIND_LOOPBACK or route.mode == "SAFE":
        lines = [uni, "SAFE / LOOPBACK"]
        if route.file_loopback or (route.tx_iface and route.tx_iface != "lo"):
            lines.append(f"TX {route.tx_iface or '--'}")
            lines.append("FILE LOOPBACK")
        return tuple(lines)
    wire = f"U{route.wire_universe}" if route.wire_universe is not None else "--"
    dest = route.destination or "--"
    if route.dest_kind == KIND_UNICAST:
        label = remote_name or dest
        lines = [
            uni,
            f"ARTNET {wire}",
            f"LOCAL {route.tx_iface or '--'}",
            route.line_uid or "--",
            f"REMOTE {label}",
            dest,
        ]
        if route.file_loopback:
            lines.append("FILE LOOPBACK")
        return tuple(lines)
    kind = route.dest_kind if route.dest_kind != KIND_UNKNOWN else ""
    dest_line = f"{dest} {kind}".strip()
    lines = [
        uni,
        f"ARTNET {wire}",
        f"TX {route.tx_iface or '--'}",
        dest_line,
    ]
    if route.file_loopback:
        lines.append("FILE LOOPBACK")
    return tuple(lines)


def parse_output_routes(text: str, *, source: str = SOURCE_WORKSPACE) -> tuple[OutputRoute, ...]:
    stripped = _DOCTYPE.sub("", text, count=1)
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError as exc:
        raise QxwError(f"invalid XML: {exc}") from exc
    routes: list[OutputRoute] = []
    for node in root.iter():
        local = node.tag.rsplit("}", 1)[-1]
        if local != "Universe":
            continue
        uid = node.attrib.get("ID", "")
        try:
            uni_id = int(uid)
        except ValueError:
            continue
        name = node.attrib.get("Name") or f"Universe {uni_id + 1}"
        output = None
        for child in list(node):
            if child.tag.rsplit("}", 1)[-1] == "Output":
                output = child
                break
        if output is None:
            continue
        plugin = (output.attrib.get("Plugin") or "NONE").upper()
        line_uid = (output.attrib.get("UID") or output.attrib.get("Name") or "").strip()
        line: int | None = None
        raw_line = output.attrib.get("Line")
        if raw_line not in (None, ""):
            try:
                line = int(raw_line)
            except ValueError:
                line = None
        output_ip: str | None = None
        wire: int | None = None
        for child in list(output):
            if child.tag.rsplit("}", 1)[-1] != "PluginParameters":
                continue
            ip = (child.attrib.get("outputIP") or "").strip()
            if ip:
                output_ip = ip
            raw_uni = child.attrib.get("outputUni")
            if raw_uni not in (None, ""):
                try:
                    wire = int(raw_uni)
                except ValueError:
                    wire = None
        if wire is None and plugin == "ARTNET":
            wire = uni_id
        routes.append(
            OutputRoute(
                qlc_universe=uni_id + 1,
                name=name,
                plugin=plugin,
                line=line,
                line_uid=line_uid,
                output_ip=output_ip,
                wire_universe=wire,
                source=source,
            )
        )
    return tuple(routes)


def parse_output_routes_file(path: Path) -> tuple[OutputRoute, ...]:
    try:
        return parse_output_routes(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise QxwError(f"cannot read {path}: {exc}") from exc
