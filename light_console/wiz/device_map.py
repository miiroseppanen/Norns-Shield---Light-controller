"""Persistent WiZ map: MAC identity, stable slots, atomic JSON."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
START_CHANNEL = 1
CHANNELS_PER_FIXTURE = 6
DMX_MAX = 512
WIZ_MAX_SLOTS = DMX_MAX // CHANNELS_PER_FIXTURE
WIZ_USED_CHANNELS = WIZ_MAX_SLOTS * CHANNELS_PER_FIXTURE
SCHEMA_MAX_SLOTS = WIZ_MAX_SLOTS
# Historical name for the retired 7-slot QLC v1 patch cap. Product cap is one universe.
WIZ_V1_PATCH_SLOTS = WIZ_MAX_SLOTS
LABEL_MAX_LEN = 40
MAP_FILENAME = "map.json"
LEGACY_FILENAME = "fixtures.json"
LAST_GOOD_SUFFIX = ".last-good"
_MAC_HEX_LEN = 12


class WizMapError(ValueError):
    """Map parse or persistence error."""


class WizMapCorruptError(WizMapError):
    """Input is not usable JSON / not an object. Never coerced to empty."""


class WizMapValidationError(WizMapError):
    """Well-formed JSON that fails the map schema."""


@dataclass(frozen=True)
class WizMappedDevice:
    id: str
    slot: int
    enabled: bool = True
    label: str = ""


@dataclass(frozen=True)
class WizDeviceMap:
    version: int = SCHEMA_VERSION
    start_channel: int = START_CHANNEL
    channels_per_fixture: int = CHANNELS_PER_FIXTURE
    devices: tuple[WizMappedDevice, ...] = ()

    @property
    def exceeds_v1_patch(self) -> bool:
        """True when a slot is past one DMX universe. Valid maps never set this."""
        return any(device.slot > WIZ_MAX_SLOTS for device in self.devices)


def default_map_path() -> Path:
    return Path.home() / ".config" / "wizbridge" / MAP_FILENAME


def default_fixtures_path() -> Path:
    return Path.home() / ".config" / "wizbridge" / LEGACY_FILENAME


def last_good_path(path: Path) -> Path:
    return path.with_name(path.name + LAST_GOOD_SUFFIX)


def dmx_start(slot: int) -> int:
    return START_CHANNEL + (int(slot) - 1) * CHANNELS_PER_FIXTURE


def dmx_end(slot: int) -> int:
    return dmx_start(slot) + CHANNELS_PER_FIXTURE - 1


def dmx_span(slot: int) -> tuple[int, int]:
    return dmx_start(slot), dmx_end(slot)


def dmx_index0(slot: int) -> int:
    """Zero-based Art-Net/DMX start index for a 1-based slot."""
    return (int(slot) - 1) * CHANNELS_PER_FIXTURE


def dmx_index0_span(slot: int) -> tuple[int, int]:
    start = dmx_index0(slot)
    return start, start + CHANNELS_PER_FIXTURE - 1


def format_dmx_span(slot: int) -> str:
    start, end = dmx_span(slot)
    return f"CH{start:03d}-{end:03d}"


def normalize_mac(value: object) -> str:
    """Canonical persistent id: lowercase 12 hex characters."""
    if not isinstance(value, str):
        raise WizMapValidationError("MAC must be a string")
    raw = value.strip()
    if not raw:
        raise WizMapValidationError("MAC is empty")
    compact: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch in ":-":
            i += 1
            continue
        compact.append(ch)
        i += 1
    text = "".join(compact).lower()
    if len(text) != _MAC_HEX_LEN:
        raise WizMapValidationError("MAC must be 12 hex characters")
    try:
        int(text, 16)
    except ValueError as exc:
        raise WizMapValidationError("MAC must be 12 hex characters") from exc
    if any(ch not in "0123456789abcdef" for ch in text):
        raise WizMapValidationError("MAC must be 12 hex characters")
    return text


def _clean_label(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise WizMapValidationError("label must be a string")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise WizMapValidationError("label contains invalid characters")
    text = value.strip()
    if len(text) > LABEL_MAX_LEN:
        raise WizMapValidationError(f"label longer than {LABEL_MAX_LEN} characters")
    return text


def _require_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WizMapValidationError(f"{name} must be an integer")
    return value


def _require_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise WizMapValidationError(f"{name} must be a boolean")
    return value


def validate_map(device_map: WizDeviceMap) -> WizDeviceMap:
    if device_map.version != SCHEMA_VERSION:
        raise WizMapValidationError(f"unsupported map version {device_map.version}")
    if device_map.start_channel != START_CHANNEL:
        raise WizMapValidationError("start_channel must be 1")
    if device_map.channels_per_fixture != CHANNELS_PER_FIXTURE:
        raise WizMapValidationError("channels_per_fixture must be 6")
    seen_ids: set[str] = set()
    seen_slots: set[int] = set()
    spans: list[tuple[int, int, int]] = []
    for device in device_map.devices:
        mac = normalize_mac(device.id)
        if mac != device.id:
            raise WizMapValidationError("device id must be a normalized MAC")
        if mac in seen_ids:
            raise WizMapValidationError(f"duplicate MAC {mac}")
        seen_ids.add(mac)
        slot = device.slot
        if slot < 1:
            raise WizMapValidationError("slot must be >= 1")
        if slot > WIZ_MAX_SLOTS:
            raise WizMapValidationError(f"slot {slot} exceeds schema maximum {WIZ_MAX_SLOTS}")
        end = dmx_end(slot)
        if end > DMX_MAX:
            raise WizMapValidationError(f"slot {slot} ends at DMX {end} (> {DMX_MAX})")
        if slot in seen_slots:
            raise WizMapValidationError(f"duplicate slot {slot}")
        seen_slots.add(slot)
        start = dmx_start(slot)
        spans.append((start, end, slot))
        if not isinstance(device.enabled, bool):
            raise WizMapValidationError("enabled must be a boolean")
        _clean_label(device.label)
    spans.sort()
    for i in range(1, len(spans)):
        prev_start, prev_end, prev_slot = spans[i - 1]
        start, end, slot = spans[i]
        if start <= prev_end:
            raise WizMapValidationError(
                f"slots {prev_slot} and {slot} overlap ({prev_start}-{prev_end} / {start}-{end})"
            )
    return device_map


def _parse_device(item: object) -> WizMappedDevice:
    if not isinstance(item, dict):
        raise WizMapValidationError("device entry must be an object")
    mac = normalize_mac(item.get("id", item.get("mac")))
    slot = _require_int(item.get("slot"), "slot")
    enabled = True if "enabled" not in item else _require_bool(item.get("enabled"), "enabled")
    label = _clean_label(item.get("label", ""))
    if "ip" in item:
        raise WizMapValidationError("persistent map must not store IP addresses")
    return WizMappedDevice(id=mac, slot=slot, enabled=enabled, label=label)


def parse_map_document(data: object) -> WizDeviceMap:
    if not isinstance(data, dict):
        raise WizMapCorruptError("map root must be an object")
    if "version" not in data or "devices" not in data:
        raise WizMapValidationError("map requires version and devices")
    version = _require_int(data.get("version"), "version")
    start = START_CHANNEL if "start_channel" not in data else _require_int(
        data.get("start_channel"), "start_channel"
    )
    channels = CHANNELS_PER_FIXTURE if "channels_per_fixture" not in data else _require_int(
        data.get("channels_per_fixture"), "channels_per_fixture"
    )
    raw_devices = data.get("devices")
    if not isinstance(raw_devices, list):
        raise WizMapValidationError("devices must be a list")
    devices = tuple(_parse_device(item) for item in raw_devices)
    return validate_map(
        WizDeviceMap(
            version=version,
            start_channel=start,
            channels_per_fixture=channels,
            devices=devices,
        )
    )


def parse_map_text(text: str) -> WizDeviceMap:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WizMapCorruptError(f"corrupt map JSON: {exc}") from exc
    if data is None:
        raise WizMapCorruptError("map JSON is null")
    return parse_map_document(data)


def parse_legacy_document(data: object) -> WizDeviceMap:
    """Convert legacy fixtures.json. Does not write. Preserves slot order."""
    if not isinstance(data, dict):
        raise WizMapCorruptError("legacy fixtures root must be an object")
    start = START_CHANNEL if "start_channel" not in data else _require_int(
        data.get("start_channel"), "start_channel"
    )
    channels = CHANNELS_PER_FIXTURE if "channels_per_fixture" not in data else _require_int(
        data.get("channels_per_fixture"), "channels_per_fixture"
    )
    raw = data.get("fixtures")
    if raw is None:
        raise WizMapValidationError("legacy fixtures list is missing")
    if not isinstance(raw, list):
        raise WizMapValidationError("legacy fixtures must be a list")
    devices: list[WizMappedDevice] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise WizMapValidationError("legacy fixture entry must be an object")
        mac = normalize_mac(item.get("mac", item.get("id")))
        if "slot" in item:
            slot = _require_int(item.get("slot"), "slot")
        else:
            slot = index + 1
        devices.append(WizMappedDevice(id=mac, slot=slot, enabled=True, label=""))
    return validate_map(
        WizDeviceMap(
            version=SCHEMA_VERSION,
            start_channel=start,
            channels_per_fixture=channels,
            devices=tuple(devices),
        )
    )


def parse_legacy_text(text: str) -> WizDeviceMap:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WizMapCorruptError(f"corrupt legacy fixtures JSON: {exc}") from exc
    if data is None:
        raise WizMapCorruptError("legacy fixtures JSON is null")
    return parse_legacy_document(data)


def parse_legacy_file(path: Path) -> WizDeviceMap:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WizMapError(f"cannot read {path}: {exc}") from exc
    return parse_legacy_text(text)


def map_to_payload(device_map: WizDeviceMap) -> dict[str, Any]:
    validate_map(device_map)
    ordered = sorted(device_map.devices, key=lambda item: (item.slot, item.id))
    return {
        "version": device_map.version,
        "start_channel": device_map.start_channel,
        "channels_per_fixture": device_map.channels_per_fixture,
        "devices": [
            {
                "id": item.id,
                "slot": item.slot,
                "enabled": item.enabled,
                "label": item.label,
            }
            for item in ordered
        ],
    }


def map_to_json(device_map: WizDeviceMap) -> str:
    return json.dumps(map_to_payload(device_map), indent=2, ensure_ascii=True) + "\n"


def load_map(path: Path) -> WizDeviceMap:
    """Read map.json. Missing/corrupt files are errors, never an empty map."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise WizMapError(f"cannot read {path}: {exc}") from exc
    return parse_map_text(text)


def load_map_or_last_good(path: Path) -> tuple[WizDeviceMap, str]:
    """Explicit fallback. Callers must opt in; load_map never does this."""
    try:
        return load_map(path), "map"
    except (WizMapCorruptError, WizMapValidationError):
        fallback = last_good_path(path)
        if not fallback.is_file():
            raise
        return load_map(fallback), "last-good"


def _fsync_directory(directory: Path) -> None:
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _write_bytes_atomic(path: Path, body: bytes) -> None:
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".map.", suffix=".tmp", dir=str(directory))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_directory(directory)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def save_map(path: Path, device_map: WizDeviceMap) -> None:
    """Atomic replace. Failure leaves the previous map bytes in place."""
    body = map_to_json(device_map).encode("utf-8")
    _write_bytes_atomic(path, body)
    try:
        _write_bytes_atomic(last_good_path(path), body)
    except OSError:
        pass
