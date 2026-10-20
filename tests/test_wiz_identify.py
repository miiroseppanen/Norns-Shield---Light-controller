"""WIZ DEVICES cursor identify: status intent only. No WiZ UDP from OLED/UI."""

from __future__ import annotations

from pathlib import Path

from light_console.display.renderer import Renderer
from light_console.hardware.events import ButtonEvent, EncoderEvent, E2, K2
from light_console.output.live_path import parse_live_controls
from light_console.prefs import load_prefs
from light_console.state import ScreenId
from light_console.ui.vocab import LOST
from light_console.wiz.device_map import WizDeviceMap, save_map
from light_console.wiz.observe import Availability, DiscoveryKind

from tests.conftest import make_controller
from tests.test_wiz_devices import _dev, _obs, _open_devices

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "light_console/ui/controller.py"
PAGES = ROOT / "light_console/ui/pages.py"
SCREENS = ROOT / "light_console/display/screens.py"
NAV = ROOT / "light_console/ui/nav.py"
BRIDGE = ROOT / "services/wiz/wiz_artnet_bridge.py"

MAC_01 = "9877d5b20620"
MAC_02 = "9877d5b206e4"
NEW_A = "9877d5aa2ece"
NEW_B = "9877d5aa4130"


def _status_path(tmp_path, monkeypatch):
    from light_console.ui import controller as ctl

    path = tmp_path / "light-console.status"
    monkeypatch.setattr(ctl, "STATUS_PATH", path)
    return path


def _identify_of(path: Path) -> str:
    if not path.is_file():
        return ""
    return parse_live_controls(path.read_text(encoding="utf-8")).identify_mac


def test_enter_devices_identifies_absolute_selected_mac(tmp_path, monkeypatch):
    path = _status_path(tmp_path, monkeypatch)
    mapped = (_dev(MAC_01, 1), _dev(MAC_02, 2))
    obs = (
        _obs(MAC_01, ip="10.42.0.10", availability=Availability.ONLINE),
        _obs(MAC_02, ip="10.42.0.11", availability=Availability.ONLINE),
    )
    c = make_controller()
    _open_devices(c, mapped, obs, wiz_enabled=True, bridge=True)
    assert c.state.screen == ScreenId.WIZ_DEVICES
    assert c.state.wiz_device_index == 0
    assert c.state.wiz_identify_mac == MAC_01
    assert _identify_of(path) == MAC_01
    assert "wiz=on" in path.read_text(encoding="utf-8")


def test_move_selection_replaces_identify_target(tmp_path, monkeypatch):
    path = _status_path(tmp_path, monkeypatch)
    mapped = (_dev(MAC_01, 1), _dev(MAC_02, 2))
    c = make_controller()
    _open_devices(c, mapped, wiz_enabled=True, bridge=True)
    assert _identify_of(path) == MAC_01
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.wiz_device_index == 1
    assert c.state.wiz_identify_mac == MAC_02
    assert _identify_of(path) == MAC_02
    assert path.read_text(encoding="utf-8").count("identify=") == 1


def test_new_device_identify_does_not_mutate_map(tmp_path, monkeypatch):
    path = _status_path(tmp_path, monkeypatch)
    map_path = tmp_path / "map.json"
    mapped = (_dev(MAC_01, 1),)
    save_map(map_path, WizDeviceMap(devices=mapped))
    before = map_path.read_bytes()
    c = make_controller(wiz_map_path=map_path)
    _open_devices(
        c,
        mapped,
        (_obs(NEW_A, ip="10.42.0.40", discovery=DiscoveryKind.NEW),),
        wiz_enabled=True,
        bridge=True,
    )
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.wiz_device_rows[1].id == NEW_A
    assert c.state.wiz_identify_mac == NEW_A
    assert _identify_of(path) == NEW_A
    assert map_path.read_bytes() == before
    assert all(row.id != NEW_A or row.slot is None for row in c.state.wiz_device_rows)


