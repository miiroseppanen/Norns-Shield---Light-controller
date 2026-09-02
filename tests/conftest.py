from __future__ import annotations

from light_console.config import load_config
from light_console.hardware.headless import HeadlessBackend
from light_console.qlc.client import MockQLCClient
from light_console.state import AppState, ScreenId
from light_console.ui.controller import Controller


def make_controller(**state_kw) -> Controller:
    config = load_config()
    config.display.fps = 1000
    defaults = dict(
        qlc_connected=True,
        qlc_project_loaded=True,
        startup_running=False,
        wiz_expected=6,
        wiz_online=6,
        wiz_ap_up=True,
        launchpad_connected=True,
        screen=ScreenId.PLAY,
    )
    defaults.update(state_kw)
    state = AppState(**defaults)
    qlc = MockQLCClient(state.functions)
    qlc.simulate_link(True)
    hw = HeadlessBackend()
    return Controller(config, state, hw, qlc)
