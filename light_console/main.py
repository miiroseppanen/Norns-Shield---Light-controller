from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

from light_console import VERSION
from light_console.version import read_build_revision
from light_console.config import AppConfig, example_config_path, load_config
from light_console.display.renderer import Renderer
from light_console.hardware.base import HardwareBackend
from light_console.hardware.headless import HeadlessBackend
from light_console.logutil import LOG, setup_logging
from light_console.qlc.client import MockQLCClient
from light_console.state import AppState, ScreenId, demo_live_state
from light_console.ui.controller import Controller
from light_console.wiz.device_map import default_map_path
from light_console.wiz.observe import default_observed_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Shield XL Light Console")
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--simulator", action="store_true", help="Mac OLED + encoder simulator")
    p.add_argument("--headless", action="store_true", help="No window (tests / dump)")
    p.add_argument("--shield", action="store_true", help="Physical shieldXL GPIO + SSD1322")
    p.add_argument("--dump-screen", type=Path, default=None, help="Write ASCII OLED dump and exit")
    p.add_argument("--screenshot", type=Path, default=None, help="Write PPM screenshot and exit")
    p.add_argument("--boot", action="store_true", help="Start with QLC assumed offline")
    p.add_argument("--debug", action="store_true")
    return p.parse_args(argv)


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return ""


def build_state(config: AppConfig, boot: bool, live: bool = True) -> AppState:
    if boot or not live:
        state = AppState(
            wiz_expected=config.wiz.expected,
            special_name=config.controls.special_name,
            version=VERSION,
            screen=ScreenId.PLAY,
            hostname=_hostname(),
            current_scene="WASH",
        )
    else:
        state = demo_live_state(config.wiz.expected)
        state.special_name = config.controls.special_name
        state.version = VERSION
        state.hostname = _hostname()
    state.build_revision = read_build_revision() or ""
    state.rebuild_warnings()
    return state


def dump_views(config: AppConfig, ascii_path: Path | None, ppm_path: Path | None, boot: bool) -> int:
    state = build_state(config, boot=boot)
    renderer = Renderer()
    renderer.render(state)
    if ascii_path:
        ascii_path.write_text(renderer.fb.to_ascii() + "\n")
        LOG.info("Wrote %s", ascii_path)
    if ppm_path:
        ppm_path.write_bytes(renderer.fb.to_ppm(scale=6))
        LOG.info("Wrote %s", ppm_path)
    return 0


def run_loop(controller: Controller, hardware: HardwareBackend) -> int:
    import signal

    from light_console.hardware.events import ButtonEvent, E1, EncoderEvent, K3
    from light_console.state import ScreenId
    from light_console.ui.pages import SYSTEM_QLC_TOGGLE

    pending_e1 = {"delta": 0}
    pending_qlc_on = {"go": False}

    def _usr1(_signum: int, _frame: object) -> None:
        pending_e1["delta"] += 5

    def _usr2(_signum: int, _frame: object) -> None:
        pending_qlc_on["go"] = True

    def _term(_signum: int, _frame: object) -> None:
        controller.running = False

    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, _usr1)
    if hasattr(signal, "SIGUSR2"):
        signal.signal(signal.SIGUSR2, _usr2)
    signal.signal(signal.SIGTERM, _term)
    try:
        while controller.running:
            delta = pending_e1["delta"]
            if delta:
                pending_e1["delta"] = 0
                controller.nav.go_play(controller.state)
                controller.inject_cooked(EncoderEvent(E1, delta))
                LOG.info("PLAY E1 %+d master=%s%%", delta, controller.state.master)
            if pending_qlc_on["go"]:
                pending_qlc_on["go"] = False
                controller.state.screen = ScreenId.SYSTEM
                controller.state.system_index = SYSTEM_QLC_TOGGLE
                controller.state.scroll_offset = 0
                if controller.state.qlc_desired:
                    controller.set_qlc_desired(True)
                else:
                    controller.inject_cooked(ButtonEvent(K3, "press"))
                LOG.info(
                    "SYSTEM QLC SERVICE enable desired=%s observed=%s",
                    controller.state.qlc_desired,
                    controller.state.qlc_observed,
                )
            controller.tick()
            hardware.idle(1.0 / max(30, controller.config.display.fps * 2))
    except KeyboardInterrupt:
        controller.running = False
    finally:
        hardware.close()
        close = getattr(controller.qlc, "close", None)
        if callable(close):
            close()
    return 0


