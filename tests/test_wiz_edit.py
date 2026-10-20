"""Operator map mutations: ADD / MOVE / SWAP / DISABLE. No auto-enroll."""

from __future__ import annotations

from pathlib import Path

import pytest

from light_console.hardware.events import ButtonEvent, EncoderEvent, E2, K1, K2, K3
from light_console.state import ScreenId
from light_console.ui.menu import menu_index_of
from light_console.wiz.device_map import (
    WizDeviceMap,
    WizMapValidationError,
    WizMappedDevice,
    load_map,
    normalize_mac,
    save_map,
)
from light_console.wiz.edit import (
    add_device,
    lowest_unused_slot,
    move_device,
    remap_slots,
    set_enabled,
    swap_devices,
)
from light_console.wiz.observe import Availability, DiscoveryKind, WizObservedDevice

from tests.conftest import make_controller

MAC5 = "9877d5b20706"
MAC6 = "9877d548f1be"
MAC_NEW = "aa4130aa4130"


def _map(*pairs: tuple[str, int], enabled: dict[str, bool] | None = None) -> WizDeviceMap:
    devices = []
    for mac, slot in pairs:
        on = True if enabled is None else enabled.get(mac, True)
        devices.append(WizMappedDevice(id=normalize_mac(mac), slot=slot, enabled=on, label=""))
    return WizDeviceMap(devices=tuple(devices))


def test_lowest_unused_with_slots_5_and_6_is_1():
    assert lowest_unused_slot(_map((MAC5, 5), (MAC6, 6))) == 1
    seven = _map(*((f"aa00000000{i:02x}", i) for i in range(1, 8)))
    assert lowest_unused_slot(seven) == 8
    full = _map(*((f"aa{i:010x}", i) for i in range(1, 86)))
    assert lowest_unused_slot(full) is None


def test_add_rejects_duplicate_mac_slot_and_range():
    base = _map((MAC5, 5), (MAC6, 6))
    with pytest.raises(WizMapValidationError, match="duplicate MAC"):
        add_device(base, MAC5, 1)
    with pytest.raises(WizMapValidationError, match="duplicate slot"):
        add_device(base, MAC_NEW, 5)
    with pytest.raises(WizMapValidationError, match="outside"):
        add_device(base, MAC_NEW, 86)
    added8 = add_device(base, "cc0000000008", 8)
    assert added8.devices[-1].slot == 8
    added = add_device(base, MAC_NEW, 1)
    assert [item.slot for item in added.devices] == [5, 6, 1]
    assert added.devices[2].id == normalize_mac(MAC_NEW)


def test_move_empty_and_swap_occupied():
    base = _map((MAC5, 5), (MAC6, 6))
    moved = move_device(base, MAC5, 1)
    assert {(item.id, item.slot) for item in moved.devices} == {
        (MAC5, 1),
        (MAC6, 6),
    }
    with pytest.raises(WizMapValidationError, match="occupied"):
        move_device(base, MAC5, 6)
    swapped = swap_devices(base, MAC5, MAC6)
    assert {(item.id, item.slot) for item in swapped.devices} == {
        (MAC5, 6),
        (MAC6, 5),
    }


def test_remap_slots_five_cycle():
    mac7, mac8, mac9, mac10, mac11 = (
        "9877d5b20a2a",
        "9877d5be9c0c",
        "9877d5aa2ece",
        "9877d5aa4130",
        "9877d5b4e4ec",
    )
    base = _map(
        ("9877d5b205b8", 1),
        (mac7, 7),
        (mac8, 8),
        (mac9, 9),
        (mac10, 10),
        (mac11, 11),
    )
    moved = remap_slots(base, {10: 8, 8: 9, 9: 7, 11: 10, 7: 11})
    assert {(item.id, item.slot) for item in moved.devices} == {
        ("9877d5b205b8", 1),
        (mac9, 7),
        (mac10, 8),
        (mac8, 9),
        (mac11, 10),
        (mac7, 11),
    }
    with pytest.raises(WizMapValidationError, match="unique"):
        remap_slots(base, {10: 8, 7: 8})
    with pytest.raises(WizMapValidationError, match="occupied"):
        remap_slots(base, {10: 1})
    with pytest.raises(WizMapValidationError, match="unknown slot"):
        remap_slots(base, {12: 13})
    assert remap_slots(base, {}) is not None
    same = remap_slots(base, {})
    assert {(item.id, item.slot) for item in same.devices} == {
        (item.id, item.slot) for item in base.devices
    }


