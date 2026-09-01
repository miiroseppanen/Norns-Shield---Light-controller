from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from light_console import VERSION
from light_console.config import AppConfig, example_config_path, load_config
from light_console.display.renderer import Renderer
from light_console.hardware.base import HardwareBackend
from light_console.hardware.headless import HeadlessBackend
from light_console.logutil import LOG, setup_logging
from light_console.qlc.client import MockQLCClient
from light_console.state import AppState, ScreenId, demo_live_state
from light_console.ui.controller import Controller


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Shield XL Light Console")
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--simulator", action="store_true", help="Mac OLED + encoder simulator")
    p.add_argument("--headless", action="store_true", help="No window (tests / dump)")
    p.add_argument("--dump-screen", type=Path, default=None, help="Write ASCII OLED dump and exit")
    p.add_argument("--screenshot", type=Path, default=None, help="Write PPM screenshot and exit")
    p.add_argument("--boot", action="store_true", help="Start on boot screen (default for dump is home live)")
    p.add_argument("--debug", action="store_true")
    return p.parse_args(argv)


def build_state(config: AppConfig, boot: bool) -> AppState:
    if boot:
        state = AppState(
            wiz_expected=config.wiz.expected,
            special_name=config.controls.special_name,
            version=VERSION,
            screen=ScreenId.BOOT,
            startup_running=True,
        )
    else:
        state = demo_live_state(config.wiz.expected)
        state.special_name = config.controls.special_name
        state.version = VERSION
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
    try:
        while controller.running:
            controller.tick()
            hardware.idle(1.0 / max(30, controller.config.display.fps * 2))
    except KeyboardInterrupt:
        controller.running = False
    finally:
        hardware.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg_path = args.config
    if cfg_path is None and example_config_path().exists():
        cfg_path = example_config_path()
    config = load_config(cfg_path)
    if args.debug:
        config.debug = True
    setup_logging(config.debug)

    if args.dump_screen or args.screenshot:
        return dump_views(config, args.dump_screen, args.screenshot, boot=args.boot)

    if not args.simulator and not args.headless:
        # Milestone 0.1 default: simulator when not on a dedicated flag? User asked python -m simulator.run
        LOG.error("Use python -m simulator.run  (Milestone 0.1 has no Pi GPIO backend)")
        return 2

    state = build_state(config, boot=args.boot)
    qlc = MockQLCClient(state.functions)
    if not args.boot:
        qlc.simulate_link(True)

    if args.headless:
        hardware: HardwareBackend = HeadlessBackend()  # type: ignore[assignment]
    else:
        from light_console.hardware.simulator import SimulatorBackend

        hardware = SimulatorBackend(scale=config.display.scale)

    controller = Controller(config, state, hardware, qlc)
    LOG.info("light-console %s simulator", VERSION)
    return run_loop(controller, hardware)


if __name__ == "__main__":
    sys.exit(main())
