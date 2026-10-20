"""Observe-only WIZ DEVICES page, view model, and SYSTEM entry."""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

from light_console.display.components import region_on_count
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import (
    CONTENT_H,
    CONTENT_ROWS,
    CONTENT_Y,
    FOCUS_W,
    LABEL_X,
    ROW,
    SCROLL_X,
)
from light_console.display.renderer import Renderer
from light_console.display.viewport import scrollbar_metrics
from light_console.display.widgets import text
from light_console.hardware.events import ButtonEvent, EncoderEvent, E2, K1, K2, K3
from light_console.state import ScreenId
from light_console.ui.menu import MENU_ITEMS, menu_index_of
from light_console.ui.pages import (
    SYSTEM_QLC_TOGGLE,
    SYSTEM_ROW_COUNT,
    SYSTEM_SHUTDOWN_ROW,
    SYSTEM_VERSION,
    WIZ_DEVICES_VISIBLE,
    system_slots,
    wiz_devices_visible_count,
    wiz_devices_viewport,
)
from light_console.ui.vocab import IDLE, LOST, NEW, OFF, OK
from light_console.wiz import PHASE_C_DEBT
from light_console.wiz.device_map import (
    WizDeviceMap,
    WizMappedDevice,
    dmx_span,
    normalize_mac,
    save_map,
)
from light_console.wiz.observe import Availability, DiscoveryKind, WizObservedDevice
from light_console.wiz.view import (
    NOTE_BRIDGE_DOWN,
    NOTE_WIZ_OFF,
    ROW_CONFIGURED,
    ROW_NEW,
    WizDeviceRow,
    display_identity,
    join_wiz_devices,
    list_label,
)

from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ROOT / "light_console/display/screens.py"
CONTROLLER = ROOT / "light_console/ui/controller.py"
PAGES = ROOT / "light_console/ui/pages.py"
BRIDGE = ROOT / "services/wiz/wiz_artnet_bridge.py"


def _has_text(fb: Framebuffer, x: int, y: int, s: str) -> bool:
    ref = Framebuffer()
    text(ref, x, y, s)
    found = False
    for yy in range(fb.height):
        for xx in range(fb.width):
            if not ref.get(xx, yy):
                continue
            if fb.get(xx, yy) != 1:
                return False
            found = True
    return found


def _fb_has_string(fb: Framebuffer, s: str) -> bool:
    for y in range(fb.height):
        for x in range(0, fb.width, 6):
            if _has_text(fb, x, y, s):
                return True
    return False


def _dev(mac: str, slot: int, label: str = "", *, enabled: bool = True) -> WizMappedDevice:
    return WizMappedDevice(id=normalize_mac(mac), slot=slot, enabled=enabled, label=label)


def _obs(
    mac: str,
    *,
    ip: str | None = None,
    availability: Availability = Availability.UNKNOWN,
    discovery: DiscoveryKind = DiscoveryKind.KNOWN,
    dmx_active: bool = False,
) -> WizObservedDevice:
    return WizObservedDevice(
        id=normalize_mac(mac),
        observed_ip=ip,
        availability=availability,
        discovery=discovery,
        configured=discovery != DiscoveryKind.NEW,
        dmx_active=dmx_active,
    )


def _join(mapped, observations=(), *, wiz_enabled=True, bridge_available=True):
    device_map = WizDeviceMap(devices=tuple(mapped)) if mapped is not None else None
    if isinstance(mapped, WizDeviceMap):
        device_map = mapped
    return join_wiz_devices(
        device_map,
        tuple(observations),
        wiz_enabled=wiz_enabled,
        bridge_available=bridge_available,
    )


