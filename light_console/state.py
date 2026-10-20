from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from light_console.output.fixtures import PatchedFixture
from light_console.output.network import NetIface
from light_console.output.nodes import KNOWN_ARTNET_NODES, ArtNetNode
from light_console.output.routing import OutputRoute
from light_console.ui.vocab import FAILED, NETWORK, RUNNING, STARTING, STOPPED
from light_console.version import VERSION
from light_console.wiz.view import WizDeviceRow


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
    WIZ_CONTROL = "wiz_control"
    WIZ_DEVICES = "wiz_devices"
    WIZ_INFO = "wiz_info"
    VERSION = "version"
    SHUTDOWN_CONFIRM = "shutdown_confirm"
    RESTART_CONFIRM = "restart_confirm"
    STARTING_UP = "starting_up"
    SHUTTING_DOWN = "shutting_down"
    RESTARTING = "restarting"


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
    qlc_desired: bool = True
    qlc_observed: str = STOPPED
    network_mode: str = "network"
    network_mode_observed: str = NETWORK
    network_mode_busy: bool = False
    startup_running: bool = False
    launchpad_connected: bool = False
    wiz_enabled: bool = False
    wiz_ap_up: bool = False
    wiz_ap_state: str = "DOWN"
    wiz_bridge_state: str = "STOPPED"
    wiz_tx_armed: bool = False
    wiz_lifecycle_busy: bool = False
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
    show_ids: tuple[str, ...] = ()
    show_name: str = ""
    show_status: str = ""
    show_open_id: str = ""
    show_busy: bool = False
    go_status: str = ""
    startup_status: str = ""
    output_mode: str = "SAFE"
    network_ifaces: tuple[NetIface, ...] = ()
    output_routes: tuple[OutputRoute, ...] = ()
    runtime_routes: tuple[OutputRoute, ...] = ()
    artnet_nodes: tuple[ArtNetNode, ...] = KNOWN_ARTNET_NODES
    output_page: int = 0
    output_focus: int = 0
    output_detail: bool = False
    route_busy: bool = False
    route_op: str = ""
    qlc_universes: tuple[int, ...] = ()
    output_universe: int = 1
    scroll_offset: int = 0
    dmx_by_universe: dict[int, tuple[int, ...]] = field(default_factory=dict)
    dmx_ready: bool = False
    fixtures: tuple[PatchedFixture, ...] = ()
    dmx_seen_ids: set[int] = field(default_factory=set)
    wiz_tx_active: bool = False
    ui_now: float = 0.0
    current_scene: str = "WASH"
    current_chaser: str = "SLOW"
    active_function: str | None = None
    master_dimmer: int = 100
    saturation: int = 100
    hue_shift: int = 0
    bpm: int = 124
    blackout: bool = False
    special_armed: bool = False
    special_name: str = "special"
    warnings: list[str] = field(default_factory=list)
    mode: UiMode = UiMode.PLAY
    screen: ScreenId = ScreenId.PLAY
    menu_index: int = 0
    menu_count: int = 6
    menu_title: str = "MENU"
    menu_labels: tuple[str, ...] = ()
    param_index: int = 0
    param_count: int = 6
    system_index: int = 0
    system_count: int = 4
    wiz_control_index: int = 0
    wiz_control_count: int = 2
    wiz_discover_until: float = 0.0
    wiz_device_index: int = 0
    wiz_device_count: int = 0
    wiz_device_detail: bool = False
    wiz_prompt: str = ""
    wiz_prompt_mac: str = ""
    wiz_prompt_slot: int = 0
    wiz_prompt_target: int = 1
    wiz_prompt_error: str = ""
    wiz_prompt_swap: str = ""
    wiz_action_index: int = 0
    wiz_device_rows: tuple[WizDeviceRow, ...] = ()
    wiz_identify_mac: str = ""
    wiz_devices_note: str = ""
    wiz_map_extended: bool = False
    wiz_bridge_available: bool = False
    shutdown_requested: bool = False
    restart_requested: bool = False
    version: str = VERSION
    build_revision: str = ""
    hostname: str = ""
    uptime_s: int = 0
    marquee_key: str = ""
    marquee_t0: float = 0.0
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
        return self.functions[max(0, min(len(self.functions) - 1, self.selected_index))]

    @property
    def qlc_lost(self) -> bool:
        return not self.qlc_connected

    @property
    def qlc_status_glyph(self) -> str:
        return "●" if self.qlc_connected else "×"

    @property
    def wiz_waiting(self) -> bool:
        return bool(
            self.wiz_enabled
            and (
                self.wiz_lifecycle_busy
                or self.wiz_ap_state == STARTING
                or self.wiz_bridge_state == STARTING
            )
        )

    @property
    def ready(self) -> bool:
        return self.qlc_connected and self.qlc_project_loaded and not self.startup_running

    def host_stopping(self) -> bool:
        return self.shutdown_requested or self.restart_requested

    def input_locked(self) -> bool:
        return self.host_stopping() or self.screen in {
            ScreenId.STARTING_UP,
            ScreenId.SHUTTING_DOWN,
            ScreenId.RESTARTING,
        }

    def clamp_indices(self) -> None:
        from light_console.controls.encoders import bound_index

        if self.scenes:
            self.scene_index = bound_index(self.scene_index, len(self.scenes))
            self.current_scene = self.scenes[self.scene_index]
        if self.chasers:
            self.chaser_index = bound_index(self.chaser_index, len(self.chasers))
            self.current_chaser = self.chasers[self.chaser_index]
        if self.show_ids:
            self.show_index = bound_index(self.show_index, len(self.show_ids))
            self.show_count = len(self.show_ids)
        elif self.show_files:
            self.show_index = bound_index(self.show_index, len(self.show_files))
            self.show_count = len(self.show_files)
        if self.functions:
            self.selected_index = bound_index(self.selected_index, len(self.functions))
        self.menu_index = bound_index(self.menu_index, max(1, self.menu_count))
        self.param_index = bound_index(self.param_index, max(1, self.param_count))
        self.system_index = bound_index(self.system_index, max(1, self.system_count))
        self.wiz_control_index = bound_index(
            self.wiz_control_index, max(1, self.wiz_control_count)
        )
        self.wiz_device_count = len(self.wiz_device_rows)
        self.wiz_device_index = bound_index(self.wiz_device_index, self.wiz_device_count)
        self.master_dimmer = max(0, min(100, self.master_dimmer))
        self.saturation = max(0, min(200, self.saturation))
        from light_console.live_color import wrap_hue_deg

        self.hue_shift = wrap_hue_deg(self.hue_shift)
        self.bpm = max(20, min(240, self.bpm))
        self.wiz_online = max(0, min(self.wiz_expected, self.wiz_online))
        if self.qlc_universes and self.output_universe not in self.qlc_universes:
            self.output_universe = self.qlc_universes[0]
        if self.screen == ScreenId.PLAY:
            self.mode = UiMode.PLAY
        else:
            self.mode = UiMode.MENU

    def reset_list_window(self) -> None:
        self.scroll_offset = 0
        self.output_focus = 0
        self.output_detail = False
        self.wiz_device_index = 0
        self.wiz_device_detail = False
        self.wiz_prompt = ""
        self.wiz_action_index = 0
        self.marquee_key = ""
        self.marquee_t0 = 0.0

    def rebuild_warnings(self) -> None:
        warnings: list[str] = []
        if self.qlc_desired:
            if self.qlc_observed == FAILED:
                warnings.append("QLC FAILED")
            elif self.qlc_observed != STARTING and not self.qlc_connected:
                warnings.append("QLC LOST")
        if self.wiz_enabled:
            if self.wiz_ap_state == FAILED:
                warnings.append("WIZ AP FAILED")
            elif self.wiz_bridge_state == FAILED:
                warnings.append("WIZ BRIDGE FAILED")
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
        qlc_desired=True,
        qlc_observed=RUNNING,
        startup_running=False,
        launchpad_connected=True,
        wiz_enabled=False,
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
        master_dimmer=100,
        saturation=100,
        hue_shift=0,
        bpm=124,
        mode=UiMode.PLAY,
        screen=ScreenId.PLAY,
        version=VERSION,
    )
    state.rebuild_warnings()
    return state