def test_disable_retains_mac_and_slot():
    base = _map((MAC5, 5), (MAC6, 6))
    off = set_enabled(base, MAC6, False)
    item = next(device for device in off.devices if device.id == MAC6)
    assert item.enabled is False
    assert item.slot == 6
    on = set_enabled(off, MAC6, True)
    item = next(device for device in on.devices if device.id == MAC6)
    assert item.enabled is True
    assert item.slot == 6


def test_no_ip_in_map_json(tmp_path: Path):
    path = tmp_path / "map.json"
    save_map(path, _map((MAC5, 5), (MAC6, 6)))
    text = path.read_text(encoding="utf-8")
    assert "10.42" not in text
    assert "ip" not in text.lower()
    loaded = load_map(path)
    assert [device.slot for device in loaded.devices] == [5, 6]


def _open_devices(c, device_map, observations=()):
    c.apply_wiz_snapshot(device_map, observations, bridge_available=True)
    c.state.wiz_enabled = True
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("WIZ")
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.state.menu_index = 1
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.WIZ_DEVICES


def test_add_confirm_and_cancel(tmp_path: Path):
    path = tmp_path / "map.json"
    save_map(path, _map((MAC5, 5), (MAC6, 6)))
    before = path.read_bytes()
    c = make_controller(wiz_map_path=path, wiz_enabled=True)
    _open_devices(
        c,
        load_map(path),
        (
            WizObservedDevice(
                id=MAC_NEW,
                discovery=DiscoveryKind.NEW,
                availability=Availability.ONLINE,
            ),
        ),
    )
    c.state.wiz_device_index = 2
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "add"
    assert c.state.wiz_prompt_slot == 1
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.wiz_prompt == ""
    assert path.read_bytes() == before
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    loaded = load_map(path)
    assert {(d.id, d.slot) for d in loaded.devices} == {
        (MAC5, 5),
        (MAC6, 6),
        (normalize_mac(MAC_NEW), 1),
    }


def test_full_map_refuses_add(tmp_path: Path):
    devices = tuple(
        WizMappedDevice(id=f"aa{i:010x}", slot=i, enabled=True, label="")
        for i in range(1, 86)
    )
    path = tmp_path / "map.json"
    save_map(path, WizDeviceMap(devices=devices))
    c = make_controller(wiz_map_path=path, wiz_enabled=True)
    _open_devices(
        c,
        load_map(path),
        (
            WizObservedDevice(
                id=MAC_NEW, discovery=DiscoveryKind.NEW, availability=Availability.ONLINE
            ),
        ),
    )
    c.state.wiz_device_index = 85
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "full"
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == ""
    assert [d.slot for d in load_map(path).devices] == list(range(1, 86))


def test_move_swap_disable_enable(tmp_path: Path):
    path = tmp_path / "map.json"
    save_map(path, _map((MAC5, 5), (MAC6, 6)))
    c = make_controller(wiz_map_path=path, wiz_enabled=True)
    _open_devices(c, load_map(path))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "actions"
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "move"
    c.state.wiz_prompt_target = 1
    c.inject_cooked(ButtonEvent(K3, "press"))
    loaded = load_map(path)
    assert {(d.id, d.slot) for d in loaded.devices} == {(MAC5, 1), (MAC6, 6)}
    c.apply_wiz_snapshot(loaded, (), bridge_available=True)
    c.state.wiz_device_index = 0
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.state.wiz_prompt_target = 6
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "swap"
    before = path.read_bytes()
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert path.read_bytes() == before
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.state.wiz_prompt_target = 6
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    loaded = load_map(path)
    assert {(d.id, d.slot) for d in loaded.devices} == {(MAC5, 6), (MAC6, 1)}
    c.apply_wiz_snapshot(loaded, (), bridge_available=True)
    c.state.wiz_device_index = 1
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "disable"
    c.inject_cooked(ButtonEvent(K3, "press"))
    loaded = load_map(path)
    item = next(d for d in loaded.devices if d.id == MAC5)
    assert item.enabled is False
    assert item.slot == 6
    c.apply_wiz_snapshot(loaded, (), bridge_available=True)
    c.state.wiz_device_index = 1
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "enable"
    c.inject_cooked(ButtonEvent(K3, "press"))
    item = next(d for d in load_map(path).devices if d.id == MAC5)
    assert item.enabled is True
    assert item.slot == 6
