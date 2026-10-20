"""Pure WiZ map domain: MAC identity, slots, persistence, legacy conversion."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from light_console.wiz.device_map import (
    CHANNELS_PER_FIXTURE,
    SCHEMA_MAX_SLOTS,
    WIZ_MAX_SLOTS,
    WIZ_USED_CHANNELS,
    WIZ_V1_PATCH_SLOTS,
    WizDeviceMap,
    WizMapCorruptError,
    WizMapValidationError,
    WizMappedDevice,
    dmx_end,
    dmx_span,
    dmx_start,
    last_good_path,
    load_map,
    load_map_or_last_good,
    map_to_json,
    normalize_mac,
    parse_legacy_document,
    parse_legacy_text,
    parse_map_text,
    save_map,
    validate_map,
)


def _dev(mac: str, slot: int, *, enabled: bool = True, label: str = "") -> WizMappedDevice:
    return WizMappedDevice(id=normalize_mac(mac), slot=slot, enabled=enabled, label=label)


def _map(*devices: WizMappedDevice) -> WizDeviceMap:
    return validate_map(WizDeviceMap(devices=devices))


def test_mac_normalization_accepts_common_forms():
    assert normalize_mac("AA:BB:CC:DD:EE:FF") == "aabbccddeeff"
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "aabbccddeeff"
    assert normalize_mac("aabbccddeeff") == "aabbccddeeff"
    assert normalize_mac("  AaBbCcDdEeFf  ") == "aabbccddeeff"


def test_invalid_mac_rejected():
    with pytest.raises(WizMapValidationError):
        normalize_mac("aabbccddee")
    with pytest.raises(WizMapValidationError):
        normalize_mac("aabbccddeeff00")
    with pytest.raises(WizMapValidationError):
        normalize_mac("ggbbccddeeff")
    with pytest.raises(WizMapValidationError):
        normalize_mac("")
    with pytest.raises(WizMapValidationError):
        normalize_mac(None)
    with pytest.raises(WizMapValidationError):
        normalize_mac("aa.bb.cc.dd.ee.ff")


def test_duplicate_normalized_mac_rejected():
    with pytest.raises(WizMapValidationError, match="duplicate MAC"):
        _map(_dev("AA:BB:CC:DD:EE:FF", 1), _dev("aa-bb-cc-dd-ee-ff", 2))


def test_six_channel_spans_and_canonical_slots():
    assert dmx_start(1) == 1
    assert dmx_end(1) == 6
    assert dmx_span(1) == (1, 6)
    assert dmx_span(7) == (37, 42)
    assert dmx_span(85) == (505, 510)
    assert CHANNELS_PER_FIXTURE == 6
    assert WIZ_MAX_SLOTS == 85
    assert WIZ_USED_CHANNELS == 510
    assert SCHEMA_MAX_SLOTS == 85
    assert WIZ_V1_PATCH_SLOTS == WIZ_MAX_SLOTS


def test_slot_85_valid_slot_86_rejected():
    ok = _map(_dev("aabbccddeeff", 85))
    assert ok.devices[0].slot == 85
    with pytest.raises(WizMapValidationError):
        _map(_dev("aabbccddeeff", 86))
    with pytest.raises(WizMapValidationError):
        _map(_dev("aabbccddeeff", 0))


def test_duplicate_slot_and_overlap_rejected():
    with pytest.raises(WizMapValidationError, match="duplicate slot"):
        _map(_dev("aabbccddeeff", 1), _dev("bbccddeeff00", 1))
    with pytest.raises(WizMapValidationError):
        validate_map(
            WizDeviceMap(
                devices=(
                    WizMappedDevice("aabbccddeeff", 2),
                    WizMappedDevice("bbccddeeff00", 2),
                )
            )
        )


def test_slot_8_is_within_universe_cap():
    device_map = _map(_dev("aabbccddeeff", 1), _dev("bbccddeeff00", 8))
    assert [item.slot for item in device_map.devices] == [1, 8]
    assert device_map.exceeds_v1_patch is False
    body = map_to_json(device_map)
    loaded = parse_map_text(body)
    assert [item.slot for item in loaded.devices] == [1, 8]
    assert "bbccddeeff00" in body


def test_schema_version_and_channel_constants():
    with pytest.raises(WizMapValidationError, match="version"):
        parse_map_text(
            json.dumps(
                {
                    "version": 2,
                    "start_channel": 1,
                    "channels_per_fixture": 6,
                    "devices": [],
                }
            )
        )
    with pytest.raises(WizMapValidationError, match="start_channel"):
        parse_map_text(
            json.dumps(
                {
                    "version": 1,
                    "start_channel": 2,
                    "channels_per_fixture": 6,
                    "devices": [],
                }
            )
        )
    with pytest.raises(WizMapValidationError, match="channels_per_fixture"):
        parse_map_text(
            json.dumps(
                {
                    "version": 1,
                    "start_channel": 1,
                    "channels_per_fixture": 8,
                    "devices": [],
                }
            )
        )


def test_enabled_and_label_validation():
    with pytest.raises(WizMapValidationError, match="boolean"):
        parse_map_text(
            json.dumps(
                {
                    "version": 1,
                    "start_channel": 1,
                    "channels_per_fixture": 6,
                    "devices": [{"id": "aabbccddeeff", "slot": 1, "enabled": 1}],
                }
            )
        )
    with pytest.raises(WizMapValidationError, match="label"):
        parse_map_text(
            json.dumps(
                {
                    "version": 1,
                    "start_channel": 1,
                    "channels_per_fixture": 6,
                    "devices": [
                        {
                            "id": "aabbccddeeff",
                            "slot": 1,
                            "enabled": True,
                            "label": "x" * 41,
                        }
                    ],
                }
            )
        )


def test_persistent_map_rejects_ip_field():
    with pytest.raises(WizMapValidationError, match="IP"):
        parse_map_text(
            json.dumps(
                {
                    "version": 1,
                    "start_channel": 1,
                    "channels_per_fixture": 6,
                    "devices": [
                        {
                            "id": "aabbccddeeff",
                            "slot": 1,
                            "enabled": True,
                            "label": "",
                            "ip": "10.42.0.9",
                        }
                    ],
                }
            )
        )


def test_deterministic_serialization(tmp_path: Path):
    device_map = _map(
        _dev("bbccddeeff00", 2, label="B"),
        _dev("aabbccddeeff", 1, label="A"),
    )
    first = map_to_json(device_map)
    second = map_to_json(device_map)
    assert first == second
    path = tmp_path / "map.json"
    save_map(path, device_map)
    save_map(path, device_map)
    assert path.read_text(encoding="utf-8") == first
    loaded = load_map(path)
    assert [item.slot for item in loaded.devices] == [1, 2]
    assert "ip" not in first
    payload = json.loads(first)
    assert list(payload.keys()) == [
        "version",
        "start_channel",
        "channels_per_fixture",
        "devices",
    ]
    assert list(payload["devices"][0].keys()) == ["id", "slot", "enabled", "label"]


def test_no_compaction_of_gapped_slots():
    device_map = _map(_dev("aabbccddeeff", 1), _dev("bbccddeeff00", 3))
    assert [item.slot for item in device_map.devices] == [1, 3]
    loaded = parse_map_text(map_to_json(device_map))
    assert [item.slot for item in loaded.devices] == [1, 3]
    assert len(loaded.devices) == 2


def test_corrupt_json_does_not_become_empty(tmp_path: Path):
    path = tmp_path / "map.json"
    path.write_text("{not json", encoding="utf-8")
    mtime = path.stat().st_mtime
    with pytest.raises(WizMapCorruptError):
        load_map(path)
    assert path.read_text(encoding="utf-8") == "{not json"
    assert path.stat().st_mtime == mtime
    with pytest.raises(WizMapCorruptError):
        parse_map_text("null")
    with pytest.raises(WizMapCorruptError):
        parse_map_text("[1]")


def test_missing_map_is_not_empty_map(tmp_path: Path):
    path = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        load_map(path)


def test_failed_atomic_write_retains_previous(tmp_path: Path, monkeypatch):
    path = tmp_path / "map.json"
    original = _map(_dev("aabbccddeeff", 1, label="keep"))
    save_map(path, original)
    before = path.read_bytes()

    def boom(src, dst):
        del src, dst
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        save_map(path, _map(_dev("bbccddeeff00", 2, label="new")))
    assert path.read_bytes() == before
    assert json.loads(before)["devices"][0]["id"] == "aabbccddeeff"


def test_last_good_is_opt_in_fallback(tmp_path: Path):
    path = tmp_path / "map.json"
    save_map(path, _map(_dev("aabbccddeeff", 1)))
    assert last_good_path(path).is_file()
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(WizMapCorruptError):
        load_map(path)
    recovered, source = load_map_or_last_good(path)
    assert source == "last-good"
    assert recovered.devices[0].id == "aabbccddeeff"
    assert path.read_text(encoding="utf-8") == "{broken"


def test_legacy_conversion_preserves_slot_order_and_drops_ip():
    data = {
        "start_channel": 1,
        "channels_per_fixture": 6,
        "fixtures": [
            {"slot": 2, "mac": "BB:CC:DD:EE:FF:00", "dmx": "7-12", "ip": "10.42.0.8"},
            {"slot": 1, "mac": "AA:BB:CC:DD:EE:FF", "dmx": "1-6", "ip": "10.42.0.7"},
            {"slot": 4, "mac": "ccdddeeff001", "dmx": "19-24"},
        ],
    }
    converted = parse_legacy_document(data)
    assert [item.slot for item in converted.devices] == [2, 1, 4]
    assert [item.id for item in converted.devices] == [
        "bbccddeeff00",
        "aabbccddeeff",
        "ccdddeeff001",
    ]
    assert all(item.enabled for item in converted.devices)
    assert all(item.label == "" for item in converted.devices)
    body = map_to_json(converted)
    assert "ip" not in body
    assert "10.42" not in body
    assert [item.slot for item in converted.devices] != sorted(
        item.slot for item in converted.devices
    )


def test_legacy_does_not_compact_or_enroll():
    converted = parse_legacy_text(
        json.dumps(
            {
                "start_channel": 1,
                "channels_per_fixture": 6,
                "fixtures": [
                    {"slot": 1, "mac": "aabbccddeeff"},
                    {"slot": 3, "mac": "bbccddeeff00"},
                ],
            }
        )
    )
    assert [item.slot for item in converted.devices] == [1, 3]
    assert len(converted.devices) == 2


def test_empty_map_is_valid_and_not_corrupt():
    parsed = parse_map_text(
        json.dumps(
            {
                "version": 1,
                "start_channel": 1,
                "channels_per_fixture": 6,
                "devices": [],
            }
        )
    )
    assert parsed.devices == ()
