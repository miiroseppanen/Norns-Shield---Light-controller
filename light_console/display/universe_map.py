"""Draw a scrollable multi-universe DMX overview. Native pixels, not glyphs."""

from __future__ import annotations

from light_console.display.components import draw_scrollbar
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import CONTENT_Y
from light_console.display.widgets import CELL_W as FONT_W, GLYPH_H, text
from light_console.output.universe_map import (
    CHANNELS,
    MAP_COLS,
    MAP_ROWS,
    cell_lit,
    cell_state,
    channel_rc,
    patched_indexes,
)

CELL_W = 2
CELL_H = 1
MATRIX_W = MAP_COLS * CELL_W
MATRIX_H = MAP_ROWS * CELL_H
VISIBLE_UNIVERSES = 3
LABEL_PAD = 1
LABEL_GAP = 2
MAP_X0 = LABEL_PAD + 2 * FONT_W + LABEL_GAP
MAP_Y0 = CONTENT_Y


def universe_label(qlc_universe: int) -> str:
    return f"U{int(qlc_universe)}"


def label_col_w(universes: tuple[int, ...]) -> int:
    if not universes:
        return 2 * FONT_W
    return max(len(universe_label(uni)) for uni in universes) * FONT_W


def raster_x0(universes: tuple[int, ...] = ()) -> int:
    return LABEL_PAD + label_col_w(universes) + LABEL_GAP


def raster_y0(row: int) -> int:
    return CONTENT_Y + int(row) * MATRIX_H


def label_origin(qlc_universe: int, universes: tuple[int, ...], row: int) -> tuple[int, int]:
    label = universe_label(qlc_universe)
    col_w = label_col_w(universes)
    lx = LABEL_PAD + col_w - len(label) * FONT_W
    ly = raster_y0(row) + (MATRIX_H - GLYPH_H) // 2
    return lx, ly


def viewport_offset(universes: tuple[int, ...], start_universe: int) -> int:
    if not universes:
        return 0
    if start_universe in universes:
        idx = universes.index(start_universe)
    else:
        idx = 0
    max_off = max(0, len(universes) - VISIBLE_UNIVERSES)
    return max(0, min(idx, max_off))


def visible_universes(universes: tuple[int, ...], start_universe: int) -> tuple[int, ...]:
    if not universes:
        return ()
    off = viewport_offset(universes, start_universe)
    return universes[off : off + VISIBLE_UNIVERSES]


def cell_origin(channel: int, *, x0: int | None = None, y0: int | None = None) -> tuple[int, int]:
    row, col = channel_rc(channel)
    ox = MAP_X0 if x0 is None else x0
    oy = MAP_Y0 if y0 is None else y0
    return ox + col * CELL_W, oy + row * CELL_H


def draw_universe_raster(
    fb: Framebuffer,
    *,
    universe_id: int,
    fixtures: tuple,
    buf: tuple[int, ...] | list[int] = (),
    now: float = 0.0,
    x0: int | None = None,
    y0: int | None = None,
) -> None:
    ox = MAP_X0 if x0 is None else x0
    oy = MAP_Y0 if y0 is None else y0
    patched = patched_indexes(fixtures, universe_id)
    for index in range(CHANNELS):
        state = cell_state(index, patched, buf)
        if not cell_lit(state, now):
            continue
        x, y = cell_origin(index + 1, x0=ox, y0=oy)
        fb.fill_rect(x, y, CELL_W, CELL_H, True)


def draw_universe_overview(
    fb: Framebuffer,
    *,
    universes: tuple[int, ...],
    fixtures: tuple,
    dmx: dict[int, tuple[int, ...]] | None = None,
    start_universe: int = 1,
    now: float = 0.0,
) -> None:
    unis = tuple(universes) or (1,)
    off = viewport_offset(unis, start_universe)
    window = unis[off : off + VISIBLE_UNIVERSES]
    x0 = raster_x0(unis)
    store = dmx or {}
    for row, qlc_uni in enumerate(window):
        y0 = raster_y0(row)
        buf = store.get(qlc_uni - 1, ())
        draw_universe_raster(
            fb,
            universe_id=qlc_uni - 1,
            fixtures=fixtures,
            buf=buf,
            now=now,
            x0=x0,
            y0=y0,
        )
        label = universe_label(qlc_uni)
        lx, ly = label_origin(qlc_uni, unis, row)
        text(fb, lx, ly, label)
    draw_scrollbar(fb, len(unis), VISIBLE_UNIVERSES, off)
