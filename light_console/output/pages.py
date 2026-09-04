"""OUTPUT diagnostic page list. Read-only; no IO or QLC mutation."""

from __future__ import annotations

from dataclasses import dataclass

from light_console.output.dmx import DMX_ROWS, dmx_windows, nonzero_channels
from light_console.output.network import NetIface
from light_console.output.routing import OutputRoute

IFACES_PER_PAGE = 2
ROUTES_PER_PAGE = 2


@dataclass(frozen=True)
class OutputPage:
    kind: str
    title: str
    offset: int = 0
    universe: int | None = None
    window: int = 0


def build_output_pages(
    ifaces: tuple[NetIface, ...],
    routes: tuple[OutputRoute, ...],
    dmx: dict[int, tuple[int, ...]] | None = None,
) -> list[OutputPage]:
    pages: list[OutputPage] = []
    names = ifaces or ()
    if not names:
        pages.append(OutputPage("network", "NETWORK", 0))
    else:
        for offset in range(0, max(1, len(names)), IFACES_PER_PAGE):
            pages.append(OutputPage("network", "NETWORK", offset))
    route_list = routes or ()
    if not route_list:
        pages.append(OutputPage("routing", "ROUTING", 0))
    else:
        for offset in range(0, max(1, len(route_list)), ROUTES_PER_PAGE):
            pages.append(OutputPage("routing", "ROUTING", offset))
    unis = [route.qlc_universe for route in route_list] or [1]
    store = dmx or {}
    for uni in unis:
        buf = store.get(uni - 1, ())
        active = nonzero_channels(buf)
        windows = dmx_windows(active, DMX_ROWS)
        for window_i, _chunk in enumerate(windows):
            pages.append(
                OutputPage("dmx", f"DMX U{uni}", universe=uni, window=window_i)
            )
    return pages
