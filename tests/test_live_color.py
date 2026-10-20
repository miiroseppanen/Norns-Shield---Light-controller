"""Live MASTER / SAT / HUE pipeline and PLAY presentation."""

from __future__ import annotations

import time
from pathlib import Path

from light_console.display.components import draw_status_row, region_on_count
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import ROW
from light_console.display.wordmark import HUE_Y, MASTER_Y, META_Y, OUTPUT_Y, SAT_Y
from light_console.display.renderer import Renderer
from light_console.fixture_roles import KIND_NON_COLOR, KIND_RGB, apply_roles_to_universe, role_for
from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K2, K3
from light_console.live_color import rgb_to_hsv, scale_intensity, transform_rgb, wrap_hue_deg
from light_console.output.fixtures import PatchedFixture, parse_fixtures
from light_console.output.pages import build_output_pages_from_state
from light_console.output.routing import OutputRoute
from light_console.output.summary import play_output_summary
from light_console.output.targets import AIR2DMX_FALLBACK_IP, PKNIGHT_FALLBACK_IP
from light_console.state import ScreenId
from light_console.status.midi import apply_launchpad
from light_console.ui.vocab import OFFLINE

from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]
SHIELD = ROOT / "qlc/projects/siirtyma-shield.qxw"

PAR = PatchedFixture(
    3,
    "PAR",
    1,
    0,
    8,
    manufacturer="Oloaxolx",
    model="60 W Battery LED Par Spot",
    mode="8ch",
)
FOG = PatchedFixture(
    0,
    "FOG",
    1,
    32,
    1,
    manufacturer="Eurolite",
    model="N-150 MK2",
    mode="1 channel mode",
)
WIZ = PatchedFixture(
    6,
    "WIZ",
    0,
    0,
    6,
    manufacturer="WiZ",
    model="WiZ RGB+CCT via Pi",
    mode="6 Channel",
)
STRANGE = PatchedFixture(99, "??", 0, 40, 4, manufacturer="Nope", model="X", mode="Y")


def _buf(**channels: int) -> list[int]:
    out = [0] * 64
    for key, val in channels.items():
        out[int(key)] = val
    return out


def _air_route() -> OutputRoute:
    return OutputRoute(2, "U2", "ARTNET", 1, "192.168.88.246", AIR2DMX_FALLBACK_IP, 1)


def _safe_route() -> OutputRoute:
    return OutputRoute(1, "U1", "ARTNET", 0, "127.0.0.1", "127.0.0.1", 0)


def _pknight_route() -> OutputRoute:
    return OutputRoute(2, "U2", "ARTNET", 1, "192.168.88.246", PKNIGHT_FALLBACK_IP, 1)


def _custom_route() -> OutputRoute:
    return OutputRoute(2, "U2", "ARTNET", 1, "192.168.88.246", "192.168.88.99", 1)


def _row_eq(fb: Framebuffer, y: int, label: str, value: str, **kwargs) -> bool:
    expected = Framebuffer()
    draw_status_row(expected, y, label, value, **kwargs)
    for dy in range(ROW):
        for x in range(fb.width):
            if fb.get(x, y + dy) != expected.get(x, y + dy):
                return False
    return True


def test_master_identity_scale_blackout_and_clamp():
    assert scale_intensity(200, 100) == 200
    assert scale_intensity(200, 50) == 100
    assert scale_intensity(200, 0) == 0
    assert scale_intensity(200, -10) == 0
    assert scale_intensity(200, 250) == 200


def test_master_preserves_rgb_ratios_on_rgb_only():
    r, g, b = transform_rgb(200, 100, 50, master=50)
    assert (r, g, b) == (100, 50, 25)
    assert transform_rgb(200, 100, 50, master=100) == (200, 100, 50)


def test_sat_identity_grayscale_boost_and_clamp():
    assert transform_rgb(255, 0, 0, sat=100) == (255, 0, 0)
    gray = transform_rgb(255, 0, 0, sat=0)
    assert gray[0] == gray[1] == gray[2]
    mid = transform_rgb(255, 0, 0, sat=50)
    h0, s0, v0 = rgb_to_hsv(255, 0, 0)
    h1, s1, v1 = rgb_to_hsv(*mid)
    assert abs(h1 - h0) < 1.0
    assert abs(v1 - v0) < 0.02
    assert abs(s1 - s0 * 0.5) < 0.03
    boosted = transform_rgb(128, 64, 64, sat=200)
    _h, s2, _v = rgb_to_hsv(*boosted)
    assert s2 <= 1.0001


