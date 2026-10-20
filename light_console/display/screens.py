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
from light_console.controls.encoders import bound_index
from light_console.display.lifecycle import (
    STARTING_UP_TEXT,
    SHUTTING_DOWN_TEXT,
    draw_lifecycle,
)
from light_console.display.widgets import CELL_W, text, text_clipped
from light_console.display.wordmark import (
    HUE_Y,
    MASTER_Y,
    META_Y,
    OUTPUT_Y,
    QLC_Y,
    SAT_Y,
    draw_wordmark,
)
from light_console.live_color import format_hue, format_percent
from light_console.output.pages import OutputItem, build_output_pages_from_state
from light_console.output.summary import play_output_summary
from light_console.output.targets import APPLYABLE_TARGETS, last_octet
from light_console.state import AppState, ScreenId
from light_console.ui.menu import MENU_ITEMS, MenuItem
from light_console.output.netmode import oled_mode_word, toggle_filled
from light_console.ui.vocab import IDLE, NEW, OFF, OFFLINE, RUNNING, STOPPED
from light_console.wiz.device_map import format_dmx_span
from light_console.wiz.view import list_label


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
    from light_console.output.wiz_lifecycle import oled_wiz_detail

    if not state.wiz_enabled:
        return OFF
    detail = oled_wiz_detail(
        desired=True,
        ap=state.wiz_ap_state,
        bridge=state.wiz_bridge_state,
        busy=state.wiz_lifecycle_busy,
        online=state.wiz_online,
    )
    return detail or OFF


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
    now = state.ui_now
    draw_wordmark(fb)
    live = dmx_output_active(state.dmx_by_universe)
    draw_status_row(fb, MASTER_Y, "MASTER", format_percent(state.master), warn=False, now=now)
    draw_status_row(fb, SAT_Y, "SAT", format_percent(state.saturation), warn=False, now=now)
    draw_status_row(fb, HUE_Y, "HUE", format_hue(state.hue_shift), warn=False, now=now)
    draw_status_row(
        fb,
        OUTPUT_Y,
        "OUTPUT",
        play_output_summary(state),
        activity=live,
        now=now,
    )
    draw_status_row(fb, QLC_Y, "QLC", play_qlc_word(state), now=now)
    if not state.launchpad_connected:
        draw_status_row(fb, META_Y, "MIDI", OFFLINE, now=now)
    else:
        draw_status_row(
            fb,
            META_Y,
            "STARTUP",
            startup_oled_word(state),
            warn=False,
            now=now,
        )


def draw_menu(fb: Framebuffer, state: AppState, items: tuple[MenuItem, ...] | None = None) -> None:
    title = state.menu_title or "MENU"
    if items is not None:
        labels = [item.label for item in items]
    elif state.menu_labels:
        labels = list(state.menu_labels)
    else:
        labels = [item.label for item in MENU_ITEMS]
    draw_page_header(fb, title)
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
            f"Master       {format_percent(state.master)}",
            f"Sat          {format_percent(state.saturation)}",
            f"Hue          {format_hue(state.hue_shift)}",
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
    index = bound_index(state.output_page, len(pages))
    page = pages[index]
    now = state.ui_now
    if state.output_detail and page.items:
        item = page.items[bound_index(state.output_focus, len(page.items))]
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
        from light_console.display.universe_map import draw_universe_overview

        draw_universe_overview(
            fb,
            universes=page.universes or state.qlc_universes or (page.universe or 1,),
            fixtures=state.fixtures,
            dmx=state.dmx_by_universe,
            start_universe=state.output_universe or page.universe or 1,
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
        system_visible_count,
    )

    draw_page_header(fb, "SYSTEM")
    state.system_index = bound_index(state.system_index, SYSTEM_ROW_COUNT)
    visible = system_visible_count(state)
    vp = viewport_for(SYSTEM_ROW_COUNT, state.system_index, state.scroll_offset, visible)
    draw_scrollbar(fb, vp.total, vp.visible, vp.offset)
    y = CONTENT_Y
    window = set(vp.window())
    for slot in system_slots(state):
        if slot.index not in window:
            continue
        focused = slot.index == vp.focused
        if slot.kind == "qlc":
            draw_toggle_row(
                fb,
                y,
                "QLC SERVICE",
                state.qlc_desired,
                focused=focused,
                rail_h=slot.rows * ROW,
            )
            draw_subordinate_status(fb, y + ROW, play_qlc_word(state))
        elif slot.kind == "net":
            draw_toggle_row(
                fb,
                y,
                "NETWORK MODE",
                toggle_filled(state.network_mode),
                focused=focused,
                rail_h=slot.rows * ROW,
            )
            word = (state.network_mode_observed or oled_mode_word(state.network_mode)).strip()
            draw_subordinate_status(fb, y + ROW, word)
        elif slot.kind == "version":
            draw_action_row(fb, y, "VERSION", focused=focused, x=TOGGLE_LABEL_X)
        elif slot.kind == "shutdown":
            draw_action_row(fb, y, "SHUTDOWN", focused=focused, x=TOGGLE_LABEL_X)
        y += slot.rows * ROW


def draw_wiz_control(fb: Framebuffer, state: AppState) -> None:
    from light_console.ui.pages import wiz_setting_detail

    draw_page_header(fb, "WIZ CONTROL")
    detail = wiz_setting_detail(state)
    rows = 2 if detail else 1
    draw_toggle_row(
        fb,
        CONTENT_Y,
        "WIZ",
        state.wiz_enabled,
        focused=True,
        rail_h=rows * ROW,
    )
    if detail:
        draw_subordinate_status(fb, CONTENT_Y + ROW, detail)


