"""5×7 bitmap font: digit 3 letterform and metrics."""

from __future__ import annotations

from light_console.display.font import CELL_W, GLYPH_H, GLYPH_W, glyph
from light_console.display.framebuffer import Framebuffer
from light_console.display.widgets import text, text_right
from light_console.live_color import format_hue, format_percent


def _ascii(ch: str) -> tuple[str, ...]:
    rows = glyph(ch)
    assert len(rows) == GLYPH_H
    lines = []
    for bits in rows:
        assert 0 <= bits < (1 << GLYPH_W)
        lines.append("".join("#" if bits & (0x10 >> col) else "." for col in range(GLYPH_W)))
    return tuple(lines)


def _hamming(a: str, b: str) -> int:
    ga, gb = glyph(a), glyph(b)
    return sum(bin(x ^ y).count("1") for x, y in zip(ga, gb, strict=True))


def test_digit_3_is_5x7_open_left_bowls():
    assert GLYPH_W == 5
    assert GLYPH_H == 7
    three = _ascii("3")
    assert three == (
        ".###.",
        "#...#",
        "....#",
        "..##.",
        "#...#",
        ".###.",
        ".....",
    )
    assert three[1] == three[4] == "#...#"
    assert three[2] == "....#"
    assert three[3] == "..##."
    assert three[0] == three[5] == ".###."
    assert three[6] == "....."
    assert three[2][0] == "."


def test_digit_3_differs_from_8_9_5_and_b():
    assert _ascii("3") != _ascii("8")
    assert _ascii("3") != _ascii("9")
    assert _ascii("3") != _ascii("5")
    assert _ascii("3") != _ascii("B")
    assert _hamming("3", "8") >= 4
    assert _hamming("3", "9") >= 3
    assert _hamming("3", "5") >= 6
    assert _hamming("3", "B") >= 6
    # 8 closes the waist; 3 keeps a short middle and an open waist.
    assert _ascii("8")[2] == ".###."
    assert _ascii("3")[2] == "....#"
    assert _ascii("3")[3] == "..##."
    # 9 keeps a closed upper bowl; 3 opens the waist.
    assert _ascii("9")[2][0] == "#"
    assert _ascii("3")[2][0] == "."
    # 3 has no solid left stem like B; bowls only.
    left = [row[0] for row in _ascii("3")]
    assert left != ["#"] * 6 + ["."]
    assert left == [".", "#", ".", ".", "#", ".", "."]
    assert _ascii("B")[0][0] == "#"
    assert _ascii("3")[0][0] == "."


def test_numeric_text_width_metrics_unchanged():
    samples = (
        "3",
        "30%",
        "33%",
        "103",
        "130%",
        "-135°",
        "+135°",
        "192.168.88.3",
        format_percent(30),
        format_percent(130),
        format_hue(-135),
        format_hue(135),
    )
    for sample in samples:
        assert len(sample) * CELL_W == len(sample) * 6
        fb = Framebuffer()
        text(fb, 0, 0, sample)
        # Glyph cell is 5 wide with 1px padding; next character starts on the cell.
        if sample[0] == "3":
            assert fb.get(0, 0) == 0
            assert fb.get(1, 0) == 1


def test_percent_and_hue_alignment_does_not_shift():
    def right_edge(s: str) -> int:
        fb = Framebuffer()
        text_right(fb, 80, 0, s)
        xs = [x for x in range(80) if any(fb.get(x, y) for y in range(GLYPH_H))]
        return xs[-1]

    assert right_edge("30%") == right_edge("80%")
    assert right_edge("33%") == right_edge("88%")
    assert right_edge("103") == right_edge("108")
    assert right_edge(format_percent(130)) == right_edge(format_percent(180))
    assert right_edge(format_hue(-135)) == right_edge(format_hue(-180))
    assert right_edge(format_hue(135)) == right_edge(format_hue(180))
    three = Framebuffer()
    eight = Framebuffer()
    text(three, 10, 8, "3")
    text(eight, 10, 8, "8")
    # Same origin and cell; only interior pixels differ.
    assert three.get(10, 8) == eight.get(10, 8) == 0
    assert three.get(11, 8) == eight.get(11, 8) == 1
