"""STATUS-page LIGHT CTRL wordmark. Custom 1-bit glyphs; no fonts or I/O."""

from __future__ import annotations

from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import CONTENT_RIGHT, LABEL_X, WIDTH

# STATUS header band. Live controls start on the next 8px row.
BAND_H = 16
MASTER_Y = 16
SAT_Y = 24
HUE_Y = 32
OUTPUT_Y = 40
QLC_Y = 48
META_Y = 56

LETTER_GAP = 2
WORD_GAP = 8
EDGE = 2
# Pair tracking, added to LETTER_GAP. C's open right side leaves extra air before T.
PAIR_KERN: dict[tuple[str, str], int] = {("C", "T"): -1}

# 13×N geometric caps. '#' = ink. All rows in a glyph share one width.
_GLYPHS: dict[str, tuple[str, ...]] = {
    "L": (
        "##........",
        "##........",
        "##........",
        "##........",
        "##........",
        "##........",
        "##........",
        "##........",
        "##........",
        "##........",
        "##........",
        "##########",
        "##########",
    ),
    "I": (
        "####",
        "####",
        ".##.",
        ".##.",
        ".##.",
        ".##.",
        ".##.",
        ".##.",
        ".##.",
        ".##.",
        ".##.",
        "####",
        "####",
    ),
    "G": (
        "...######...",
        "..########..",
        ".##......##.",
        "##........##",
        "##..........",
        "##..........",
        "##....######",
        "##....######",
        "##........##",
        "##........##",
        ".##......##.",
        "..########..",
        "...######...",
    ),
    "H": (
        "##........##",
        "##........##",
        "##........##",
        "##........##",
        "##........##",
        "############",
        "############",
        "##........##",
        "##........##",
        "##........##",
        "##........##",
        "##........##",
        "##........##",
    ),
    "T": (
        "############",
        "############",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        ".....##.....",
    ),
    "C": (
        "...######...",
        "..########..",
        ".##......##.",
        "##........##",
        "##..........",
        "##..........",
        "##..........",
        "##..........",
        "##..........",
        "##........##",
        ".##......##.",
        "..########..",
        "...######...",
    ),
    "R": (
        "###########.",
        "##........##",
        "##........##",
        "##........##",
        "##........##",
        "###########.",
        "###########.",
        "##..##......",
        "##..##......",
        "##...##.....",
        "##....##....",
        "##.....##...",
        "##......##..",
    ),
}


def _pair_gap(left: str, right: str) -> int:
    return LETTER_GAP + PAIR_KERN.get((left, right), 0)


def _pack(rows: tuple[str, ...]) -> tuple[tuple[int, ...], int, int]:
    height = len(rows)
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("glyph rows must be rectangular")
    packed = []
    for row in rows:
        bits = 0
        for ch in row:
            bits = (bits << 1) | (1 if ch == "#" else 0)
        packed.append(bits)
    return tuple(packed), width, height


def _compose(text: str) -> tuple[tuple[int, ...], int, int, frozenset[tuple[int, int]]]:
    glyphs: list[tuple[tuple[int, ...], int, int]] = []
    for ch in text:
        if ch == " ":
            empty = (0,) * 13
            glyphs.append((empty, WORD_GAP, 13))
            continue
        if ch not in _GLYPHS:
            raise KeyError(f"no wordmark glyph for {ch!r}")
        glyphs.append(_pack(_GLYPHS[ch]))
    height = 13
    width = 0
    parts: list[tuple[tuple[int, ...], int, int]] = []
    for i, glyph in enumerate(glyphs):
        if i and text[i] != " " and text[i - 1] != " ":
            width += _pair_gap(text[i - 1], text[i])
        parts.append(glyph)
        width += glyph[1]
    rows = [0] * height
    on: set[tuple[int, int]] = set()
    x = 0
    for i, (packed, gw, _gh) in enumerate(parts):
        if i and text[i] != " " and text[i - 1] != " ":
            x += _pair_gap(text[i - 1], text[i])
        for y, bits in enumerate(packed):
            rows[y] |= bits << (width - x - gw)
            for col in range(gw):
                if bits & (1 << (gw - 1 - col)):
                    on.add((x + col, y))
        x += gw
    min_x = min(px for px, _py in on)
    max_x = max(px for px, _py in on)
    min_y = min(py for _px, py in on)
    max_y = max(py for _px, py in on)
    trimmed_w = max_x - min_x + 1
    trimmed_h = max_y - min_y + 1
    trimmed_on = frozenset((px - min_x, py - min_y) for px, py in on)
    trimmed_rows = []
    shift = width - 1 - max_x
    for y in range(min_y, max_y + 1):
        trimmed_rows.append((rows[y] >> shift) & ((1 << trimmed_w) - 1))
    return tuple(trimmed_rows), trimmed_w, trimmed_h, trimmed_on


MASK_ROWS, MASK_WIDTH, MASK_HEIGHT, ON_PIXELS = _compose("LIGHT CTRL")


def origin(fb_width: int = WIDTH) -> tuple[int, int]:
    """Top-left of the ink bbox, left-aligned with MASTER/SAT/HUE labels."""
    max_right = min(fb_width - EDGE, CONTENT_RIGHT)
    x = LABEL_X
    if x + MASK_WIDTH > max_right:
        x = max(EDGE, max_right - MASK_WIDTH)
    y = max(0, (BAND_H - MASK_HEIGHT) // 2)
    return x, y


def draw_wordmark(fb: Framebuffer) -> None:
    """Blit the static LIGHT CTRL mark. No scan or invert."""
    x0, y0 = origin(fb.width)
    for lx, ly in ON_PIXELS:
        fb.pixel(x0 + lx, y0 + ly, True)