def test_configured_sorted_by_slot_then_new_by_mac():
    view = _join(
        (_dev("cccc00000003", 3), _dev("aaaa00000001", 1), _dev("bbbb00000002", 2)),
        (
            _obs("ffff000000ff", discovery=DiscoveryKind.NEW, ip="10.42.0.9"),
            _obs("eeee000000ee", discovery=DiscoveryKind.NEW),
            _obs("aaaa00000001", availability=Availability.ONLINE, ip="10.0.0.1"),
        ),
    )
    slots = [row.slot for row in view.rows if row.kind == ROW_CONFIGURED]
    assert slots == [1, 2, 3]
    news = [row for row in view.rows if row.kind == ROW_NEW]
    assert [row.id for row in news] == ["eeee000000ee", "ffff000000ff"]
    assert all(row.slot is None and row.dmx_start is None for row in news)
    assert news[0].state == NEW
    assert view.rows[0].state == OK
    assert view.rows[0].observed_ip == "10.0.0.1"


def test_discovery_order_does_not_reorder_configured():
    late_first = (
        _obs("bbbb00000002", availability=Availability.ONLINE),
        _obs("aaaa00000001", availability=Availability.OFFLINE),
    )
    view = _join((_dev("bbbb00000002", 2), _dev("aaaa00000001", 1)), late_first)
    assert [row.slot for row in view.rows] == [1, 2]
    assert view.rows[0].id == "aaaa00000001"
    assert view.rows[1].id == "bbbb00000002"


def test_same_mac_merges_and_ip_change_does_not_move_slot():
    mapped = (_dev("aa:bb:cc:dd:ee:ff", 5),)
    view_a = _join(mapped, (_obs("AA:BB:CC:DD:EE:FF", ip="10.42.0.2", availability=Availability.ONLINE),))
    view_b = _join(
        mapped,
        (
            _obs("aabbccddeeff", ip="10.42.0.99", availability=Availability.ONLINE, discovery=DiscoveryKind.NEW),
            _obs("aabbccddeeff", ip="10.42.0.99", availability=Availability.ONLINE),
        ),
    )
    assert len(view_a.rows) == 1
    assert len(view_b.rows) == 1
    assert view_a.rows[0].slot == view_b.rows[0].slot == 5
    assert dmx_span(5) == (25, 30)
    assert view_b.rows[0].observed_ip == "10.42.0.99"
    assert view_b.rows[0].kind == ROW_CONFIGURED


def test_offline_configured_retains_slot():
    view = _join(
        (_dev("aabbccddeeff", 4),),
        (_obs("aabbccddeeff", availability=Availability.OFFLINE),),
    )
    row = view.rows[0]
    assert row.slot == 4
    assert (row.dmx_start, row.dmx_end) == dmx_span(4)
    assert row.state == LOST


def test_wiz_off_shows_idle_not_lost_and_hides_new():
    view = _join(
        (_dev("aabbccddeeff", 1), _dev("bbccddeeff00", 2)),
        (
            _obs("aabbccddeeff", availability=Availability.OFFLINE),
            _obs("ffffffff0001", discovery=DiscoveryKind.NEW),
        ),
        wiz_enabled=False,
        bridge_available=True,
    )
    assert view.note == NOTE_WIZ_OFF
    assert [row.state for row in view.rows] == [IDLE, IDLE]
    assert all(row.kind == ROW_CONFIGURED for row in view.rows)
    assert not any(row.state == LOST for row in view.rows)
    assert not any(row.kind == ROW_NEW for row in view.rows)


def test_bridge_unavailable_is_idle_not_lost():
    view = _join(
        (_dev("aabbccddeeff", 1),),
        (_obs("aabbccddeeff", availability=Availability.OFFLINE),),
        wiz_enabled=True,
        bridge_available=False,
    )
    assert view.note == NOTE_BRIDGE_DOWN
    assert view.rows[0].state == IDLE
    assert view.rows[0].state != LOST


def test_healthy_bridge_unknown_vs_lost():
    idle = _join((_dev("aabbccddeeff", 1),), (), wiz_enabled=True, bridge_available=True)
    assert idle.rows[0].state == LOST
    lost = _join(
        (_dev("aabbccddeeff", 1),),
        (_obs("aabbccddeeff", availability=Availability.OFFLINE),),
        wiz_enabled=True,
        bridge_available=True,
    )
    assert lost.rows[0].state == LOST


