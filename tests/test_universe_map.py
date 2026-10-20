from pathlib import Path

from light_console.display.components import draw_page_header, region_on_count
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import ACTIVITY_W, ACTIVITY_X, CONTENT_H, CONTENT_Y, SCROLL_W, SCROLL_X
from light_console.display.universe_map import (
    CELL_H,
    CELL_W,
    MAP_X0,
    MAP_Y0,
    MATRIX_H,
    MATRIX_W,
    VISIBLE_UNIVERSES,
    cell_origin,
    draw_universe_overview,
    draw_universe_raster,
    label_origin,
    raster_x0,
    raster_y0,
    universe_label,
    viewport_offset,
    visible_universes,
)
from light_console.display.screens import draw_output
from light_console.display.viewport import scrollbar_metrics
from light_console.display.widgets import text
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
UNIVERSE_SRC = ROOT / "light_console/display/universe_map.py"


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


def _cell_on(fb: Framebuffer, channel: int, x0: int, y0: int) -> bool:
    x, y = cell_origin(channel, x0=x0, y0=y0)
    return fb.get(x, y) == 1 and fb.get(x + CELL_W - 1, y) == 1


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


def test_cell_geometry_is_2x1_and_mapping_matches_each_raster():
    assert CELL_W == 2
    assert CELL_H == 1
    assert MATRIX_W == 64
    assert MATRIX_H == 16
    assert VISIBLE_UNIVERSES == 3
    fx = PatchedFixture(1, "PAR", 0, 0, 512)
    buf = empty_universe()
    buf[0] = 0
    buf[31] = 0
    buf[32] = 0
    buf[511] = 0
    for row in range(VISIBLE_UNIVERSES):
        fb = Framebuffer()
        x0 = raster_x0((1, 2, 3, 4))
        y0 = raster_y0(row)
        draw_universe_raster(fb, universe_id=0, fixtures=(fx,), buf=buf, now=0.0, x0=x0, y0=y0)
        x1, y1 = cell_origin(1, x0=x0, y0=y0)
        x32, y32 = cell_origin(32, x0=x0, y0=y0)
        x33, y33 = cell_origin(33, x0=x0, y0=y0)
        x512, y512 = cell_origin(512, x0=x0, y0=y0)
        assert (x1, y1) == (x0, y0)
        assert (x32, y32) == (x0 + 31 * CELL_W, y0)
        assert (x33, y33) == (x0, y0 + CELL_H)
        assert (x512, y512) == (x0 + 31 * CELL_W, y0 + 15 * CELL_H)
        assert fb.get(x1, y1) == 1
        assert fb.get(x1 + 1, y1) == 1
        assert fb.get(x32, y32) == 1
        assert fb.get(x33, y33) == 1
        assert fb.get(x512, y512) == 1
        assert fb.get(x512 + 1, y512) == 1
        assert y33 == y1 + 1
        assert y32 == y1


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
    assert (x1, y1) == (MAP_X0 + CELL_W, MAP_Y0)
    assert off.get(x0, y0) == 1
    assert on.get(x0, y0) == 1
    assert off.get(x1, y1) == 0
    assert on.get(x1, y1) == 1
    assert cell_origin(2) == (x1, y1)
    assert off.get(x0, y0 + 1) == 0
    assert on.get(x0, y0 + 1) == 0


def test_tail_channels_remain_addressable_and_dark():
    fx = PatchedFixture(1, "WIZ", 0, 0, 42)
    fb = Framebuffer()
    draw_universe_raster(fb, universe_id=0, fixtures=(fx,), buf=empty_universe(), now=0.0)
    x, y = cell_origin(43)
    assert fb.get(x, y) == 0
    x512, y512 = cell_origin(512)
    assert (x512, y512) == (MAP_X0 + 31 * CELL_W, MAP_Y0 + 15 * CELL_H)
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
    assert pages[0].title == "UNIVERSE"
    assert pages[0].universe == 2
    assert pages[0].universes == (1, 2, 3, 4)
    dmx_pages = [p for p in pages if p.kind == "dmx"]
    assert [p.universe for p in dmx_pages] == [1, 2]
    assert [p.title for p in dmx_pages] == ["LIVE DMX U1", "LIVE DMX U2"]


def test_three_universes_render_and_e2_scrolls_viewport(tmp_path):
    shows = tmp_path / "shows"
    shows.mkdir()
    dest = shows / "master.qxw"
    dest.write_text(SHIELD.read_text(encoding="utf-8"), encoding="utf-8")
    c = make_controller(shows_dir=shows)
    before = dest.read_bytes()
    routes = tuple(c.state.output_routes)
    c.state.screen = ScreenId.OUTPUT
    c.state.qlc_universes = (1, 2, 3, 4)
    c.state.output_universe = 1
    c.state.output_page = 0
    assert visible_universes((1, 2, 3, 4), c.state.output_universe) == (1, 2, 3)
    fb = Framebuffer()
    draw_output(fb, c.state)
    assert _has_text(fb, *label_origin(1, (1, 2, 3, 4), 0), "U1")
    assert _has_text(fb, *label_origin(2, (1, 2, 3, 4), 1), "U2")
    assert _has_text(fb, *label_origin(3, (1, 2, 3, 4), 2), "U3")
    assert not _has_text(fb, *label_origin(4, (1, 2, 3, 4), 2), "U4")
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.output_universe == 2
    assert c.state.output_page == 0
    assert visible_universes((1, 2, 3, 4), c.state.output_universe) == (2, 3, 4)
    fb2 = Framebuffer()
    draw_output(fb2, c.state)
    assert _has_text(fb2, *label_origin(2, (1, 2, 3, 4), 0), "U2")
    assert _has_text(fb2, *label_origin(3, (1, 2, 3, 4), 1), "U3")
    assert _has_text(fb2, *label_origin(4, (1, 2, 3, 4), 2), "U4")
    assert not _has_text(fb2, *label_origin(1, (1, 2, 3, 4), 0), "U1")
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.state.output_universe == 1
    assert visible_universes((1, 2, 3, 4), c.state.output_universe) == (1, 2, 3)
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.state.output_universe == 1
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.output_universe == 2
    c.inject_cooked(EncoderEvent(E3, 2))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert dest.read_bytes() == before
    assert c.state.output_routes == routes
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.output_page == 1


def test_e2_does_not_wrap_and_more_than_four_scrolls():
    c = make_controller()
    c.state.screen = ScreenId.OUTPUT
    c.state.qlc_universes = (1, 2, 3, 4, 5, 6)
    c.state.output_universe = 1
    c.state.output_page = 0
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.output_universe == 4
    assert visible_universes((1, 2, 3, 4, 5, 6), 4) == (4, 5, 6)
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.output_universe == 4
    fb = Framebuffer()
    draw_output(fb, c.state)
    assert _has_text(fb, *label_origin(4, (1, 2, 3, 4, 5, 6), 0), "U4")
    assert _has_text(fb, *label_origin(5, (1, 2, 3, 4, 5, 6), 1), "U5")
    assert _has_text(fb, *label_origin(6, (1, 2, 3, 4, 5, 6), 2), "U6")
    c.inject_cooked(EncoderEvent(E2, -3))
    assert c.state.output_universe == 1
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.state.output_universe == 1


def test_no_channel_endpoint_labels():
    src = UNIVERSE_SRC.read_text(encoding="utf-8")
    assert '"512"' not in src
    assert "text_right" not in src
    unis = (1, 2, 3, 4)
    fb = Framebuffer()
    draw_universe_overview(fb, universes=unis, fixtures=(), dmx={}, start_universe=1)
    want = Framebuffer()
    for row, uni in enumerate((1, 2, 3)):
        lx, ly = label_origin(uni, unis, row)
        text(want, lx, ly, universe_label(uni))
    from light_console.display.components import draw_scrollbar

    draw_scrollbar(want, 4, VISIBLE_UNIVERSES, 0)
    assert fb.digest() == want.digest()
    c = make_controller()
    c.state.screen = ScreenId.OUTPUT
    c.state.qlc_universes = unis
    c.state.output_universe = 1
    page = Framebuffer()
    draw_output(page, c.state)
    header = Framebuffer()
    draw_page_header(header, "UNIVERSE")
    assert all(page.get(x, y) == header.get(x, y) for y in range(CONTENT_Y) for x in range(page.width))
    assert not _has_text(page, MAP_X0, MAP_Y0 + MATRIX_H + 4, "1")
    assert not _has_text(page, MAP_X0 + MATRIX_W - 18, MAP_Y0 + MATRIX_H + 4, "512")


