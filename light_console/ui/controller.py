from __future__ import annotations

import logging
import socket
import threading
import time
from pathlib import Path

from light_console.config import AppConfig
from light_console.controls.buttons import ButtonTracker
from light_console.controls.encoders import fold_encoder_stream, is_nav_encoder, nav_steps, bound_index
from light_console.display.lifecycle import (
    consume_starting_mark,
    hold_starting_up_visible,
)
from light_console.display.renderer import Renderer
from light_console.display.screens import qlc_output_label
from light_console.hardware.base import HardwareBackend
from light_console.hardware.events import ButtonEvent, EncoderEvent, HardwareEvent, SimCommandEvent
from light_console.output.fixtures import parse_fixtures_file, update_seen
from light_console.output.observe import LiveDiagnostics
from light_console.output.routing import merge_routes, parse_output_routes_file, routing_mode
from light_console.output.universe_map import parse_qlc_universes_file
from light_console.output.netmode import (
    MockNetworkModeService,
    NetworkModeService,
    oled_mode_word,
    parse_network_mode,
)
from light_console.output.wiz_lifecycle import (
    LinuxWizLifecycleService,
    MockWizLifecycleService,
    WizLifecycleService,
)
from light_console.output.apply import (
    APPLYING,
    RouteApplyError,
    apply_managed_target,
)
from light_console.output.workspace_switch import (
    WorkspaceSwitchError,
    switch_workspace,
)
from light_console.output.targets import (
    APPLYABLE_TARGETS,
    TargetId,
    TargetUnavailable,
    apply_plan_for,
    detect_target,
    icmp_reachable,
    lan_line_uid,
    read_arp_table,
    resolve_apply_ipv4,
)
from light_console.power import MockPowerService, PowerService
from light_console.prefs import OperatorPrefs, load_prefs, save_prefs
from light_console.qlc.binding import QlcBinding
from light_console.qlc.client import QLCClient
from light_console.qlc.functions import QlcFunction
from light_console.qlc.launch import RUNTIME_MASTER
from light_console.qlc.runtime import (
    STARTUP_NAME,
    apply_live_startup_runtime,
    function_runtime_available,
    invalidate_function_runtime,
    parse_startup_status_file,
)
from light_console.qlc.service import LinuxQlcService, MockQlcService, QlcService
from light_console.qxw import QxwError
from light_console.ui.vocab import FAILED, LOAD, OPEN, READY, SWITCHING
from light_console.shows import ShowCatalog
from light_console.workspaces import WorkspaceCatalog
from light_console.showdef import ShowDefinition
from light_console.state import AppState, ScreenId, UiMode
from light_console.status.dmx import apply_dmx
from light_console.status.midi import apply_launchpad
from light_console.status.network import apply_upstream, apply_wiz_ap
from light_console.status.wiz import apply_wiz_observed, bump_wiz
from light_console.ui.nav import Navigation
from light_console.ui.pages import SYSTEM_ROW_COUNT, WIZ_CONTROL_ROW_COUNT, WIZ_DISCOVER_HOLD_S
from light_console.ui.params import bind_console_params
from light_console.ui.shell import NornsUIShell
from light_console.wiz.device_map import (
    WizDeviceMap,
    WizMapCorruptError,
    WizMapError,
    WizMapValidationError,
    load_map,
    parse_legacy_file,
    save_map,
)
from light_console.wiz.edit import (
    add_device,
    lowest_unused_slot,
    move_device,
    set_enabled,
    swap_devices,
)
from light_console.wiz.observe import (
    WizObservedDevice,
    empty_observed_snapshot,
    read_observed_status,
)
from light_console.wiz.view import ROW_NEW, join_wiz_devices

LOG = logging.getLogger("light-console")
STATUS_PATH = Path("/tmp/light-console.status")
STARTUP_STATUS_PATH = Path("/tmp/qlc-startup.status")


def _read_cpu_temp() -> float | None:
    path = Path("/sys/class/thermal/thermal_zone0/temp")
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip()) / 1000.0
    except (OSError, ValueError):
        return None