def test_hue_identity_pos_neg_180_wrap_and_spacing():
    assert transform_rgb(255, 0, 0, hue=0) == (255, 0, 0)
    plus = transform_rgb(255, 0, 0, hue=60)
    assert plus[1] > plus[2]
    minus = transform_rgb(255, 0, 0, hue=-60)
    assert minus[2] > minus[1]
    flipped = transform_rgb(255, 0, 0, hue=180)
    assert flipped[0] < 20
    assert wrap_hue_deg(181) == -179
    assert wrap_hue_deg(-181) == 179
    assert wrap_hue_deg(180) == 180
    red = transform_rgb(255, 0, 0, hue=60)
    green = transform_rgb(0, 255, 0, hue=60)
    blue = transform_rgb(0, 0, 255, hue=60)
    assert len({red, green, blue}) == 3
    h_r, s_r, v_r = rgb_to_hsv(*red)
    h_g, _s_g, _v_g = rgb_to_hsv(*green)
    assert abs(s_r - 1) < 0.05
    assert abs(v_r - 1) < 0.05
    delta = (h_g - h_r) % 360
    assert abs(delta - 120) < 8
    del blue


def test_pipeline_identity_combined_and_no_cumulative_error():
    src = (200, 40, 80)
    assert transform_rgb(*src, sat=100, hue=0, master=100) == src
    once = transform_rgb(*src, sat=50, hue=60, master=50)
    twice = transform_rgb(*src, sat=50, hue=60, master=50)
    assert once == twice
    restored = transform_rgb(*src, sat=100, hue=0, master=100)
    assert restored == src
    source = list(src)
    transform_rgb(*source, sat=50, hue=90, master=40)
    assert tuple(source) == src
    h0, s0, v0 = rgb_to_hsv(*src)
    h1, s1, v1 = rgb_to_hsv(*transform_rgb(*src, sat=50, hue=60, master=100))
    assert abs(((h1 - h0) % 360) - 60) < 8
    assert abs(s1 - s0 * 0.5) < 0.05
    assert abs(v1 - v0) < 0.05
    full = transform_rgb(*src, sat=50, hue=60, master=100)
    half = transform_rgb(*src, sat=50, hue=60, master=50)
    assert half == tuple(scale_intensity(ch, 50) for ch in full)


def test_dynamic_source_is_not_snapshotted():
    a = transform_rgb(255, 0, 0, sat=50, hue=30, master=50)
    b = transform_rgb(0, 0, 255, sat=50, hue=30, master=50)
    c = transform_rgb(0, 255, 0, sat=50, hue=30, master=50)
    assert a != b != c


def test_par_fog_wiz_roles_and_passthrough():
    assert role_for(PAR).kind == KIND_RGB
    assert role_for(FOG).kind == KIND_NON_COLOR
    assert role_for(WIZ).kind == KIND_RGB
    assert role_for(STRANGE).kind == "unsupported"
    src = _buf(**{"0": 200, "1": 40, "2": 255, "3": 0, "4": 0, "5": 90, "6": 10, "7": 12, "32": 180})
    frozen = list(src)
    out = apply_roles_to_universe(src, (PAR, FOG), sat=0, hue=60, master=50)
    assert src == frozen
    assert out[0] == 100
    assert out[1] == 40
    assert out[5] == 90
    assert out[6] == 10
    assert out[7] == 12
    assert out[32] == 180
    assert out[2] == out[3] == out[4]
    ident = apply_roles_to_universe(src, (PAR, FOG), sat=100, hue=0, master=100)
    assert ident == src
    wiz_src = _buf(**{"0": 200, "1": 255, "2": 0, "3": 0, "4": 90, "5": 40})
    wiz_out = apply_roles_to_universe(wiz_src, (WIZ,), sat=0, hue=60, master=50)
    assert wiz_out[0] == 100
    assert wiz_out[1] == 255
    assert wiz_out[2] == 0
    assert wiz_out[3] == 0
    assert wiz_out[4] == 90
    assert wiz_out[5] == 40
    wiz_rgb = _buf(**{"0": 200, "1": 255, "2": 0, "3": 0, "4": 0, "5": 40})
    wiz_rgb_out = apply_roles_to_universe(wiz_rgb, (WIZ,), sat=0, hue=60, master=50)
    assert wiz_rgb_out[0] == 100
    assert wiz_rgb_out[4] == 0
    assert wiz_rgb_out[5] == 40
    assert wiz_rgb_out[1] == wiz_rgb_out[2] == wiz_rgb_out[3]
    strange_src = _buf(**{"40": 10, "41": 20, "42": 30, "43": 40})
    strange_out = apply_roles_to_universe(strange_src, (STRANGE,), sat=0, hue=90, master=10)
    assert strange_out[40:44] == [10, 20, 30, 40]