def test_extended_map_is_not_truncated():
    view = _join((_dev("aabbccddeeff", 1), _dev("bbccddeeff00", 8)))
    assert [row.slot for row in view.rows] == [1, 8]
    assert view.extended is False
    assert view.rows[1].exceeds_v1 is False
    assert view.rows[1].dmx_start == 43


def test_short_identity_prefers_label():
    assert display_identity("aabbccddeeff", "") == "eeff"
    assert display_identity("aabbccddeeff", " WASH ") == "WASH"
    row = WizDeviceRow(
        kind=ROW_CONFIGURED,
        id="aabbccddeeff",
        slot=1,
        dmx_start=1,
        dmx_end=6,
        identity="WASH",
        state=OK,
    )
    assert list_label(row) == "01 WASH"
    new_row = WizDeviceRow(kind=ROW_NEW, id="aabbccddeeff", identity="CCDDEE", state=NEW)
    assert list_label(new_row) == "CCDDEE"
    assert new_row.slot is None
    assert display_identity("aa4130aa4130", new=True) == "AA4130"


def _open_devices(c, mapped=None, observations=(), *, wiz_enabled=False, bridge=False):
    if wiz_enabled:
        c.wiz_service.desired = True
        c.wiz_service.ap = "READY"
        c.wiz_service.bridge = "READY"
        c.wiz_service.tx_armed = True
        c.wiz_service.busy = False
        c._sync_wiz_runtime()
    if mapped is not None or observations or bridge or wiz_enabled:
        c.state.wiz_enabled = wiz_enabled
        c.apply_wiz_snapshot(
            WizDeviceMap(devices=tuple(mapped or ())),
            tuple(observations),
            bridge_available=bridge or wiz_enabled,
        )
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("WIZ")
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.state.menu_index = 1
    c.inject_cooked(ButtonEvent(K3, "press"))
    return c


def test_wiz_devices_is_after_control_in_wiz_submenu():
    c = make_controller()
    kinds = [slot.kind for slot in system_slots(c.state)]
    assert kinds == ["qlc", "net", "version", "shutdown"]
    assert "wiz" not in kinds
    assert "wiz_devices" not in kinds
    labels = [item.label for item in MENU_ITEMS]
    assert labels == ["STATUS", "OUTPUT", "WIZ", "SYSTEM"]
    assert labels.index("WIZ") == labels.index("SYSTEM") - 1
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("WIZ")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert [item.label for item in c.nav.current_items()] == ["CONTROL", "DEVICES"]
    c.state.menu_index = 1
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.WIZ_DEVICES
    fb = Renderer().render(c.state)
    assert _has_text(fb, 0, 0, "WIZ DEVICES")
    assert region_on_count(fb, 0, CONTENT_Y, FOCUS_W, ROW) == 0


def test_system_still_clamps_with_wiz_devices_row():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = 0
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.state.system_index == 0
    c.inject_cooked(EncoderEvent(E2, 40))
    assert c.state.system_index == SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.system_index == SYSTEM_SHUTDOWN_ROW
    assert SYSTEM_ROW_COUNT == 4


def test_k2_returns_and_k3_does_not_mutate(tmp_path: Path):
    mapped = (_dev("aabbccddeeff", 1), _dev("bbccddeeff00", 2))
    c = make_controller()
    path = tmp_path / "map.json"
    save_map(path, WizDeviceMap(devices=mapped))
    before = path.read_bytes()
    _open_devices(c, mapped, wiz_enabled=False)
    assert c.state.screen == ScreenId.WIZ_DEVICES
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "actions"
    assert c.state.screen == ScreenId.WIZ_DEVICES
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.wiz_prompt == ""
    assert [row.slot for row in c.state.wiz_device_rows] == [1, 2]
    assert path.read_bytes() == before
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    assert [item.label for item in c.nav.current_items()] == ["CONTROL", "DEVICES"]


