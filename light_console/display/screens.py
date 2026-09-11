from __future__ import annotations

from light_console.display.activity import dmx_output_active
from light_console.display.components import (
    draw_action_row,
    draw_empty_state,
    draw_named_status_row,
    draw_page_header,
    draw_prefixed_name,
    draw_scrollbar,
    draw_status_row,
    draw_subordinate_status,
    draw_text_row,
    draw_toggle,
    draw_toggle_row,
    status_label_field_w,
)
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import (
    CONTENT_RIGHT,
    CONTENT_ROWS,
    CONTENT_Y,
    LABEL_X,
    ROW,
    TOGGLE_D,
    TOGGLE_LABEL_X,
    VALUE_RIGHT,
)
from light_console.display.marquee import field_offset
from light_console.display.viewport import ListViewport
from light_console.display.lifecycle import (
    STARTING_UP_TEXT,
    SHUTTING_DOWN_TEXT,
    draw_lifecycle,
)
from light_console.display.widgets import CELL_W, text, text_clipped
from light_console.output.pages import OutputItem, build_output_pages_from_state
from light_console.output.targets import APPLYABLE_TARGETS, last_octet
from light_console.state import AppState, ScreenId
from light_console.ui.menu import MENU_ITEMS, MenuItem
from light_console.output.netmode import oled_mode_word, toggle_filled
from light_console.ui.vocab import IDLE, LOST, OFF, OFFLINE, OK, RUNNING, STOPPED


def qlc_output_label(state: AppState) -> str:
    """Status file / WS word. Engine down or socket error is OFFLINE."""
    if state.qlc_connected:
        return "CONNECTED"
    return "OFFLINE"


def startup_oled_word(state: AppState) -> str:
    word = (state.startup_status or "").strip()
    if word:
        return word[:9]
    return STOPPED


def play_qlc_word(state: AppState) -> str:
    word = (state.qlc_observed or "").strip()
    if word:
        return word
    return RUNNING if state.qlc_connected else OFFLINE


def wiz_status_word(state: AppState) -> str:
    if not state.wiz_enabled:
        return OFF
    if state.wiz_online >= state.wiz_expected and state.wiz_expected > 0:
        return OK
    return LOST


def viewport_for(total: int, focused: int, offset: int, visible: int = CONTENT_ROWS) -> ListViewport:
    vp = ListViewport(total=total, focused=focused, offset=offset, visible=visible)
    vp.reveal()
    return vp


def _marquee_offset(
    state: AppState | None,
    key: str,
    value: str,
    field_w: int,
    *,
    enabled: bool,
) -> int:
    if state is None or not enabled or not value:
        return 0
    return field_offset(state, key, state.ui_now, value, field_w)


def draw_list(
    fb: Framebuffer,
    labels: list[str],
    selected: int,
    y0: int = CONTENT_Y,
    rows: int = CONTENT_ROWS,
    offset: int = 0,
    *,
    state: AppState | None = None,
    list_id: str = "list",
    marquee: bool = True,
) -> None:
    """Shared list: focus rail + scrollbar. No invert (would flip toggles)."""
    del y0
    if not labels:
        draw_empty_state(fb, "NO DEVICES")
        return
    vp = viewport_for(len(labels), selected, offset, rows)
    draw_scrollbar(fb, vp.total, vp.visible, vp.offset)
    field_w = CONTENT_RIGHT - LABEL_X
    for i, idx in enumerate(vp.window()):
        y = CONTENT_Y + i * ROW
        focused = idx == selected
        off = _marquee_offset(
            state,
            f"{list_id}:{idx}",
            labels[idx],
            field_w,
            enabled=marquee and focused,
        )
        draw_text_row(fb, y, labels[idx], focused=focused, offset=off)