def test_workspace_fixture_classification():
    fixtures = parse_fixtures(SHIELD.read_text(encoding="utf-8"))
    kinds = {(fx.manufacturer, fx.model.strip(), fx.mode, role_for(fx).kind) for fx in fixtures}
    assert ("Eurolite", "N-150 MK2", "1 channel mode", KIND_NON_COLOR) in kinds
    assert ("Oloaxolx", "60 W Battery LED Par Spot", "8ch", KIND_RGB) in kinds
    assert ("WiZ", "WiZ RGB+CCT via Pi", "6 Channel", KIND_RGB) in kinds
    assert all(role_for(fx).kind != "unsupported" for fx in fixtures)


def test_play_layout_order_and_removed_rows():
    c = make_controller()
    fb = Renderer().render(c.state)
    assert _row_eq(fb, MASTER_Y, "MASTER", "100%", warn=False)
    assert _row_eq(fb, SAT_Y, "SAT", "100%", warn=False)
    assert _row_eq(fb, HUE_Y, "HUE", "0°", warn=False)
    show_ref = Framebuffer()
    draw_status_row(show_ref, SAT_Y, "SHOW", "MASTER")
    assert region_on_count(fb, 0, SAT_Y, 80, ROW) != region_on_count(
        show_ref, 0, SAT_Y, 80, ROW
    )
    midi_ref = Framebuffer()
    draw_status_row(midi_ref, MASTER_Y, "MIDI", "OK")
    assert region_on_count(fb, 0, MASTER_Y, 40, ROW) != region_on_count(
        midi_ref, 0, MASTER_Y, 40, ROW
    )


def test_play_midi_fault_still_visible():
    c = make_controller(launchpad_connected=False)
    fb = Renderer().render(c.state)
    assert _row_eq(fb, META_Y, "MIDI", OFFLINE)
    apply_launchpad(c.state, False)
    c._finish()
    assert "MIDI LP --" in c.state.warnings


def test_play_encoders_do_not_leak_into_output_or_system():
    c = make_controller()
    c.state.qlc_universes = (1, 2, 3, 4)
    c.state.output_universe = 1
    c.inject_cooked(EncoderEvent(E2, 5))
    assert c.state.saturation == 105
    c.state.screen = ScreenId.OUTPUT
    pages = build_output_pages_from_state(c.state)
    uni_pages = [i for i, p in enumerate(pages) if p.kind == "universe"]
    if uni_pages:
        c.state.output_page = uni_pages[0]
        c.inject_cooked(EncoderEvent(E2, 1))
        assert c.state.output_universe == 2
    assert c.state.saturation == 105
    before_master = c.state.master
    before_page = c.state.output_page
    c.inject_cooked(EncoderEvent(E1, 1))
    if len(pages) > 1:
        assert c.state.output_page != before_page
    assert c.state.master == before_master
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = 0
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.system_index == 1
    assert c.state.saturation == 105
    c.inject_cooked(EncoderEvent(E1, -3))
    assert c.state.master == before_master
    assert c.state.saturation == 105


def test_output_summary_from_state_not_hardcoded():
    c = make_controller(wiz_enabled=False)
    c.state.output_routes = (_safe_route(), _air_route())
    assert play_output_summary(c.state) == "AIR2DMX"
    c.state.wiz_enabled = True
    assert play_output_summary(c.state) == "WIZ + AIR2DMX"
    c.state.wiz_enabled = False
    c.state.output_routes = (_pknight_route(),)
    assert play_output_summary(c.state) == "PKNIGHT"
    c.state.output_routes = (_safe_route(),)
    assert play_output_summary(c.state) == "LOOPBACK"
    c.state.output_routes = ()
    assert play_output_summary(c.state) == "--"
    c.state.wiz_enabled = True
    assert play_output_summary(c.state) == "WIZ"
    c.state.wiz_enabled = False
    c.state.output_routes = (_custom_route(),)
    assert play_output_summary(c.state) == "--"


