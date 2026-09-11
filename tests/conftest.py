from __future__ import annotations

from pathlib import Path

from light_console.config import load_config
from light_console.hardware.headless import HeadlessBackend
from light_console.qlc.client import MockQLCClient
from light_console.qlc.functions import QlcFunction
from light_console.state import AppState, ScreenId
from light_console.ui.controller import Controller


def make_controller(
    shows_dir: Path | None = None,
    prefs_path: Path | None = None,
    **state_kw,
) -> Controller:
    config = load_config()
    config.display.fps = 1000
    defaults = dict(
        qlc_connected=True,
        qlc_project_loaded=True,
        qlc_desired=True,
        qlc_observed="RUNNING",
        network_mode="network",
        network_mode_observed="NETWORK",
        startup_running=False,
        wiz_enabled=False,
        wiz_expected=6,
        wiz_online=6,
        wiz_ap_up=True,
        launchpad_connected=True,
        screen=ScreenId.PLAY,
    )
    defaults.update(state_kw)
    state = AppState(**defaults)
    funcs = [
        QlcFunction(i, name, "Scene") for i, name in enumerate(state.scenes)
    ]
    ch_base = 100
    funcs.extend(
        QlcFunction(ch_base + i, name, "Chaser")
        for i, name in enumerate(state.chasers)
    )
    state.scene_function_ids = tuple(range(len(state.scenes)))
    state.chaser_function_ids = tuple(ch_base + i for i in range(len(state.chasers)))
    qlc = MockQLCClient(state.functions)
    qlc.replace_functions(funcs)
    qlc.simulate_link(True)
    hw = HeadlessBackend()
    return Controller(config, state, hw, qlc, shows_dir=shows_dir, prefs_path=prefs_path)
