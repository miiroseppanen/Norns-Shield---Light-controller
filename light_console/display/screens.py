from __future__ import annotations

from light_console.display.framebuffer import Framebuffer
from light_console.display.widgets import ROW, invert_bar, status_pair, text, text_right
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
    scene = state.current_scene or "--"
    if state.blackout:
        text(fb, 0, ROW * 2, "BLACKOUT")
    else:
        status_pair(fb, ROW * 2, "SCENE", scene)
    status_pair(fb, ROW * 3, "MASTER", f"{state.master}%")
    status_pair(fb, ROW * 4, "SPEED", str(state.speed))


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


def draw_output(fb: Framebuffer, state: AppState) -> None:
    _header(fb, "OUTPUT", state)
    status_pair(fb, ROW * 2, "QLC", qlc_output_label(state))
    status_pair(fb, ROW * 3, "ENGINE", (state.qlc_engine or "--")[:9])
    status_pair(fb, ROW * 4, "HOST", (state.qlc_host or "--")[:9])


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


def draw_shutdown(fb: Framebuffer, state: AppState) -> None:
    _header(fb, "SHUTDOWN?", state)
    if state.shutdown_requested:
        text(fb, 0, ROW * 3, "SHUTDOWN REQUESTED"[:21])
        return
    text(fb, 0, ROW * 3, "K2  CANCEL")
    text(fb, 0, ROW * 4, "K3  CONFIRM")


DRAWERS = {
    ScreenId.PLAY: draw_play,
    ScreenId.MENU: draw_menu,
    ScreenId.PARAMS: draw_params,
    ScreenId.SCENES: draw_scenes,
    ScreenId.OUTPUT: draw_output,
    ScreenId.SYSTEM: draw_system,
    ScreenId.SHUTDOWN: draw_shutdown,
}


def draw_screen(fb: Framebuffer, state: AppState) -> None:
    fb.clear()
    drawer = DRAWERS.get(state.screen, draw_play)
    drawer(fb, state)
