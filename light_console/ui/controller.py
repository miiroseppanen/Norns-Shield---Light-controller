from __future__ import annotations

import logging
import socket
import time
from pathlib import Path

from light_console.config import AppConfig
from light_console.controls.buttons import ButtonTracker
from light_console.display.renderer import Renderer
from light_console.hardware.base import HardwareBackend
from light_console.hardware.events import ButtonEvent, EncoderEvent, HardwareEvent, SimCommandEvent
from light_console.qlc.binding import QlcBinding
from light_console.qlc.client import QLCClient
from light_console.state import AppState
from light_console.status.dmx import apply_dmx
from light_console.status.midi import apply_launchpad
from light_console.status.network import apply_upstream, apply_wiz_ap
from light_console.status.wiz import bump_wiz
from light_console.ui.nav import Navigation
from light_console.ui.params import bind_console_params
from light_console.ui.shell import NornsUIShell

LOG = logging.getLogger("light-console")


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
    ) -> None:
        self.config = config
        self.state = state
        self.hardware = hardware
        self.qlc = qlc
        self.nav = Navigation()
        self.params = bind_console_params(state)
        self.shell = NornsUIShell(state, nav=self.nav, params=self.params)
        self.buttons = ButtonTracker(long_press_s=config.controls.long_press_ms / 1000.0)
        self.renderer = Renderer(config.display.width, config.display.height)
        self.binding = QlcBinding(qlc)
        self._t0 = time.monotonic()
        self._last_draw = 0.0
        self.running = True
        if not self.state.hostname:
            try:
                self.state.hostname = socket.gethostname()
            except OSError:
                self.state.hostname = ""

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
        now = time.monotonic() if now is None else now
        self.state.uptime_s = int(now - self._t0)
        temp = _read_cpu_temp()
        if temp is not None:
            self.state.cpu_temp_c = temp
        for ev in self.hardware.read_events():
            self.handle_event(ev, now)
        for ev in self.buttons.poll(now):
            self._dispatch_key(ev)
        try:
            self.qlc.pump(now)
        except Exception:
            LOG.exception("QLC pump failed; UI continues")
        self._finish()
        interval = 1.0 / max(1, self.config.display.fps)
        if now - self._last_draw >= interval:
            self.renderer.render(self.state)
            if self.renderer.changed():
                self.hardware.set_display(self.renderer.fb)
            self._last_draw = now

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

    def _finish(self) -> None:
        self.state.clamp_indices()
        self.params.store_index(self.state)
        self._sync_qlc()
        self.state.rebuild_warnings()