def test_play_shows_air2dmx_without_wiz_when_wiz_off():
    c = make_controller(wiz_enabled=False)
    c.state.output_routes = (_air_route(),)
    fb = Renderer().render(c.state)
    assert _row_eq(fb, OUTPUT_Y, "OUTPUT", "AIR2DMX", activity=False, now=c.state.ui_now)
    c.state.wiz_enabled = True
    fb2 = Renderer().render(c.state)
    assert _row_eq(fb2, OUTPUT_Y, "OUTPUT", "WIZ + AIR2DMX", activity=False, now=c.state.ui_now)


def test_sat_hue_do_not_write_simple_desk_or_mutate_qxw():
    original = SHIELD.read_text(encoding="utf-8")
    c = make_controller()
    desk: list[tuple] = []
    c.qlc.set_simple_desk_channel = lambda *args, **kwargs: desk.append(args)
    c.tick(now=0.1)
    c.inject_cooked(EncoderEvent(E2, -20))
    c.inject_cooked(EncoderEvent(E3, 15))
    c.tick(now=0.2)
    assert c.state.saturation == 80
    assert c.state.hue_shift == 15
    assert desk == []
    c.inject_cooked(EncoderEvent(E1, -10))
    c.tick(now=0.3)
    assert c.qlc.gm_sends[-1] == int(90 * 255 / 100)
    assert SHIELD.read_text(encoding="utf-8") == original


def test_transform_is_cheap():
    src = [i % 256 for i in range(512)]
    fixtures = (PAR, FOG, WIZ)
    t0 = time.perf_counter()
    for _ in range(2000):
        apply_roles_to_universe(src, fixtures, sat=80, hue=40, master=70)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0
    assert src[0] == 0


def test_hue_primary_rotations_and_neutral_lock():
    assert transform_rgb(255, 0, 0, hue=120) == (0, 255, 0)
    assert transform_rgb(0, 255, 0, hue=120) == (0, 0, 255)
    assert transform_rgb(0, 0, 255, hue=120) == (255, 0, 0)
    assert transform_rgb(255, 0, 0, hue=-120) == (0, 0, 255)
    assert transform_rgb(255, 0, 0, hue=180) == (0, 255, 255)
    assert transform_rgb(255, 0, 0, hue=-180) == (0, 255, 255)
    assert transform_rgb(128, 128, 128, hue=90) == (128, 128, 128)
    assert transform_rgb(255, 255, 255, hue=45) == (255, 255, 255)
    assert transform_rgb(0, 0, 0, hue=90, sat=200) == (0, 0, 0)
    assert transform_rgb(10, 10, 10, sat=0, hue=90) == (10, 10, 10)
    red = transform_rgb(255, 0, 0, hue=40)
    orange = transform_rgb(255, 128, 0, hue=40)
    green = transform_rgb(0, 255, 0, hue=40)
    blue = transform_rgb(0, 0, 255, hue=40)
    assert len({red, orange, green, blue}) == 4
    h_r, _s, v_r = rgb_to_hsv(*red)
    h_g, _s2, v_g = rgb_to_hsv(*green)
    assert abs(v_r - 1) < 0.02
    assert abs(v_g - 1) < 0.02
    assert abs(((h_g - h_r) % 360) - 120) < 8


def test_sat_progression_and_zero_hides_hue():
    src = (255, 0, 0)
    assert transform_rgb(*src, sat=100) == src
    assert transform_rgb(*src, sat=0) == (255, 255, 255)
    p25 = transform_rgb(*src, sat=25)
    p50 = transform_rgb(*src, sat=50)
    p75 = transform_rgb(*src, sat=75)
    _h, s25, v25 = rgb_to_hsv(*p25)
    _h2, s50, v50 = rgb_to_hsv(*p50)
    _h3, s75, v75 = rgb_to_hsv(*p75)
    assert abs(v25 - 1) < 0.02 and abs(v50 - 1) < 0.02 and abs(v75 - 1) < 0.02
    assert s25 < s50 < s75 < 1.01
    assert transform_rgb(*src, sat=0, hue=120) == (255, 255, 255)
    boosted = transform_rgb(200, 80, 80, sat=200)
    _hb, sb, vb = rgb_to_hsv(*boosted)
    _hs, ss, vs = rgb_to_hsv(200, 80, 80)
    assert sb >= ss
    assert abs(vb - vs) < 0.05
    assert transform_rgb(90, 90, 90, sat=200, hue=90) == (90, 90, 90)


