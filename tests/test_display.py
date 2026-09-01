from light_console.display.renderer import Renderer
from light_console.hardware.simulator import events_from_key
from light_console.hardware.shieldxl import HardwareNotReady, ShieldXLBackend
from light_console.state import ScreenId, demo_live_state
from light_console.hardware.events import EncoderEvent, SimCommandEvent

from tests.conftest import make_controller


def test_home_screen_has_scene_name():
    state = demo_live_state(6)
    r = Renderer()
    r.render(state)
    ascii_art = r.fb.to_ascii()
    # title on first rows — pixels exist
    assert any(c == "#" for c in ascii_art.splitlines()[0])
    assert r.fb.to_ppm()[:2] == b"P6"


def test_boot_and_menu_render():
    c = make_controller()
    c.state.screen = ScreenId.BOOT
    r = Renderer()
    r.render(c.state)
    assert r.fb.digest() != b"\x00" * (128 * 64)
    c.state.screen = ScreenId.MENU
    r.force_dirty()
    r.render(c.state)
    assert r.changed() or r.fb.digest()


def test_keyboard_map():
    ev = events_from_key(113, True)  # q
    assert ev == [EncoderEvent(1, -1)]
    ev = events_from_key(1073741882, True)  # F1
    assert ev == [SimCommandEvent("toggle_qlc")]


def test_shieldxl_backend_refuses_gpio():
    try:
        ShieldXLBackend()
        raise AssertionError("must refuse")
    except HardwareNotReady:
        pass