class Controller:
    def __init__(
        self,
        config: AppConfig,
        state: AppState,
        hardware: HardwareBackend,
        qlc: QLCClient,
        power: PowerService | None = None,
        shows_dir: Path | None = None,
        prefs_path: Path | None = None,
        qlc_service: QlcService | None = None,
        net_service: NetworkModeService | None = None,
        wiz_service: WizLifecycleService | None = None,
        live_diag: bool | None = None,
        wiz_map_path: Path | None = None,
        wiz_observed_path: Path | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.hardware = hardware
        self.qlc = qlc
        self.power = power or MockPowerService()
        self._prefs_path = prefs_path
        if prefs_path is not None:
            prefs = load_prefs(prefs_path)
            self.state.wiz_enabled = prefs.wiz_enabled
            self.state.qlc_desired = prefs.qlc_desired
            self.state.network_mode = parse_network_mode(prefs.network_mode)
        else:
            prefs = OperatorPrefs(
                wiz_enabled=self.state.wiz_enabled,
                qlc_desired=self.state.qlc_desired,
                network_mode=parse_network_mode(self.state.network_mode),
            )
        observed = "RUNNING" if self.state.qlc_connected else "STOPPED"
        self.qlc_service = qlc_service or MockQlcService(
            desired_on=prefs.qlc_desired,
            observed=self.state.qlc_observed if self.state.qlc_observed else observed,
        )
        self.qlc_service.desired_on = prefs.qlc_desired
        if isinstance(self.qlc_service, LinuxQlcService) and not prefs.qlc_desired:
            self.qlc_service.set_desired(False)
        self.state.qlc_desired = self.qlc_service.desired_on
        self.state.qlc_observed = self.qlc_service.poll()
        self.net_service = net_service or MockNetworkModeService(
            mode=parse_network_mode(prefs.network_mode)
        )
        self.state.network_mode = self.net_service.mode
        self.state.network_mode_observed = self.net_service.poll()
        self.state.network_mode_busy = self.net_service.busy
        self.wiz_service = wiz_service or MockWizLifecycleService(
            desired=bool(prefs.wiz_enabled)
        )
        if isinstance(self.wiz_service, LinuxWizLifecycleService):
            self.wiz_service.status_path = STATUS_PATH
            self.wiz_service.set_desired(bool(prefs.wiz_enabled))
        self._sync_wiz_runtime()
        self.nav = Navigation()
        self.params = bind_console_params(state)
        self.binding = QlcBinding(qlc)
        self.catalog = ShowCatalog(shows_dir) if shows_dir is not None else None
        self.workspaces = WorkspaceCatalog(shows_dir) if shows_dir is not None else None
        self.show_load = None
        self._applied_show: str | None = None
        self.shell = NornsUIShell(
            state, nav=self.nav, params=self.params, power=self.power, actions=self
        )
        self.buttons = ButtonTracker(long_press_s=config.controls.long_press_ms / 1000.0)
        self.renderer = Renderer(config.display.width, config.display.height)
        self._t0 = time.monotonic()
        self._last_draw = 0.0
        self.running = True
        self._status_body = ""
        self.workspace_path = (shows_dir / "master.qxw") if shows_dir is not None else RUNTIME_MASTER
        self._diag: LiveDiagnostics | None = None
        self._dmx_t = -2.0
        self._dmx_cursor = 0
        self._startup_status_t = -1.0
        self._route_mtime: float | None = None
        self._route_lock = threading.Lock()
        self._route_thread: threading.Thread | None = None
        self._route_ping = icmp_reachable
        self._route_arp: dict[str, str] | None = None
        self.state.system_count = SYSTEM_ROW_COUNT
        self.state.wiz_control_count = WIZ_CONTROL_ROW_COUNT
        self._wiz_map_path = wiz_map_path
        self._wiz_observed_path = wiz_observed_path
        self._wiz_observed_mtime: float | None = None
        self._wiz_map_mtime: float | None = None
        self._wiz_map: WizDeviceMap | None = None
        self._wiz_map_error = ""
        self._wiz_observations: tuple[WizObservedDevice, ...] = ()
        self._load_wiz_cache()
        self._note_wiz_map_mtime()
        self._poll_wiz_observed()
        self._sync_wiz_view()
        if not self.state.hostname:
            try:
                self.state.hostname = socket.gethostname()
            except OSError:
                self.state.hostname = ""
        self.state.qlc_engine = config.qlc.engine_version
        self.state.qlc_host = qlc.host_label()
        self._load_routes()
        self._refresh_show_state(force=True)
        self._refresh_workspace_state()
        if live_diag is None:
            live_diag = not self._is_headless()
        if live_diag:
            try:
                from light_console.machine import load_machine_profile

                usb_id = load_machine_profile().launchpad.usb_id
            except Exception:
                usb_id = "1235:0036"
            self._diag = LiveDiagnostics(
                usb_id=usb_id,
            )
        self.reveal_normal_ui()

    def reveal_normal_ui(self) -> None:
        """Leave appliance STARTING UP once this process can render a real page."""
        if self.state.host_stopping() or self.state.screen in {
            ScreenId.SHUTTING_DOWN,
            ScreenId.RESTARTING,
        }:
            return
        if self.state.screen != ScreenId.STARTING_UP:
            return
        t0 = getattr(self.hardware, "starting_up_at", None)
        marked = consume_starting_mark()
        slept = hold_starting_up_visible(t0, enabled=marked)
        elapsed = (time.monotonic() - t0) if t0 is not None else 0.0
        if marked:
            LOG.info(
                "STARTING UP reveal after %.2fs (held %.2fs)",
                elapsed,
                slept,
            )
        self.state.mode = UiMode.PLAY
        self.state.screen = ScreenId.PLAY
        self.state.reset_list_window()

    def begin_appliance_shutdown(self) -> None:
        """Paint SHUTTING DOWN, flush OLED, then halt. Not used for service restarts."""
        if self.state.host_stopping():
            return
        self.nav.begin_shutdown(self.state)
        self._flush_lifecycle_frame("SHUTTING DOWN")
        self.power.request_shutdown()
        self.state.shutdown_requested = self.power.shutdown_requested

    def begin_appliance_restart(self) -> None:
        """Paint RESTARTING, flush OLED, then reboot. Not used for service restarts."""
        if self.state.host_stopping():
            return
        self.nav.begin_restart(self.state)
        self._flush_lifecycle_frame("RESTARTING")
        self.power.request_restart()
        self.state.restart_requested = self.power.restart_requested

    def _flush_lifecycle_frame(self, label: str) -> None:
        self._write_status()
        try:
            self.renderer.force_dirty()
            self.renderer.render(self.state)
            self.hardware.set_display(self.renderer.fb)
            self._last_draw = time.monotonic()
        except Exception:
            LOG.exception("%s flush failed", label)

    def handle_event(self, event: HardwareEvent, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if isinstance(event, SimCommandEvent):
            self._sim(event)
        elif isinstance(event, EncoderEvent):
            self.shell.enc(event.encoder, event.delta)
        elif isinstance(event, ButtonEvent):
            if event.action == "press":
                cooked = self.buttons.on_hardware_press(event.button, now)
                if cooked:
                    for c in cooked:
                        self._dispatch_key(c)
            elif event.action == "release":
                for c in self.buttons.on_hardware_release(event.button, now):
                    self._dispatch_key(c)
            elif event.action == "long_press":
                self._dispatch_key(event)
        self._finish()

    def _dispatch_key(self, event: ButtonEvent) -> None:
        if event.action == "release":
            self.shell.key(event.button, 0)
        else:
            self.shell.key(event.button, 1)

    def inject_cooked(self, event: HardwareEvent) -> None:
        """Tests: already short/long ButtonEvents, skip debounce tracker."""
        if isinstance(event, ButtonEvent):
            self._dispatch_key(event)
        elif isinstance(event, EncoderEvent):
            self.shell.enc(event.encoder, event.delta)
        elif isinstance(event, SimCommandEvent):
            self._sim(event)
        self._finish()

    def tick(self, now: float | None = None) -> None:
        started = time.monotonic()
        now = started if now is None else now
        self.state.ui_now = now
        self.state.uptime_s = int(now - self._t0)
        temp = _read_cpu_temp()
        if temp is not None:
            self.state.cpu_temp_c = temp
        for ev in fold_encoder_stream(self.hardware.read_events()):
            if isinstance(ev, EncoderEvent) and is_nav_encoder(self.state.screen, ev.encoder):
                stepped = nav_steps(ev.delta)
                if stepped == 0:
                    continue
                ev = EncoderEvent(encoder=ev.encoder, delta=stepped)
            self.handle_event(ev, now)
        for ev in self.buttons.poll(now):
            self._dispatch_key(ev)
        try:
            self.qlc.pump(now)
        except Exception:
            LOG.exception("QLC pump failed; UI continues")
        self._refresh_diagnostics(now)
        self._finish()
        interval = 1.0 / max(1, self.config.display.fps)
        if now - self._last_draw >= interval:
            self.renderer.render(self.state)
            if self.renderer.changed():
                self.hardware.set_display(self.renderer.fb)
            self._last_draw = now
        elapsed = time.monotonic() - started
        if elapsed > 0.12:
            LOG.warning("slow tick %.0fms", elapsed * 1000.0)

    def _is_headless(self) -> bool:
        return type(self.hardware).__name__ == "HeadlessBackend"

    def _load_routes(self) -> None:
        path = self.workspace_path
        if not path.is_file():
            return
        try:
            mtime = path.stat().st_mtime
            if mtime == self._route_mtime:
                return
            routes = parse_output_routes_file(path)
            self._route_mtime = mtime
            self.state.output_routes = routes
            try:
                self.state.qlc_universes = parse_qlc_universes_file(path)
            except (OSError, QxwError):
                LOG.debug("universe list parse failed", exc_info=True)
            try:
                self.state.fixtures = parse_fixtures_file(path)
            except (OSError, QxwError):
                LOG.debug("fixture parse failed", exc_info=True)
            self._sync_output_mode()
        except (OSError, QxwError):
            LOG.debug("routing parse failed", exc_info=True)

    def _sync_output_mode(self) -> None:
        resolved = merge_routes(
            self.state.output_routes,
            self.state.runtime_routes,
            self.state.network_ifaces,
        )
        self.state.output_mode = routing_mode(resolved)

    def _refresh_diagnostics(self, now: float) -> None:
        if self._diag is not None:
            ifaces, launchpad = self._diag.snapshot()
            self.state.network_ifaces = ifaces
            apply_launchpad(self.state, launchpad)
        self._load_routes()
        self._sync_output_mode()
        self.state.qlc_observed = self.qlc_service.poll()
        if not self.state.route_busy:
            self.state.qlc_desired = self.qlc_service.desired_on
        self._sync_network_mode()
        self._sync_wiz_runtime()
        if self.state.dmx_by_universe and self.state.fixtures:
            update_seen(self.state.fixtures, self.state.dmx_by_universe, self.state.dmx_seen_ids)
        if not self.qlc.connected():
            if self.state.dmx_ready or self.state.dmx_by_universe:
                self.qlc.clear_dmx()
                self.state.dmx_by_universe = {}
                self.state.dmx_ready = False
            return
        unis = [route.qlc_universe for route in self.state.output_routes] or [1]
        if now - self._dmx_t >= 1.5:
            uni = unis[self._dmx_cursor % len(unis)]
            self._dmx_cursor += 1
            try:
                self.qlc.request_channels_values(uni, 1, 512)
            except Exception:
                LOG.debug("dmx request failed", exc_info=True)
            self._dmx_t = now
        for uni in unis:
            snap = self.qlc.dmx_snapshot(uni - 1)
            if snap is not None:
                self.state.dmx_by_universe[uni - 1] = snap
                self.state.dmx_ready = True
        if self.state.dmx_by_universe and self.state.fixtures:
            update_seen(self.state.fixtures, self.state.dmx_by_universe, self.state.dmx_seen_ids)

    def apply_route_target(self, target_id: str) -> None:
        try:
            target = TargetId(target_id)
        except ValueError:
            return
        if target not in APPLYABLE_TARGETS:
            return
        with self._route_lock:
            if self.state.route_busy or self.state.show_busy:
                return
            self.state.route_busy = True
        self.state.route_op = APPLYING
        worker = threading.Thread(
            target=self._route_worker,
            args=(target,),
            daemon=True,
            name="qlc-route",
        )
        self._route_thread = worker
        worker.start()

    def _route_worker(self, target: TargetId) -> None:
        def progress(stage: str) -> None:
            self.state.route_op = stage

        failed = False
        try:
            arp = self._route_arp if self._route_arp is not None else read_arp_table()
            ip = resolve_apply_ipv4(
                target,
                nodes=self.state.artnet_nodes,
                arp=arp,
                ping=self._route_ping,
            )
            ifaces = {iface.name: iface.ipv4 for iface in self.state.network_ifaces}
            plan = apply_plan_for(target, ip, lan_uid=lan_line_uid(ifaces))
            already = detect_target(
                self.state.output_routes,
                nodes=self.state.artnet_nodes,
                arp=arp,
            )
            apply_managed_target(
                self.workspace_path,
                target,
                plan,
                qlc_service=self.qlc_service,
                progress=progress,
                connected=self.qlc.connected,
                already=already,
            )
            self._route_mtime = None
            self._load_routes()
        except (TargetUnavailable, RouteApplyError, OSError, UnicodeError) as exc:
            LOG.warning("route apply failed: %s", exc)
            failed = True
            self.state.route_op = FAILED
        finally:
            self.state.route_busy = False
            if not failed:
                self.state.route_op = ""

    def set_qlc_desired(self, on: bool) -> None:
        self.qlc_service.set_desired(on)
        self.state.qlc_desired = on
        self.state.qlc_observed = self.qlc_service.observed
        if not on:
            self.qlc.clear_function_runtime()
            invalidate_function_runtime(self.state)
        self._save_prefs()

    def set_wiz_enabled(self, on: bool) -> None:
        if self.wiz_service.busy or self.state.wiz_lifecycle_busy:
            return
        if not self.wiz_service.set_desired(on):
            return
        self.state.wiz_enabled = on
        if not on:
            self.state.wiz_discover_until = 0.0
        self._save_prefs()
        self._sync_wiz_runtime()
        self._sync_wiz_view()

    def request_wiz_discover(self) -> None:
        """Pulse discover=1 on the status file. Light Console never sends WiZ UDP."""
        if self.state.host_stopping() or self.state.wiz_lifecycle_busy:
            return
        if not self.state.wiz_tx_armed:
            return
        self.state.wiz_discover_until = self.state.ui_now + WIZ_DISCOVER_HOLD_S

    def set_network_mode(self, mode: str) -> None:
        if self.net_service.busy or self.state.network_mode_busy:
            return
        target = parse_network_mode(mode)
        if not self.net_service.set_desired(target):
            return
        self.state.network_mode_busy = self.net_service.busy
        self.state.network_mode_observed = self.net_service.poll()

    def _sync_network_mode(self) -> None:
        observed = self.net_service.poll()
        self.state.network_mode_busy = self.net_service.busy
        applied = parse_network_mode(self.net_service.mode)
        if not self.net_service.busy and applied != parse_network_mode(self.state.network_mode):
            self.state.network_mode = applied
            self._save_prefs()
        self.state.network_mode_observed = observed
        if not self.net_service.busy and observed not in {SWITCHING, FAILED}:
            self.state.network_mode_observed = oled_mode_word(applied)

    def _sync_wiz_runtime(self) -> None:
        snap = self.wiz_service.snapshot()
        self.state.wiz_lifecycle_busy = snap.busy
        self.state.wiz_ap_state = snap.ap
        self.state.wiz_bridge_state = snap.bridge
        self.state.wiz_tx_armed = snap.tx_armed
        self.state.wiz_ap_up = snap.ap == READY
        self.state.wiz_bridge_available = snap.bridge == READY

    def _save_prefs(self) -> None:
        save_prefs(
            self._prefs_path,
            OperatorPrefs(
                wiz_enabled=self.state.wiz_enabled,
                qlc_desired=self.state.qlc_desired,
                network_mode=parse_network_mode(self.state.network_mode),
            ),
        )

    def _sync_qlc(self) -> None:
        self.binding.pull(self.state)
        self.binding.push(self.state)

    def _sim(self, event: SimCommandEvent) -> None:
        cmd = event.command
        if cmd == "toggle_qlc":
            self.qlc.simulate_link(not self.qlc.connected())  # type: ignore[attr-defined]
        elif cmd == "qlc_on":
            self.qlc.simulate_link(True)  # type: ignore[attr-defined]
        elif cmd == "qlc_off":
            self.qlc.simulate_link(False)  # type: ignore[attr-defined]
        elif cmd == "toggle_launchpad":
            apply_launchpad(self.state, not self.state.launchpad_connected)
            LOG.info("Launchpad %s", "connected" if self.state.launchpad_connected else "disconnected")
        elif cmd == "toggle_pknight":
            if self.state.dmx_node_reachable:
                apply_dmx(self.state, net_ok=False, node_ok=False)
                LOG.warning("PKNight unreachable")
            else:
                apply_dmx(self.state, net_ok=True, node_ok=True)
        elif cmd == "toggle_upstream":
            if self.state.upstream_connected:
                apply_upstream(self.state, False)
            else:
                apply_upstream(self.state, True, "LIGHT-CONTROL")
        elif cmd == "toggle_wiz_ap":
            apply_wiz_ap(self.state, not self.state.wiz_ap_up)
        elif cmd == "wiz_delta":
            before = self.state.wiz_online
            bump_wiz(self.state, int(event.value or 0))
            if self.state.wiz_online != before:
                LOG.info("WiZ %s/%s", self.state.wiz_online, self.state.wiz_expected)
        elif cmd == "wiz_set":
            bump_wiz(self.state, int(event.value or 0) - self.state.wiz_online)
            LOG.info("WiZ %s/%s", self.state.wiz_online, self.state.wiz_expected)
        elif cmd == "quit":
            self.running = False
        elif cmd == "screen_boot":
            self.nav.go_play(self.state)

    def go_scene(self, state: AppState) -> None:
        self.binding.go_scene(state)

    def go_chaser(self, state: AppState) -> None:
        self.binding.go_chaser(state)

    def confirm_load(self, state: AppState) -> None:
        self.activate_show(state)

    def activate_show(self, state: AppState) -> None:
        """Select the active logical show. Does not load or restart QLC."""
        if self.catalog is None or not state.show_ids:
            return
        show_id = state.show_ids[bound_index(state.show_index, len(state.show_ids))]
        try:
            show = self.catalog.activate(show_id)
        except Exception as exc:
            LOG.warning("show activate rejected: %s", exc)
            state.show_status = "FAIL"
            return
        self._apply_show(show)
        state.show_status = "ACTIVE"

    def open_workspace(self) -> None:
        """Install the selected .qxw as master.qxw and bounce QLC."""
        if self.workspaces is None or not self.state.show_ids:
            return
        if self.state.show_busy or self.state.route_busy:
            return
        filename = self.state.show_ids[
            bound_index(self.state.show_index, len(self.state.show_ids))
        ]
        if self.workspaces.is_open(filename):
            self.state.show_status = OPEN
            return
        with self._route_lock:
            if self.state.show_busy or self.state.route_busy:
                return
            self.state.show_busy = True
        self.state.show_status = APPLYING
        worker = threading.Thread(
            target=self._workspace_worker,
            args=(filename,),
            daemon=True,
            name="qlc-show",
        )
        worker.start()

    def _workspace_worker(self, filename: str) -> None:
        def progress(stage: str) -> None:
            if stage:
                self.state.show_status = APPLYING

        try:
            opened = switch_workspace(
                self.workspaces,
                filename,
                qlc_service=self.qlc_service,
                progress=progress,
            )
            self.state.show_open_id = opened
            self.state.show_status = OPEN
            self.state.qlc_desired = True
            self._save_prefs()
            if self.state.screen == ScreenId.LOAD_SHOW:
                self.state.screen = ScreenId.SHOWS
            self._route_mtime = None
            self._load_routes()
        except (WorkspaceSwitchError, OSError, UnicodeError) as exc:
            LOG.warning("workspace switch failed: %s", exc)
            self.state.show_status = FAILED
        finally:
            self.state.show_busy = False

    def _apply_show(self, show: ShowDefinition) -> None:
        self._applied_show = show.show_id
        self.state.show_name = show.name
        self.state.scenes = tuple(ref.name for ref in show.scenes)
        self.state.chasers = tuple(ref.name for ref in show.chasers)
        self.state.scene_function_ids = tuple(ref.function_id for ref in show.scenes)
        self.state.chaser_function_ids = tuple(ref.function_id for ref in show.chasers)
        self.state.functions = self.state.scenes
        self.state.scene_index = 0
        self.state.chaser_index = 0
        self.state.clamp_indices()

    def _refresh_show_state(self, force: bool = False) -> None:
        if self.catalog is None:
            return
        current = self.catalog.current_show()
        if current is None:
            return
        if not force and current.show_id == self._applied_show:
            return
        self._apply_show(current)

    def _refresh_workspace_state(self) -> None:
        if self.workspaces is None:
            return
        entries = self.workspaces.list_entries()
        self.state.show_ids = tuple(entry.filename for entry in entries)
        self.state.show_files = tuple(entry.label for entry in entries)
        self.state.show_open_id = self.workspaces.open_filename() or ""
        self.state.show_count = len(entries)
        if self.state.show_busy:
            return
        if self.state.screen == ScreenId.LOAD_SHOW and self.state.show_status in {
            LOAD,
            APPLYING,
            FAILED,
        }:
            return
        if self.state.show_open_id:
            for entry in entries:
                if entry.filename == self.state.show_open_id:
                    self.state.show_name = entry.label
                    break
            if self.state.show_status != FAILED:
                self.state.show_status = OPEN

    def apply_wiz_snapshot(
        self,
        device_map: WizDeviceMap | None = None,
        observations: tuple[WizObservedDevice, ...] = (),
        *,
        bridge_available: bool = False,
        error: str = "",
    ) -> None:
        """Tests / observe-only cache. Never sends WiZ traffic."""
        self._wiz_map = device_map
        self._wiz_observations = observations
        self._wiz_map_error = error
        self.state.wiz_bridge_available = bridge_available
        self._sync_wiz_view()

    def _selected_wiz_row(self):
        rows = self.state.wiz_device_rows
        if not rows:
            return None
        return rows[bound_index(self.state.wiz_device_index, len(rows))]

    def open_wiz_device(self) -> None:
        row = self._selected_wiz_row()
        if row is None:
            return
        self.state.wiz_prompt_error = ""
        self.state.wiz_prompt_swap = ""
        if row.kind == ROW_NEW:
            slot = lowest_unused_slot(self._wiz_map)
            if slot is None:
                self.state.wiz_prompt = "full"
                self.state.wiz_prompt_error = "FULL"
                return
            self.state.wiz_prompt = "add"
            self.state.wiz_prompt_mac = row.id
            self.state.wiz_prompt_slot = slot
            return
        self.state.wiz_prompt = "actions"
        self.state.wiz_prompt_mac = row.id
        self.state.wiz_prompt_slot = int(row.slot or 0)
        self.state.wiz_action_index = 0

    def confirm_wiz_prompt(self) -> None:
        prompt = self.state.wiz_prompt
        if prompt in {"full", "fail"}:
            self.state.wiz_prompt = ""
            self.state.wiz_prompt_error = ""
            return
        if prompt == "actions":
            if self.state.wiz_action_index == 0:
                self.state.wiz_prompt = "move"
                self.state.wiz_prompt_target = max(1, int(self.state.wiz_prompt_slot or 1))
                return
            row = self._selected_wiz_row()
            self.state.wiz_prompt = "enable" if row is not None and not row.enabled else "disable"
            return
        if prompt == "add":
            slot = lowest_unused_slot(self._wiz_map)
            if slot is None:
                self.state.wiz_prompt = "full"
                self.state.wiz_prompt_error = "FULL"
                return
            self._commit_wiz_map(lambda current: add_device(current, self.state.wiz_prompt_mac, slot))
            return
        if prompt == "move":
            target = int(self.state.wiz_prompt_target)
            mac = self.state.wiz_prompt_mac
            current = self._wiz_map
            if current is None:
                self._fail_wiz_prompt("NO MAP")
                return
            occupant = next((item for item in current.devices if item.slot == target), None)
            if occupant is not None and occupant.id != mac:
                self.state.wiz_prompt = "swap"
                self.state.wiz_prompt_swap = occupant.id
                return
            self._commit_wiz_map(lambda device_map: move_device(device_map, mac, target))
            return
        if prompt == "swap":
            self._commit_wiz_map(
                lambda device_map: swap_devices(
                    device_map, self.state.wiz_prompt_mac, self.state.wiz_prompt_swap
                )
            )
            return
        if prompt == "disable":
            self._commit_wiz_map(
                lambda device_map: set_enabled(device_map, self.state.wiz_prompt_mac, False)
            )
            return
        if prompt == "enable":
            self._commit_wiz_map(
                lambda device_map: set_enabled(device_map, self.state.wiz_prompt_mac, True)
            )

    def _fail_wiz_prompt(self, word: str) -> None:
        self.state.wiz_prompt = "fail"
        self.state.wiz_prompt_error = word[:16]

    def _commit_wiz_map(self, mutate) -> None:
        path = self._wiz_map_path
        if path is None:
            self._fail_wiz_prompt("NO MAP")
            return
        try:
            updated = mutate(self._wiz_map)
            save_map(path, updated)
            self._wiz_map = load_map(path)
            self._wiz_map_error = ""
            self._note_wiz_map_mtime()
            self.state.wiz_prompt = ""
            self.state.wiz_prompt_error = ""
            self.state.wiz_prompt_swap = ""
            self._sync_wiz_view()
        except (WizMapValidationError, WizMapCorruptError, WizMapError, OSError) as exc:
            LOG.warning("WiZ map edit failed: %s", exc)
            self._fail_wiz_prompt("WRITE FAIL")

    def _poll_wiz_observed(self) -> None:
        """Local status file only. Missing/malformed fail closed. Never probes."""
        path = self._wiz_observed_path
        if path is None:
            return
        try:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                self._wiz_observed_mtime = None
                apply_wiz_observed(self.state, empty_observed_snapshot(error="missing"))
                self._wiz_observations = ()
                return
            if mtime == self._wiz_observed_mtime:
                return
            snapshot = read_observed_status(path)
            self._wiz_observed_mtime = mtime
            apply_wiz_observed(self.state, snapshot)
            self._wiz_observations = snapshot.observations
        except Exception:
            LOG.debug("wiz observed poll failed", exc_info=True)
            self._wiz_observed_mtime = None
            apply_wiz_observed(self.state, empty_observed_snapshot(error="malformed"))
            self._wiz_observations = ()

    def _note_wiz_map_mtime(self) -> None:
        path = self._wiz_map_path
        if path is None:
            self._wiz_map_mtime = None
            return
        try:
            self._wiz_map_mtime = path.stat().st_mtime
        except OSError:
            self._wiz_map_mtime = None

    def _reload_wiz_map_if_changed(self) -> None:
        path = self._wiz_map_path
        if path is None:
            return
        try:
            mtime = path.stat().st_mtime
        except OSError:
            if self._wiz_map_mtime is not None or self._wiz_map is not None:
                self._wiz_map_mtime = None
                self._load_wiz_cache()
            return
        if mtime == self._wiz_map_mtime:
            return
        self._wiz_map_mtime = mtime
        self._load_wiz_cache()

    def _load_wiz_cache(self) -> None:
        self._wiz_map = None
        self._wiz_map_error = ""
        path = self._wiz_map_path
        if path is None:
            return
        if path.is_file():
            try:
                self._wiz_map = load_map(path)
            except (WizMapCorruptError, WizMapValidationError) as exc:
                self._wiz_map_error = "MAP CORRUPT"
                LOG.warning("WiZ map unreadable: %s", exc)
            except (OSError, WizMapError):
                LOG.debug("WiZ map load failed", exc_info=True)
            return
        legacy = path.with_name("fixtures.json")
        if not legacy.is_file():
            return
        try:
            self._wiz_map = parse_legacy_file(legacy)
        except (WizMapError, OSError):
            LOG.debug("legacy WiZ fixtures preview failed", exc_info=True)

    def _sync_wiz_view(self) -> None:
        view = join_wiz_devices(
            self._wiz_map,
            self._wiz_observations,
            wiz_enabled=self.state.wiz_enabled,
            bridge_available=self.state.wiz_bridge_available,
            error=self._wiz_map_error,
        )
        self.state.wiz_device_rows = view.rows
        self.state.wiz_devices_note = view.note
        self.state.wiz_map_extended = view.extended
        self.state.wiz_device_count = len(view.rows)
        if (
            self.state.screen == ScreenId.WIZ_DEVICES
            and not self.state.wiz_prompt
            and not self.state.wiz_device_detail
        ):
            from light_console.ui.pages import wiz_devices_viewport

            vp = wiz_devices_viewport(self.state)
            self.state.wiz_device_index = vp.focused
            self.state.scroll_offset = vp.offset

    def _finish(self) -> None:
        self.state.clamp_indices()
        self.params.store_index(self.state)
        self._sync_qlc()
        self._refresh_startup_runtime()
        if self.catalog is not None:
            self._refresh_show_state()
        self._refresh_workspace_state()
        self._sync_wiz_runtime()
        self._reload_wiz_map_if_changed()
        self._poll_wiz_observed()
        self._sync_wiz_view()
        self.state.rebuild_warnings()
        self._write_status()

    def _startup_file_status(self) -> str:
        try:
            text = STARTUP_STATUS_PATH.read_text(encoding="utf-8")
        except OSError:
            return ""
        return parse_startup_status_file(text)

    def _refresh_startup_runtime(self) -> None:
        """Function RUNNING is valid only while QLC is connected and the unit is up."""
        connected = self.state.qlc_connected
        observed = self.state.qlc_observed
        if not function_runtime_available(connected, observed):
            self.qlc.clear_function_runtime()
            invalidate_function_runtime(self.state)
            self._startup_status_t = -1.0
            return
        file_status = self._startup_file_status()
        if file_status and not self.state.show_name:
            self.state.show_name = "SIIRTYMA"
        fn = self.qlc.function_by_name(STARTUP_NAME)
        now = self.state.ui_now
        if fn is not None and now - self._startup_status_t >= 1.0:
            self.qlc.request_function_status(fn.function_id)
            self._startup_status_t = now
        live = None if fn is None else bool(fn.running)
        apply_live_startup_runtime(
            self.state, live_running=live, file_status=file_status
        )

    def _sync_identify(self) -> None:
        """Publish the selected WIZ DEVICES MAC as transient identify intent.

        The local status file is the only Light Console → bridge control path.
        Rendering a frame must not call this.
        """
        mac = ""
        if (
            self.state.wiz_tx_armed
            and not self.state.host_stopping()
            and self.state.screen == ScreenId.WIZ_DEVICES
        ):
            row = self._selected_wiz_row()
            ident = (row.id if row is not None else "").strip().lower()
            if len(ident) == 12:
                try:
                    int(ident, 16)
                except ValueError:
                    ident = ""
                mac = ident
        self.state.wiz_identify_mac = mac

    def _write_status(self) -> None:
        self._sync_identify()
        screen = self.state.screen.value if hasattr(self.state.screen, "value") else str(self.state.screen)
        discovering = (
            self.state.wiz_tx_armed
            and not self.state.host_stopping()
            and self.state.wiz_discover_until > self.state.ui_now
        )
        body = (
            f"screen={screen}\n"
            f"master={self.state.master}\n"
            f"sat={self.state.saturation}\n"
            f"hue={self.state.hue_shift}\n"
            f"qlc_state={self.state.qlc_state}\n"
            f"qlc={qlc_output_label(self.state)}\n"
            f"qlc_observed={self.state.qlc_observed}\n"
            f"startup={self.state.startup_status}\n"
            f"network_mode={self.state.network_mode}\n"
            f"network_observed={self.state.network_mode_observed}\n"
            f"wiz={'on' if self.state.wiz_tx_armed else 'off'}\n"
            f"identify={self.state.wiz_identify_mac}\n"
            f"discover={'1' if discovering else ''}\n"
        )
        if body == self._status_body:
            return
        self._status_body = body
        try:
            STATUS_PATH.write_text(body)
        except OSError:
            LOG.debug("status write failed", exc_info=True)