def test_combined_reset_master_independence_no_drift():
    src = (200, 40, 80)
    moved = transform_rgb(*src, sat=30, hue=90)
    assert transform_rgb(*src, sat=100, hue=0) == src
    assert transform_rgb(*src, sat=150, hue=-120)
    assert transform_rgb(*src, sat=100, hue=0) == src
    sat_then_hue = transform_rgb(*src, sat=50, hue=60)
    assert sat_then_hue == transform_rgb(*src, sat=50, hue=60)
    color = transform_rgb(*src, sat=40, hue=30, master=100)
    dim = transform_rgb(*src, sat=40, hue=30, master=50)
    assert dim == tuple(scale_intensity(ch, 50) for ch in color)
    acc = src
    for sat, hue in ((30, 40), (150, -20), (80, 90), (100, 0)):
        acc = transform_rgb(*src, sat=sat, hue=hue)
    assert acc == src


def test_par_channel_policy_matrix():
    from light_console.fixture_roles import transform_par_channels

    src = (200, 40, 255, 0, 0, 90, 10, 12)
    ident = transform_par_channels(src, sat=100, hue=0)
    assert ident == src
    assert len(ident) == 8
    hue120 = transform_par_channels(src, sat=100, hue=120)
    assert hue120[0] == 200
    assert hue120[1] == 40
    assert hue120[2:5] == (0, 255, 0)
    assert hue120[5] == 90
    assert hue120[6] == 10
    assert hue120[7] == 12
    sat0 = transform_par_channels(src, sat=0, hue=120)
    assert sat0[0] == 200 and sat0[1] == 40
    assert sat0[2] == sat0[3] == sat0[4] == 255
    assert sat0[5:] == (90, 10, 12)
    sat50 = transform_par_channels(src, sat=50, hue=0)
    _h, s50, v50 = rgb_to_hsv(*sat50[2:5])
    assert abs(s50 - 0.5) < 0.05
    assert abs(v50 - 1) < 0.02
    assert sat50[5:] == (90, 10, 12)
    sat200 = transform_par_channels((200, 0, 200, 80, 80, 0, 3, 4), sat=200, hue=0)
    _hb, sb, _vb = rgb_to_hsv(*sat200[2:5])
    assert sb <= 1.0001
    assert sat200[0] == 200 and sat200[5:] == (0, 3, 4)
    white_only = transform_par_channels((255, 0, 0, 0, 0, 180, 0, 0), sat=0, hue=90)
    assert white_only == (255, 0, 0, 0, 0, 180, 0, 0)
    gray = transform_par_channels((200, 0, 40, 40, 40, 0, 0, 0), sat=50, hue=90)
    assert gray[2:5] == (40, 40, 40)


def test_play_reset_writes_status_not_ch_or_qxw(tmp_path, monkeypatch):
    from light_console.ui import controller as ctl

    path = tmp_path / "light-console.status"
    monkeypatch.setattr(ctl, "STATUS_PATH", path)
    original = SHIELD.read_text(encoding="utf-8")
    c = make_controller()
    desk: list[tuple] = []
    c.qlc.set_simple_desk_channel = lambda *args, **kwargs: desk.append(args)
    c.state.saturation = 40
    c.state.hue_shift = 70
    c.tick(now=0.1)
    c.inject_cooked(ButtonEvent(K2, "press"))
    c.tick(now=0.2)
    text = path.read_text()
    assert "sat=100" in text
    assert "hue=70" in text
    c.inject_cooked(ButtonEvent(K3, "press"))
    c.tick(now=0.3)
    text = path.read_text()
    assert "hue=0" in text
    assert "sat=100" in text
    assert "master=100" in text
    assert desk == []
    assert SHIELD.read_text(encoding="utf-8") == original