def draw_play(fb: Framebuffer, state: AppState) -> None:
    draw_page_header(fb, "LIGHT CONSOLE")
    qlc = play_qlc_word(state)
    startup = startup_oled_word(state)
    midi = OK if state.launchpad_connected else OFFLINE
    output = (state.output_mode or "SAFE")[:9]
    live = dmx_output_active(state.dmx_by_universe)
    now = state.ui_now
    draw_status_row(fb, ROW * 1, "QLC", qlc, now=now)
    draw_status_row(fb, ROW * 2, "SHOW", "MASTER", now=now)
    draw_status_row(fb, ROW * 3, "STARTUP", startup, warn=False, now=now)
    draw_status_row(fb, ROW * 4, "MIDI", midi, now=now)
    draw_status_row(fb, ROW * 5, "OUTPUT", output, activity=live, now=now)
    draw_status_row(fb, ROW * 6, "MASTER", f"{state.master}%", warn=False, now=now)


def draw_menu(fb: Framebuffer, state: AppState, items: tuple[MenuItem, ...] | None = None) -> None:
    draw_page_header(fb, "MENU")
    rows = items if items is not None else MENU_ITEMS
    labels = [item.label for item in rows]
    draw_list(
        fb,
        labels,
        state.menu_index,
        offset=state.scroll_offset,
        state=state,
        list_id="menu",
    )


def draw_params(fb: Framebuffer, state: AppState, params=None) -> None:
    draw_page_header(fb, "PARAMS")
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
    draw_list(
        fb,
        labels,
        state.param_index,
        offset=state.scroll_offset,
        state=state,
        list_id="params",
        marquee=False,
    )


def draw_scenes(fb: Framebuffer, state: AppState) -> None:
    draw_page_header(fb, "SCENES")
    if not state.scenes:
        draw_empty_state(fb, "NO SCENES")
        return
    draw_list(
        fb,
        list(state.scenes),
        state.scene_index,
        offset=state.scroll_offset,
        state=state,
        list_id="scenes",
    )


def draw_chasers(fb: Framebuffer, state: AppState) -> None:
    draw_page_header(fb, "CHASERS")
    if not state.chasers:
        draw_empty_state(fb, "NO CHASERS")
        return
    draw_list(
        fb,
        list(state.chasers),
        state.chaser_index,
        offset=state.scroll_offset,
        state=state,
        list_id="chasers",
    )


def draw_shows(fb: Framebuffer, state: AppState) -> None:
    draw_page_header(fb, "SHOWS")
    labels_src = state.show_files
    if not labels_src:
        draw_empty_state(fb, "NO SHOWS")
        return
    labels = []
    current = state.show_name
    for name in labels_src:
        mark = "*" if name == current else " "
        labels.append(f"{mark}{name}")
    draw_list(
        fb,
        labels,
        state.show_index,
        offset=state.scroll_offset,
        state=state,
        list_id="shows",
    )


def draw_load_show(fb: Framebuffer, state: AppState) -> None:
    draw_page_header(fb, "SHOW")
    name = state.show_name or "--"
    field_w = CONTENT_RIGHT - LABEL_X
    off = field_offset(state, "load_show", state.ui_now, name, field_w)
    text_clipped(fb, LABEL_X - off, ROW * 2, name, LABEL_X, LABEL_X + field_w)
    text(fb, LABEL_X, ROW * 3, (state.show_status or "ACTIVE")[:21])


def _item_span(items: tuple[OutputItem, ...]) -> int:
    if any(item.subtitle for item in items):
        return 2
    return 1