def test_detail_is_observe_only():
    c = make_controller()
    _open_devices(
        c,
        (_dev("aabbccddeeff", 2, "FRONT"),),
        (_obs("aabbccddeeff", ip="10.42.0.4", availability=Availability.ONLINE),),
        wiz_enabled=True,
        bridge=True,
    )
    c.inject_cooked(ButtonEvent(K3, "press"))
    fb = Renderer().render(c.state)
    assert _has_text(fb, 0, 0, "WIZ DEVICE")
    assert _has_text(fb, LABEL_X, CONTENT_Y, "MOVE")
    c.state.wiz_prompt = ""
    c.state.wiz_device_detail = True
    fb = Renderer().render(c.state)
    assert _has_text(fb, LABEL_X, CONTENT_Y, "SLOT 02 CH007-012")
    assert _has_text(fb, LABEL_X, CONTENT_Y + ROW, "MAC aabbccddeeff")
    assert _has_text(fb, LABEL_X, CONTENT_Y + ROW * 2, "STATE OK")
    assert _has_text(fb, LABEL_X, CONTENT_Y + ROW * 3, "IP 10.42.0.4")
    c.state.wiz_device_rows = (
        WizDeviceRow(kind=ROW_NEW, id="ffeeddccbbaa", identity="bbaa", state=NEW, observed_ip="10.42.0.8"),
    )
    c.state.wiz_device_index = 0
    fb = Renderer().render(c.state)
    assert _has_text(fb, 0, 0, "NEW WIZ DEVICE")
    assert _has_text(fb, LABEL_X, CONTENT_Y + ROW * 3, "NOT MAPPED")


def test_wiz_off_page_renders_idle_rows():
    c = make_controller(wiz_enabled=False)
    _open_devices(
        c,
        (_dev("aabbccddeeff", 1), _dev("bbccddeeff00", 2)),
        (_obs("aabbccddeeff", availability=Availability.OFFLINE),),
        wiz_enabled=False,
        bridge=True,
    )
    assert c.state.wiz_devices_note == NOTE_WIZ_OFF
    assert [row.state for row in c.state.wiz_device_rows] == [IDLE, IDLE]
    fb = Renderer().render(c.state)
    assert _has_text(fb, 0, 0, "WIZ DEVICES")
    assert not _fb_has_string(fb, "LOST")


def test_list_clamps_scrollbar_and_short_list():
    mapped = tuple(_dev(f"aa00000000{i:02x}", i) for i in range(1, 13))
    c = make_controller()
    _open_devices(c, mapped)
    assert c.state.wiz_device_index == 0
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.state.wiz_device_index == 0
    assert c.state.scroll_offset == 0
    visible = wiz_devices_visible_count(c.state)
    y0 = CONTENT_Y + (ROW if c.state.wiz_devices_note else 0)
    fb = Renderer().render(c.state)
    top = scrollbar_metrics(12, visible, 0, visible * ROW)
    assert top is not None
    assert region_on_count(fb, SCROLL_X, y0, 3, visible * ROW) > 0
    below = CONTENT_Y + CONTENT_H - (y0 + visible * ROW)
    if below > 0:
        assert region_on_count(fb, SCROLL_X, y0 + visible * ROW, 3, below) == 0
    assert region_on_count(fb, 0, CONTENT_Y + (ROW if c.state.wiz_devices_note else 0), FOCUS_W, ROW) == FOCUS_W * ROW
    c.inject_cooked(EncoderEvent(E2, 40))
    assert c.state.wiz_device_index == 11
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.wiz_device_index == 11
    assert c.state.scroll_offset == 12 - visible
    fb2 = Renderer().render(c.state)
    assert region_on_count(fb2, 0, CONTENT_Y + (visible - 1) * ROW + (ROW if c.state.wiz_devices_note else 0), FOCUS_W, ROW) == FOCUS_W * ROW
    short = make_controller()
    _open_devices(short, (_dev("aabbccddeeff", 1),))
    vis = wiz_devices_visible_count(short.state)
    assert short.state.scroll_offset == 0
    fb3 = Renderer().render(short.state)
    assert scrollbar_metrics(1, vis, 0, vis * ROW) is None
    y0 = CONTENT_Y + (ROW if short.state.wiz_devices_note else 0)
    assert region_on_count(fb3, SCROLL_X, y0, 3, vis * ROW) == 0


