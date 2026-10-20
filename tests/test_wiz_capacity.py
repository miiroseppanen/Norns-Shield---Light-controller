"""One DMX universe of WiZ slots: 1..85, 510 used channels, no second universe."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from light_console.display.layout import CONTENT_Y, FOCUS_W, ROW, SCROLL_X
from light_console.display.renderer import Renderer
from light_console.display.components import region_on_count
from light_console.display.viewport import scrollbar_metrics
from light_console.hardware.events import ButtonEvent, EncoderEvent, E2, K3
from light_console.output.live_path import parse_live_controls
from light_console.output.mutate import (
    apply_universe_channels,
    set_artnet_universe_channels,
    universe_channels,
)
from light_console.output.routing import parse_output_routes
from light_console.qxw import _DOCTYPE
from light_console.ui.pages import WIZ_DEVICES_VISIBLE
from light_console.wiz.device_map import (
    CHANNELS_PER_FIXTURE,
    DMX_MAX,
    WIZ_MAX_SLOTS,
    WIZ_USED_CHANNELS,
    WizDeviceMap,
    WizMapValidationError,
    WizMappedDevice,
    dmx_end,
    dmx_index0,
    dmx_index0_span,
    dmx_start,
    load_map,
    map_to_json,
    normalize_mac,
    parse_map_text,
    save_map,
    validate_map,
)
from light_console.wiz.edit import (
    add_device,
    lowest_unused_slot,
    move_device,
    swap_devices,
)
from light_console.wiz.observe import Availability, DiscoveryKind

from tests.conftest import make_controller
from tests.test_wiz_bridge import _map_doc
from tests.test_wiz_devices import _dev, _obs, _open_devices, wiz_devices_viewport
from tests.test_wiz_identify import _identify_of, _status_path

ROOT = Path(__file__).resolve().parents[1]
SHIELD = ROOT / "qlc/projects/siirtyma-shield.qxw"
PROD_PI = "192.168.88.248"

# Operator map at capacity expansion time. Must round-trip unchanged.
LIVE_CONFIGURED = (
    ("9877d5b205b8", 1),
    ("9877d5b20736", 2),
    ("9877d5b206e4", 3),
    ("9877d5b20620", 4),
    ("9877d5b20706", 5),
    ("9877d548f1be", 6),
    ("9877d5be9c0c", 7),
)


def _mac(n: int) -> str:
    return f"aa{n:010x}"


def _full_map() -> WizDeviceMap:
    return WizDeviceMap(
        devices=tuple(WizMappedDevice(id=_mac(i), slot=i, enabled=True, label="") for i in range(1, 86))
    )


def test_canonical_capacity():
    assert CHANNELS_PER_FIXTURE == 6
    assert DMX_MAX == 512
    assert WIZ_MAX_SLOTS == 85
    assert WIZ_USED_CHANNELS == 510
    assert DMX_MAX // CHANNELS_PER_FIXTURE == 85
    assert WIZ_MAX_SLOTS * CHANNELS_PER_FIXTURE == 510


def test_validation_slot_bounds_and_uniqueness():
    ok1 = validate_map(WizDeviceMap(devices=(_dev("aabbccddeeff", 1),)))
    assert ok1.devices[0].slot == 1
    ok85 = validate_map(WizDeviceMap(devices=(_dev("aabbccddeeff", 85),)))
    assert ok85.devices[0].slot == 85
    with pytest.raises(WizMapValidationError):
        validate_map(WizDeviceMap(devices=(_dev("aabbccddeeff", 0),)))
    with pytest.raises(WizMapValidationError):
        validate_map(WizDeviceMap(devices=(_dev("aabbccddeeff", 86),)))
    with pytest.raises(WizMapValidationError, match="duplicate slot"):
        validate_map(
            WizDeviceMap(devices=(_dev("aabbccddeeff", 1), _dev("bbccddeeff00", 1)))
        )
    with pytest.raises(WizMapValidationError, match="duplicate MAC"):
        validate_map(
            WizDeviceMap(devices=(_dev("AA:BB:CC:DD:EE:FF", 1), _dev("aa-bb-cc-dd-ee-ff", 2)))
        )


def test_add_lowest_unused_gaps_and_full():
    seven = WizDeviceMap(devices=tuple(_dev(_mac(i), i) for i in range(1, 8)))
    assert lowest_unused_slot(seven) == 8
    added = add_device(seven, _mac(8), 8)
    assert added.devices[-1].slot == 8
    gapped = WizDeviceMap(devices=(_dev(_mac(1), 1), _dev(_mac(2), 2), _dev(_mac(4), 4)))
    assert lowest_unused_slot(gapped) == 3
    assert lowest_unused_slot(_full_map()) is None


def test_move_swap_slot_85_and_reject_86():
    base = WizDeviceMap(devices=(_dev(_mac(1), 1), _dev(_mac(2), 2)))
    moved = move_device(base, _mac(1), 85)
    assert {(d.id, d.slot) for d in moved.devices} == {(_mac(1), 85), (_mac(2), 2)}
    with pytest.raises(WizMapValidationError, match="outside"):
        move_device(base, _mac(1), 86)
    paired = WizDeviceMap(devices=(_dev(_mac(1), 1), _dev(_mac(2), 85)))
    swapped = swap_devices(paired, _mac(1), _mac(2))
    assert {(d.id, d.slot) for d in swapped.devices} == {(_mac(1), 85), (_mac(2), 1)}


def test_move_to_85_is_atomic(tmp_path: Path, monkeypatch):
    import os

    path = tmp_path / "map.json"
    original = WizDeviceMap(devices=(_dev(_mac(1), 1),))
    save_map(path, original)
    before = path.read_bytes()

    def boom(src, dst):
        del src, dst
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        save_map(path, move_device(original, _mac(1), 85))
    assert path.read_bytes() == before


def test_live_configured_map_roundtrip_preserves_slots():
    devices = tuple(_dev(mac, slot) for mac, slot in LIVE_CONFIGURED)
    device_map = validate_map(WizDeviceMap(devices=devices))
    loaded = parse_map_text(map_to_json(device_map))
    assert [(d.id, d.slot) for d in loaded.devices] == list(LIVE_CONFIGURED)
    assert lowest_unused_slot(loaded) == 8


def test_bridge_slot_indices(harness):
    assert harness.mod.WIZ_MAX_SLOTS == 85
    assert harness.mod.DMX_MAX == 512
    assert dmx_index0(1) == 0
    assert dmx_index0_span(1) == (0, 5)
    assert dmx_index0_span(7) == (36, 41)
    assert dmx_index0_span(8) == (42, 47)
    assert dmx_index0_span(85) == (504, 509)
    assert dmx_start(85) == 505
    assert dmx_end(85) == 510
    lo, hi = dmx_index0_span(85)
    assert hi == 509
    assert hi < 510
    assert lo + 5 <= 511
    worker = harness.mod.FixtureWorker(_mac(85), 85, autostart=False)
    assert worker.base == 504
    assert worker.base + CHANNELS_PER_FIXTURE - 1 == 509
    assert len(harness.mod.latest_dmx) == 512


def test_activity_high_slot_idle_semantics(harness):
    mac = _mac(85)
    harness.map_path.write_text(json.dumps(_map_doc((mac, 85))) + "\n", encoding="utf-8")
    harness.mod.load_configured_devices()
    base = dmx_index0(85)
    assert base == 504
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[base:base + 6] = bytes([10, 0, 0, 0, 0, 0])
        assert harness.mod.latest_dmx[510] == 0
        assert harness.mod.latest_dmx[511] == 0
    harness.mod.note_dmx_activity(now=100.0)
    active, last = harness.mod.slot_dmx_fields(mac, now=100.0)
    assert active is False
    assert last is None
    harness.mod.note_dmx_activity(now=100.2)
    active, _ = harness.mod.slot_dmx_fields(mac, now=100.2)
    assert active is False
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[base] = 20
    harness.mod.note_dmx_activity(now=100.5)
    active, last = harness.mod.slot_dmx_fields(mac, now=100.5)
    assert active is True
    assert last == 100.5


def test_oled_viewport_scrollbar_k3_and_identify_far_row(tmp_path, monkeypatch):
    assert WIZ_DEVICES_VISIBLE == 6
    status = _status_path(tmp_path, monkeypatch)
    far = _dev(_mac(85), 85)
    mapped = tuple(_dev(_mac(i), i) for i in range(1, 7)) + (far,)
    obs = tuple(
        _obs(row.id, ip=f"10.42.0.{i + 10}", availability=Availability.ONLINE)
        for i, row in enumerate(mapped)
    )
    c = make_controller()
    _open_devices(c, mapped, obs, wiz_enabled=True, bridge=True)
    vis = 6
    assert len(c.state.wiz_device_rows) == 7
    assert list(wiz_devices_viewport(c.state).window()) == [0, 1, 2, 3, 4, 5]
    fb = Renderer().render(c.state)
    assert scrollbar_metrics(7, vis, 0, vis * ROW) is not None
    assert region_on_count(fb, SCROLL_X, CONTENT_Y, 3, vis * ROW) > 0
    c.inject_cooked(EncoderEvent(E2, 6))
    assert c.state.wiz_device_index == 6
    assert c.state.scroll_offset == 1
    assert list(wiz_devices_viewport(c.state).window()) == [1, 2, 3, 4, 5, 6]
    assert c.state.wiz_device_rows[6].id == _mac(85)
    assert c.state.wiz_device_rows[6].slot == 85
    assert parse_live_controls(status.read_text(encoding="utf-8")).identify_mac == _mac(85)
    assert _identify_of(status) == _mac(85)
    fb2 = Renderer().render(c.state)
    assert region_on_count(fb2, 0, CONTENT_Y + 5 * ROW, FOCUS_W, ROW) == FOCUS_W * ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "actions"
    assert c.state.wiz_prompt_mac == _mac(85)
    assert c.state.wiz_prompt_slot == 85


def test_move_encoder_reaches_slot_85(tmp_path: Path):
    path = tmp_path / "map.json"
    save_map(path, WizDeviceMap(devices=(_dev(_mac(1), 1),)))
    c = make_controller(wiz_map_path=path, wiz_enabled=True)
    _open_devices(c, load_map(path).devices, wiz_enabled=True, bridge=True)
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "move"
    assert c.state.wiz_prompt_target == 1
    c.inject_cooked(EncoderEvent(E2, 84))
    assert c.state.wiz_prompt_target == 85
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.wiz_prompt_target == 85
    c.inject_cooked(ButtonEvent(K3, "press"))
    loaded = load_map(path)
    assert loaded.devices[0].slot == 85


def test_add_after_seven_gets_slot_8(tmp_path: Path):
    path = tmp_path / "map.json"
    seven = WizDeviceMap(devices=tuple(_dev(_mac(i), i) for i in range(1, 8)))
    save_map(path, seven)
    new_mac = "cc00000000aa"
    c = make_controller(wiz_map_path=path, wiz_enabled=True)
    _open_devices(
        c,
        seven.devices,
        (_obs(new_mac, discovery=DiscoveryKind.NEW, availability=Availability.ONLINE),),
        wiz_enabled=True,
        bridge=True,
    )
    c.state.wiz_device_index = 7
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "add"
    assert c.state.wiz_prompt_slot == 8
    c.inject_cooked(ButtonEvent(K3, "press"))
    loaded = load_map(path)
    assert {(d.id, d.slot) for d in loaded.devices} == {
        *((_mac(i), i) for i in range(1, 8)),
        (normalize_mac(new_mac), 8),
    }


def test_full_only_at_85(tmp_path: Path):
    path = tmp_path / "map.json"
    save_map(path, _full_map())
    c = make_controller(wiz_map_path=path, wiz_enabled=True)
    _open_devices(
        c,
        load_map(path).devices,
        (_obs("cc00000000ff", discovery=DiscoveryKind.NEW, availability=Availability.ONLINE),),
        wiz_enabled=True,
        bridge=True,
    )
    c.state.wiz_device_index = 85
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "full"


def test_qlc_u1_full_universe_and_routing():
    text = SHIELD.read_text(encoding="utf-8")
    assert universe_channels(text, 0) == 512
    assert universe_channels(text, 1) == 33
    routes = parse_output_routes(text)
    assert routes[0].output_ip == "127.0.0.1"
    assert routes[1].output_ip == "127.0.0.1"
    assert PROD_PI not in text
    import xml.etree.ElementTree as ET

    ET.fromstring(_DOCTYPE.sub("", text, count=1))
    wiz = 0
    for node in ET.fromstring(_DOCTYPE.sub("", text, count=1)).iter():
        if node.tag.rsplit("}", 1)[-1] != "Fixture":
            continue
        fields = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in list(node)}
        if fields.get("Manufacturer") == "WiZ":
            wiz += 1
            assert int(fields["Universe"]) == 0
            assert int(fields["Channels"]) == 6
            assert int(fields["Address"]) + 6 <= 512
    assert wiz == 7


def test_qlc_universe_channels_patch_preserves_routing(tmp_path: Path):
    original = SHIELD.read_text(encoding="utf-8")
    lowered = set_artnet_universe_channels(original, 0, 42)
    assert universe_channels(lowered, 0) == 42
    assert universe_channels(lowered, 1) == universe_channels(original, 1)
    assert parse_output_routes(lowered) == parse_output_routes(original)
    assert PROD_PI not in lowered
    path = tmp_path / "master.qxw"
    path.write_text(lowered, encoding="utf-8")
    assert apply_universe_channels(path, 0, 512) is True
    patched = path.read_text(encoding="utf-8")
    assert universe_channels(patched, 0) == 512
    assert parse_output_routes(patched) == parse_output_routes(original)
    assert apply_universe_channels(path, 0, 512) is False
    assert PROD_PI not in patched


@pytest.fixture
def harness(tmp_path, monkeypatch):
    from tests.test_wiz_bridge import _BridgeHarness

    h = _BridgeHarness(tmp_path, monkeypatch)
    yield h
    h.mod.reset_runtime_for_tests()