def test_new_a_to_new_b_swaps_identify_without_add(tmp_path, monkeypatch):
    path = _status_path(tmp_path, monkeypatch)
    map_path = tmp_path / "map.json"
    mapped = (_dev(MAC_01, 1),)
    save_map(map_path, WizDeviceMap(devices=mapped))
    before = map_path.read_bytes()
    c = make_controller(wiz_map_path=map_path)
    _open_devices(
        c,
        mapped,
        (
            _obs(NEW_A, ip="10.42.0.40", discovery=DiscoveryKind.NEW),
            _obs(NEW_B, ip="10.42.0.41", discovery=DiscoveryKind.NEW),
        ),
        wiz_enabled=True,
        bridge=True,
    )
    news = [row.id for row in c.state.wiz_device_rows if row.kind == "new"]
    assert news == [NEW_A, NEW_B]
    c.inject_cooked(EncoderEvent(E2, 1))
    assert _identify_of(path) == NEW_A
    c.inject_cooked(EncoderEvent(E2, 1))
    assert _identify_of(path) == NEW_B
    assert c.state.wiz_prompt == ""
    assert map_path.read_bytes() == before


def test_k2_leave_devices_clears_identify(tmp_path, monkeypatch):
    path = _status_path(tmp_path, monkeypatch)
    c = make_controller()
    _open_devices(c, (_dev(MAC_01, 1),), wiz_enabled=True, bridge=True)
    assert _identify_of(path) == MAC_01
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    assert c.state.wiz_identify_mac == ""
    assert _identify_of(path) == ""


def test_scroll_beyond_six_uses_absolute_mac(tmp_path, monkeypatch):
    path = _status_path(tmp_path, monkeypatch)
    mapped = tuple(_dev(f"aa00000000{i:02x}", i) for i in range(1, 7))
    extra = (
        _obs(NEW_A, ip="10.42.0.40", discovery=DiscoveryKind.NEW),
        _obs(NEW_B, ip="10.42.0.41", discovery=DiscoveryKind.NEW),
    )
    c = make_controller()
    _open_devices(c, mapped, extra, wiz_enabled=True, bridge=True)
    assert len(c.state.wiz_device_rows) == 8
    assert c.state.wiz_device_index == 0
    c.inject_cooked(EncoderEvent(E2, 6))
    assert c.state.wiz_device_index == 6
    assert c.state.scroll_offset >= 1
    assert c.state.wiz_device_rows[6].id == NEW_A
    assert _identify_of(path) == NEW_A
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.wiz_device_index == 7
    assert _identify_of(path) == NEW_B


def test_lost_without_ip_still_navigates(tmp_path, monkeypatch):
    path = _status_path(tmp_path, monkeypatch)
    c = make_controller()
    _open_devices(
        c,
        (_dev(MAC_01, 1), _dev(MAC_02, 2)),
        (_obs(MAC_01, availability=Availability.OFFLINE),),
        wiz_enabled=True,
        bridge=True,
    )
    assert c.state.wiz_device_rows[0].state == LOST
    assert _identify_of(path) == MAC_01
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.wiz_device_index == 1
    assert _identify_of(path) == MAC_02
    assert c.state.screen == ScreenId.WIZ_DEVICES


def test_wiz_off_publishes_no_identify(tmp_path, monkeypatch):
    path = _status_path(tmp_path, monkeypatch)
    c = make_controller(wiz_enabled=False)
    _open_devices(c, (_dev(MAC_01, 1),), wiz_enabled=False, bridge=True)
    assert c.state.wiz_tx_armed is False
    assert c.state.screen == ScreenId.WIZ_DEVICES
    assert c.state.wiz_identify_mac == ""
    text = path.read_text(encoding="utf-8")
    assert "wiz=off" in text
    assert _identify_of(path) == ""


