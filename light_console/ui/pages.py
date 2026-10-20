"""Norns-like screens: enc(n, delta), key(n, z), redraw(fb).

n is E1/E2/E3 or K1/K2/K3 (1,2,3). z is 1 down/tap, 0 up.
K1 PLAY↔MENU and MENU E1/E2/K2/K3 are handled by NornsUIShell, not these screens.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import Any

from light_console.controls.encoders import (
    apply_encoder_delta,
    bound_index,
    clamp_index,
    is_list_nav,
)
from light_console.display.framebuffer import Framebuffer
from light_console.display.screens import (
    draw_chasers,
    draw_load_show,
    draw_menu,
    draw_output,
    draw_params,
    draw_play,
    draw_scenes,
    draw_shows,
    draw_restart_confirm,
    draw_restarting,
    draw_shutdown_confirm,
    draw_shutting_down,
    draw_starting_up,
    draw_system,
    draw_version,
    draw_wiz_info,
    draw_wiz_control,
    draw_wiz_devices,
)
from light_console.display.layout import CONTENT_ROWS, CONTENT_Y, ROW
from light_console.display.universe_map import VISIBLE_UNIVERSES
from light_console.display.viewport import ListViewport
from light_console.output.pages import build_output_pages_from_state
from light_console.output.targets import APPLYABLE_TARGETS
from light_console.hardware.events import E1, E2, E3, K2, K3
from light_console.live_color import HUE_DEFAULT, SAT_DEFAULT
from light_console.power import PowerService
from light_console.state import AppState, ScreenId
from light_console.wiz.device_map import WIZ_MAX_SLOTS
from light_console.ui.vocab import LOAD, OPEN, SCANNING, SWITCHING
from light_console.ui.nav import Navigation
from light_console.ui.params import Params

SYSTEM_QLC_TOGGLE = 0
SYSTEM_NET_TOGGLE = 1
SYSTEM_VERSION = 2
SYSTEM_ROW_COUNT = 3
SYSTEM_EDITABLE_ROWS = frozenset({SYSTEM_QLC_TOGGLE, SYSTEM_NET_TOGGLE})
WIZ_CONTROL_TOGGLE = 0
WIZ_CONTROL_SCAN = 1
WIZ_CONTROL_ROW_COUNT = 2
WIZ_DISCOVER_HOLD_S = 4.0
WIZ_DEVICES_VISIBLE = 6


def wiz_devices_visible_count(state: AppState) -> int:
    """Device rows that fit under the header (and optional note). Max 6."""
    note = 1 if (state.wiz_devices_note or "").strip() else 0
    return max(1, min(WIZ_DEVICES_VISIBLE, CONTENT_ROWS - note))


def wiz_devices_viewport(state: AppState) -> ListViewport:
    """Selection + offset owned here; renderer only paints the revealed window."""
    vp = ListViewport(
        len(state.wiz_device_rows),
        state.wiz_device_index,
        state.scroll_offset,
        wiz_devices_visible_count(state),
    )
    vp.reveal()
    return vp


@dataclass(frozen=True)
class SystemSlot:
    index: int
    kind: str
    y: int
    rows: int


def wiz_setting_detail(state: AppState) -> str | None:
    """Independent WiZ observation, or None when the toggle already says enough."""
    from light_console.output.wiz_lifecycle import oled_wiz_detail

    return oled_wiz_detail(
        desired=state.wiz_enabled,
        ap=state.wiz_ap_state,
        bridge=state.wiz_bridge_state,
        busy=state.wiz_lifecycle_busy,
        online=state.wiz_online,
    )


def wiz_discovering(state: AppState) -> bool:
    return bool(state.wiz_tx_armed) and state.wiz_discover_until > state.ui_now


def wiz_control_slots(state: AppState) -> tuple[SystemSlot, ...]:
    y = CONTENT_Y
    toggle_rows = 2 if wiz_setting_detail(state) else 1
    toggle = SystemSlot(WIZ_CONTROL_TOGGLE, "wiz", y, toggle_rows)
    y += toggle.rows * ROW
    scan_rows = 2 if wiz_discovering(state) else 1
    scan = SystemSlot(WIZ_CONTROL_SCAN, "scan", y, scan_rows)
    return (toggle, scan)


def wiz_control_visible_count(state: AppState) -> int:
    rows = sum(slot.rows for slot in wiz_control_slots(state))
    if rows <= CONTENT_ROWS:
        return WIZ_CONTROL_ROW_COUNT
    return WIZ_CONTROL_ROW_COUNT - 1


def system_slots(state: AppState) -> tuple[SystemSlot, ...]:
    y = CONTENT_Y
    qlc = SystemSlot(SYSTEM_QLC_TOGGLE, "qlc", y, 2)
    y += qlc.rows * ROW
    net = SystemSlot(SYSTEM_NET_TOGGLE, "net", y, 2)
    y += net.rows * ROW
    version = SystemSlot(SYSTEM_VERSION, "version", y, 1)
    return (qlc, net, version)


def system_visible_count(state: AppState) -> int:
    """How many SYSTEM items fit in the content window."""
    rows = sum(slot.rows for slot in system_slots(state))
    if rows <= CONTENT_ROWS:
        return SYSTEM_ROW_COUNT
    return SYSTEM_ROW_COUNT - 1


def _follow(state: AppState, focused: int, total: int, visible: int = CONTENT_ROWS) -> None:
    vp = ListViewport(total, focused, state.scroll_offset, visible)
    vp.reveal()
    state.scroll_offset = vp.offset


def _move_list(state: AppState, attr: str, delta: int, count: int, visible: int = CONTENT_ROWS) -> None:
    nxt = clamp_index(getattr(state, attr), delta, count)
    setattr(state, attr, nxt)
    _follow(state, nxt, count, visible)


@dataclass
class ScreenContext:
    state: AppState
    nav: Navigation
    params: Params
    power: PowerService
    actions: Any = None


class Screen(ABC):
    id: ScreenId
    title: str = ""

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        del n, delta, ctx

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        del n, z, ctx

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        del fb, ctx


def _go_scene(ctx: ScreenContext) -> None:
    actions = ctx.actions
    if actions is not None:
        actions.go_scene(ctx.state)


def _go_chaser(ctx: ScreenContext) -> None:
    actions = ctx.actions
    if actions is not None:
        actions.go_chaser(ctx.state)


class PlayScreen(Screen):
    id = ScreenId.PLAY
    title = "PLAY"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if n == E1:
            ctx.params["master"].delta(delta)
        elif n == E2:
            ctx.params["sat"].delta(delta)
        elif n == E3:
            ctx.params["hue"].delta(delta)

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1:
            return
        if n == K2:
            ctx.params["sat"].set(SAT_DEFAULT)
        elif n == K3:
            ctx.params["hue"].set(HUE_DEFAULT)

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_play(fb, ctx.state)


class MenuScreen(Screen):
    id = ScreenId.MENU
    title = "MENU"

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_menu(fb, ctx.state, ctx.nav.current_items())


class ParamsScreen(Screen):
    id = ScreenId.PARAMS
    title = "PARAMS"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        ctx.params.sync_index_to_state(ctx.state)
        if is_list_nav(n):
            ctx.params.select_delta(delta)
            ctx.params.store_index(ctx.state)
            _follow(ctx.state, ctx.state.param_index, max(1, ctx.state.param_count))
        elif n == E3:
            ctx.params.selected.delta(delta)

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1:
            return
        ctx.params.sync_index_to_state(ctx.state)
        if n == K3:
            ctx.params.selected.trigger()

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        ctx.params.sync_index_to_state(ctx.state)
        draw_params(fb, ctx.state, ctx.params)


class ShowsScreen(Screen):
    id = ScreenId.SHOWS
    title = "SHOWS"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        items = ctx.state.show_ids or ctx.state.show_files
        if is_list_nav(n) and items:
            _move_list(ctx.state, "show_index", delta, len(items))

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1 or n != K3:
            return
        if ctx.state.show_busy:
            return
        items = ctx.state.show_ids or ctx.state.show_files
        if not items:
            return
        idx = bound_index(ctx.state.show_index, len(items))
        filename = ctx.state.show_ids[idx] if ctx.state.show_ids else items[idx]
        if ctx.state.show_files:
            ctx.state.show_name = ctx.state.show_files[idx]
        else:
            ctx.state.show_name = filename
        if ctx.state.show_open_id == filename:
            ctx.state.show_status = OPEN
        else:
            ctx.state.show_status = LOAD
        ctx.nav.open_load_show_confirm(ctx.state)

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_shows(fb, ctx.state)


class LoadShowScreen(Screen):
    id = ScreenId.LOAD_SHOW
    title = "SHOW"

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1:
            return
        if n == K2:
            if not ctx.state.show_busy:
                ctx.nav.back(ctx.state)
            return
        if n != K3:
            return
        if ctx.state.show_busy:
            return
        if ctx.state.show_status == OPEN:
            ctx.nav.back(ctx.state)
            return
        actions = ctx.actions
        if actions is not None and hasattr(actions, "open_workspace"):
            actions.open_workspace()

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_load_show(fb, ctx.state)


class ScenesScreen(Screen):
    id = ScreenId.SCENES
    title = "SCENES"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if is_list_nav(n) and ctx.state.scenes:
            _move_list(ctx.state, "scene_index", delta, len(ctx.state.scenes))

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1 or n != K3:
            return
        _go_scene(ctx)

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_scenes(fb, ctx.state)


class ChasersScreen(Screen):
    id = ScreenId.CHASERS
    title = "CHASERS"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if is_list_nav(n) and ctx.state.chasers:
            _move_list(ctx.state, "chaser_index", delta, len(ctx.state.chasers))

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1 or n != K3:
            return
        _go_chaser(ctx)

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_chasers(fb, ctx.state)


class OutputScreen(Screen):
    id = ScreenId.OUTPUT
    title = "OUTPUT"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        pages = build_output_pages_from_state(ctx.state)
        count = max(1, len(pages))
        if n == E1:
            ctx.state.output_page = clamp_index(ctx.state.output_page, delta, count)
            ctx.state.reset_list_window()
            return
        if n != E2:
            return
        page = pages[bound_index(ctx.state.output_page, count)]
        if page.kind == "universe":
            unis = page.universes or ctx.state.qlc_universes or (page.universe or 1,)
            current = (
                ctx.state.output_universe
                if ctx.state.output_universe in unis
                else (page.universe or unis[0])
            )
            idx = unis.index(current) if current in unis else 0
            max_off = max(0, len(unis) - VISIBLE_UNIVERSES)
            idx = apply_encoder_delta(idx, delta, 0, max_off)
            ctx.state.output_universe = unis[idx]
            return
        if ctx.state.output_detail and page.items:
            item = page.items[bound_index(ctx.state.output_focus, len(page.items))]
            if item.target_id:
                return
            lines = item.detail or (item.title,)
            total = len(lines)
            vp = ListViewport(total, ctx.state.scroll_offset, ctx.state.scroll_offset, CONTENT_ROWS)
            vp.move(delta)
            ctx.state.scroll_offset = vp.offset
            return
        if page.archetype == "summary":
            return
        items = page.items
        total = len(items) if items else len(page.lines)
        if total <= 0:
            return
        span = 2 if items and any(it.subtitle for it in items) else 1
        visible = max(1, CONTENT_ROWS // span)
        vp = ListViewport(total, ctx.state.output_focus, ctx.state.scroll_offset, visible)
        vp.stabilize(total)
        vp.move(delta)
        ctx.state.output_focus = vp.focused
        ctx.state.scroll_offset = vp.offset

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1:
            return
        pages = build_output_pages_from_state(ctx.state)
        if not pages:
            return
        page = pages[bound_index(ctx.state.output_page, len(pages))]
        if n == K2:
            if ctx.state.output_detail:
                ctx.state.output_detail = False
                ctx.state.scroll_offset = 0
            return
        if n != K3:
            return
        if ctx.state.output_detail:
            if page.items:
                item = page.items[bound_index(ctx.state.output_focus, len(page.items))]
                if item.target_id in {t.value for t in APPLYABLE_TARGETS}:
                    actions = ctx.actions
                    if actions is not None and not ctx.state.route_busy:
                        actions.apply_route_target(item.target_id)
                    return
            ctx.state.output_detail = False
            ctx.state.scroll_offset = 0
            return
        if not page.items:
            return
        item = page.items[bound_index(ctx.state.output_focus, len(page.items))]
        if item.detail or item.target_id:
            ctx.state.output_detail = True
            ctx.state.scroll_offset = 0

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_output(fb, ctx.state)


class SystemScreen(Screen):
    id = ScreenId.SYSTEM
    title = "SYSTEM"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if not is_list_nav(n):
            return
        ctx.state.system_count = SYSTEM_ROW_COUNT
        ctx.state.system_index = bound_index(ctx.state.system_index, SYSTEM_ROW_COUNT)
        visible = system_visible_count(ctx.state)
        vp = ListViewport(
            SYSTEM_ROW_COUNT,
            ctx.state.system_index,
            ctx.state.scroll_offset,
            visible,
        )
        vp.move(delta)
        ctx.state.system_index = vp.focused
        ctx.state.scroll_offset = vp.offset

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1 or n != K3:
            return
        if ctx.state.system_index == SYSTEM_VERSION:
            ctx.state.screen = ScreenId.VERSION
            ctx.state.scroll_offset = 0
            return
        actions = ctx.actions
        if actions is None:
            return
        if ctx.state.system_index == SYSTEM_QLC_TOGGLE:
            actions.set_qlc_desired(not ctx.state.qlc_desired)
        elif ctx.state.system_index == SYSTEM_NET_TOGGLE:
            if ctx.state.network_mode_busy or ctx.state.network_mode_observed == SWITCHING:
                return
            current = ctx.state.network_mode
            nxt = "standalone" if current != "standalone" else "network"
            actions.set_network_mode(nxt)

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_system(fb, ctx.state)


class WizDevicesScreen(Screen):
    id = ScreenId.WIZ_DEVICES
    title = "WIZ DEVICES"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if not is_list_nav(n):
            return
        if ctx.state.wiz_prompt == "move":
            ctx.state.wiz_prompt_target = bound_index(
                ctx.state.wiz_prompt_target - 1 + delta, WIZ_MAX_SLOTS
            ) + 1
            return
        if ctx.state.wiz_prompt == "actions":
            ctx.state.wiz_action_index = bound_index(ctx.state.wiz_action_index + delta, 2)
            return
        if ctx.state.wiz_prompt or ctx.state.wiz_device_detail:
            return
        rows = ctx.state.wiz_device_rows
        if not rows:
            ctx.state.wiz_device_index = 0
            ctx.state.scroll_offset = 0
            return
        vp = wiz_devices_viewport(ctx.state)
        vp.move(delta)
        ctx.state.wiz_device_index = vp.focused
        ctx.state.scroll_offset = vp.offset

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1:
            return
        if n == K2:
            return
        if n != K3:
            return
        actions = ctx.actions
        if ctx.state.wiz_prompt:
            if actions is not None and hasattr(actions, "confirm_wiz_prompt"):
                actions.confirm_wiz_prompt()
            return
        rows = ctx.state.wiz_device_rows
        if not rows:
            return
        ctx.state.wiz_device_index = bound_index(ctx.state.wiz_device_index, len(rows))
        if actions is not None and hasattr(actions, "open_wiz_device"):
            actions.open_wiz_device()
            return
        ctx.state.wiz_device_detail = True
        ctx.state.scroll_offset = 0

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_wiz_devices(fb, ctx.state)


class WizControlScreen(Screen):
    id = ScreenId.WIZ_CONTROL
    title = "WIZ CONTROL"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if not is_list_nav(n):
            return
        ctx.state.wiz_control_count = WIZ_CONTROL_ROW_COUNT
        ctx.state.wiz_control_index = bound_index(
            ctx.state.wiz_control_index, WIZ_CONTROL_ROW_COUNT
        )
        visible = wiz_control_visible_count(ctx.state)
        vp = ListViewport(
            WIZ_CONTROL_ROW_COUNT,
            ctx.state.wiz_control_index,
            ctx.state.scroll_offset,
            visible,
        )
        vp.move(delta)
        ctx.state.wiz_control_index = vp.focused
        ctx.state.scroll_offset = vp.offset

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1 or n != K3:
            return
        actions = ctx.actions
        if actions is None:
            return
        if ctx.state.wiz_lifecycle_busy:
            return
        if ctx.state.wiz_control_index == WIZ_CONTROL_SCAN:
            if hasattr(actions, "request_wiz_discover"):
                actions.request_wiz_discover()
            return
        actions.set_wiz_enabled(not ctx.state.wiz_enabled)

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_wiz_control(fb, ctx.state)


class ShutdownConfirmScreen(Screen):
    id = ScreenId.SHUTDOWN_CONFIRM
    title = "SHUTDOWN"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        del n, delta, ctx

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1 or n != K3:
            return
        actions = ctx.actions
        if actions is not None and hasattr(actions, "begin_appliance_shutdown"):
            actions.begin_appliance_shutdown()
            return
        ctx.nav.begin_shutdown(ctx.state)
        ctx.power.request_shutdown()
        ctx.state.shutdown_requested = ctx.power.shutdown_requested

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_shutdown_confirm(fb, ctx.state)


class RestartConfirmScreen(Screen):
    id = ScreenId.RESTART_CONFIRM
    title = "RESTART"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        del n, delta, ctx

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1 or n != K3:
            return
        actions = ctx.actions
        if actions is not None and hasattr(actions, "begin_appliance_restart"):
            actions.begin_appliance_restart()
            return
        ctx.nav.begin_restart(ctx.state)
        ctx.power.request_restart()
        ctx.state.restart_requested = ctx.power.restart_requested

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_restart_confirm(fb, ctx.state)


class VersionScreen(Screen):
    id = ScreenId.VERSION
    title = "VERSION"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        del n, delta, ctx

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        del n, z, ctx

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_version(fb, ctx.state)


class WizInfoScreen(Screen):
    id = ScreenId.WIZ_INFO
    title = "WIZ INFO"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        del n, delta, ctx

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        del n, z, ctx

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_wiz_info(fb, ctx.state)


class StartingUpScreen(Screen):
    id = ScreenId.STARTING_UP
    title = "STARTING UP"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        del n, delta, ctx

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        del n, z, ctx

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_starting_up(fb, ctx.state)


class ShuttingDownScreen(Screen):
    id = ScreenId.SHUTTING_DOWN
    title = "SHUTTING DOWN"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        del n, delta, ctx

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        del n, z, ctx

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_shutting_down(fb, ctx.state)


class RestartingScreen(Screen):
    id = ScreenId.RESTARTING
    title = "RESTARTING"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        del n, delta, ctx

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        del n, z, ctx

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_restarting(fb, ctx.state)


def build_screens() -> dict[ScreenId, Screen]:
    screens: tuple[Screen, ...] = (
        PlayScreen(),
        MenuScreen(),
        ParamsScreen(),
        ShowsScreen(),
        LoadShowScreen(),
        ScenesScreen(),
        ChasersScreen(),
        OutputScreen(),
        SystemScreen(),
        WizControlScreen(),
        WizDevicesScreen(),
        WizInfoScreen(),
        VersionScreen(),
        ShutdownConfirmScreen(),
        RestartConfirmScreen(),
        StartingUpScreen(),
        ShuttingDownScreen(),
        RestartingScreen(),
    )
    return {s.id: s for s in screens}
