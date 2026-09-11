"""Draw the 32×16 DMX universe raster. Native pixels, not glyphs."""

from __future__ import annotations

from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import CONTENT_Y, WIDTH
from light_console.display.widgets import text, text_right
from light_console.output.universe_map import (
    CELL,
    CHANNELS,
    MAP_COLS,
    MAP_ROWS,
    cell_lit,
    cell_state,
    channel_rc,
    patched_indexes,
)

MATRIX_W = MAP_COLS * CELL
MATRIX_H = MAP_ROWS * CELL
MAP_X0 = (WIDTH - MATRIX_W) // 2
MAP_Y0 = CONTENT_Y + 4
LABEL_Y = MAP_Y0 + MATRIX_H + 4


def cell_origin(channel: int) -> tuple[int, int]:
    row, col = channel_rc(channel)
    return MAP_X0 + col * CELL, MAP_Y0 + row * CELL


def draw_universe_raster(
    fb: Framebuffer,
    *,
    universe_id: int,
    fixtures: tuple,
    buf: tuple[int, ...] | list[int] = (),
    now: float = 0.0,
) -> None:
    patched = patched_indexes(fixtures, universe_id)
    for index in range(CHANNELS):
        state = cell_state(index, patched, buf)
        if not cell_lit(state, now):
            continue
        x, y = cell_origin(index + 1)
        fb.fill_rect(x, y, CELL, CELL, True)
    text(fb, MAP_X0, LABEL_Y, "1")
    text_right(fb, MAP_X0 + MATRIX_W, LABEL_Y, "512")