def test_shutdown_clears_identify(tmp_path, monkeypatch):
    path = _status_path(tmp_path, monkeypatch)
    c = make_controller()
    _open_devices(c, (_dev(MAC_01, 1),), wiz_enabled=True, bridge=True)
    assert _identify_of(path) == MAC_01
    c.begin_appliance_shutdown()
    assert c.state.screen == ScreenId.SHUTTING_DOWN
    assert c.state.wiz_identify_mac == ""
    assert _identify_of(path) == ""


def test_restart_does_not_persist_identify(tmp_path, monkeypatch):
    path = _status_path(tmp_path, monkeypatch)
    prefs = tmp_path / "prefs.yaml"
    c = make_controller(prefs_path=prefs)
    _open_devices(c, (_dev(MAC_01, 1),), wiz_enabled=True, bridge=True)
    assert _identify_of(path) == MAC_01
    loaded = load_prefs(prefs)
    assert not hasattr(loaded, "identify_mac") or getattr(loaded, "identify_mac", "") == ""
    yaml_text = prefs.read_text(encoding="utf-8") if prefs.is_file() else ""
    assert "identify" not in yaml_text
    c2 = make_controller(prefs_path=prefs)
    assert c2.state.screen == ScreenId.PLAY
    assert c2.state.wiz_identify_mac == ""
    c2.tick(now=0.1)
    assert _identify_of(path) == ""


def test_selection_leaves_map_byte_identical(tmp_path, monkeypatch):
    _status_path(tmp_path, monkeypatch)
    map_path = tmp_path / "map.json"
    mapped = (_dev(MAC_01, 1), _dev(MAC_02, 2))
    save_map(map_path, WizDeviceMap(devices=mapped))
    before = map_path.read_bytes()
    c = make_controller(wiz_map_path=map_path)
    _open_devices(
        c,
        mapped,
        (
            _obs(NEW_A, ip="10.42.0.40", discovery=DiscoveryKind.NEW),
            _obs(MAC_01, ip="10.42.0.10", availability=Availability.ONLINE),
        ),
        wiz_enabled=True,
        bridge=True,
    )
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert map_path.read_bytes() == before


def test_renderer_does_not_write_identify(tmp_path, monkeypatch):
    path = _status_path(tmp_path, monkeypatch)
    c = make_controller()
    _open_devices(c, (_dev(MAC_01, 1),), wiz_enabled=True, bridge=True)
    before = path.read_text(encoding="utf-8")
    mtime = path.stat().st_mtime
    Renderer().render(c.state)
    assert path.read_text(encoding="utf-8") == before
    assert path.stat().st_mtime == mtime


def test_dmx_activity_flag_independent_of_identify(tmp_path, monkeypatch):
    _status_path(tmp_path, monkeypatch)
    c = make_controller()
    _open_devices(
        c,
        (_dev(MAC_01, 1),),
        (_obs(MAC_01, ip="10.42.0.10", availability=Availability.ONLINE, dmx_active=True),),
        wiz_enabled=True,
        bridge=True,
    )
    assert c.state.wiz_device_rows[0].dmx_active is True
    assert c.state.wiz_identify_mac == MAC_01


def test_ui_modules_do_not_send_wiz_udp():
    for src_path in (CONTROLLER, PAGES, SCREENS, NAV):
        text = src_path.read_text(encoding="utf-8")
        assert "sendto" not in text
        assert "38899" not in text
        assert "getPilot" not in text
        assert "setPilot" not in text
    screens = SCREENS.read_text(encoding="utf-8")
    draw = screens.split("def draw_wiz_devices")[1].split("\ndef ")[0]
    assert "identify" not in draw
    assert "STATUS_PATH" not in draw
    bridge = BRIDGE.read_text(encoding="utf-8")
    assert "identify_once" in bridge
    assert "IDENTIFY_PARAMS" in bridge
    assert 'return sock.sendto(payload,dest)' in bridge
    sendto_lines = [ln.strip() for ln in bridge.splitlines() if ".sendto(" in ln]
    assert sendto_lines == ["return sock.sendto(payload,dest)"]
