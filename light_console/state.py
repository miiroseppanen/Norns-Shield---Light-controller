from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ScreenId(str, Enum):
    BOOT = "boot"
    HOME = "home"
    MENU = "menu"
    SHOW = "show"
    WIZ = "wiz"
    NETWORK = "network"
    SYSTEM = "system"
    ABOUT = "about"


DEFAULT_FUNCTIONS = (
    "SININEN",
    "PUNAINEN",
    "AMBER",
    "VALKOINEN",
    "CHASE",
)

MENU_ITEMS = (
    ScreenId.HOME,
    ScreenId.SHOW,
    ScreenId.WIZ,
    ScreenId.NETWORK,
    ScreenId.SYSTEM,
    ScreenId.ABOUT,
)


@dataclass
class AppState:
    qlc_connected: bool = False
    qlc_project_loaded: bool = False
    startup_running: bool = True
    launchpad_connected: bool = False
    wiz_ap_up: bool = False
    wiz_expected: int = 6
    wiz_online: int = 0
    upstream_connected: bool = False
    upstream_ssid: str = ""
    dmx_net_ok: bool = False
    dmx_node_reachable: bool = False
    functions: tuple[str, ...] = DEFAULT_FUNCTIONS
    selected_index: int = 0
    active_function: str | None = None
    master_dimmer: int = 80
    bpm: int = 124
    blackout: bool = False
    special_armed: bool = False
    special_name: str = "special"
    warnings: list[str] = field(default_factory=list)
    screen: ScreenId = ScreenId.BOOT
    menu_index: int = 0
    version: str = "0.1.0"
    uptime_s: int = 0
    cpu_temp_c: float | None = None

    @property
    def selected_function(self) -> str:
        if not self.functions:
            return "—"
        return self.functions[self.selected_index % len(self.functions)]

    @property
    def qlc_lost(self) -> bool:
        return not self.qlc_connected

    @property
    def wiz_waiting(self) -> bool:
        return self.wiz_ap_up and self.wiz_online == 0

    @property
    def ready(self) -> bool:
        return self.qlc_connected and self.qlc_project_loaded and not self.startup_running

    def clamp_indices(self) -> None:
        if self.functions:
            self.selected_index %= len(self.functions)
        self.menu_index %= len(MENU_ITEMS)
        self.master_dimmer = max(0, min(100, self.master_dimmer))
        self.bpm = max(20, min(240, self.bpm))
        self.wiz_online = max(0, min(self.wiz_expected, self.wiz_online))

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
    """A plausible 'show running' snapshot for screenshots and the simulator start option."""
    state = AppState(
        qlc_connected=True,
        qlc_project_loaded=True,
        startup_running=False,
        launchpad_connected=True,
        wiz_ap_up=True,
        wiz_expected=wiz_expected,
        wiz_online=wiz_expected,
        upstream_connected=False,
        dmx_net_ok=False,
        dmx_node_reachable=False,
        selected_index=0,
        active_function="SININEN",
        master_dimmer=80,
        bpm=124,
        screen=ScreenId.HOME,
    )
    state.rebuild_warnings()
    return state
