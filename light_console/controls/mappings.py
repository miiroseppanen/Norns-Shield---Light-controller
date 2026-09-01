from __future__ import annotations

from light_console.config import ControlsConfig
from light_console.hardware.events import ButtonEvent, EncoderEvent
from light_console.qlc.client import QLCClient
from light_console.state import MENU_ITEMS, AppState, ScreenId
from light_console.controls.encoders import apply_encoder_delta, wrap_index


class ControlMapper:
    def __init__(self, controls: ControlsConfig) -> None:
        self.controls = controls
        self._encoders = {
            1: controls.encoder1,
            2: controls.encoder2,
            3: controls.encoder3,
        }
        self._keys = {
            1: controls.key1,
            2: controls.key2,
            3: controls.key3,
        }

    def handle_encoder(self, event: EncoderEvent, state: AppState, qlc: QLCClient) -> None:
        if state.screen == ScreenId.MENU and event.encoder == 2:
            state.menu_index = wrap_index(state.menu_index, event.delta, len(MENU_ITEMS))
            return
        if state.screen not in (ScreenId.HOME, ScreenId.SHOW, ScreenId.BOOT) and event.encoder == 2:
            # On subpages, E2 still selects functions so the operator is never stuck.
            pass
        action = self._encoders[event.encoder]
        self._run_encoder(action, event.delta, state, qlc)

    def handle_button(self, event: ButtonEvent, state: AppState, qlc: QLCClient) -> None:
        if event.action == "release":
            return
        mapping = self._keys[event.button]
        action = mapping.long if event.action == "long_press" else mapping.short
        self._run_action(action, state, qlc)

    def _run_encoder(self, action: str, delta: int, state: AppState, qlc: QLCClient) -> None:
        if action == "master_dimmer":
            state.master_dimmer = apply_encoder_delta(state.master_dimmer, delta, 0, 100)
            if state.qlc_connected:
                qlc.set_grand_master(int(state.master_dimmer * 255 / 100))
        elif action == "select":
            state.selected_index = wrap_index(state.selected_index, delta, len(state.functions))
        elif action == "speed":
            state.bpm = apply_encoder_delta(state.bpm, delta, 20, 240)
            if state.qlc_connected:
                qlc.set_speed(state.bpm)
        # unknown encoder actions are ignored (configurable YAML)

    def _run_action(self, action: str, state: AppState, qlc: QLCClient) -> None:
        if action in ("none", "", "noop"):
            return
        if action == "blackout":
            _toggle_blackout(state, qlc)
        elif action == "all_off":
            _all_off(state, qlc)
        elif action == "go":
            if state.screen == ScreenId.MENU:
                _menu_activate(state)
            else:
                _go(state, qlc)
        elif action == "home":
            state.screen = ScreenId.HOME if state.ready else ScreenId.BOOT
        elif action == "menu":
            state.screen = ScreenId.MENU
        elif action == "special":
            state.special_armed = not state.special_armed
        elif action == "select":
            state.selected_index = wrap_index(state.selected_index, 1, len(state.functions))


def _toggle_blackout(state: AppState, qlc: QLCClient) -> None:
    state.blackout = not state.blackout
    if state.qlc_connected:
        qlc.set_blackout(state.blackout)


def _all_off(state: AppState, qlc: QLCClient) -> None:
    state.blackout = True
    state.active_function = None
    if state.qlc_connected:
        qlc.all_off()
        qlc.set_blackout(True)


def _go(state: AppState, qlc: QLCClient) -> None:
    name = state.selected_function
    if state.qlc_connected:
        qlc.start_function_by_name(name)
        qlc.set_blackout(False)
    state.active_function = name
    state.blackout = False


def _menu_activate(state: AppState) -> None:
    target = MENU_ITEMS[state.menu_index]
    if target == ScreenId.HOME:
        state.screen = ScreenId.HOME if state.ready else ScreenId.BOOT
    else:
        state.screen = target
