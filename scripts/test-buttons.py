#!/usr/bin/env python3
"""Shield XL K1/K2/K3 hardware proof — Linux GPIO character device, read-only.

Reads BCM GPIO 22 / 26 / 13 on gpiochip0 (pinctrl-bcm2711). Active-low:
electrical HIGH = released, LOW = pressed. Does not set output, does not
enable pull-up or pull-down (Bias.AS_IS), does not touch SPI / OLED /
encoders / codec pins.

Requires python3-libgpiod (libgpiod 2.x). On Raspberry Pi OS Lite 64-bit
(Debian 13) this is already installed with the image used for Milestone 0.2.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import timedelta

import gpiod
from gpiod.edge_event import EdgeEvent
from gpiod.line import Bias, Direction, Edge, Value

CHIP_PATH = "/dev/gpiochip0"
EXPECTED_CHIP_LABEL = "pinctrl-bcm2711"

# Schematic / overlay labels. Physical left/middle/right is recorded live.
BUTTONS: dict[str, int] = {
    "K1": 22,
    "K2": 26,
    "K3": 13,
}

DEBOUNCE = timedelta(milliseconds=10)


@dataclass
class ButtonLog:
    presses: int = 0
    releases: int = 0
    first_press_s: float | None = None
    extra: list[str] = field(default_factory=list)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def preflight(chip: gpiod.Chip, offsets: list[int]) -> None:
    info = chip.get_info()
    if info.label != EXPECTED_CHIP_LABEL:
        fail(
            f"{chip.path} label is {info.label!r}, expected {EXPECTED_CHIP_LABEL!r}"
        )
    for off in offsets:
        li = chip.get_line_info(off)
        consumer = li.consumer if li.consumer not in (None, "None", "") else None
        if li.used or consumer:
            fail(
                f"GPIO{off} already has a kernel consumer "
                f"(used={li.used} consumer={li.consumer!r})"
            )
        if li.direction != Direction.INPUT:
            fail(f"GPIO{off} direction is {li.direction}, expected INPUT")


def request_buttons(path: str, offsets: list[int]) -> gpiod.LineRequest:
    settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
        bias=Bias.AS_IS,
        debounce_period=DEBOUNCE,
    )
    return gpiod.request_lines(
        path,
        consumer="shieldxl-button-test",
        config={off: settings for off in offsets},
    )


def idle_ok(request: gpiod.LineRequest, name_by_off: dict[int, str]) -> None:
    """Released keys must be electrical HIGH (Value.ACTIVE, active_low=False)."""
    bad: list[str] = []
    for off, name in name_by_off.items():
        val = request.get_value(off)
        level = "HIGH" if val == Value.ACTIVE else "LOW"
        print(f"IDLE {name} gpio={off} {level}", flush=True)
        if val != Value.ACTIVE:
            bad.append(f"{name}/GPIO{off}={level}")
    if bad:
        fail("idle is not HIGH (keys should be released): " + ", ".join(bad))


def print_event(name: str, gpio: int, kind: str, t0: float) -> None:
    dt = time.monotonic() - t0
    print(f"{name} {kind}  gpio={gpio}  t+{dt:.3f}s", flush=True)


def summarize(logs: dict[str, ButtonLog], press_order: list[str]) -> int:
    print("", flush=True)
    print("=== SUMMARY ===", flush=True)
    print(f"press order: {' '.join(press_order) if press_order else '(none)'}", flush=True)
    ok = True
    for name in BUTTONS:
        log = logs[name]
        chatter = log.presses > 1 or log.releases > 1
        match = log.presses == 1 and log.releases == 1
        status = "PASS" if match and not chatter else "FAIL"
        if status != "PASS":
            ok = False
        print(
            f"{name} GPIO{BUTTONS[name]}: "
            f"{log.presses} PRESS / {log.releases} RELEASE  {status}",
            flush=True,
        )
        if chatter:
            print(f"  chatter or extra events on {name}", flush=True)
    expected = ["K1", "K2", "K3"]
    firsts = [n for n in press_order if n in expected]
    # Unique first-press order (ignore extra chatter presses).
    seen: list[str] = []
    for n in firsts:
        if n not in seen:
            seen.append(n)
    if seen != expected:
        print(
            f"physical press order was {seen}, expected K1 K2 K3 "
            "(document actual mapping; do not guess)",
            flush=True,
        )
        # Order mismatch is not an automatic FAIL if each BCM line still
        # produced exactly one press/release — operator mapping is recorded.
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chip", default=CHIP_PATH)
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.0,
        help="stop after N seconds (0 = until Ctrl-C)",
    )
    args = parser.parse_args()

    name_by_off = {bcm: name for name, bcm in BUTTONS.items()}
    offsets = list(BUTTONS.values())

    try:
        chip = gpiod.Chip(args.chip)
    except OSError as exc:
        fail(f"cannot open {args.chip}: {exc}")

    logs = {name: ButtonLog() for name in BUTTONS}
    press_order: list[str] = []
    t0 = time.monotonic()
    deadline = None if args.timeout <= 0 else t0 + args.timeout

    stop = False

    def on_stop(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True
        print("\nstopping (Ctrl-C)", flush=True)

    signal.signal(signal.SIGINT, on_stop)
    signal.signal(signal.SIGTERM, on_stop)

    with chip:
        preflight(chip, offsets)
        print(
            f"chip {chip.get_info().name} label={chip.get_info().label!r} "
            f"path={chip.path}",
            flush=True,
        )
        print(
            "watching "
            + ", ".join(f"{n}=GPIO{b}" for n, b in BUTTONS.items())
            + "  (active-low, Bias.AS_IS, input, 10ms debounce)",
            flush=True,
        )
        print("ready — press K1, then K2, then K3 (Ctrl-C to stop)", flush=True)

        try:
            request = request_buttons(chip.path, offsets)
        except OSError as exc:
            fail(f"request_lines failed: {exc}")

        with request:
            idle_ok(request, name_by_off)
            while not stop:
                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    print("TIMEOUT", flush=True)
                    break
                wait_s = 0.2
                if deadline is not None:
                    wait_s = min(wait_s, max(0.0, deadline - now))
                if not request.wait_edge_events(wait_s):
                    continue
                for event in request.read_edge_events():
                    name = name_by_off.get(event.line_offset)
                    if name is None:
                        print(
                            f"UNEXPECTED offset={event.line_offset} type={event.event_type}",
                            flush=True,
                        )
                        continue
                    log = logs[name]
                    if event.event_type == EdgeEvent.Type.FALLING_EDGE:
                        log.presses += 1
                        press_order.append(name)
                        if log.first_press_s is None:
                            log.first_press_s = time.monotonic() - t0
                        print_event(name, event.line_offset, "PRESS", t0)
                    elif event.event_type == EdgeEvent.Type.RISING_EDGE:
                        log.releases += 1
                        print_event(name, event.line_offset, "RELEASE", t0)
                    else:
                        print(
                            f"{name} UNKNOWN_EDGE type={event.event_type} gpio={event.line_offset}",
                            flush=True,
                        )

    return summarize(logs, press_order)


if __name__ == "__main__":
    sys.exit(main())
