from __future__ import annotations

import logging
import time

from light_console.config import AppConfig
from light_console.controls.buttons import ButtonTracker
from light_console.controls.mappings import ControlMapper
from light_console.display.renderer import Renderer
from light_console.hardware.base import HardwareBackend
from light_console.hardware.events import ButtonEvent, EncoderEvent, HardwareEvent, SimCommandEvent
from light_console.qlc.client import QLCClient
from light_console.state import AppState, ScreenId
from light_console.status.dmx import apply_dmx
from light_console.status.midi import apply_launchpad
from light_console.status.network import apply_upstream, apply_wiz_ap
from light_console.status.wiz import bump_wiz

LOG = logging.getLogger("light-console")


class Controller:
    def __init__(
        self,
        config: AppConfig,
        state: AppState,
        hardware: HardwareBackend,
        qlc: QLCClient,
    ) -> None:
        self.config = config
        self.state = state
        self.hardware = hardware
        self.qlc = qlc
        self.mapper = ControlMapper(config.controls)
        self.buttons = ButtonTracker(long_press_s=config.controls.long_press_ms / 1000.0)
        self.renderer = Renderer(config.display.width, config.display.height)
        self._t0 = time.monotonic()
        self._last_draw = 0.0
        self.running = True

    def handle_event(self, event: HardwareEvent, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if isinstance(event, SimCommandEvent):
            self._sim(event)
        elif isinstance(event, EncoderEvent):
            self.mapper.handle_encoder(event, self.state, self.qlc)
        elif isinstance(event, ButtonEvent):
            if event.action == "press":
                # Simulator may send cooked press/long_press. Hardware sends raw press/release.
                cooked = self.buttons.on_hardware_press(event.button, now)
                if cooked:
                    for c in cooked:
                        self.mapper.handle_button(c, self.state, self.qlc)
                else:
                    # raw down: wait for tracker
                    pass
            elif event.action == "release":
                for c in self.buttons.on_hardware_release(event.button, now):
                    self.mapper.handle_button(c, self.state, self.qlc)
            elif event.action == "long_press":
                self.mapper.handle_button(event, self.state, self.qlc)
        self._finish()

    def inject_cooked(self, event: HardwareEvent) -> None:
        """Tests: already short/long ButtonEvents, skip debounce tracker."""
        if isinstance(event, ButtonEvent):
            self.mapper.handle_button(event, self.state, self.qlc)
        elif isinstance(event, EncoderEvent):
            self.mapper.handle_encoder(event, self.state, self.qlc)
        elif isinstance(event, SimCommandEvent):
            self._sim(event)
        self._finish()

    def tick(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self.state.uptime_s = int(now - self._t0)
        for ev in self.hardware.read_events():
            self.handle_event(ev, now)
        for ev in self.buttons.poll(now):
            self.mapper.handle_button(ev, self.state, self.qlc)
        self.qlc.pump(now)
        self._sync_qlc()
        self._boot_advance()
        self._finish()
        interval = 1.0 / max(1, self.config.display.fps)
        if now - self._last_draw >= interval:
            self.renderer.render(self.state)
            if self.renderer.changed():
                self.hardware.set_display(self.renderer.fb)
            self._last_draw = now

    def _sync_qlc(self) -> None:
        was = self.state.qlc_connected
        self.state.qlc_connected = self.qlc.connected()
        self.state.qlc_project_loaded = self.qlc.project_loaded()
        if was and not self.state.qlc_connected:
            LOG.warning("QLC connection lost")
        if not was and self.state.qlc_connected:
            LOG.info("QLC connected")
            names = tuple(fn.name for fn in self.qlc.list_functions())
            if names:
                self.state.functions = names

    def _boot_advance(self) -> None:
        if self.state.startup_running and self.state.qlc_connected and self.state.qlc_project_loaded:
            self.state.startup_running = False
            if self.state.screen == ScreenId.BOOT:
                self.state.screen = ScreenId.HOME

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
            self.state.screen = ScreenId.BOOT
            self.state.startup_running = True

    def _finish(self) -> None:
        self.state.clamp_indices()
        self.state.rebuild_warnings()