def test_empty_list_has_no_blank_focus_crash():
    c = make_controller()
    _open_devices(c, ())
    c.inject_cooked(EncoderEvent(E2, 1))
    fb = Renderer().render(c.state)
    assert _has_text(fb, 0, 0, "WIZ DEVICES")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_device_detail is False


def test_shutdown_reachable_when_wiz_control_has_detail():
    c = make_controller(wiz_enabled=True, wiz_online=6, wiz_expected=6)
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(EncoderEvent(E2, 20))
    assert c.state.system_index == SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHUTTING_DOWN
    assert c.power.request_count == 1
    c = make_controller()
    _open_devices(c, (_dev("aabbccddeeff", 1),))
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_SHUTDOWN_ROW
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHUTTING_DOWN
    assert c.power.request_count == 1
    assert c.state.shutdown_requested is True


def test_draw_and_tick_do_not_touch_network_or_write_map(tmp_path: Path, monkeypatch):
    mapped = (_dev("aabbccddeeff", 1),)
    path = tmp_path / "map.json"
    save_map(path, WizDeviceMap(devices=mapped))
    before = path.read_bytes()
    c = make_controller(wiz_map_path=path)

    def boom(*args, **kwargs):
        raise AssertionError("hot-path subprocess")

    def no_send(*args, **kwargs):
        raise AssertionError("hot-path UDP")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "check_output", boom)
    monkeypatch.setattr(socket.socket, "sendto", no_send)
    monkeypatch.setattr(socket.socket, "send", no_send)
    _open_devices(c, mapped)
    c.inject_cooked(EncoderEvent(E2, 1))
    c.tick(now=1.0)
    Renderer().render(c.state)
    c.inject_cooked(ButtonEvent(K3, "press"))
    Renderer().render(c.state)
    assert path.read_bytes() == before
    src = SCREENS.read_text(encoding="utf-8")
    fn = src.split("def draw_wiz_devices")[1].split("\nSHUTTING")[0]
    assert "json.loads" not in fn
    assert "subprocess" not in fn
    assert "nmcli" not in fn
    assert "sendto" not in fn
    assert "save_map" not in PAGES.read_text(encoding="utf-8")
    ctrl = CONTROLLER.read_text(encoding="utf-8")
    assert "wizbridge" not in ctrl
    assert "38899" not in ctrl


