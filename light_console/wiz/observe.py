"""Transient WiZ observation. Not persisted. Not mixed into map identity.

Reads the local bridge status file only. Never probes lamps, DHCP, or UDP.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from light_console.wiz.device_map import normalize_mac

MAX_OBSERVED_BYTES = 65536
_DEFAULT_OBSERVED = "/tmp/wizbridge.status"


class Availability(str, Enum):
    UNKNOWN = "UNKNOWN"
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class DiscoveryKind(str, Enum):
    KNOWN = "KNOWN"
    NEW = "NEW"


@dataclass(frozen=True)
class WizObservedDevice:
    id: str
    observed_ip: str | None = None
    availability: Availability = Availability.UNKNOWN
    discovery: DiscoveryKind = DiscoveryKind.KNOWN
    last_seen: float | None = None
    configured: bool = False
    dmx_active: bool = False
    dmx_last_change: float | None = None


@dataclass(frozen=True)
class WizObservedSnapshot:
    """Fail-closed view of configured/observed WiZ devices."""

    observations: tuple[WizObservedDevice, ...] = ()
    configured: int = 0
    online: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def default_observed_path() -> Path:
    env = os.environ.get("WIZBRIDGE_OBSERVED", "").strip()
    if env:
        return Path(env)
    return Path(_DEFAULT_OBSERVED)


def empty_observed_snapshot(*, error: str = "") -> WizObservedSnapshot:
    return WizObservedSnapshot(error=error)


def configured_online_count(observations: tuple[WizObservedDevice, ...]) -> int:
    return sum(
        1
        for item in observations
        if item.configured and item.availability is Availability.ONLINE
    )


def _parse_availability(value: object) -> Availability:
    word = str(value or "").strip().upper()
    if word == Availability.ONLINE.value:
        return Availability.ONLINE
    if word == Availability.OFFLINE.value:
        return Availability.OFFLINE
    return Availability.UNKNOWN


def _parse_discovery(value: object, *, configured: bool) -> DiscoveryKind:
    word = str(value or "").strip().upper()
    if word == DiscoveryKind.NEW.value or not configured:
        return DiscoveryKind.NEW
    return DiscoveryKind.KNOWN


def _parse_last_seen(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _parse_ip(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _parse_device_row(raw: object) -> WizObservedDevice | None:
    if not isinstance(raw, dict):
        return None
    try:
        mac = normalize_mac(str(raw.get("id") or raw.get("mac") or ""))
    except Exception:
        return None
    configured = raw.get("configured") is True
    availability = _parse_availability(raw.get("availability"))
    dmx_active = configured and raw.get("dmx_active") is True
    return WizObservedDevice(
        id=mac,
        observed_ip=_parse_ip(raw.get("observed_ip") or raw.get("ip")),
        availability=availability,
        discovery=_parse_discovery(raw.get("discovery"), configured=configured),
        last_seen=_parse_last_seen(raw.get("last_seen")),
        configured=configured,
        dmx_active=dmx_active,
        dmx_last_change=_parse_last_seen(raw.get("dmx_last_change")),
    )


def parse_observed_status(text: str) -> WizObservedSnapshot:
    """Parse bridge JSON. Missing/malformed/partial → no available devices."""
    try:
        if not isinstance(text, str) or not text.strip():
            return empty_observed_snapshot(error="malformed")
        doc = json.loads(text)
        if not isinstance(doc, dict):
            return empty_observed_snapshot(error="malformed")
        rows = doc.get("devices", [])
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            return empty_observed_snapshot(error="malformed")
        seen: set[str] = set()
        observations: list[WizObservedDevice] = []
        for raw in rows:
            item = _parse_device_row(raw)
            if item is None or item.id in seen:
                continue
            seen.add(item.id)
            observations.append(item)
        snap_obs = tuple(observations)
        configured = sum(1 for item in snap_obs if item.configured)
        return WizObservedSnapshot(
            observations=snap_obs,
            configured=configured,
            online=configured_online_count(snap_obs),
        )
    except Exception:
        return empty_observed_snapshot(error="malformed")


def read_observed_status(path: Path | None = None) -> WizObservedSnapshot:
    """Local file read only. Missing or unreadable → empty snapshot."""
    target = path if path is not None else default_observed_path()
    try:
        size = target.stat().st_size
    except OSError:
        return empty_observed_snapshot(error="missing")
    if size > MAX_OBSERVED_BYTES:
        return empty_observed_snapshot(error="malformed")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeError:
        return empty_observed_snapshot(error="malformed")
    except OSError:
        return empty_observed_snapshot(error="missing")
    return parse_observed_status(text)