def _draw_output_item(
    fb: Framebuffer,
    y: int,
    item: OutputItem,
    *,
    focused: bool,
    now: float,
    span: int,
    state: AppState,
    idx: int,
) -> None:
    del span
    if item.subtitle:
        prefix = item.prefix
        name = item.name
        if prefix and name:
            field_w = CONTENT_RIGHT - (LABEL_X + len(prefix) * CELL_W)
            off = _marquee_offset(
                state, f"out:{idx}:name", name, field_w, enabled=focused
            )
            draw_prefixed_name(fb, y, prefix, name, focused=focused, offset=off)
        else:
            field_w = CONTENT_RIGHT - LABEL_X
            off = _marquee_offset(
                state, f"out:{idx}:title", item.title, field_w, enabled=focused
            )
            draw_text_row(fb, y, item.title, focused=focused, offset=off)
        label = item.subtitle
        value = item.status
        if value and label.endswith(value):
            label = label[: -(len(value) + 1)].rstrip()
        if value:
            draw_status_row(
                fb,
                y + ROW,
                label,
                value,
                activity=item.activity,
                now=now,
            )
        else:
            draw_text_row(fb, y + ROW, item.subtitle)
        return
    if item.status:
        label = item.name or item.title
        field_w = status_label_field_w(item.status)
        off = _marquee_offset(
            state,
            f"out:{idx}:label",
            label,
            field_w,
            enabled=focused and bool(item.name),
        )
        draw_status_row(
            fb,
            y,
            label,
            item.status,
            focused=focused,
            activity=item.activity,
            now=now,
            label_offset=off,
        )
        return
    field_w = CONTENT_RIGHT - LABEL_X
    off = _marquee_offset(
        state, f"out:{idx}:title", item.title, field_w, enabled=focused
    )
    draw_text_row(fb, y, item.title, focused=focused, offset=off)


