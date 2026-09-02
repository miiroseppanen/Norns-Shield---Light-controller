"""Norns-like screens: enc(n, delta), key(n, z), redraw(fb).

n is E1/E2/E3 or K1/K2/K3 (1,2,3). z is 1 down/tap, 0 up.
K1 PLAY↔MENU is handled by NornsUIShell, not these screens.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass

from light_console.controls.encoders import wrap_index
from light_console.display.framebuffer import Framebuffer
from light_console.display.screens import (
    draw_menu,
    draw_output,
    draw_params,
    draw_play,
    draw_scenes,
    draw_shutdown,
    draw_system,
)
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


class Screen(ABC):
    id: ScreenId
    title: str = ""

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        del n, delta, ctx

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        del n, z, ctx

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        del fb, ctx


class PlayScreen(Screen):
    id = ScreenId.PLAY
    title = "PLAY"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if n == E1:
            ctx.params["master"].delta(delta)
        elif n == E2:
            ctx.params["scene"].delta(delta)
        elif n == E3:
            ctx.params["speed"].delta(delta)

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1:
            return
        if n == K2:
            return
        if n == K3:
            ctx.state.active_function = ctx.state.current_scene

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_play(fb, ctx.state)


class MenuScreen(Screen):
    id = ScreenId.MENU
    title = "MENU"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if n != E2:
            return
        items = ctx.nav.current_items()
        if not items:
            return
        ctx.state.menu_index = wrap_index(ctx.state.menu_index, delta, len(items))
        ctx.state.menu_count = len(items)

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1:
            return
        if n == K3:
            ctx.nav.forward(ctx.state)
        elif n == K2:
            ctx.nav.back(ctx.state)

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


class ScenesScreen(Screen):
    id = ScreenId.SCENES
    title = "SCENES"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        if n == E2 and ctx.state.scenes:
            ctx.state.scene_index = wrap_index(
                ctx.state.scene_index, delta, len(ctx.state.scenes)
            )

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1 or n != K3:
            return
        if ctx.state.scenes:
            ctx.params["scene"].set(ctx.state.scenes[ctx.state.scene_index])

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_scenes(fb, ctx.state)


class OutputScreen(Screen):
    id = ScreenId.OUTPUT
    title = "OUTPUT"

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
            ctx.nav.open_shutdown_confirm(ctx.state)

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_system(fb, ctx.state)


class ShutdownScreen(Screen):
    id = ScreenId.SHUTDOWN
    title = "SHUTDOWN"

    def enc(self, n: int, delta: int, ctx: ScreenContext) -> None:
        del n, delta, ctx

    def key(self, n: int, z: int, ctx: ScreenContext) -> None:
        if z != 1:
            return
        if n == K3:
            accepted = ctx.power.request_shutdown()
            ctx.state.shutdown_requested = ctx.power.shutdown_requested
            del accepted
        elif n == K2:
            ctx.nav.back(ctx.state)

    def redraw(self, fb: Framebuffer, ctx: ScreenContext) -> None:
        draw_shutdown(fb, ctx.state)


def build_screens() -> dict[ScreenId, Screen]:
    screens: tuple[Screen, ...] = (
        PlayScreen(),
        MenuScreen(),
        ParamsScreen(),
        ScenesScreen(),
        OutputScreen(),
        SystemScreen(),
        ShutdownScreen(),
    )
    return {s.id: s for s in screens}
