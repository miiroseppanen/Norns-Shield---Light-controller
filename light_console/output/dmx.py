"""Live DMX cache from QLC+API|getChannelsValues. Observe only; never write Simple Desk."""

from __future__ import annotations

from dataclasses import dataclass, field

UNIVERSE_SIZE = 512
DMX_ROWS = 6


def parse_get_channels_values(msg: str) -> list[tuple[int, int]]:
    parts = msg.split("|")
    if len(parts) < 4 or parts[0] != "QLC+API" or parts[1] != "getChannelsValues":
        return []
    rest = parts[2:]
    if not rest:
        return []
    stride = 4 if len(rest) % 4 == 0 else 3
    out: list[tuple[int, int]] = []
    for i in range(0, len(rest) - stride + 1, stride):
        try:
            channel = int(rest[i])
            value = int(rest[i + 1])
        except ValueError:
            continue
        if 1 <= channel <= UNIVERSE_SIZE:
            out.append((channel, max(0, min(255, value))))
    return out


def empty_universe() -> list[int]:
    return [0] * UNIVERSE_SIZE


def apply_channel_pairs(buf: list[int], pairs: list[tuple[int, int]]) -> None:
    for channel, value in pairs:
        if 1 <= channel <= len(buf):
            buf[channel - 1] = value


def nonzero_channels(buf: list[int] | tuple[int, ...]) -> list[tuple[int, int]]:
    return [(i + 1, value) for i, value in enumerate(buf) if value]


def dmx_windows(active: list[tuple[int, int]], rows: int = DMX_ROWS) -> list[list[tuple[int, int]]]:
    if rows < 1:
        rows = DMX_ROWS
    if not active:
        return [[]]
    return [active[i : i + rows] for i in range(0, len(active), rows)]


@dataclass
class DmxCache:
    """512 slots per QLC universe (0-based). Cleared on disconnect."""

    values: dict[int, list[int]] = field(default_factory=dict)
    pending_universe: int | None = None
    ready: bool = False

    def clear(self) -> None:
        self.values.clear()
        self.pending_universe = None
        self.ready = False

    def begin_request(self, universe_0: int) -> None:
        self.pending_universe = universe_0

    def ingest(self, msg: str) -> None:
        pairs = parse_get_channels_values(msg)
        if not pairs:
            return
        uni = self.pending_universe if self.pending_universe is not None else 0
        buf = self.values.setdefault(uni, empty_universe())
        if pairs[0][0] == 1 and len(pairs) >= UNIVERSE_SIZE:
            buf[:] = empty_universe()
        apply_channel_pairs(buf, pairs)
        self.ready = True
        self.pending_universe = None

    def snapshot(self, universe_0: int) -> tuple[int, ...] | None:
        buf = self.values.get(universe_0)
        if buf is None:
            return None
        return tuple(buf)