def draw_version(fb: Framebuffer, state: AppState) -> None:
    draw_page_header(fb, "VERSION")
    draw_text_row(fb, CONTENT_Y, "LIGHT CTRL")
    draw_status_row(fb, CONTENT_Y + ROW, "VERSION", state.version or "--")
    rev = (state.build_revision or "").strip()
    if rev:
        draw_status_row(fb, CONTENT_Y + ROW * 2, "REV", rev[:7])


def _draw_wiz_device_detail(fb: Framebuffer, state: AppState) -> None:
    rows = state.wiz_device_rows
    if not rows:
        draw_empty_state(fb, "NO DEVICES")
        return
    row = rows[bound_index(state.wiz_device_index, len(rows))]
    if row.kind == "new" or row.slot is None:
        draw_page_header(fb, "NEW WIZ DEVICE")
        lines = (
            f"MAC {row.id}",
            f"IP {row.observed_ip or '--'}",
            f"STATE {NEW}",
            "NOT MAPPED",
        )
    else:
        draw_page_header(fb, "WIZ DEVICE")
        span = format_dmx_span(row.slot)
        lines = (
            f"SLOT {row.slot:02d} {span}",
            f"MAC {row.id}",
            f"STATE {row.state}",
            f"IP {row.observed_ip or '--'}",
        )
    for i, line in enumerate(lines):
        draw_text_row(fb, CONTENT_Y + i * ROW, line)


def _draw_wiz_prompt(fb: Framebuffer, state: AppState) -> None:
    prompt = state.wiz_prompt
    mac = (state.wiz_prompt_mac or "").strip()
    short = mac[-6:].upper() if len(mac) >= 6 else mac.upper()
    if prompt == "add":
        draw_page_header(fb, "ADD DEVICE")
        lines = (f"MAC {short or mac}", f"SLOT {state.wiz_prompt_slot:02d}")
    elif prompt == "move":
        draw_page_header(fb, "MOVE")
        lines = (f"SLOT {state.wiz_prompt_target:02d}",)
    elif prompt == "swap":
        draw_page_header(fb, "SWAP")
        lines = (f"{state.wiz_prompt_slot:02d} <-> {state.wiz_prompt_target:02d}",)
    elif prompt == "disable":
        draw_page_header(fb, "DISABLE")
        lines = (f"SLOT {state.wiz_prompt_slot:02d}",)
    elif prompt == "enable":
        draw_page_header(fb, "ENABLE")
        lines = (f"SLOT {state.wiz_prompt_slot:02d}",)
    elif prompt == "full":
        draw_page_header(fb, "ADD DEVICE")
        lines = ("FULL",)
    elif prompt == "fail":
        draw_page_header(fb, "WIZ DEVICES")
        lines = ((state.wiz_prompt_error or "WRITE FAIL")[:16],)
    elif prompt == "actions":
        draw_page_header(fb, "WIZ DEVICE")
        rows = state.wiz_device_rows
        row = rows[bound_index(state.wiz_device_index, len(rows))] if rows else None
        enable = bool(row is not None and not row.enabled)
        labels = ("MOVE", "ENABLE" if enable else "DISABLE")
        for i, label in enumerate(labels):
            draw_action_row(
                fb,
                CONTENT_Y + i * ROW,
                label,
                focused=state.wiz_action_index == i,
                x=LABEL_X,
            )
        return
    else:
        draw_page_header(fb, "WIZ DEVICES")
        lines = (prompt.upper()[:16],)
    for i, line in enumerate(lines):
        draw_text_row(fb, CONTENT_Y + i * ROW, line)


def draw_wiz_devices(fb: Framebuffer, state: AppState) -> None:
    from light_console.ui.pages import wiz_devices_viewport

    if state.wiz_prompt:
        _draw_wiz_prompt(fb, state)
        return
    if state.wiz_device_detail:
        _draw_wiz_device_detail(fb, state)
        return
    draw_page_header(fb, "WIZ DEVICES")
    note = (state.wiz_devices_note or "").strip()
    y0 = CONTENT_Y
    if note:
        draw_subordinate_status(fb, y0, note)
        y0 += ROW
    rows = state.wiz_device_rows
    if not rows:
        draw_empty_state(fb, "NO DEVICES")
        return
    vp = wiz_devices_viewport(state)
    draw_scrollbar(
        fb,
        vp.total,
        vp.visible,
        vp.offset,
        y=y0,
        h=vp.visible * ROW,
    )
    now = state.ui_now
    for i, idx in enumerate(vp.window()):
        y = y0 + i * ROW
        if y + ROW > CONTENT_Y + CONTENT_ROWS * ROW:
            break
        row = rows[idx]
        draw_status_row(
            fb,
            y,
            list_label(row),
            row.state,
            focused=idx == vp.focused,
            activity=row.dmx_active,
            now=now,
        )


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
    ScreenId.WIZ_CONTROL: draw_wiz_control,
    ScreenId.WIZ_DEVICES: draw_wiz_devices,
    ScreenId.VERSION: draw_version,
    ScreenId.STARTING_UP: draw_starting_up,
    ScreenId.SHUTTING_DOWN: draw_shutting_down,
}


def draw_screen(fb: Framebuffer, state: AppState) -> None:
    fb.clear()
    drawer = DRAWERS.get(state.screen, draw_play)
    drawer(fb, state)
