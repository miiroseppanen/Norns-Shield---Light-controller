#!/usr/bin/env python3
"""Shield XL E1 hardware proof — Linux GPIO character device, read-only.

Schematic E1: A=GPIO4, B=GPIO27 on gpiochip0 (pinctrl-bcm2711).
Does not set output, does not enable pull-up or pull-down (Bias.AS_IS),
does not touch K2/K3-unrelated pins beyond E1, SPI, OLED, or codec.

Software sense: A (GPIO4) leading B (GPIO27) is labeled CW +1.
Physical clockwise vs that label is recorded from the operator test.

Requires python3-libgpiod (libgpiod 2.x), already on Raspberry Pi OS Lite.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import timedelta

import gpiod
from gpiod.edge_event import EdgeEvent
from gpiod.line import Bias, Direction, Edge, Value

CHIP_PATH = "/dev/gpiochip0"
EXPECTED_CHIP_LABEL = "pinctrl-bcm2711"
GPIO_A = 4
GPIO_B = 27
# One detent on PEC11R is typically one full quadrature cycle (4 gray steps).
EDGES_PER_DETENT = 4
DEBOUNCE = timedelta(milliseconds=2)

# old_ab, new_ab — A is MSB. A-leads-B: 00→10→11→01→00
CW = {(0, 2), (2, 3), (3, 1), (1, 0)}
CCW = {(0, 1), (1, 3), (3, 2), (2, 0)}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def level(val: Value) -> str:
    return "H" if val == Value.ACTIVE else "L"


def ab_int(a: Value, b: Value) -> int:
    return ((1 if a == Value.ACTIVE else 0) << 1) | (1 if b == Value.ACTIVE else 0)


def preflight(chip: gpiod.Chip) -> None:
    info = chip.get_info()
    if info.label != EXPECTED_CHIP_LABEL:
        fail(
            f"{chip.path} label is {info.label!r}, expected {EXPECTED_CHIP_LABEL!r}"
        )
    for off, name in ((GPIO_A, "E1A"), (GPIO_B, "E1B")):
        li = chip.get_line_info(off)
        consumer = li.consumer if li.consumer not in (None, "None", "") else None
        if li.used or consumer:
            fail(
                f"{name} GPIO{off} already has a kernel consumer "
                f"(used={li.used} consumer={li.consumer!r})"
            )
        if li.direction != Direction.INPUT:
            fail(f"{name} GPIO{off} direction is {li.direction}, expected INPUT")


def request_e1(path: str) -> gpiod.LineRequest:
    settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
        bias=Bias.AS_IS,
        debounce_period=DEBOUNCE,
    )
    return gpiod.request_lines(
        path,
        consumer="shieldxl-e1-test",
        config={GPIO_A: settings, GPIO_B: settings},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chip", default=CHIP_PATH)
    parser.add_argument("--debug", action="store_true", help="print raw A/B edges")
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.0,
        help="stop after N seconds (0 = until Ctrl-C)",
    )
    args = parser.parse_args()

    try:
        chip = gpiod.Chip(args.chip)
    except OSError as exc:
        fail(f"cannot open {args.chip}: {exc}")

    stop = False

    def on_stop(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True
        print("\nstopping (Ctrl-C)", flush=True)

    signal.signal(signal.SIGINT, on_stop)
    signal.signal(signal.SIGTERM, on_stop)

    cw_n = 0
    ccw_n = 0
    invalid_n = 0
    quarter = 0
    t0 = time.monotonic()
    deadline = None if args.timeout <= 0 else t0 + args.timeout

    with chip:
        preflight(chip)
        print(
            f"chip {chip.get_info().name} label={chip.get_info().label!r} "
            f"path={chip.path}",
            flush=True,
        )
        print(
            f"watching E1 A=GPIO{GPIO_A} B=GPIO{GPIO_B}  "
            f"(input, Bias.AS_IS, 2ms debounce, {EDGES_PER_DETENT} edges/detent)",
            flush=True,
        )
        print(
            "software CW = A leads B; turn E1 slowly 3 detents CW, then 3 CCW",
            flush=True,
        )
        print("ready — Ctrl-C to stop", flush=True)

        try:
            request = request_e1(chip.path)
        except OSError as exc:
            fail(f"request_lines failed: {exc}")

        with request:
            a = request.get_value(GPIO_A)
            b = request.get_value(GPIO_B)
            state = ab_int(a, b)
            print(f"IDLE A={level(a)} B={level(b)} ab={state:02b}", flush=True)

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
                    bit = (
                        Value.ACTIVE
                        if event.event_type == EdgeEvent.Type.RISING_EDGE
                        else Value.INACTIVE
                    )
                    if event.line_offset == GPIO_A:
                        a = bit
                    elif event.line_offset == GPIO_B:
                        b = bit
                    else:
                        print(
                            f"UNEXPECTED offset={event.line_offset}",
                            flush=True,
                        )
                        continue
                    new = ab_int(a, b)
                    old = state
                    if new == old:
                        continue
                    delta = 0
                    if (old, new) in CW:
                        delta = 1
                    elif (old, new) in CCW:
                        delta = -1
                    else:
                        invalid_n += 1
                        if args.debug:
                            print(
                                f"RAW skip  {old:02b}->{new:02b}  "
                                f"A={level(a)} B={level(b)}",
                                flush=True,
                            )
                        state = new
                        continue
                    if args.debug:
                        edge = (
                            "A"
                            if event.line_offset == GPIO_A
                            else "B" if event.line_offset == GPIO_B else "?"
                        )
                        print(
                            f"RAW {old:02b}->{new:02b} {edge} "
                            f"A={level(a)} B={level(b)} q={delta:+d}",
                            flush=True,
                        )
                    quarter += delta
                    state = new
                    if quarter >= EDGES_PER_DETENT:
                        n = quarter // EDGES_PER_DETENT
                        quarter -= n * EDGES_PER_DETENT
                        for _ in range(n):
                            cw_n += 1
                            dt = time.monotonic() - t0
                            print(f"E1 CW +1  t+{dt:.3f}s  cw={cw_n} ccw={ccw_n}", flush=True)
                    elif quarter <= -EDGES_PER_DETENT:
                        n = (-quarter) // EDGES_PER_DETENT
                        quarter += n * EDGES_PER_DETENT
                        for _ in range(n):
                            ccw_n += 1
                            dt = time.monotonic() - t0
                            print(f"E1 CCW -1  t+{dt:.3f}s  cw={cw_n} ccw={ccw_n}", flush=True)

    print("", flush=True)
    print("=== SUMMARY ===", flush=True)
    print(f"software CW (A leads B): {cw_n}", flush=True)
    print(f"software CCW (B leads A): {ccw_n}", flush=True)
    print(f"invalid/bounce skips: {invalid_n}", flush=True)
    print(f"leftover quarter-steps: {quarter}", flush=True)
    print(
        "map physical clockwise to the label that appeared during the 3 CW detents",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
