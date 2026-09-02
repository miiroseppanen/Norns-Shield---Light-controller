"""Global Norns UI shell: K1 PLAY↔MENU, menu stack, dispatch to the active screen.

Show functions are not here — screens talk to parameters, parameters mutate AppState.
"""

from __future__ import annotations

from light_console.display.framebuffer import Framebuffer
from light_console.hardware.events import K1, K2
from light_console.power import MockPowerService, PowerService
from light_console.state import AppState, ScreenId
from light_console.ui.nav import Navigation
from light_console.ui.pages import SYSTEM_ROW_COUNT, Screen, ScreenContext, build_screens
from light_console.ui.params import Params, bind_console_params


class NornsUIShell:
    def __init__(
        self,
        state: AppState,
        nav: Navigation | None = None,
        params: Params | None = None,
        power: PowerService | None = None,
    ) -> None:
        self.state = state
        self.nav = nav or Navigation()
        self.params = params or bind_console_params(state)
        self.power = power or MockPowerService()
        self.screens = build_screens()
        state.menu_count = len(self.nav.current_items())
        state.param_count = len(self.params)
        state.system_count = SYSTEM_ROW_COUNT
        self.params.sync_index_to_state(state)

    def ctx(self) -> ScreenContext:
        return ScreenContext(state=self.state, nav=self.nav, params=self.params, power=self.power)

    def active_screen(self) -> Screen:
        return self.screens[self.state.screen]

    def enc(self, n: int, delta: int) -> None:
        self.active_screen().enc(n, delta, self.ctx())
        self.params.store_index(self.state)

    def key(self, n: int, z: int) -> None:
        if z != 1:
            return
        if n == K1:
            if self.state.screen == ScreenId.PLAY:
                self.nav.enter_menu(self.state)
            else:
                self.nav.go_play(self.state)
            return
        if n == K2 and self.state.screen not in (ScreenId.PLAY, ScreenId.MENU):
            self.nav.back(self.state)
            return
        self.active_screen().key(n, z, self.ctx())
        self.params.store_index(self.state)

    def redraw(self, fb: Framebuffer) -> None:
        fb.clear()
        self.active_screen().redraw(fb, self.ctx())
