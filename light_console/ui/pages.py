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
    draw_system,
)
from light_console.output.pages import build_output_pages
from light_console.hardware.events import E1, E2, E3, K2, K3
from light_console.power import PowerService
from light_console.state import AppState, ScreenId
from light_console.ui.nav import Navigation
from light_console.ui.params import Params

SYSTEM_SHUTDOWN_ROW = 4
SYSTEM_ROW_COUNT = 5


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
        if n != E1:
            return
        pages = build_output_pages(
            ctx.state.network_ifaces,
            ctx.state.output_routes,
            ctx.state.dmx_by_universe,
        )
        count = max(1, len(pages))
        ctx.state.output_page = wrap_index(ctx.state.output_page, delta, count)

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        del n, z, ctx

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_output(fb, ctx.state)


class SystemScreen(Screen):
    id = ScreenId.SYSTEM
    title = "SYSTEM"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if n != E2:
            return
        ctx.state.system_count = SYSTEM_ROW_COUNT
        ctx.state.system_index = wrap_index(
            ctx.state.system_index, delta, SYSTEM_ROW_COUNT
        )

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1 or n != K3:
            return
        if ctx.state.system_index == SYSTEM_SHUTDOWN_ROW:
            ctx.nav.begin_shutdown(ctx.state)
            ctx.power.request_shutdown()
            ctx.state.shutdown_requested = ctx.power.shutdown_requested

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_system(fb, ctx.state)


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
        ShuttingDownScreen(),
    )
    return {s.id: s for s in screens}