def draw_output(fb: Framebuffer, state: AppState) -> None:
    pages = build_output_pages_from_state(state)
    if not pages:
        draw_page_header(fb, "OUTPUT")
        draw_empty_state(fb, "NO DEVICES")
        return
    index = state.output_page % len(pages)
    page = pages[index]
    now = state.ui_now
    if state.output_detail and page.items:
        item = page.items[state.output_focus % len(page.items)]
        if item.target_id:
            draw_page_header(fb, item.title[:16])
            _draw_node_detail(fb, item, state)
            return
        draw_page_header(fb, page.title[:16])
        detail = item.detail or (item.title,)
        _draw_scrolled_lines(fb, detail, state.scroll_offset, state.output_focus)
        return
    draw_page_header(fb, page.title[:16])
    if page.kind == "universe":
        from light_console.display.universe_map import draw_universe_raster

        uni = page.universe or 1
        buf = state.dmx_by_universe.get(uni - 1, ())
        draw_universe_raster(
            fb,
            universe_id=uni - 1,
            fixtures=state.fixtures,
            buf=buf,
            now=now,
        )
        return
    if page.kind == "dmx" and not state.qlc_connected:
        draw_empty_state(fb, "QLC OFFLINE")
        return
    if page.kind == "dmx" and (not state.dmx_ready or page.empty and not page.items):
        draw_empty_state(fb, page.empty or "NO LIVE DMX")
        return
    if page.empty and not page.items and not page.lines:
        draw_empty_state(fb, page.empty)
        return
    if page.archetype == "summary" or page.kind == "overview":
        y = CONTENT_Y
        for item in page.items:
            if item.subtitle:
                draw_named_status_row(
                    fb,
                    y,
                    item.title,
                    item.subtitle,
                    item.status,
                    activity=item.activity,
                    now=now,
                )
            elif item.status:
                draw_status_row(
                    fb,
                    y,
                    item.title,
                    item.status,
                    activity=item.activity,
                    now=now,
                )
            else:
                draw_text_row(fb, y, item.title)
            y += ROW
            if y >= ROW * 8:
                break
        return
    items = page.items
    if not items and page.lines:
        _draw_scrolled_lines(fb, page.lines, state.scroll_offset, state.output_focus)
        return
    if not items:
        draw_empty_state(fb, page.empty or "NO DEVICES")
        return
    span = _item_span(items)
    visible = max(1, CONTENT_ROWS // span)
    vp = viewport_for(len(items), state.output_focus, state.scroll_offset, visible)
    draw_scrollbar(fb, vp.total, vp.visible, vp.offset)
    for i, idx in enumerate(vp.window()):
        y = CONTENT_Y + i * span * ROW
        _draw_output_item(
            fb,
            y,
            items[idx],
            focused=idx == vp.focused,
            now=now,
            span=span,
            state=state,
            idx=idx,
        )


def _draw_node_detail(fb: Framebuffer, item: OutputItem, state: AppState) -> None:
    y = CONTENT_Y
    draw_status_row(fb, y, "STATUS", item.status or IDLE)
    y += ROW
    ip = last_octet(item.ipv4) if item.ipv4 else "--"
    draw_status_row(fb, y, "IP", ip)
    y += ROW
    draw_text_row(fb, y, "QLC TARGET")
    draw_toggle(fb, VALUE_RIGHT - TOGGLE_D, y, item.is_qlc_target)
    y += ROW
    if item.target_id in {target.value for target in APPLYABLE_TARGETS}:
        label = state.route_op or "SET TARGET"
        draw_action_row(fb, y, label, focused=not state.route_busy)


def _draw_scrolled_lines(
    fb: Framebuffer,
    lines: tuple[str, ...],
    offset: int,
    focused: int,
) -> None:
    if not lines:
        draw_empty_state(fb, "NO DATA")
        return
    vp = viewport_for(len(lines), min(focused, len(lines) - 1), offset, CONTENT_ROWS)
    draw_scrollbar(fb, vp.total, vp.visible, vp.offset)
    for i, idx in enumerate(vp.window()):
        y = CONTENT_Y + i * ROW
        draw_text_row(fb, y, lines[idx], focused=idx == vp.focused)


def _draw_dmx(fb: Framebuffer, state: AppState, universe: int, window: int) -> None:
    """Kept for tests that import the drawer; live DMX uses the list path."""
    del universe, window
    draw_output(fb, state)


def draw_system(fb: Framebuffer, state: AppState) -> None:
    from light_console.ui.pages import (
        SYSTEM_ROW_COUNT,
        system_slots,
        wiz_setting_detail,
    )

    draw_page_header(fb, "SYSTEM")
    if state.system_index >= SYSTEM_ROW_COUNT:
        state.system_index %= SYSTEM_ROW_COUNT
    vp = viewport_for(SYSTEM_ROW_COUNT, state.system_index, state.scroll_offset, SYSTEM_ROW_COUNT)
    draw_scrollbar(fb, vp.total, vp.visible, vp.offset)
    wiz_detail = wiz_setting_detail(state)
    for slot in system_slots(state):
        focused = slot.index == vp.focused
        if slot.kind == "qlc":
            draw_toggle_row(
                fb,
                slot.y,
                "QLC SERVICE",
                state.qlc_desired,
                focused=focused,
                rail_h=slot.rows * ROW,
            )
            draw_subordinate_status(fb, slot.y + ROW, play_qlc_word(state))
        elif slot.kind == "wiz":
            draw_toggle_row(
                fb,
                slot.y,
                "WIZ CONTROL",
                state.wiz_enabled,
                focused=focused,
                rail_h=slot.rows * ROW,
            )
            if wiz_detail:
                draw_subordinate_status(fb, slot.y + ROW, wiz_detail)
        elif slot.kind == "net":
            draw_toggle_row(
                fb,
                slot.y,
                "NETWORK MODE",
                toggle_filled(state.network_mode),
                focused=focused,
                rail_h=slot.rows * ROW,
            )
            word = (state.network_mode_observed or oled_mode_word(state.network_mode)).strip()
            draw_subordinate_status(fb, slot.y + ROW, word)
        elif slot.kind == "shutdown":
            draw_action_row(fb, slot.y, "SHUTDOWN", focused=focused, x=TOGGLE_LABEL_X)


SHUTTING_DOWN_LINES = (SHUTTING_DOWN_TEXT,)


def draw_starting_up(fb: Framebuffer, state: AppState) -> None:
    del state
    draw_lifecycle(fb, STARTING_UP_TEXT)


def draw_shutting_down(fb: Framebuffer, state: AppState) -> None:
    del state
    draw_lifecycle(fb, SHUTTING_DOWN_TEXT)


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
    ScreenId.STARTING_UP: draw_starting_up,
    ScreenId.SHUTTING_DOWN: draw_shutting_down,
}


def draw_screen(fb: Framebuffer, state: AppState) -> None:
    fb.clear()
    drawer = DRAWERS.get(state.screen, draw_play)
    drawer(fb, state)
