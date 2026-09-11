"""Norns-like screens: enc(n, delta), key(n, z), redraw(fb).

n is E1/E2/E3 or K1/K2/K3 (1,2,3). z is 1 down/tap, 0 up.
K1 PLAY↔MENU and MENU E1/K2/K3 are handled by NornsUIShell, not these screens.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import Any

from light_console.controls.encoders import wrap_index
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
    draw_shutting_down,
    draw_starting_up,
    draw_system,
)
from light_console.display.layout import CONTENT_ROWS, CONTENT_Y, ROW
from light_console.display.viewport import ListViewport
from light_console.output.pages import build_output_pages_from_state
from light_console.output.targets import APPLYABLE_TARGETS
from light_console.hardware.events import E1, E2, E3, K2, K3
from light_console.power import PowerService
from light_console.state import AppState, ScreenId
from light_console.ui.vocab import LOST, SWITCHING
from light_console.ui.nav import Navigation
from light_console.ui.params import Params

SYSTEM_QLC_TOGGLE = 0
SYSTEM_WIZ_TOGGLE = 1
SYSTEM_NET_TOGGLE = 2
SYSTEM_SHUTDOWN_ROW = 3
SYSTEM_ROW_COUNT = 4
SYSTEM_EDITABLE_ROWS = frozenset({SYSTEM_QLC_TOGGLE, SYSTEM_WIZ_TOGGLE, SYSTEM_NET_TOGGLE})


@dataclass(frozen=True)
class SystemSlot:
    index: int
    kind: str
    y: int
    rows: int


def wiz_setting_detail(state: AppState) -> str | None:
    """Independent WiZ observation, or None when the toggle already says enough."""
    if not state.wiz_enabled:
        return None
    count = f"{state.wiz_online}/{state.wiz_expected}"
    if state.wiz_expected > 0 and state.wiz_online >= state.wiz_expected:
        return f"{count} ONLINE"
    return f"{count} {LOST}"


def system_slots(state: AppState) -> tuple[SystemSlot, ...]:
    y = CONTENT_Y
    qlc = SystemSlot(SYSTEM_QLC_TOGGLE, "qlc", y, 2)
    y += qlc.rows * ROW
    wiz_rows = 2 if wiz_setting_detail(state) else 1
    wiz = SystemSlot(SYSTEM_WIZ_TOGGLE, "wiz", y, wiz_rows)
    y += wiz.rows * ROW
    net = SystemSlot(SYSTEM_NET_TOGGLE, "net", y, 2)
    y += net.rows * ROW
    shutdown = SystemSlot(SYSTEM_SHUTDOWN_ROW, "shutdown", y, 1)
    return (qlc, wiz, net, shutdown)


def _follow(state: AppState, focused: int, total: int, visible: int = CONTENT_ROWS) -> None:
    vp = ListViewport(total, focused, state.scroll_offset, visible)
    vp.reveal()
    state.scroll_offset = vp.offset


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
        elif n == E2 and ctx.state.scenes:
            ctx.state.scene_index = wrap_index(
                ctx.state.scene_index, delta, len(ctx.state.scenes)
            )
        elif n == E3 and ctx.state.chasers:
            ctx.state.chaser_index = wrap_index(
                ctx.state.chaser_index, delta, len(ctx.state.chasers)
            )

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1:
            return
        if n == K2:
            _go_scene(ctx)
        elif n == K3:
            _go_chaser(ctx)

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
        if n == E2:
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
        if n == E1 and items:
            ctx.state.show_index = wrap_index(
                ctx.state.show_index, delta, len(items)
            )
            _follow(ctx.state, ctx.state.show_index, len(items))

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1 or n != K3:
            return
        actions = ctx.actions
        if actions is not None:
            actions.activate_show(ctx.state)
        if ctx.state.show_status == "ACTIVE":
            ctx.nav.open_load_show_confirm(ctx.state)

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_shows(fb, ctx.state)


class LoadShowScreen(Screen):
    id = ScreenId.LOAD_SHOW
    title = "SHOW"

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1:
            return
        if n == K3:
            actions = ctx.actions
            if actions is not None:
                actions.activate_show(ctx.state)
            ctx.nav.back(ctx.state)
        elif n == K2:
            ctx.nav.back(ctx.state)

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_load_show(fb, ctx.state)


class ScenesScreen(Screen):
    id = ScreenId.SCENES
    title = "SCENES"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if n == E1 and ctx.state.scenes:
            ctx.state.scene_index = wrap_index(
                ctx.state.scene_index, delta, len(ctx.state.scenes)
            )
            _follow(ctx.state, ctx.state.scene_index, len(ctx.state.scenes))

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
        if n == E1 and ctx.state.chasers:
            ctx.state.chaser_index = wrap_index(
                ctx.state.chaser_index, delta, len(ctx.state.chasers)
            )
            _follow(ctx.state, ctx.state.chaser_index, len(ctx.state.chasers))

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
            ctx.state.output_page = wrap_index(ctx.state.output_page, delta, count)
            ctx.state.reset_list_window()
            return
        if n != E2:
            return
        page = pages[ctx.state.output_page % count]
        if page.kind == "universe":
            unis = page.universes or ctx.state.qlc_universes or (page.universe or 1,)
            current = ctx.state.output_universe if ctx.state.output_universe in unis else (page.universe or unis[0])
            idx = unis.index(current) if current in unis else 0
            ctx.state.output_universe = unis[wrap_index(idx, delta, len(unis))]
            return
        if ctx.state.output_detail and page.items:
            item = page.items[ctx.state.output_focus % len(page.items)]
            if item.target_id:
                return
            lines = item.detail or (item.title,)
            total = len(lines)
            vp = ListViewport(total, ctx.state.scroll_offset, ctx.state.scroll_offset, CONTENT_ROWS)
            vp.move(delta, wrap=False)
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
        page = pages[ctx.state.output_page % len(pages)]
        if n == K2:
            if ctx.state.output_detail:
                ctx.state.output_detail = False
                ctx.state.scroll_offset = 0
            return
        if n != K3:
            return
        if ctx.state.output_detail:
            if page.items:
                item = page.items[ctx.state.output_focus % len(page.items)]
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
        item = page.items[ctx.state.output_focus % len(page.items)]
        if item.detail or item.target_id:
            ctx.state.output_detail = True
            ctx.state.scroll_offset = 0

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_output(fb, ctx.state)


class SystemScreen(Screen):
    id = ScreenId.SYSTEM
    title = "SYSTEM"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if n != E2:
            return
        ctx.state.system_count = SYSTEM_ROW_COUNT
        if ctx.state.system_index >= SYSTEM_ROW_COUNT:
            ctx.state.system_index %= SYSTEM_ROW_COUNT
        vp = ListViewport(
            SYSTEM_ROW_COUNT,
            ctx.state.system_index,
            ctx.state.scroll_offset,
            SYSTEM_ROW_COUNT,
        )
        vp.move(delta)
        ctx.state.system_index = vp.focused
        ctx.state.scroll_offset = vp.offset

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1 or n != K3:
            return
        if ctx.state.system_index == SYSTEM_SHUTDOWN_ROW:
            actions = ctx.actions
            if actions is not None and hasattr(actions, "begin_appliance_shutdown"):
                actions.begin_appliance_shutdown()
            else:
                ctx.nav.begin_shutdown(ctx.state)
                ctx.power.request_shutdown()
                ctx.state.shutdown_requested = ctx.power.shutdown_requested
            return
        actions = ctx.actions
        if actions is None:
            return
        if ctx.state.system_index == SYSTEM_QLC_TOGGLE:
            actions.set_qlc_desired(not ctx.state.qlc_desired)
        elif ctx.state.system_index == SYSTEM_WIZ_TOGGLE:
            actions.set_wiz_enabled(not ctx.state.wiz_enabled)
        elif ctx.state.system_index == SYSTEM_NET_TOGGLE:
            if ctx.state.network_mode_busy or ctx.state.network_mode_observed == SWITCHING:
                return
            current = ctx.state.network_mode
            nxt = "standalone" if current != "standalone" else "network"
            actions.set_network_mode(nxt)

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_system(fb, ctx.state)


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
        StartingUpScreen(),
        ShuttingDownScreen(),
    )
    return {s.id: s for s in screens}
