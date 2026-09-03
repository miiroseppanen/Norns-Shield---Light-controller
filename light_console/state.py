from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class UiMode(str, Enum):
    PLAY = "play"
    MENU = "menu"


class ScreenId(str, Enum):
    """Visible surface. PLAY is the performance screen; the rest are menu destinations."""

    PLAY = "play"
    MENU = "menu"
    PARAMS = "params"
    SHOWS = "shows"
    SCENES = "scenes"
    CHASERS = "chasers"
    LOAD_SHOW = "load_show"
    OUTPUT = "output"
    SYSTEM = "system"
    SHUTDOWN = "shutdown"


PLACEHOLDER_SCENES = (
    "WASH",
    "SPOT",
    "AMBER",
    "CHASE",
)

PLACEHOLDER_CHASERS = (
    "SLOW",
    "FAST",
)

DEFAULT_FUNCTIONS = PLACEHOLDER_SCENES


@dataclass
class AppState:
    qlc_connected: bool = False
    qlc_project_loaded: bool = False
    qlc_state: str = "disconnected"
    qlc_engine: str = "5.2.2"
    qlc_host: str = "localhost"
    startup_running: bool = False
    launchpad_connected: bool = False
    wiz_ap_up: bool = False
    wiz_expected: int = 6
    wiz_online: int = 0
    upstream_connected: bool = False
    upstream_ssid: str = ""
    dmx_net_ok: bool = False
    dmx_node_reachable: bool = False
    functions: tuple[str, ...] = PLACEHOLDER_SCENES
    scenes: tuple[str, ...] = PLACEHOLDER_SCENES
    scene_function_ids: tuple[int, ...] = ()
    chasers: tuple[str, ...] = PLACEHOLDER_CHASERS
    chaser_function_ids: tuple[int, ...] = ()
    selected_index: int = 0
    scene_index: int = 0
    chaser_index: int = 0
    show_index: int = 0
    show_count: int = 0
    show_files: tuple[str, ...] = ()
    show_name: str = ""
    show_status: str = ""
    go_status: str = ""
    current_scene: str = "WASH"
    current_chaser: str = "SLOW"
    active_function: str | None = None
    master_dimmer: int = 80
    bpm: int = 124
    blackout: bool = False
    special_armed: bool = False
    special_name: str = "special"
    warnings: list[str] = field(default_factory=list)
    mode: UiMode = UiMode.PLAY
    screen: ScreenId = ScreenId.PLAY
    menu_index: int = 0
    menu_count: int = 5
    param_index: int = 0
    param_count: int = 4
    system_index: int = 0
    system_count: int = 5
    shutdown_requested: bool = False
    version: str = "0.4.0"
    hostname: str = ""
    uptime_s: int = 0
    cpu_temp_c: float | None = None

    @property
    def master(self) -> int:
        return self.master_dimmer

    @master.setter
    def master(self, value: int) -> None:
        self.master_dimmer = value

    @property
    def speed(self) -> int:
        return self.bpm

    @speed.setter
    def speed(self, value: int) -> None:
        self.bpm = value

    @property
    def selected_function(self) -> str:
        if not self.functions:
            return "—"
        return self.functions[self.selected_index % len(self.functions)]

    @property
    def qlc_lost(self) -> bool:
        return not self.qlc_connected

    @property
    def qlc_status_glyph(self) -> str:
        return "●" if self.qlc_connected else "×"

    @property
    def wiz_waiting(self) -> bool:
        return self.wiz_ap_up and self.wiz_online == 0

    @property
    def ready(self) -> bool:
        return self.qlc_connected and self.qlc_project_loaded and not self.startup_running

    def clamp_indices(self) -> None:
        if self.scenes:
            self.scene_index %= len(self.scenes)
            self.current_scene = self.scenes[self.scene_index]
        if self.chasers:
            self.chaser_index %= len(self.chasers)
            self.current_chaser = self.chasers[self.chaser_index]
        if self.show_files:
            self.show_index %= len(self.show_files)
            self.show_count = len(self.show_files)
        if self.functions:
            self.selected_index %= len(self.functions)
        self.menu_index %= max(1, self.menu_count)
        self.param_index %= max(1, self.param_count)
        self.system_index %= max(1, self.system_count)
        self.master_dimmer = max(0, min(100, self.master_dimmer))
        self.bpm = max(20, min(240, self.bpm))
        self.wiz_online = max(0, min(self.wiz_expected, self.wiz_online))
        if self.screen == ScreenId.PLAY:
            self.mode = UiMode.PLAY
        else:
            self.mode = UiMode.MENU

    def rebuild_warnings(self) -> None:
        warnings: list[str] = []
        if not self.qlc_connected:
            warnings.append("QLC LOST")
        if self.wiz_ap_up and self.wiz_online < self.wiz_expected:
            if self.wiz_online == 0:
                warnings.append(f"! WIZ 0/{self.wiz_expected} WAIT")
            else:
                warnings.append(f"! WIZ {self.wiz_online}/{self.wiz_expected}")
        if not self.launchpad_connected:
            warnings.append("MIDI LP --")
        if self.dmx_net_ok and not self.dmx_node_reachable:
            warnings.append("DMX NODE --")
        if self.blackout:
            warnings.append("BLACKOUT")
        self.warnings = warnings


def demo_live_state(wiz_expected: int = 6) -> AppState:
    """Simulator start: PLAY, QLC mocked online. Shield starts disconnected."""
    state = AppState(
        qlc_connected=True,
        qlc_project_loaded=True,
        qlc_state="connected",
        qlc_engine="5.2.2",
        qlc_host="localhost",
        startup_running=False,
        launchpad_connected=True,
        wiz_ap_up=True,
        wiz_expected=wiz_expected,
        wiz_online=wiz_expected,
        upstream_connected=False,
        dmx_net_ok=False,
        dmx_node_reachable=False,
        selected_index=0,
        scene_index=0,
        chaser_index=0,
        current_scene="WASH",
        current_chaser="SLOW",
        active_function="WASH",
        master_dimmer=80,
        bpm=124,
        mode=UiMode.PLAY,
        screen=ScreenId.PLAY,
        version="0.4.0",
    )
    state.rebuild_warnings()
    return state
