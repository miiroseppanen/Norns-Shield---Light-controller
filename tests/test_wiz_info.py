from light_console.display.layout import CONTENT_RIGHT, LABEL_X
from light_console.display.renderer import Renderer
from light_console.display.screens import WIZ_INFO_LINES
from light_console.display.widgets import CELL_W
from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, K1, K2, K3
from light_console.state import ScreenId
from light_console.ui.menu import menu_index_of

from tests.conftest import make_controller
from tests.test_wiz_nav import _has_text, _row_has


def _open_wiz_info(c):
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("WIZ")
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.state.menu_index = 2
    c.inject_cooked(ButtonEvent(K3, "press"))


def test_wiz_info_lines_fit_one_oled_page():
    field_w = CONTENT_RIGHT - LABEL_X
    assert len(WIZ_INFO_LINES) <= 7
    for line in WIZ_INFO_LINES:
        assert len(line) * CELL_W <= field_w, line
    assert WIZ_INFO_LINES == (
        "AFTER BOOT WAIT.",
        "LAMPS JOIN LATE.",
        "THEY APPEAR IN",
        "DEVICES.",
        "",
        "GONE 10 MIN:",
        "POWER CYCLE IT.",
    )


def test_wiz_info_opens_from_submenu_and_k2_returns():
    c = make_controller()
    _open_wiz_info(c)
    assert c.state.screen == ScreenId.WIZ_INFO
    fb = Renderer().render(c.state)
    assert _has_text(fb, 0, 0, "WIZ INFO")
    assert _row_has(fb, 0, "AFTER BOOT WAIT.")
    assert _row_has(fb, 1, "LAMPS JOIN LATE.")
    assert _row_has(fb, 6, "POWER CYCLE IT.")
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    assert [item.label for item in c.nav.current_items()] == ["CONTROL", "DEVICES", "INFO"]
    assert c.state.menu_index == 2


def test_wiz_info_ignores_keys_and_encoders():
    c = make_controller()
    _open_wiz_info(c)
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.inject_cooked(EncoderEvent(E1, 2))
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.screen == ScreenId.WIZ_INFO
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.PLAY
