from __future__ import annotations

from light_console.display.framebuffer import Framebuffer
from light_console.display.widgets import ROW, invert_bar, status_pair, text, text_center, text_right
from light_console.state import MENU_ITEMS, AppState, ScreenId


def _ok(flag: bool) -> str:
    return "OK" if flag else "--"


def _qlc_label(state: AppState) -> str:
    if state.qlc_connected:
        return "OK"
    return "LOST" if not state.startup_running else "WAIT"


def _wiz_label(state: AppState) -> str:
    base = f"{state.wiz_online}/{state.wiz_expected}"
    if state.wiz_waiting:
        return f"{base} WAIT"
    if state.wiz_online >= state.wiz_expected and state.wiz_ap_up:
        return f"{base} OK"
    return base


def _dmx_home(state: AppState) -> str:
    if state.dmx_node_reachable:
        return "DMX OK"
    if state.dmx_net_ok:
        return "DMX NET"
    return "DMX --"


def _midi_label(state: AppState) -> str:
    return "MIDI LP OK" if state.launchpad_connected else "MIDI LP --"


def draw_boot(fb: Framebuffer, state: AppState) -> None:
    text(fb, 0, 0, "LIGHT CONSOLE")
    status_pair(fb, ROW, "QLC", _qlc_label(state))
    status_pair(fb, ROW * 2, "WIZ AP", _ok(state.wiz_ap_up))
    status_pair(fb, ROW * 3, "WiZ", _wiz_label(state))
    status_pair(fb, ROW * 4, "MIDI", "OK" if state.launchpad_connected else "--")
    status_pair(fb, ROW * 5, "DMX", "OK" if state.dmx_node_reachable else "--")
    if state.warnings:
        text(fb, 0, ROW * 7, state.warnings[0][:21])


def draw_home(fb: Framebuffer, state: AppState) -> None:
    title = state.active_function or state.selected_function
    if state.blackout:
        text(fb, 0, 0, "BLACKOUT")
        invert_bar(fb, 0)
    else:
        text(fb, 0, 0, title[:21])
        if state.active_function and state.selected_function != state.active_function:
            text_right(fb, fb.width, 0, "*")

    status_pair(fb, ROW, f"WiZ {_wiz_label(state)}", _dmx_home(state))
    status_pair(fb, ROW * 2, f"DIM {state.master_dimmer}%", f"BPM {state.bpm}")
    text(fb, 0, ROW * 3, "E1 DIM E2 FX E3 SPD")

    warn_y = ROW * 5
    for i, w in enumerate(state.warnings[:2]):
        if w == "BLACKOUT":
            continue
        text(fb, 0, warn_y + i * ROW, w[:21])

    if not state.qlc_connected:
        text(fb, 0, ROW * 7, "QLC LOST")


def draw_menu(fb: Framebuffer, state: AppState) -> None:
    text(fb, 0, 0, "MENU")
    for i, item in enumerate(MENU_ITEMS):
        prefix = ">" if i == state.menu_index else " "
        text(fb, 0, ROW + i * ROW, f"{prefix}{item.value.upper()}")


def draw_show(fb: Framebuffer, state: AppState) -> None:
    text(fb, 0, 0, "SHOW")
    text(fb, 0, ROW, f"SEL {state.selected_function[:16]}")
    text(fb, 0, ROW * 2, f"ACT {state.active_function or '--'}")
    text(fb, 0, ROW * 3, f"QLC {_qlc_label(state)}")
    text(fb, 0, ROW * 4, f"DIM {state.master_dimmer}%")
    text(fb, 0, ROW * 5, f"K2 GO  K1 BLK")


def draw_wiz(fb: Framebuffer, state: AppState) -> None:
    text(fb, 0, 0, "WIZ")
    status_pair(fb, ROW, "AP", _ok(state.wiz_ap_up))
    status_pair(fb, ROW * 2, "ONLINE", f"{state.wiz_online}/{state.wiz_expected}")
    if state.wiz_waiting:
        text(fb, 0, ROW * 3, "WAIT COLDBOOT")
    # Per-fixture mock: first N expected, online prefix OK
    for i in range(min(4, state.wiz_expected)):
        mark = "OK" if i < state.wiz_online else "--"
        rssi = f"-{60 + i * 4}" if i < state.wiz_online else ""
        text(fb, 0, ROW * (4 + i), f"W{i + 1} {mark} {rssi}".strip())


def draw_network(fb: Framebuffer, state: AppState) -> None:
    text(fb, 0, 0, "NETWORK")
    status_pair(fb, ROW, "WIZ-LTS", _ok(state.wiz_ap_up))
    up = state.upstream_ssid[:9] if state.upstream_connected else "--"
    status_pair(fb, ROW * 2, "WLAN0", up if state.upstream_connected else "--")
    text(fb, 0, ROW * 3, "10.42.0.1" if state.wiz_ap_up else "AP DOWN")
    if not state.upstream_connected:
        text(fb, 0, ROW * 5, "NO UPSTREAM OK")
    text(fb, 0, ROW * 7, "WiZ INDEP OF U0")


def draw_system(fb: Framebuffer, state: AppState) -> None:
    text(fb, 0, 0, "SYSTEM")
    mins, sec = divmod(state.uptime_s, 60)
    hours, mins = divmod(mins, 60)
    text(fb, 0, ROW, f"UP {hours:02d}:{mins:02d}:{sec:02d}")
    temp = f"{state.cpu_temp_c:.0f}C" if state.cpu_temp_c is not None else "--"
    status_pair(fb, ROW * 2, "CPU", temp)
    status_pair(fb, ROW * 3, "QLC", _qlc_label(state))
    text(fb, 0, ROW * 4, f"LC {state.version}")
    text(fb, 0, ROW * 6, "UI CRASH != SHOW")


def draw_about(fb: Framebuffer, state: AppState) -> None:
    text_center(fb, ROW, "SHIELD XL")
    text_center(fb, ROW * 2, "LIGHT CONSOLE")
    text_center(fb, ROW * 4, f"v{state.version}")
    text_center(fb, ROW * 6, "QLC+ ENGINE")


DRAWERS = {
    ScreenId.BOOT: draw_boot,
    ScreenId.HOME: draw_home,
    ScreenId.MENU: draw_menu,
    ScreenId.SHOW: draw_show,
    ScreenId.WIZ: draw_wiz,
    ScreenId.NETWORK: draw_network,
    ScreenId.SYSTEM: draw_system,
    ScreenId.ABOUT: draw_about,
}


def draw_screen(fb: Framebuffer, state: AppState) -> None:
    fb.clear()
    DRAWERS[state.screen](fb, state)
