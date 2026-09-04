"""Read-only QLC output routing parsed from a workspace. Never patches IO."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from light_console.artnet.destinations import LOOPBACK_HOSTS, classify_destination
from light_console.qxw import QxwError, _DOCTYPE


@dataclass(frozen=True)
class OutputRoute:
    qlc_universe: int
    name: str
    plugin: str
    destination: str
    wire_universe: int | None
    mode: str

    @property
    def safe(self) -> bool:
        return self.mode == "SAFE"


def parse_output_routes(text: str) -> tuple[OutputRoute, ...]:
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
        plugin = output.attrib.get("Plugin") or "NONE"
        dest = (
            output.attrib.get("UID")
            or output.attrib.get("Name")
            or ""
        )
        wire: int | None = None
        for child in list(output):
            if child.tag.rsplit("}", 1)[-1] != "PluginParameters":
                continue
            ip = child.attrib.get("outputIP")
            if ip:
                dest = ip
            raw_uni = child.attrib.get("outputUni")
            if raw_uni is not None and raw_uni != "":
                try:
                    wire = int(raw_uni)
                except ValueError:
                    wire = None
        if wire is None and plugin.lower() == "artnet":
            wire = uni_id
        dest = dest or "--"
        if dest.strip().lower() in LOOPBACK_HOSTS or dest.startswith("127."):
            mode = "SAFE"
        else:
            mode = "SAFE" if classify_destination(dest).value == "safe_loopback" else "RIG"
        routes.append(
            OutputRoute(
                qlc_universe=uni_id + 1,
                name=name,
                plugin=plugin.upper(),
                destination=dest,
                wire_universe=wire,
                mode=mode,
            )
        )
    return tuple(routes)


def parse_output_routes_file(path: Path) -> tuple[OutputRoute, ...]:
    try:
        return parse_output_routes(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise QxwError(f"cannot read {path}: {exc}") from exc


def routing_mode(routes: tuple[OutputRoute, ...]) -> str:
    if not routes:
        return "SAFE"
    if all(route.safe for route in routes):
        return "SAFE"
    return "RIG"
