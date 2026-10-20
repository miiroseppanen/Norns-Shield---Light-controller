from light_console.display.renderer import Renderer
from light_console.hardware.simulator import events_from_key
from light_console.hardware.shieldxl import HardwareNotReady, ShieldXLBackend
from light_console.state import ScreenId, demo_live_state
from light_console.hardware.events import EncoderEvent, SimCommandEvent

from tests.conftest import make_controller


def test_play_screen_has_pixels():
    state = demo_live_state(6)
    r = Renderer()
    r.render(state)
    ascii_art = r.fb.to_ascii()
    band = ascii_art.splitlines()[:16]
    assert any("#" in line for line in band)
    assert r.fb.to_ppm()[:2] == b"P6"


def test_renderer_every_page_without_exception():
    c = make_controller()
    r = Renderer()
    for screen in ScreenId:
        c.state.screen = screen
        r.force_dirty()
        fb = r.render(c.state)
        assert fb.width == 128
        assert fb.height == 64
        assert fb.digest() != b"\x00" * (128 * 64)


def test_menu_render():
    c = make_controller()
    c.state.screen = ScreenId.MENU
    r = Renderer()
    r.render(c.state)
    assert r.fb.digest() != b"\x00" * (128 * 64)


def test_keyboard_map():
    ev = events_from_key(113, True)  # q
    assert ev == [EncoderEvent(1, -1)]
    ev = events_from_key(1073741882, True)  # F1
    assert ev == [SimCommandEvent("toggle_qlc")]


def test_shieldxl_backend_refuses_without_gpio():
    try:
        ShieldXLBackend()
        raise AssertionError("must refuse on machines without shield SPI/GPIO")
    except HardwareNotReady:
        pass
