"""Operator map mutations. MAC identity, slots 1..WIZ_MAX_SLOTS, never persist IPs."""

from __future__ import annotations

from light_console.wiz.device_map import (
    WIZ_MAX_SLOTS,
    WizDeviceMap,
    WizMapValidationError,
    WizMappedDevice,
    normalize_mac,
    validate_map,
)

UI_SLOTS = WIZ_MAX_SLOTS


def used_slots(device_map: WizDeviceMap | None) -> set[int]:
    if device_map is None:
        return set()
    return {device.slot for device in device_map.devices}


def unused_slots(device_map: WizDeviceMap | None, *, limit: int = UI_SLOTS) -> tuple[int, ...]:
    taken = used_slots(device_map)
    return tuple(slot for slot in range(1, limit + 1) if slot not in taken)


def lowest_unused_slot(device_map: WizDeviceMap | None, *, limit: int = UI_SLOTS) -> int | None:
    free = unused_slots(device_map, limit=limit)
    return free[0] if free else None


def _replace(device_map: WizDeviceMap | None, devices: tuple[WizMappedDevice, ...]) -> WizDeviceMap:
    base = device_map or WizDeviceMap()
    return validate_map(
        WizDeviceMap(
            version=base.version,
            start_channel=base.start_channel,
            channels_per_fixture=base.channels_per_fixture,
            devices=devices,
        )
    )


def add_device(device_map: WizDeviceMap | None, mac: str, slot: int) -> WizDeviceMap:
    ident = normalize_mac(mac)
    slot = int(slot)
    if slot < 1 or slot > UI_SLOTS:
        raise WizMapValidationError(f"slot {slot} outside 1..{UI_SLOTS}")
    existing = device_map.devices if device_map is not None else ()
    if any(item.id == ident for item in existing):
        raise WizMapValidationError(f"duplicate MAC {ident}")
    if any(item.slot == slot for item in existing):
        raise WizMapValidationError(f"duplicate slot {slot}")
    added = WizMappedDevice(id=ident, slot=slot, enabled=True, label="")
    return _replace(device_map, existing + (added,))


def move_device(device_map: WizDeviceMap, mac: str, slot: int) -> WizDeviceMap:
    ident = normalize_mac(mac)
    slot = int(slot)
    if slot < 1 or slot > UI_SLOTS:
        raise WizMapValidationError(f"slot {slot} outside 1..{UI_SLOTS}")
    occupant = next((item for item in device_map.devices if item.slot == slot), None)
    if occupant is not None and occupant.id != ident:
        raise WizMapValidationError("target slot occupied")
    found = False
    out: list[WizMappedDevice] = []
    for item in device_map.devices:
        if item.id == ident:
            found = True
            out.append(WizMappedDevice(id=item.id, slot=slot, enabled=item.enabled, label=item.label))
        else:
            out.append(item)
    if not found:
        raise WizMapValidationError(f"unknown MAC {ident}")
    return _replace(device_map, tuple(out))


def remap_slots(device_map: WizDeviceMap, slot_to: dict[int, int]) -> WizDeviceMap:
    """Move mapped devices from current slots to new slots in one validate.

    Keys are current slots. Unmentioned slots stay. Destinations must be unique.
    A destination that is occupied by a device that is not itself moving is an error.
    """
    mapping = {int(src): int(dst) for src, dst in slot_to.items()}
    if not mapping:
        return validate_map(device_map)
    destinations = list(mapping.values())
    if len(set(destinations)) != len(destinations):
        raise WizMapValidationError("remap destinations must be unique")
    for dst in destinations:
        if dst < 1 or dst > UI_SLOTS:
            raise WizMapValidationError(f"slot {dst} outside 1..{UI_SLOTS}")
    by_slot = {item.slot: item for item in device_map.devices}
    missing = sorted(src for src in mapping if src not in by_slot)
    if missing:
        raise WizMapValidationError(f"unknown slot {missing[0]}")
    moving = set(mapping)
    for dst in destinations:
        occupant = by_slot.get(dst)
        if occupant is not None and occupant.slot not in moving:
            raise WizMapValidationError("target slot occupied")
    out: list[WizMappedDevice] = []
    for item in device_map.devices:
        if item.slot in mapping:
            out.append(
                WizMappedDevice(
                    id=item.id,
                    slot=mapping[item.slot],
                    enabled=item.enabled,
                    label=item.label,
                )
            )
        else:
            out.append(item)
    return _replace(device_map, tuple(out))


def swap_devices(device_map: WizDeviceMap, mac_a: str, mac_b: str) -> WizDeviceMap:
    a = normalize_mac(mac_a)
    b = normalize_mac(mac_b)
    if a == b:
        raise WizMapValidationError("cannot swap a device with itself")
    slots = {item.id: item.slot for item in device_map.devices}
    if a not in slots or b not in slots:
        raise WizMapValidationError("swap requires two mapped devices")
    slot_a, slot_b = slots[a], slots[b]
    out: list[WizMappedDevice] = []
    for item in device_map.devices:
        if item.id == a:
            out.append(WizMappedDevice(id=item.id, slot=slot_b, enabled=item.enabled, label=item.label))
        elif item.id == b:
            out.append(WizMappedDevice(id=item.id, slot=slot_a, enabled=item.enabled, label=item.label))
        else:
            out.append(item)
    return _replace(device_map, tuple(out))


def set_enabled(device_map: WizDeviceMap, mac: str, enabled: bool) -> WizDeviceMap:
    ident = normalize_mac(mac)
    found = False
    out: list[WizMappedDevice] = []
    for item in device_map.devices:
        if item.id == ident:
            found = True
            out.append(WizMappedDevice(id=item.id, slot=item.slot, enabled=bool(enabled), label=item.label))
        else:
            out.append(item)
    if not found:
        raise WizMapValidationError(f"unknown MAC {ident}")
    return _replace(device_map, tuple(out))