def test_legacy_preview_is_read_only(tmp_path: Path):
    fixtures = tmp_path / "fixtures.json"
    fixtures.write_text(
        json.dumps(
            {
                "start_channel": 1,
                "channels_per_fixture": 6,
                "fixtures": [{"slot": 1, "mac": "AA:BB:CC:DD:EE:FF", "ip": "10.42.0.3"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = fixtures.read_bytes()
    c = make_controller(wiz_map_path=tmp_path / "map.json")
    assert c.state.wiz_device_rows[0].id == "aabbccddeeff"
    assert c.state.wiz_device_rows[0].slot == 1
    assert fixtures.read_bytes() == before
    assert not (tmp_path / "map.json").exists()


def test_phase_c_gate_and_loopback_artnet():
    src = BRIDGE.read_text(encoding="utf-8")
    assert "ARTNET_BIND" in src
    assert '"127.0.0.1"' in src
    assert "wiz_tx_allowed" in src
    assert "enroll_new_fixtures" not in src
    assert "save_known_fixtures" not in src
    assert PHASE_C_DEBT == ()
    assert "set_wiz_enabled" in CONTROLLER.read_text(encoding="utf-8")
    assert "wizbridge" not in CONTROLLER.read_text(encoding="utf-8")


def test_disabled_is_off_without_activity():
    view = _join(
        (_dev("aabbccddeeff", 5, enabled=False),),
        (_obs("aabbccddeeff", availability=Availability.ONLINE, dmx_active=True),),
    )
    assert view.rows[0].state == OFF
    assert view.rows[0].dmx_active is False


def test_activity_independent_of_availability():
    ok_active = _join(
        (_dev("aabbccddeeff", 5),),
        (_obs("aabbccddeeff", availability=Availability.ONLINE, dmx_active=True),),
    )
    ok_idle = _join(
        (_dev("aabbccddeeff", 5),),
        (_obs("aabbccddeeff", availability=Availability.ONLINE, dmx_active=False),),
    )
    lost_active = _join(
        (_dev("bbccddeeff00", 6),),
        (_obs("bbccddeeff00", availability=Availability.OFFLINE, dmx_active=True),),
    )
    lost_idle = _join(
        (_dev("bbccddeeff00", 6),),
        (_obs("bbccddeeff00", availability=Availability.OFFLINE, dmx_active=False),),
    )
    new_row = _join(
        (),
        (_obs("aa4130aa4130", discovery=DiscoveryKind.NEW, dmx_active=True),),
    )
    assert ok_active.rows[0].state == OK and ok_active.rows[0].dmx_active is True
    assert ok_idle.rows[0].state == OK and ok_idle.rows[0].dmx_active is False
    assert lost_active.rows[0].state == LOST and lost_active.rows[0].dmx_active is True
    assert lost_idle.rows[0].state == LOST and lost_idle.rows[0].dmx_active is False
    assert new_row.rows[0].state == NEW and new_row.rows[0].dmx_active is False


def test_device_row_activity_uses_existing_primitive():
    from light_console.display.activity import activity_frame
    from light_console.display.layout import ACTIVITY_W, ACTIVITY_X

    c = make_controller()
    _open_devices(
        c,
        (_dev("aabbccddeeff", 5),),
        (_obs("aabbccddeeff", availability=Availability.ONLINE, dmx_active=True),),
        wiz_enabled=True,
        bridge=True,
    )
    c.state.ui_now = 0.0
    fb = Renderer().render(c.state)
    y = CONTENT_Y
    assert activity_frame(0.0, True) == 0
    assert region_on_count(fb, ACTIVITY_X, y, ACTIVITY_W, ROW) > 0
    c.apply_wiz_snapshot(
        WizDeviceMap(devices=(_dev("aabbccddeeff", 5),)),
        (_obs("aabbccddeeff", availability=Availability.ONLINE, dmx_active=False),),
        bridge_available=True,
    )
    fb_idle = Renderer().render(c.state)
    assert region_on_count(fb_idle, ACTIVITY_X, y, ACTIVITY_W, ROW) == 0


def test_six_row_geometry_fits_without_clip():
    from light_console.display.layout import HEIGHT

    assert WIZ_DEVICES_VISIBLE == 6
    assert ROW == 8
    assert CONTENT_Y == 8
    last_bottom = CONTENT_Y + WIZ_DEVICES_VISIBLE * ROW - 1
    assert last_bottom == 55
    assert last_bottom < HEIGHT
    mapped = tuple(_dev(f"aa00000000{i:02x}", i) for i in range(1, 7))
    observations = tuple(
        _obs(f"aa00000000{i:02x}", availability=Availability.ONLINE, dmx_active=True)
        for i in range(1, 7)
    )
    c = make_controller()
    _open_devices(c, mapped, observations, wiz_enabled=True, bridge=True)
    c.state.ui_now = 0.0
    fb = Renderer().render(c.state)
    vis = wiz_devices_visible_count(c.state)
    assert vis == 6
    assert _has_text(fb, 0, 0, "WIZ DEVICES")
    assert region_on_count(fb, 0, ROW - 1, 8, 1) > 0
    sixth_y = CONTENT_Y + 5 * ROW
    assert sixth_y == 48
    assert _has_text(fb, LABEL_X, sixth_y, "06")
    from light_console.display.layout import ACTIVITY_W, ACTIVITY_X

    assert region_on_count(fb, ACTIVITY_X, sixth_y, ACTIVITY_W, ROW) > 0
    assert region_on_count(fb, ACTIVITY_X, sixth_y + ROW, ACTIVITY_W, HEIGHT - (sixth_y + ROW)) == 0
    c.inject_cooked(EncoderEvent(E2, 5))
    fb2 = Renderer().render(c.state)
    assert region_on_count(fb2, 0, sixth_y, FOCUS_W, ROW) == FOCUS_W * ROW
    assert region_on_count(fb2, 0, sixth_y + ROW, FOCUS_W, HEIGHT - (sixth_y + ROW)) == 0


def _bar_col(fb: Framebuffer, y: int, h: int) -> list[int]:
    return [fb.get(SCROLL_X + 1, yy) for yy in range(y, y + h)]


def test_zero_one_and_six_fit_without_scrollbar():
    empty = make_controller()
    _open_devices(empty, (), wiz_enabled=True, bridge=True)
    fb0 = Renderer().render(empty.state)
    assert empty.state.wiz_device_index == 0
    assert region_on_count(fb0, SCROLL_X, CONTENT_Y, 3, CONTENT_H) == 0
    assert _has_text(fb0, 0, 0, "WIZ DEVICES")

    one = make_controller()
    _open_devices(one, (_dev("aaaaaaaaaa01", 1),), wiz_enabled=True, bridge=True)
    fb1 = Renderer().render(one.state)
    vis = wiz_devices_visible_count(one.state)
    assert vis == 6
    assert scrollbar_metrics(1, vis, 0, vis * ROW) is None
    assert region_on_count(fb1, SCROLL_X, CONTENT_Y, 3, vis * ROW) == 0
    assert one.state.scroll_offset == 0

    six = make_controller()
    _open_devices(
        six,
        tuple(_dev(f"aa00000000{i:02x}", i) for i in range(1, 7)),
        wiz_enabled=True,
        bridge=True,
    )
    fb6 = Renderer().render(six.state)
    assert len(six.state.wiz_device_rows) == 6
    assert scrollbar_metrics(6, vis, 0, vis * ROW) is None
    assert region_on_count(fb6, SCROLL_X, CONTENT_Y, 3, vis * ROW) == 0
    assert six.state.scroll_offset == 0
    assert list(wiz_devices_viewport(six.state).window()) == [0, 1, 2, 3, 4, 5]
    six.inject_cooked(EncoderEvent(E2, 5))
    assert six.state.wiz_device_index == 5
    assert six.state.scroll_offset == 0
    six.inject_cooked(EncoderEvent(E2, 1))
    assert six.state.wiz_device_index == 5


def test_seven_rows_scrollbar_and_index_six_scrolls():
    mapped = tuple(_dev(f"aa00000000{i:02x}", i) for i in range(1, 8))
    c = make_controller()
    _open_devices(c, mapped, wiz_enabled=True, bridge=True)
    vis = wiz_devices_visible_count(c.state)
    assert vis == 6
    assert len(c.state.wiz_device_rows) == 7
    vp = wiz_devices_viewport(c.state)
    assert list(vp.window()) == [0, 1, 2, 3, 4, 5]
    fb = Renderer().render(c.state)
    track = vis * ROW
    assert scrollbar_metrics(7, vis, 0, track) is not None
    assert region_on_count(fb, SCROLL_X, CONTENT_Y, 3, track) > 0
    assert region_on_count(fb, SCROLL_X, CONTENT_Y + track, 3, CONTENT_H - track) == 0
    c.inject_cooked(EncoderEvent(E2, 6))
    assert c.state.wiz_device_index == 6
    assert c.state.scroll_offset == 1
    vp = wiz_devices_viewport(c.state)
    assert list(vp.window()) == [1, 2, 3, 4, 5, 6]
    fb2 = Renderer().render(c.state)
    assert region_on_count(fb2, 0, CONTENT_Y + 5 * ROW, FOCUS_W, ROW) == FOCUS_W * ROW
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.wiz_device_index == 6
    c.inject_cooked(EncoderEvent(E2, -20))
    assert c.state.wiz_device_index == 0
    assert c.state.scroll_offset == 0


def test_nine_and_eleven_rows_reach_last_and_scroll_up():
    nine = make_controller()
    _open_devices(
        nine,
        tuple(_dev(f"aa00000000{i:02x}", i) for i in range(1, 10)),
        wiz_enabled=True,
        bridge=True,
    )
    vis = wiz_devices_visible_count(nine.state)
    assert vis == 6
    nine.inject_cooked(EncoderEvent(E2, 20))
    assert nine.state.wiz_device_index == 8
    assert nine.state.scroll_offset == 3
    assert list(wiz_devices_viewport(nine.state).window()) == [3, 4, 5, 6, 7, 8]
    nine.inject_cooked(EncoderEvent(E2, -1))
    assert nine.state.wiz_device_index == 7
    assert nine.state.scroll_offset == 3

    eleven = make_controller()
    _open_devices(
        eleven,
        tuple(_dev(f"aa00000000{i:02x}", i) for i in range(1, 12)),
        wiz_enabled=True,
        bridge=True,
    )
    assert len(eleven.state.wiz_device_rows) == 11
    eleven.inject_cooked(EncoderEvent(E2, 10))
    assert eleven.state.wiz_device_index == 10
    assert eleven.state.wiz_device_rows[10].slot == 11
    assert eleven.state.scroll_offset == 5
    vp = wiz_devices_viewport(eleven.state)
    assert list(vp.window()) == [5, 6, 7, 8, 9, 10]
    eleven.inject_cooked(EncoderEvent(E2, 1))
    assert eleven.state.wiz_device_index == 10
    eleven.inject_cooked(EncoderEvent(E2, -20))
    assert eleven.state.wiz_device_index == 0
    assert eleven.state.scroll_offset == 0


def test_eleven_plus_new_rows_k3_targets_last_new():
    mapped = tuple(_dev(f"aa00000000{i:02x}", i) for i in range(1, 12))
    observations = (
        _obs("aaa111aaa111", discovery=DiscoveryKind.NEW),
        _obs("bbb222bbb222", discovery=DiscoveryKind.NEW),
        _obs("ccc333ccc333", discovery=DiscoveryKind.NEW),
    )
    c = make_controller()
    _open_devices(c, mapped, observations, wiz_enabled=True, bridge=True)
    rows = c.state.wiz_device_rows
    assert len(rows) == 14
    assert [row.state for row in rows[-3:]] == [NEW, NEW, NEW]
    vis = wiz_devices_visible_count(c.state)
    assert vis == 6
    vp = wiz_devices_viewport(c.state)
    assert list(vp.window()) == [0, 1, 2, 3, 4, 5]
    fb = Renderer().render(c.state)
    track = vis * ROW
    assert region_on_count(fb, SCROLL_X, CONTENT_Y, 3, track) > 0
    top_col = _bar_col(fb, CONTENT_Y, track)
    c.inject_cooked(EncoderEvent(E2, 13))
    assert c.state.wiz_device_index == 13
    assert c.state.scroll_offset == 8
    vp = wiz_devices_viewport(c.state)
    assert list(vp.window()) == [8, 9, 10, 11, 12, 13]
    assert rows[13].id == "ccc333ccc333"
    fb2 = Renderer().render(c.state)
    y0 = CONTENT_Y + (ROW if c.state.wiz_devices_note else 0)
    assert region_on_count(fb2, 0, y0 + 5 * ROW, FOCUS_W, ROW) == FOCUS_W * ROW
    bot_col = _bar_col(fb2, CONTENT_Y, track)
    assert top_col != bot_col
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_prompt == "add"
    assert c.state.wiz_prompt_slot == 12
    assert c.state.wiz_prompt_mac == "ccc333ccc333"
    assert c.state.wiz_device_index == 13
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.WIZ_DEVICES
    assert c.state.wiz_prompt == ""
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU

