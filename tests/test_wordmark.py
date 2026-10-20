"""STATUS LIGHT CTRL wordmark geometry and page isolation."""

from __future__ import annotations

import time
from pathlib import Path

from light_console.display.components import draw_page_header, draw_status_row
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import CONTENT_RIGHT, LABEL_X, ROW, WIDTH
from light_console.display.lifecycle import (
    STARTING_UP_TEXT,
    SHUTTING_DOWN_TEXT,
    lifecycle_origin,
    render_lifecycle,
)
from light_console.display.renderer import Renderer
from light_console.display.screens import draw_output, draw_play, draw_system
from light_console.display.universe_map import draw_universe_overview
from light_console.display.wordmark import (
    BAND_H,
    HUE_Y,
    LETTER_GAP,
    MASK_HEIGHT,
    MASK_WIDTH,
    PAIR_KERN,
    MASTER_Y,
    ON_PIXELS,
    SAT_Y,
    WORD_GAP,
    _GLYPHS,
    draw_wordmark,
    origin,
)
from light_console.state import ScreenId

from tests.conftest import make_controller
from tests.test_universe_map import _has_text

WORDMARK_SRC = Path(__file__).resolve().parents[1] / "light_console/display/wordmark.py"


def _heading_present(fb: Framebuffer, title: str) -> bool:
    return _has_text(fb, 0, 0, title)


def test_wordmark_size_and_placement():
    assert 110 <= MASK_WIDTH <= 124
    assert MASK_HEIGHT == 13
    x, y = origin()
    assert x == LABEL_X
    assert x != (WIDTH - MASK_WIDTH) // 2
    assert y == max(0, (BAND_H - MASK_HEIGHT) // 2)
    assert y >= 0
    assert x + MASK_WIDTH <= CONTENT_RIGHT
    assert x + MASK_WIDTH <= WIDTH
    assert y + MASK_HEIGHT <= MASTER_Y
    assert y + MASK_HEIGHT <= BAND_H
    assert LETTER_GAP == 2
    assert WORD_GAP == 8
    assert PAIR_KERN[("C", "T")] == -1


def test_status_uses_light_ctrl_not_light_console_heading():
    c = make_controller()
    c.state.ui_now = 0.0
    fb = Renderer().render(c.state)
    assert not _heading_present(fb, "LIGHT CONSOLE")
    x0, y0 = origin()
    for lx, ly in ON_PIXELS:
        assert fb.get(x0 + lx, y0 + ly) == 1
    expected = Framebuffer()
    draw_wordmark(expected)
    for y in range(BAND_H):
        for x in range(fb.width):
            assert fb.get(x, y) == expected.get(x, y)


def test_wordmark_does_not_collide_with_live_controls():
    c = make_controller()
    fb = Renderer().render(c.state)
    x0, y0 = origin()
    for _lx, ly in ON_PIXELS:
        assert y0 + ly < MASTER_Y
    master = Framebuffer()
    draw_status_row(master, MASTER_Y, "MASTER", "100%", warn=False)
    for dy in range(ROW):
        for x in range(fb.width):
            assert fb.get(x, MASTER_Y + dy) == master.get(x, MASTER_Y + dy)
    sat = Framebuffer()
    draw_status_row(sat, SAT_Y, "SAT", "100%", warn=False)
    for dy in range(ROW):
        for x in range(fb.width):
            assert fb.get(x, SAT_Y + dy) == sat.get(x, SAT_Y + dy)
    hue = Framebuffer()
    draw_status_row(hue, HUE_Y, "HUE", "0°", warn=False)
    for dy in range(ROW):
        for x in range(fb.width):
            assert fb.get(x, HUE_Y + dy) == hue.get(x, HUE_Y + dy)


def test_static_wordmark_is_complete_and_time_invariant():
    idle = Framebuffer()
    later = Framebuffer()
    draw_wordmark(idle)
    draw_wordmark(later)
    assert idle.digest() == later.digest()
    assert len(ON_PIXELS) > 400
    x0, y0 = origin()
    assert idle.get(x0, y0) == 1
    c = make_controller()
    c.state.ui_now = 0.0
    a = Framebuffer()
    draw_play(a, c.state)
    c.state.ui_now = 12.3
    b = Framebuffer()
    draw_play(b, c.state)
    x0, y0 = origin()
    for lx, ly in ON_PIXELS:
        assert a.get(x0 + lx, y0 + ly) == 1
        assert b.get(x0 + lx, y0 + ly) == 1


def test_wordmark_left_aligns_with_status_labels():
    x0, _y0 = origin()
    assert x0 == LABEL_X
    master = Framebuffer()
    draw_status_row(master, MASTER_Y, "MASTER", "100%", warn=False)
    master_xs = [
        x
        for x in range(WIDTH)
        if any(master.get(x, MASTER_Y + y) for y in range(ROW))
    ]
    word_left = min(x0 + lx for lx, _ly in ON_PIXELS)
    assert word_left == master_xs[0] == LABEL_X


def test_ctrl_ct_kerning_is_tighter_than_letter_gap():
    from light_console.display.wordmark import _GLYPHS, _compose, _pair_gap

    assert _pair_gap("C", "T") == LETTER_GAP - 1
    assert _pair_gap("L", "I") == LETTER_GAP
    _, _w, _h, on = _compose("CT")
    c_w = len(_GLYPHS["C"][0])
    t_bar = min(x for x, y in on if y <= 1 and x >= c_w - 1)
    assert t_bar == c_w + _pair_gap("C", "T")


def test_wordmark_i_stem_is_two_pixels():
    rows = _GLYPHS["I"]
    assert len(rows) == 13
    assert all(len(row) == 4 for row in rows)
    assert rows[0] == rows[1] == "####"
    assert rows[-1] == rows[-2] == "####"
    stem = rows[2:-2]
    assert stem == (".##.",) * 9
    for row in stem:
        assert row.count("#") == 2
        assert "###" not in row


def test_wordmark_g_and_c_are_related_rounded_and_distinct():
    g, c = _GLYPHS["G"], _GLYPHS["C"]
    assert len(g) == len(c) == 13
    assert all(len(row) == 12 for row in g)
    assert all(len(row) == 12 for row in c)
    assert g != c
    # Shared stepped outer silhouette at the cap.
    assert g[0] == c[0] == "...######..."
    assert g[1] == c[1] == "..########.."
    assert g[2] == c[2] == ".##......##."
    assert g[-1] == c[-1] == "...######..."
    assert g[-2] == c[-2] == "..########.."
    assert g[-3] == c[-3] == ".##......##."
    # Left edge steps in instead of a square corner.
    assert g[0][0] == c[0][0] == "."
    assert g[3][0] == c[3][0] == "#"
    # ~2px left stroke on the flats.
    assert g[5][:2] == c[5][:2] == "##"
    assert g[5][2] == c[5][2] == "."
    # G keeps an inner bar and a more closed lower right; C stays open.
    assert "##....######" in g
    assert "##....######" not in c
    assert g[6] != c[6]
    assert c[6] == "##.........."
    assert g[8][-2:] == "##"
    assert c[6][-2:] == ".."


def test_wordmark_source_has_no_runtime_io_or_fonts():
    src = WORDMARK_SRC.read_text(encoding="utf-8")
    forbidden = (
        "subprocess",
        "nmcli",
        "systemctl",
        "socket",
        "urllib",
        "http",
        "Path(",
        "open(",
        "PIL",
        "TrueType",
        "ImageFont",
        "qlc",
        "WebSocket",
    )
    for token in forbidden:
        assert token not in src


def test_output_system_universe_headers_unchanged():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    sys_fb = Renderer().render(c.state)
    sys_ref = Framebuffer()
    draw_system(sys_ref, c.state)
    assert sys_fb.digest() == sys_ref.digest()
    assert _heading_present(sys_fb, "SYSTEM")

    out_fb = Framebuffer()
    draw_output(out_fb, c.state)
    assert not _has_text(out_fb, origin()[0], origin()[1], "LIGHT")
    sep = sum(out_fb.get(x, ROW - 1) for x in range(CONTENT_RIGHT))
    assert sep >= CONTENT_RIGHT - 4

    uni = Framebuffer()
    draw_page_header(uni, "UNIVERSE")
    draw_universe_overview(uni, universes=(1, 2, 3), fixtures=(), dmx={}, start_universe=1)
    assert _heading_present(uni, "UNIVERSE")
    play = Renderer().render(make_controller().state)
    assert not _heading_present(play, "UNIVERSE")
    assert not _heading_present(play, "SYSTEM")


def test_lifecycle_screens_unchanged():
    from light_console.state import AppState

    start = AppState(screen=ScreenId.STARTING_UP)
    fb = Renderer().render(start)
    assert fb.digest() == render_lifecycle(STARTING_UP_TEXT).digest()
    sx, sy = lifecycle_origin(STARTING_UP_TEXT)
    assert _has_text(fb, sx, sy, STARTING_UP_TEXT)
    stop = AppState(screen=ScreenId.SHUTTING_DOWN)
    fb2 = Renderer().render(stop)
    assert fb2.digest() == render_lifecycle(SHUTTING_DOWN_TEXT).digest()
    dx, dy = lifecycle_origin(SHUTTING_DOWN_TEXT)
    assert _has_text(fb2, dx, dy, SHUTTING_DOWN_TEXT)
    play = Renderer().render(make_controller().state)
    assert play.digest() != fb.digest()
    assert play.digest() != fb2.digest()


def test_status_render_cost_is_cheap():
    c = make_controller()
    fb = Framebuffer()
    t0 = time.perf_counter()
    for _ in range(400):
        fb.clear()
        draw_play(fb, c.state)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 800.0
