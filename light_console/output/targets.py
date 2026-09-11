"""QLC Art-Net destination targets. Workspace outputIP is the source of truth.

Local Art-Net line UID (wlan0 / 192.168.88.246) is the transmit interface.
It is never treated as the remote destination.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import subprocess

from light_console.output.nodes import ArtNetNode
from light_console.output.routing import OutputRoute, is_loopback_ip

# QLC UI Universe 2 / XML <Universe ID="1"> — wired PAR + fog.
# Universe 1 / XML ID 0 is WiZ loopback and must not follow this selector.
MANAGED_XML_UNIVERSE_ID = 1
MANAGED_QLC_UNIVERSE = 2

SAFE_OUTPUT_IP = "127.0.0.1"
SAFE_LINE = 0
SAFE_LINE_UID = "127.0.0.1"
LAN_ARTNET_LINE = 1
DEFAULT_LAN_UID = "192.168.88.246"
PROD_PI = "192.168.88.248"

AIR2DMX_NAME = "AIR2DMX"
AIR2DMX_MAC = "3c:61:05:97:e1:93"
AIR2DMX_FALLBACK_IP = "192.168.88.242"
PKNIGHT_NAME = "PKNight"
PKNIGHT_FALLBACK_IP = "192.168.88.201"


class TargetId(str, Enum):
    SAFE = "SAFE"
    AIR2DMX = "AIR2DMX"
    PKNIGHT = "PKNIGHT"
    CUSTOM = "CUSTOM"
    UNKNOWN = "UNKNOWN"


APPLYABLE_TARGETS = frozenset({TargetId.SAFE, TargetId.AIR2DMX, TargetId.PKNIGHT})

FORBIDDEN_APPLY_HOSTS = frozenset(
    {
        PROD_PI,
        "192.168.88.255",
        "255.255.255.255",
    }
)


@dataclass(frozen=True)
class DetectedTarget:
    target_id: TargetId
    output_ip: str | None
    managed: OutputRoute | None = None

    @property
    def oled_name(self) -> str:
        if self.target_id is TargetId.CUSTOM and self.output_ip:
            return "CUSTOM"
        if self.target_id is TargetId.SAFE:
            return "SAFE"
        return self.target_id.value

    @property
    def last_octet(self) -> str:
        return last_octet(self.output_ip or "")


@dataclass(frozen=True)
class ApplyPlan:
    target_id: TargetId
    output_ip: str
    line: int
    line_uid: str
    line_name: str


class TargetUnavailable(ValueError):
    """Known target cannot be resolved to a verified IPv4 destination."""


def last_octet(ip: str) -> str:
    parts = ip.strip().split(".")
    if len(parts) == 4 and parts[-1].isdigit():
        return f".{parts[-1]}"
    return ip.strip()


def label_for_output_ip(ip: str) -> str:
    text = (ip or "").strip()
    if not text:
        return ""
    if is_loopback_ip(text):
        return "LOOPBACK"
    if text == AIR2DMX_FALLBACK_IP:
        return TargetId.AIR2DMX.value
    if text == PKNIGHT_FALLBACK_IP:
        return TargetId.PKNIGHT.value
    return TargetId.CUSTOM.value


def managed_route(routes: tuple[OutputRoute, ...]) -> OutputRoute | None:
    matches = [
        route
        for route in routes
        if route.qlc_universe == MANAGED_QLC_UNIVERSE and route.plugin == "ARTNET"
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def detect_target(
    routes: tuple[OutputRoute, ...],
    *,
    nodes: tuple[ArtNetNode, ...] = (),
    arp: dict[str, str] | None = None,
) -> DetectedTarget:
    route = managed_route(routes)
    if route is None:
        return DetectedTarget(TargetId.UNKNOWN, None, None)
    ip = (route.output_ip or "").strip()
    if not ip:
        if is_loopback_ip(route.line_uid):
            return DetectedTarget(TargetId.SAFE, route.line_uid or SAFE_OUTPUT_IP, route)
        return DetectedTarget(TargetId.UNKNOWN, None, route)
    if is_loopback_ip(ip):
        return DetectedTarget(TargetId.SAFE, ip, route)
    identified = _identify_ip(ip, nodes=nodes, arp=arp)
    return DetectedTarget(identified, ip, route)


def _identify_ip(
    ip: str,
    *,
    nodes: tuple[ArtNetNode, ...],
    arp: dict[str, str] | None,
) -> TargetId:
    mac = (arp or {}).get(ip, "").lower()
    if mac and mac == AIR2DMX_MAC:
        return TargetId.AIR2DMX
    for node in nodes:
        if node.ipv4 != ip:
            continue
        key = node.name.upper().replace(" ", "")
        if key == TargetId.AIR2DMX.value:
            return TargetId.AIR2DMX
        if key == TargetId.PKNIGHT.value:
            return TargetId.PKNIGHT
    if ip == AIR2DMX_FALLBACK_IP:
        return TargetId.AIR2DMX
    if ip == PKNIGHT_FALLBACK_IP:
        return TargetId.PKNIGHT
    return TargetId.CUSTOM


def is_forbidden_apply_host(ip: str) -> bool:
    text = ip.strip()
    if text in FORBIDDEN_APPLY_HOSTS:
        return True
    if text.startswith("10.42."):
        return True
    return False


def read_arp_table(text: str | None = None) -> dict[str, str]:
    """Map IPv4 -> MAC from /proc/net/arp (or injected text)."""
    if text is None:
        try:
            text = Path("/proc/net/arp").read_text(encoding="utf-8")
        except OSError:
            return {}
    table: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        ip, mac = parts[0], parts[3].lower()
        if mac.count(":") != 5 or mac == "00:00:00:00:00:00":
            continue
        table[ip] = mac
    return table


def lan_line_uid(ifaces_ipv4: dict[str, str] | None = None) -> str:
    if ifaces_ipv4:
        wlan0 = (ifaces_ipv4.get("wlan0") or "").strip()
        if wlan0:
            return wlan0
    return DEFAULT_LAN_UID


def apply_plan_for(target_id: TargetId, output_ip: str, *, lan_uid: str) -> ApplyPlan:
    if is_forbidden_apply_host(output_ip):
        raise TargetUnavailable("destination is forbidden")
    if target_id is TargetId.SAFE:
        return ApplyPlan(
            target_id=TargetId.SAFE,
            output_ip=SAFE_OUTPUT_IP,
            line=SAFE_LINE,
            line_uid=SAFE_LINE_UID,
            line_name=SAFE_LINE_UID,
        )
    return ApplyPlan(
        target_id=target_id,
        output_ip=output_ip,
        line=LAN_ARTNET_LINE,
        line_uid=lan_uid,
        line_name=lan_uid,
    )


def resolve_apply_ipv4(
    target_id: TargetId,
    *,
    nodes: tuple[ArtNetNode, ...] = (),
    arp: dict[str, str] | None = None,
    ping=None,
) -> str:
    if target_id is TargetId.SAFE:
        return SAFE_OUTPUT_IP
    if target_id is TargetId.AIR2DMX:
        return _resolve_air2dmx(nodes=nodes, arp=arp or {}, ping=ping)
    if target_id is TargetId.PKNIGHT:
        return _resolve_pknight(nodes=nodes, ping=ping)
    raise TargetUnavailable("not an applyable target")


def _resolve_air2dmx(
    *,
    nodes: tuple[ArtNetNode, ...],
    arp: dict[str, str],
    ping,
) -> str:
    candidates: list[str] = []
    for node in nodes:
        if node.name.upper().replace(" ", "") != TargetId.AIR2DMX.value:
            continue
        if node.ipv4:
            candidates.append(node.ipv4)
    for ip, mac in arp.items():
        if mac.lower() == AIR2DMX_MAC and ip not in candidates:
            candidates.append(ip)
    if AIR2DMX_FALLBACK_IP not in candidates:
        candidates.append(AIR2DMX_FALLBACK_IP)
    for ip in candidates:
        if is_forbidden_apply_host(ip):
            continue
        mac = arp.get(ip, "").lower()
        if mac == AIR2DMX_MAC:
            return ip
        if mac:
            continue
        if ping is None:
            continue
        if not ping(ip):
            continue
        # Ping alone is not identity. Require ARP MAC after reachability.
        raise TargetUnavailable("AIR2DMX MAC not confirmed")
    raise TargetUnavailable("AIR2DMX unavailable")


def _resolve_pknight(*, nodes: tuple[ArtNetNode, ...], ping) -> str:
    candidates: list[str] = []
    for node in nodes:
        if node.name.upper().replace(" ", "") != TargetId.PKNIGHT.value:
            continue
        if node.ipv4:
            candidates.append(node.ipv4)
    if PKNIGHT_FALLBACK_IP not in candidates:
        candidates.append(PKNIGHT_FALLBACK_IP)
    for ip in candidates:
        if is_forbidden_apply_host(ip):
            continue
        if ping is not None and not ping(ip):
            continue
        if ping is None:
            raise TargetUnavailable("PKNight identity not verified")
        return ip
    raise TargetUnavailable("PKNight unavailable")


def icmp_reachable(ip: str) -> bool:
    if is_forbidden_apply_host(ip):
        return False
    try:
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            capture_output=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0
