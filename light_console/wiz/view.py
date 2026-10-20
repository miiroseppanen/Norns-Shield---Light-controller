"""Join persistent WiZ mapping with cached observations for OLED rows."""

from __future__ import annotations

from dataclasses import dataclass

from light_console.ui.vocab import IDLE, LOST, NEW, OFF, OK
from light_console.wiz.device_map import (
    WIZ_MAX_SLOTS,
    WizDeviceMap,
    WizMappedDevice,
    dmx_end,
    dmx_start,
    normalize_mac,
)
from light_console.wiz.observe import Availability, WizObservedDevice

ROW_CONFIGURED = "configured"
ROW_NEW = "new"

NOTE_WIZ_OFF = "WIZ OFF"
NOTE_BRIDGE_DOWN = "BRIDGE DOWN"
NOTE_EXTENDED = "EXTENDED MAP"
NOTE_CORRUPT = "MAP CORRUPT"


@dataclass(frozen=True)
class WizDeviceRow:
    kind: str
    id: str
    state: str
    slot: int | None = None
    dmx_start: int | None = None
    dmx_end: int | None = None
    enabled: bool = True
    label: str = ""
    identity: str = ""
    observed_ip: str | None = None
    exceeds_v1: bool = False
    dmx_active: bool = False

    @property
    def mapped(self) -> bool:
        return self.kind == ROW_CONFIGURED and self.slot is not None


@dataclass(frozen=True)
class WizDevicesView:
    rows: tuple[WizDeviceRow, ...] = ()
    note: str = ""
    extended: bool = False
    error: str = ""


def display_identity(device_id: str, label: str = "", *, new: bool = False) -> str:
    text = (label or "").strip()
    if text:
        return text
    mac = device_id.strip().lower()
    if new and len(mac) >= 6:
        return mac[-6:].upper()
    if len(mac) >= 4:
        return mac[-4:]
    return mac


def _obs_by_id(observations: tuple[WizObservedDevice, ...]) -> dict[str, WizObservedDevice]:
    out: dict[str, WizObservedDevice] = {}
    for item in observations:
        try:
            mac = normalize_mac(item.id)
        except Exception:
            continue
        out[mac] = item
    return out


def _configured_state(
    device: WizMappedDevice,
    observed: WizObservedDevice | None,
    *,
    wiz_enabled: bool,
    bridge_available: bool,
) -> str:
    if not device.enabled:
        return OFF
    if not wiz_enabled or not bridge_available:
        return IDLE
    if observed is not None and observed.availability is Availability.ONLINE:
        return OK
    return LOST


def _row_for_mapped(
    device: WizMappedDevice,
    observed: WizObservedDevice | None,
    *,
    wiz_enabled: bool,
    bridge_available: bool,
) -> WizDeviceRow:
    ip = None if observed is None else observed.observed_ip
    active = bool(
        device.enabled
        and observed is not None
        and observed.dmx_active
    )
    return WizDeviceRow(
        kind=ROW_CONFIGURED,
        id=device.id,
        slot=device.slot,
        dmx_start=dmx_start(device.slot),
        dmx_end=dmx_end(device.slot),
        enabled=device.enabled,
        label=device.label,
        identity=display_identity(device.id, device.label),
        state=_configured_state(
            device,
            observed,
            wiz_enabled=wiz_enabled,
            bridge_available=bridge_available,
        ),
        observed_ip=ip,
        exceeds_v1=device.slot > WIZ_MAX_SLOTS,
        dmx_active=active,
    )


def _row_for_new(observed: WizObservedDevice) -> WizDeviceRow:
    mac = normalize_mac(observed.id)
    return WizDeviceRow(
        kind=ROW_NEW,
        id=mac,
        identity=display_identity(mac, new=True),
        state=NEW,
        observed_ip=observed.observed_ip,
        enabled=False,
    )


def join_wiz_devices(
    device_map: WizDeviceMap | None,
    observations: tuple[WizObservedDevice, ...] = (),
    *,
    wiz_enabled: bool,
    bridge_available: bool,
    error: str = "",
) -> WizDevicesView:
    """Configured rows in slot order, then unmapped NEW rows sorted by MAC."""
    if error:
        return WizDevicesView(note=NOTE_CORRUPT, error=error)
    mapped = device_map.devices if device_map is not None else ()
    obs_map = _obs_by_id(observations)
    configured = tuple(
        _row_for_mapped(
            device,
            obs_map.get(device.id),
            wiz_enabled=wiz_enabled,
            bridge_available=bridge_available,
        )
        for device in sorted(mapped, key=lambda item: item.slot)
    )
    mapped_ids = {device.id for device in mapped}
    new_rows: list[WizDeviceRow] = []
    if wiz_enabled and bridge_available:
        seen_new: set[str] = set()
        for item in observations:
            try:
                mac = normalize_mac(item.id)
            except Exception:
                continue
            if mac in mapped_ids or mac in seen_new:
                continue
            seen_new.add(mac)
            new_rows.append(_row_for_new(item))
        new_rows.sort(key=lambda row: row.id)
    if not wiz_enabled:
        note = NOTE_WIZ_OFF
    elif not bridge_available:
        note = NOTE_BRIDGE_DOWN
    elif any(row.exceeds_v1 for row in configured):
        note = NOTE_EXTENDED
    else:
        note = ""
    return WizDevicesView(
        rows=configured + tuple(new_rows),
        note=note,
        extended=any(row.exceeds_v1 for row in configured),
        error="",
    )


def list_label(row: WizDeviceRow) -> str:
    if row.kind == ROW_NEW or row.slot is None or row.dmx_start is None:
        return row.identity
    return f"{row.slot:02d} {row.identity}"