def _shows_dir() -> Path | None:
    env = os.environ.get("LIGHT_CONSOLE_SHOWS")
    if env:
        return Path(env)
    pi = Path("/home/light/shows")
    if pi.is_dir():
        return pi
    return None


def _load_config(path: Path | None) -> AppConfig:
    if path is not None:
        return load_config(path)
    example = example_config_path()
    try:
        if example.exists():
            return load_config(example)
    except RuntimeError:
        pass
    return load_config(None)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = _load_config(args.config)
    if args.debug:
        config.debug = True
    setup_logging(config.debug)

    if args.dump_screen or args.screenshot:
        return dump_views(config, args.dump_screen, args.screenshot, boot=args.boot)

    if not args.simulator and not args.headless and not args.shield:
        LOG.error("Use python -m simulator.run  or  python -m light_console.main --shield")
        return 2

    live = not args.boot and not args.shield
    state = build_state(config, boot=args.boot, live=live)

    lock = None
    prefs_path = None
    qlc_service = None
    net_service = None
    wiz_service = None
    if args.shield:
        from light_console.hardware.shieldxl import ShieldXLBackend
        from light_console.instance import InstanceLock, InstanceLockHeld
        from light_console.power import LinuxPowerService
        from light_console.output.netmode import (
            LinuxNetworkModeService,
            MODE_STANDALONE,
            parse_network_mode,
        )
        from light_console.output.wiz_lifecycle import LinuxWizLifecycleService
        from light_console.prefs import default_prefs_path, load_prefs
        from light_console.qlc.service import LinuxQlcService
        from light_console.qlc.ws_client import QlcWebSocketClient

        lock = InstanceLock()
        try:
            lock.acquire()
        except InstanceLockHeld as exc:
            LOG.error("%s", exc)
            print(str(exc), file=sys.stderr, flush=True)
            return 1
        try:
            hardware: HardwareBackend = ShieldXLBackend()
        except Exception:
            lock.close()
            raise
        state.screen = ScreenId.STARTING_UP
        qlc = QlcWebSocketClient(config.qlc.websocket, config.qlc.reconnect_seconds)
        power = LinuxPowerService()
        prefs_path = default_prefs_path()
        qlc_service = LinuxQlcService()
        boot_mode = parse_network_mode(load_prefs(prefs_path).network_mode)
        net_service = LinuxNetworkModeService(mode=boot_mode)
        if boot_mode == MODE_STANDALONE:
            net_service.set_desired(MODE_STANDALONE)
        wiz_service = LinuxWizLifecycleService(desired=False)
    else:
        from light_console.power import MockPowerService
        from light_console.qlc.service import MockQlcService

        qlc = MockQLCClient(state.functions)
        if live:
            qlc.simulate_link(True)
        power = MockPowerService()
        qlc_service = MockQlcService(
            desired_on=state.qlc_desired,
            observed=state.qlc_observed if state.qlc_observed else ("RUNNING" if live else "STOPPED"),
            auto_settle=True,
        )
        if args.headless:
            hardware = HeadlessBackend()
        else:
            from light_console.hardware.simulator import SimulatorBackend

            hardware = SimulatorBackend(scale=config.display.scale)

    controller = Controller(
        config,
        state,
        hardware,
        qlc,
        power=power,
        shows_dir=_shows_dir(),
        prefs_path=prefs_path,
        qlc_service=qlc_service,
        net_service=net_service,
        wiz_service=wiz_service,
        wiz_map_path=default_map_path() if args.shield else None,
        wiz_observed_path=default_observed_path() if args.shield else None,
    )
    if args.shield:
        print(f"light-console {VERSION}  shield  PLAY  Ctrl-C to quit", flush=True)
    LOG.info("light-console %s", VERSION)
    try:
        return run_loop(controller, hardware)
    finally:
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    sys.exit(main())