def test_independent_and_empty_universes_and_blink():
    fx1 = PatchedFixture(1, "A", 0, 0, 2)
    fx2 = PatchedFixture(2, "B", 1, 0, 1)
    dmx = {
        0: tuple([0, 255] + [0] * 510),
        1: tuple([0] * 512),
    }
    unis = (1, 2, 3)
    fb_on = Framebuffer()
    draw_universe_overview(
        fb_on, universes=unis, fixtures=(fx1, fx2), dmx=dmx, start_universe=1, now=0.0
    )
    fb_off = Framebuffer()
    draw_universe_overview(
        fb_off, universes=unis, fixtures=(fx1, fx2), dmx=dmx, start_universe=1, now=0.25
    )
    x0 = raster_x0(unis)
    y_u1 = raster_y0(0)
    y_u2 = raster_y0(1)
    y_u3 = raster_y0(2)
    assert _cell_on(fb_on, 1, x0, y_u1)
    assert _cell_on(fb_on, 2, x0, y_u1)
    assert not _cell_on(fb_off, 2, x0, y_u1)
    assert _cell_on(fb_off, 1, x0, y_u1)
    assert _cell_on(fb_on, 1, x0, y_u2)
    assert _cell_on(fb_off, 1, x0, y_u2)
    assert not _cell_on(fb_on, 2, x0, y_u2)
    assert region_on_count(fb_on, x0, y_u3, MATRIX_W, MATRIX_H) == 0
    assert region_on_count(fb_off, x0, y_u3, MATRIX_W, MATRIX_H) == 0


def test_scrollbar_tracks_viewport_and_hides_when_all_fit():
    unis4 = (1, 2, 3, 4)
    top = Framebuffer()
    draw_universe_overview(top, universes=unis4, fixtures=(), start_universe=1)
    bot = Framebuffer()
    draw_universe_overview(bot, universes=unis4, fixtures=(), start_universe=2)
    assert scrollbar_metrics(4, 3, 0, CONTENT_H) is not None
    assert scrollbar_metrics(4, 3, 1, CONTENT_H) is not None
    top_m = scrollbar_metrics(4, 3, 0, CONTENT_H)
    bot_m = scrollbar_metrics(4, 3, 1, CONTENT_H)
    assert top_m is not None and bot_m is not None
    assert top_m[0] < bot_m[0]
    assert region_on_count(top, SCROLL_X, CONTENT_Y, SCROLL_W, CONTENT_H) > 0
    assert region_on_count(bot, SCROLL_X, CONTENT_Y, SCROLL_W, CONTENT_H) > 0
    fit = Framebuffer()
    draw_universe_overview(fit, universes=(1, 2, 3), fixtures=(), start_universe=1)
    assert scrollbar_metrics(3, 3, 0, CONTENT_H) is None
    assert region_on_count(fit, SCROLL_X, CONTENT_Y, SCROLL_W, CONTENT_H) == 0
    assert viewport_offset((1, 2), 2) == 0


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
    assert MATRIX_H == 16
    assert CELL_W == 2
    assert CELL_H == 1
    total = 0
    for yy in range(CONTENT_Y, CONTENT_Y + 8):
        for xx in range(ACTIVITY_X, ACTIVITY_X + ACTIVITY_W):
            total += fb.get(xx, yy)
    assert total == 0
    assert c.state.marquee_key == ""
    x0 = raster_x0((1, 2))
    assert _cell_on(fb, 1, x0, raster_y0(0))
    assert not _cell_on(fb, 1, x0, raster_y0(1))
    assert cell_origin(512, x0=x0, y0=raster_y0(0)) == (
        x0 + 31 * CELL_W,
        raster_y0(0) + 15 * CELL_H,
    )


def test_overview_draw_is_local_framebuffer_work(monkeypatch):
    import subprocess
    import socket

    def boom(*args, **kwargs):
        raise AssertionError(f"overview draw escaped locally: {args[:1]}")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "check_output", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "socket", boom)
    src = UNIVERSE_SRC.read_text(encoding="utf-8")
    assert "subprocess" not in src
    assert "nmcli" not in src
    assert "qlcplusWS" not in src
    fx = tuple(PatchedFixture(i + 1, f"F{i}", i, 0, 512) for i in range(3))
    dmx = {i: tuple([255] * 512) for i in range(3)}
    fb = Framebuffer()
    draw_universe_overview(
        fb, universes=(1, 2, 3), fixtures=fx, dmx=dmx, start_universe=1, now=0.0
    )
    assert region_on_count(fb, raster_x0((1, 2, 3)), raster_y0(0), MATRIX_W, MATRIX_H) == 512 * 2
