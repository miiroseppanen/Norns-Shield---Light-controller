from pathlib import Path

from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import ACTIVITY_W, ACTIVITY_X, CONTENT_Y
from light_console.display.universe_map import (
    CELL,
    MAP_X0,
    MAP_Y0,
    MATRIX_H,
    MATRIX_W,
    cell_origin,
    draw_universe_raster,
)
from light_console.display.screens import draw_output
from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K3
from light_console.output.dmx import empty_universe
from light_console.output.fixtures import PatchedFixture, parse_fixtures
from light_console.output.pages import build_output_pages
from light_console.output.routing import parse_output_routes
from light_console.output.universe_map import (
    BLINK,
    CHANNELS,
    DARK,
    MAP_COLS,
    MAP_ROWS,
    STEADY,
    blink_lit,
    cell_state,
    channel_rc,
    parse_qlc_universes,
    patched_indexes,
    rc_channel,
)
from light_console.state import ScreenId
from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]
SHIELD = ROOT / "qlc/projects/siirtyma-shield.qxw"


def test_raster_mapping_is_32x16_exact():
    assert MAP_COLS == 32
    assert MAP_ROWS == 16
    assert CHANNELS == 512
    assert MAP_COLS * MAP_ROWS == 512
    assert channel_rc(1) == (0, 0)
    assert channel_rc(32) == (0, 31)
    assert channel_rc(33) == (1, 0)
    assert channel_rc(64) == (1, 31)
    assert channel_rc(65) == (2, 0)
    assert channel_rc(512) == (15, 31)
    assert rc_channel(0, 0) == 1
    assert rc_channel(15, 31) == 512
    cells = {channel_rc(ch) for ch in range(1, 513)}
    assert len(cells) == 512
    assert all(0 <= r < 16 and 0 <= c < 32 for r, c in cells)


def test_fixture_zero_based_address_maps_human_channels():
    fx = PatchedFixture(1, "WIZ", 0, 24, 6)
    occupied = patched_indexes((fx,), 0)
    assert occupied == frozenset(range(24, 30))
    human = {idx + 1 for idx in occupied}
    assert human == {25, 26, 27, 28, 29, 30}


def test_u1_xml0_u2_xml1_and_empty_universes():
    text = SHIELD.read_text(encoding="utf-8")
    assert parse_qlc_universes(text) == (1, 2, 3, 4)
    fixtures = parse_fixtures(text)
    u1 = patched_indexes(fixtures, 0)
    u2 = patched_indexes(fixtures, 1)
    assert min(u1) == 0
    assert max(u1) == 41
    assert 42 not in u1
    assert 511 not in u1
    assert min(u2) == 0
    assert max(u2) == 32
    assert 33 not in u2
    assert 511 not in u2


def test_unpatched_dark_patched_zero_steady_nonzero_blinks():
    patched = frozenset({0, 1, 2})
    buf = [0] * 512
    buf[1] = 40
    assert cell_state(10, patched, buf) == DARK
    assert cell_state(0, patched, buf) == STEADY
    assert cell_state(1, patched, buf) == BLINK
    assert blink_lit(0.0) is True
    assert blink_lit(0.24) is True
    assert blink_lit(0.25) is False
    assert blink_lit(0.49) is False
    assert blink_lit(0.50) is True


def test_blink_does_not_change_coordinates():
    fx = PatchedFixture(1, "PAR", 0, 0, 2)
    buf = empty_universe()
    buf[0] = 0
    buf[1] = 255
    off = Framebuffer()
    on = Framebuffer()
    draw_universe_raster(off, universe_id=0, fixtures=(fx,), buf=buf, now=0.25)
    draw_universe_raster(on, universe_id=0, fixtures=(fx,), buf=buf, now=0.0)
    x0, y0 = cell_origin(1)
    x1, y1 = cell_origin(2)
    assert (x0, y0) == (MAP_X0, MAP_Y0)
    assert (x1, y1) == (MAP_X0 + CELL, MAP_Y0)
    assert off.get(x0, y0) == 1
    assert on.get(x0, y0) == 1
    assert off.get(x1, y1) == 0
    assert on.get(x1, y1) == 1
    assert cell_origin(2) == (x1, y1)


def test_tail_channels_remain_addressable_and_dark():
    fx = PatchedFixture(1, "WIZ", 0, 0, 42)
    fb = Framebuffer()
    draw_universe_raster(fb, universe_id=0, fixtures=(fx,), buf=empty_universe(), now=0.0)
    x, y = cell_origin(43)
    assert fb.get(x, y) == 0
    x512, y512 = cell_origin(512)
    assert (x512, y512) == (MAP_X0 + 31 * CELL, MAP_Y0 + 15 * CELL)
    assert fb.get(x512, y512) == 0
    x42, y42 = cell_origin(42)
    assert fb.get(x42, y42) == 1


def test_output_starts_on_universe_map_live_dmx_unchanged():
    routes = parse_output_routes(SHIELD.read_text(encoding="utf-8"))
    fixtures = parse_fixtures(SHIELD.read_text(encoding="utf-8"))
    pages = build_output_pages(
        (),
        routes,
        fixtures=fixtures,
        qlc_universes=(1, 2, 3, 4),
        view_universe=2,
    )
    assert pages[0].kind == "universe"
    assert pages[0].title == "UNIVERSE 2"
    assert pages[0].universe == 2
    assert pages[0].universes == (1, 2, 3, 4)
    dmx_pages = [p for p in pages if p.kind == "dmx"]
    assert [p.universe for p in dmx_pages] == [1, 2]
    assert [p.title for p in dmx_pages] == ["LIVE DMX U1", "LIVE DMX U2"]


def test_e2_changes_universe_not_routing(tmp_path):
    shows = tmp_path / "shows"
    shows.mkdir()
    dest = shows / "master.qxw"
    dest.write_text(SHIELD.read_text(encoding="utf-8"), encoding="utf-8")
    c = make_controller(shows_dir=shows)
    before = dest.read_bytes()
    routes = tuple(c.state.output_routes)
    c.state.screen = ScreenId.OUTPUT
    assert c.state.qlc_universes == (1, 2, 3, 4)
    assert c.state.output_page == 0
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.output_universe == 2
    assert c.state.output_page == 0
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.output_universe == 3
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.output_universe == 4
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.output_universe == 1
    c.inject_cooked(EncoderEvent(E3, 2))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert dest.read_bytes() == before
    assert c.state.output_routes == routes
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.output_page == 1


def test_geometry_independent_of_target_marquee_and_activity():
    c = make_controller()
    c.state.fixtures = (PatchedFixture(1, "PAR", 0, 0, 8),)
    c.state.qlc_universes = (1, 2)
    c.state.output_universe = 1
    c.state.screen = ScreenId.OUTPUT
    c.state.ui_now = 0.4
    fb = Framebuffer()
    draw_output(fb, c.state)
    assert MATRIX_W == 64
    assert MATRIX_H == 32
    assert CELL == 2
    total = 0
    for yy in range(CONTENT_Y, CONTENT_Y + 8):
        for xx in range(ACTIVITY_X, ACTIVITY_X + ACTIVITY_W):
            total += fb.get(xx, yy)
    assert total == 0
    assert c.state.marquee_key == ""
    x, y = cell_origin(1)
    assert fb.get(x, y) == 1
    c.state.output_universe = 2
    fb2 = Framebuffer()
    draw_output(fb2, c.state)
    assert cell_origin(512) == (MAP_X0 + 31 * CELL, MAP_Y0 + 15 * CELL)
    assert fb2.get(*cell_origin(1)) == 0
