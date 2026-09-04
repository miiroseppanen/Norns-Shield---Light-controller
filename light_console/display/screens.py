from __future__ import annotations

from light_console.display.framebuffer import Framebuffer
from light_console.display.widgets import ROW, invert_bar, status_pair, text, text_right
from light_console.output.dmx import DMX_ROWS, dmx_windows, nonzero_channels
from light_console.output.pages import IFACES_PER_PAGE, ROUTES_PER_PAGE, build_output_pages
from light_console.state import AppState, ScreenId
from light_console.ui.menu import MENU_ITEMS, MenuItem


def _qlc_word(state: AppState) -> str:
    return "ON" if state.qlc_connected else "OFF"


def qlc_output_label(state: AppState) -> str:
    """OLED word. Engine down or socket error is OFFLINE, not a distinct ERROR glyph."""
    if state.qlc_connected:
        return "CONNECTED"
    return "OFFLINE"


def _fmt_uptime(seconds: int) -> str:
    mins, sec = divmod(max(0, seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours:d}:{mins:02d}:{sec:02d}"
    return f"{mins:02d}:{sec:02d}"


def _header(fb: Framebuffer, title: str, state: AppState) -> None:
    text(fb, 0, 0, title[:16])
    text_right(fb, fb.width, 0, state.qlc_status_glyph)


def draw_list(fb: Framebuffer, labels: list[str], selected: int, y0: int = ROW * 2, rows: int = 6) -> None:
    if not labels:
        return
    start = 0
    if selected >= start + rows:
        start = selected - rows + 1
    window = labels[start : start + rows]
    for i, label in enumerate(window):
        idx = start + i
        y = y0 + i * ROW
        prefix = ">" if idx == selected else " "
        text(fb, 0, y, f"{prefix} {label}"[:21])
        if idx == selected:
            invert_bar(fb, y)


def draw_play(fb: Framebuffer, state: AppState) -> None:
    _header(fb, "LIGHT CONSOLE", state)
    qlc = "OK" if state.qlc_connected else "OFF"
    startup = (state.startup_status or ("WAIT" if state.qlc_connected else "--"))[:9]
    midi = "OK" if state.launchpad_connected else "--"
    output = (state.output_mode or "SAFE")[:9]
    status_pair(fb, ROW * 1, "QLC", qlc)
    status_pair(fb, ROW * 2, "SHOW", "MASTER")
    status_pair(fb, ROW * 3, "STARTUP", startup)
    status_pair(fb, ROW * 4, "MIDI", midi)
    status_pair(fb, ROW * 5, "OUTPUT", output)
    status_pair(fb, ROW * 6, "MASTER", f"{state.master}%")


def draw_menu(fb: Framebuffer, state: AppState, items: tuple[MenuItem, ...] | None = None) -> None:
    _header(fb, "MENU", state)
    rows = items if items is not None else MENU_ITEMS
    labels = [item.label for item in rows]
    draw_list(fb, labels, state.menu_index)


def draw_params(fb: Framebuffer, state: AppState, params=None) -> None:
    _header(fb, "PARAMS", state)
    if params is None:
        labels = [
            f"Master       {state.master}%",
            f"Speed        {state.speed}",
            f"Blackout     {'On' if state.blackout else 'Off'}",
            f"Scene        {state.current_scene}",
        ]
    else:
        labels = []
        for p in params:
            val = p.formatted()
            pad = max(1, 14 - len(p.name))
            labels.append(f"{p.name}{' ' * pad}{val}"[:21])
    draw_list(fb, labels, state.param_index)


def draw_scenes(fb: Framebuffer, state: AppState) -> None:
    _header(fb, "SCENES", state)
    if not state.scenes:
        text(fb, 0, ROW * 2, "NO SCENES")
        return
    labels = list(state.scenes)
    draw_list(fb, labels, state.scene_index)


def draw_chasers(fb: Framebuffer, state: AppState) -> None:
    _header(fb, "CHASERS", state)
    if not state.chasers:
        text(fb, 0, ROW * 2, "NO CHASERS")
        return
    draw_list(fb, list(state.chasers), state.chaser_index)


def draw_shows(fb: Framebuffer, state: AppState) -> None:
    _header(fb, "SHOWS", state)
    labels_src = state.show_files
    if not labels_src:
        text(fb, 0, ROW * 2, "NO SHOWS")
        return
    labels = []
    current = state.show_name
    for name in labels_src:
        mark = "*" if name == current else " "
        labels.append(f"{mark}{name}"[:21])
    draw_list(fb, labels, state.show_index)
    if state.show_status == "ACTIVE" and current:
        text(fb, 0, ROW * 6, "ACTIVE"[:21])


def draw_load_show(fb: Framebuffer, state: AppState) -> None:
    _header(fb, "SHOW", state)
    name = (state.show_name or "--")[:21]
    text(fb, 0, ROW * 2, name)
    text(fb, 0, ROW * 3, (state.show_status or "ACTIVE")[:21])


def draw_output(fb: Framebuffer, state: AppState) -> None:
    pages = build_output_pages(state.network_ifaces, state.output_routes, state.dmx_by_universe)

    pages = build_output_pages(state.network_ifaces, state.output_routes, state.dmx_by_universe)
    if not pages:
        _header(fb, "OUTPUT", state)
        text(fb, 0, ROW * 2, "NO DATA")
        return
    index = state.output_page % len(pages)
    page = pages[index]
    _header(fb, page.title[:16], state)
    if page.kind == "network":
        _draw_network(fb, state, page.offset)
    elif page.kind == "routing":
        _draw_routing(fb, state, page.offset)
    else:
        _draw_dmx(fb, state, page.universe or 1, page.window)


def _draw_network(fb: Framebuffer, state: AppState, offset: int) -> None:

    ifaces = state.network_ifaces
    if not ifaces:
        text(fb, 0, ROW * 2, "NO DATA")
        return
    slice_ = ifaces[offset : offset + IFACES_PER_PAGE]
    y = ROW
    for iface in slice_:
        flag = "UP" if iface.up else "DOWN"
        text(fb, 0, y, f"{iface.name} {flag}"[:21])
        y += ROW
        if iface.ssid:
            text(fb, 0, y, iface.ssid[:21])
            y += ROW
        addr = iface.ipv4 or "--"
        text(fb, 0, y, addr[:21])
        y += ROW


def _draw_routing(fb: Framebuffer, state: AppState, offset: int) -> None:

    if not state.qlc_connected and not state.output_routes:
        text(fb, 0, ROW * 2, "QLC OFFLINE")
        return
    routes = state.output_routes
    if not routes:
        text(fb, 0, ROW * 2, "NO DATA")
        return
    y = ROW
    for route in routes[offset : offset + ROUTES_PER_PAGE]:
        text(fb, 0, y, f"U{route.qlc_universe} {route.plugin}"[:21])
        y += ROW
        text(fb, 0, y, route.destination[:21])
        y += ROW
        wire = f"U{route.wire_universe}" if route.wire_universe is not None else "--"
        text(fb, 0, y, f"WIRE {wire} {route.mode}"[:21])
        y += ROW


def _draw_dmx(fb: Framebuffer, state: AppState, universe: int, window: int) -> None:

    if not state.qlc_connected:
        text(fb, 0, ROW * 2, "NO DATA")
        return
    buf = state.dmx_by_universe.get(universe - 1)
    if buf is None or not state.dmx_ready:
        text(fb, 0, ROW * 2, "NO DATA")
        return
    active = nonzero_channels(buf)
    windows = dmx_windows(active, DMX_ROWS)
    chunk = windows[window % len(windows)] if windows else []
    total = len(active)
    status_pair(fb, ROW, "ACTIVE", str(total)[:9])
    if not chunk:
        text(fb, 0, ROW * 2, "NO DATA" if total == 0 else "--")
        return
    start = window * DMX_ROWS + 1
    end = start + len(chunk) - 1
    if total > DMX_ROWS:
        text(fb, 0, ROW * 2, f"{start}-{end}/{total}"[:21])
        y = ROW * 3
    else:
        y = ROW * 2
    for channel, value in chunk:
        text(fb, 0, y, f"{channel:02d} {value:03d}"[:21])
        y += ROW
        if y >= ROW * 8:
            break


def draw_system(fb: Framebuffer, state: AppState) -> None:
    _header(fb, "SYSTEM", state)
    host = (state.hostname or "--")[:9]
    labels = [
        f"QLC STATUS  {_qlc_word(state)}",
        f"HOSTNAME    {host}"[:21],
        f"VERSION     {state.version[:9]}",
        f"UPTIME      {_fmt_uptime(state.uptime_s)}",
        "SHUTDOWN",
    ]
    draw_list(fb, labels, state.system_index, y0=ROW)


SHUTTING_DOWN_LINES = (
    "SHUTTING DOWN",
    "WAIT",
    "GREEN LED STOPS",
    "SAFE TO UNPLUG",
)


def draw_shutting_down(fb: Framebuffer, state: AppState) -> None:
    del state
    text(fb, 0, 0, SHUTTING_DOWN_LINES[0])
    text(fb, 0, ROW * 2, SHUTTING_DOWN_LINES[1])
    text(fb, 0, ROW * 3, SHUTTING_DOWN_LINES[2])
    text(fb, 0, ROW * 4, SHUTTING_DOWN_LINES[3])


DRAWERS = {
    ScreenId.PLAY: draw_play,
    ScreenId.MENU: draw_menu,
    ScreenId.PARAMS: draw_params,
    ScreenId.SHOWS: draw_shows,
    ScreenId.SCENES: draw_scenes,
    ScreenId.CHASERS: draw_chasers,
    ScreenId.LOAD_SHOW: draw_load_show,
    ScreenId.OUTPUT: draw_output,
    ScreenId.SYSTEM: draw_system,
    ScreenId.SHUTTING_DOWN: draw_shutting_down,
}


def draw_screen(fb: Framebuffer, state: AppState) -> None:
    fb.clear()
    drawer = DRAWERS.get(state.screen, draw_play)
    drawer(fb, state)
