"""512-channel DMX universe raster. One cell per channel; no aggregation."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from light_console.output.dmx import UNIVERSE_SIZE
from light_console.output.fixtures import PatchedFixture
from light_console.qxw import QxwError, _DOCTYPE

MAP_COLS = 32
MAP_ROWS = 16
CHANNELS = UNIVERSE_SIZE
BLINK_HALF_S = 0.25
BLINK_PERIOD_S = BLINK_HALF_S * 2  # 2 Hz

DARK = "dark"
STEADY = "steady"
BLINK = "blink"


def channel_rc(channel: int) -> tuple[int, int]:
    """Operator channel 1..512 -> (row, col) on the 16×32 raster."""
    index = channel - 1
    return index // MAP_COLS, index % MAP_COLS


def rc_channel(row: int, col: int) -> int:
    return row * MAP_COLS + col + 1


def blink_lit(now: float) -> bool:
    t = now if now >= 0 else 0.0
    return (t % BLINK_PERIOD_S) < BLINK_HALF_S


def parse_qlc_universes(text: str) -> tuple[int, ...]:
    """1-based QLC UI universe numbers from workspace InputOutputMap."""
    stripped = _DOCTYPE.sub("", text, count=1)
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError as exc:
        raise QxwError(f"invalid XML: {exc}") from exc
    found: list[int] = []
    seen: set[int] = set()
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "Universe":
            continue
        raw = node.attrib.get("ID")
        if raw in (None, ""):
            continue
        try:
            uni_id = int(raw)
        except ValueError:
            continue
        qlc = uni_id + 1
        if qlc in seen:
            continue
        seen.add(qlc)
        found.append(qlc)
    return tuple(found)


def parse_qlc_universes_file(path: Path) -> tuple[int, ...]:
    try:
        return parse_qlc_universes(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise QxwError(f"cannot read {path}: {exc}") from exc


def configured_universes(
    *,
    parsed: tuple[int, ...] = (),
    routes_unis: tuple[int, ...] = (),
    fixtures: tuple[PatchedFixture, ...] = (),
) -> tuple[int, ...]:
    if parsed:
        return parsed
    order: list[int] = []
    for uni in routes_unis:
        if uni not in order:
            order.append(uni)
    for fixture in fixtures:
        uni = fixture.qlc_universe
        if uni not in order:
            order.append(uni)
    return tuple(order) or (1,)


def patched_indexes(
    fixtures: tuple[PatchedFixture, ...],
    universe_id: int,
) -> frozenset[int]:
    """Zero-based channel indexes occupied by fixtures on this XML universe."""
    occupied: set[int] = set()
    for fixture in fixtures:
        if fixture.universe_id != universe_id:
            continue
        for offset in range(fixture.channels):
            idx = fixture.address + offset
            if 0 <= idx < CHANNELS:
                occupied.add(idx)
    return frozenset(occupied)


def cell_state(
    index: int,
    patched: frozenset[int],
    buf: tuple[int, ...] | list[int] = (),
) -> str:
    if index not in patched:
        return DARK
    value = 0
    if 0 <= index < len(buf):
        value = buf[index]
    return BLINK if value else STEADY


def cell_lit(state: str, now: float) -> bool:
    if state == DARK:
        return False
    if state == STEADY:
        return True
    return blink_lit(now)
