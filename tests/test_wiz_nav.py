"""Top-level WIZ navigation. No SCENES/CHASERS added by this task."""

from __future__ import annotations

from light_console.display.components import region_on_count
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import CONTENT_Y, FOCUS_W, LABEL_X, ROW, TOGGLE_LABEL_X
from light_console.display.renderer import Renderer
from light_console.display.widgets import text
from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, K1, K2, K3
from light_console.state import ScreenId
from light_console.ui.menu import DEFERRED_MENU_ITEMS, MENU_ITEMS, menu_index_of
from light_console.ui.pages import (
    SYSTEM_VERSION,
    WIZ_CONTROL_SCAN,
    WIZ_CONTROL_TOGGLE,
    system_slots,
    wiz_control_slots,
)
from light_console.ui.vocab import SCANNING

from tests.conftest import make_controller


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


def _render(c) -> Framebuffer:
    """Live OLED path: Renderer → draw_screen(state), no Navigation in the drawer."""
    r = Renderer()
    return r.render(c.state)


def _enter_wiz_submenu(c):
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("WIZ")
    c.inject_cooked(ButtonEvent(K3, "press"))


def _focus_on(fb: Framebuffer, row: int) -> bool:
    y = CONTENT_Y + row * ROW
    return region_on_count(fb, 0, y, FOCUS_W, ROW) == FOCUS_W * ROW


def _row_has(fb: Framebuffer, row: int, label: str) -> bool:
    return _has_text(fb, LABEL_X, CONTENT_Y + row * ROW, label)


def test_top_level_is_status_shows_output_wiz_system():
    labels = [item.label for item in MENU_ITEMS]
    assert labels == ["STATUS", "SHOWS", "OUTPUT", "WIZ", "SYSTEM", "RESTART", "SHUTDOWN"]
    assert labels.count("WIZ") == 1
    assert labels.index("WIZ") < labels.index("SYSTEM")
    deferred = {item.label for item in DEFERRED_MENU_ITEMS}
    assert "SCENES" in deferred and "SCENES" not in labels
    assert "CHASERS" in deferred and "CHASERS" not in labels
    assert "SHOWS" in labels and "SHOWS" not in deferred
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert [item.label for item in c.nav.current_items()] == labels


def test_wiz_submenu_control_and_devices():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("WIZ")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.MENU
    assert [item.label for item in c.nav.current_items()] == ["CONTROL", "DEVICES", "INFO"]
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.WIZ_CONTROL
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    c.state.menu_index = 1
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.WIZ_DEVICES
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    assert [item.label for item in c.nav.current_items()] == [
        "STATUS",
        "SHOWS",
        "OUTPUT",
        "WIZ",
        "SYSTEM",
        "RESTART",
        "SHUTDOWN",
    ]
    assert c.state.menu_index == menu_index_of("WIZ")


def test_system_has_version_and_no_wiz_duplicates():
    c = make_controller()
    kinds = [slot.kind for slot in system_slots(c.state)]
    assert kinds == ["qlc", "net", "version"]
    assert "wiz" not in kinds
    assert "wiz_devices" not in kinds
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_VERSION
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.VERSION
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.SYSTEM


def test_menu_clamps_and_does_not_wrap():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.menu_index == 0
    c.inject_cooked(EncoderEvent(E1, 20))
    assert c.state.menu_index == len(MENU_ITEMS) - 1
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.menu_index == len(MENU_ITEMS) - 1
    c.inject_cooked(EncoderEvent(E2, 3))
    assert c.state.menu_index == len(MENU_ITEMS) - 1


def test_wiz_submenu_renders_control_and_devices_not_top_level():
    c = make_controller()
    _enter_wiz_submenu(c)
    assert c.state.screen == ScreenId.MENU
    assert c.state.menu_title == "WIZ"
    assert c.state.menu_labels == ("CONTROL", "DEVICES", "INFO")
    assert c.state.menu_index == 0
    fb = _render(c)
    assert _has_text(fb, 0, 0, "WIZ")
    assert _row_has(fb, 0, "CONTROL")
    assert _row_has(fb, 1, "DEVICES")
    assert _row_has(fb, 2, "INFO")
    assert _focus_on(fb, 0)
    assert not _focus_on(fb, 1)
    assert not _focus_on(fb, 2)
    for row in range(7):
        assert not _row_has(fb, row, "STATUS")
        assert not _row_has(fb, row, "OUTPUT")
        assert not _row_has(fb, row, "SYSTEM")


def test_wiz_submenu_selector_follows_navigation_on_render():
    c = make_controller()
    _enter_wiz_submenu(c)
    fb = _render(c)
    assert _focus_on(fb, 0)
    assert not _focus_on(fb, 1)
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.menu_index == 1
    fb = _render(c)
    assert _row_has(fb, 0, "CONTROL")
    assert _row_has(fb, 1, "DEVICES")
    assert not _focus_on(fb, 0)
    assert _focus_on(fb, 1)
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.menu_index == 2
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.menu_index == 2
    c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.menu_index == 1
    c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.menu_index == 0
    fb = _render(c)
    assert _focus_on(fb, 0)
    assert not _focus_on(fb, 1)


def test_wiz_submenu_k3_opens_control_and_devices_pages():
    c = make_controller()
    _enter_wiz_submenu(c)
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.WIZ_CONTROL
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    assert c.state.menu_labels == ("CONTROL", "DEVICES", "INFO")
    assert c.state.menu_index == 0
    fb = _render(c)
    assert _has_text(fb, 0, 0, "WIZ")
    assert _row_has(fb, 0, "CONTROL")
    assert _focus_on(fb, 0)
    c.inject_cooked(EncoderEvent(E1, 1))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.WIZ_DEVICES
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    assert c.state.menu_index == 1
    fb = _render(c)
    assert _has_text(fb, 0, 0, "WIZ")
    assert _row_has(fb, 1, "DEVICES")
    assert _focus_on(fb, 1)


def test_wiz_submenu_k2_returns_top_level_with_wiz_selected():
    c = make_controller()
    _enter_wiz_submenu(c)
    c.inject_cooked(EncoderEvent(E1, 1))
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    assert c.state.menu_title == "MENU"
    assert c.state.menu_labels == ("STATUS", "SHOWS", "OUTPUT", "WIZ", "SYSTEM", "RESTART", "SHUTDOWN")
    assert c.state.menu_index == menu_index_of("WIZ")
    fb = _render(c)
    assert _has_text(fb, 0, 0, "MENU")
    assert _row_has(fb, 0, "STATUS")
    assert _row_has(fb, 1, "SHOWS")
    assert _row_has(fb, 2, "OUTPUT")
    assert _row_has(fb, 3, "WIZ")
    assert _row_has(fb, 4, "SYSTEM")
    assert _row_has(fb, 5, "RESTART")
    assert _row_has(fb, 6, "SHUTDOWN")
    assert _focus_on(fb, menu_index_of("WIZ"))
    assert not _focus_on(fb, 0)


def test_top_level_and_system_still_render_after_menu_view_publish():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    fb = _render(c)
    assert _has_text(fb, 0, 0, "MENU")
    assert _row_has(fb, 0, "STATUS")
    assert _row_has(fb, 1, "SHOWS")
    assert _row_has(fb, 2, "OUTPUT")
    assert _row_has(fb, 3, "WIZ")
    assert _row_has(fb, 4, "SYSTEM")
    assert _row_has(fb, 5, "RESTART")
    assert _row_has(fb, 6, "SHUTDOWN")
    assert _focus_on(fb, 0)
    c.state.menu_index = menu_index_of("SYSTEM")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SYSTEM
    fb = _render(c)
    assert _has_text(fb, 0, 0, "SYSTEM")
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    assert c.state.menu_index == menu_index_of("SYSTEM")
    fb = _render(c)
    assert _has_text(fb, 0, 0, "MENU")
    assert _row_has(fb, 4, "SYSTEM")
    assert _row_has(fb, 5, "RESTART")
    assert _row_has(fb, 6, "SHUTDOWN")
    assert _focus_on(fb, menu_index_of("SYSTEM"))


def test_wiz_control_has_scan_row():
    c = make_controller()
    _enter_wiz_submenu(c)
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.WIZ_CONTROL
    kinds = [slot.kind for slot in wiz_control_slots(c.state)]
    assert kinds == ["wiz", "scan"]
    fb = _render(c)
    assert _has_text(fb, 0, 0, "WIZ CONTROL")
    assert _has_text(fb, TOGGLE_LABEL_X, CONTENT_Y, "WIZ")
    assert _has_text(fb, TOGGLE_LABEL_X, CONTENT_Y + ROW, "SCAN")
    assert _focus_on(fb, 0)
    assert not _focus_on(fb, 1)
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.wiz_control_index == WIZ_CONTROL_SCAN
    fb = _render(c)
    assert not _focus_on(fb, 0)
    assert _focus_on(fb, 1)
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.wiz_control_index == WIZ_CONTROL_SCAN
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.state.wiz_control_index == WIZ_CONTROL_TOGGLE


def test_wiz_control_scan_pulses_discover_status(tmp_path, monkeypatch):
    from light_console.output.live_path import parse_live_controls
    from light_console.ui import controller as ctl

    path = tmp_path / "light-console.status"
    monkeypatch.setattr(ctl, "STATUS_PATH", path)
    c = make_controller(wiz_enabled=True)
    c.wiz_service.desired = True
    c.wiz_service.ap = "READY"
    c.wiz_service.bridge = "READY"
    c.wiz_service.tx_armed = True
    c.wiz_service.busy = False
    c._sync_wiz_runtime()
    c.state.ui_now = 1.0
    _enter_wiz_submenu(c)
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.wiz_control_index == WIZ_CONTROL_SCAN
    c.inject_cooked(ButtonEvent(K3, "press"))
    text = path.read_text(encoding="utf-8")
    assert parse_live_controls(text).discover is True
    assert "discover=1" in text
    slots = {slot.kind: slot for slot in wiz_control_slots(c.state)}
    fb = _render(c)
    assert _has_text(fb, TOGGLE_LABEL_X, slots["scan"].y, "SCAN")
    assert _has_text(fb, TOGGLE_LABEL_X, slots["scan"].y + ROW, SCANNING)
    c.state.ui_now = 10.0
    c._finish()
    assert parse_live_controls(path.read_text(encoding="utf-8")).discover is False


def test_wiz_control_scan_is_noop_when_wiz_off(tmp_path, monkeypatch):
    from light_console.output.live_path import parse_live_controls
    from light_console.ui import controller as ctl

    path = tmp_path / "light-console.status"
    monkeypatch.setattr(ctl, "STATUS_PATH", path)
    c = make_controller()
    _enter_wiz_submenu(c)
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_tx_armed is False
    assert parse_live_controls(path.read_text(encoding="utf-8")).discover is False
    assert c.state.wiz_enabled is False
