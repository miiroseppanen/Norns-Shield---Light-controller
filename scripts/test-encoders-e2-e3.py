#!/usr/bin/env python3
"""Shield XL E2+E3 hardware proof — two candidate pairs, one run.

Does not assume which pair is physical E2 vs E3.

PAIR-A: GPIO12 / GPIO25  (norns overlay e2; schematic part E3)
PAIR-B: GPIO24 / GPIO23  (norns overlay e3; schematic part E2)

Software CW = A leads B on that pair. Physical mapping comes from the
operator turning silkscreen E2 first, then E3.

Inputs only, Bias.AS_IS, no SPI/OLED/codec. libgpiod 2.x.
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
EDGES_PER_DETENT = 4
DEBOUNCE = timedelta(milliseconds=2)

CW = {(0, 2), (2, 3), (3, 1), (1, 0)}
CCW = {(0, 1), (1, 3), (3, 2), (2, 0)}

PAIRS: dict[str, tuple[int, int]] = {
    "PAIR-A": (12, 25),
    "PAIR-B": (24, 23),
}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def level(val: Value) -> str:
    return "H" if val == Value.ACTIVE else "L"


def ab_int(a: Value, b: Value) -> int:
    return ((1 if a == Value.ACTIVE else 0) << 1) | (1 if b == Value.ACTIVE else 0)


@dataclass
class PairState:
    name: str
    gpio_a: int
    gpio_b: int
    a: Value = Value.INACTIVE
    b: Value = Value.INACTIVE
    gray: int = 0
    quarter: int = 0
    cw: int = 0
    ccw: int = 0
    invalid: int = 0
    events: list[str] = field(default_factory=list)


def preflight(chip: gpiod.Chip) -> None:
    info = chip.get_info()
    if info.label != EXPECTED_CHIP_LABEL:
        fail(
            f"{chip.path} label is {info.label!r}, expected {EXPECTED_CHIP_LABEL!r}"
        )
    for name, (ga, gb) in PAIRS.items():
        for off, role in ((ga, "A"), (gb, "B")):
            li = chip.get_line_info(off)
            consumer = li.consumer if li.consumer not in (None, "None", "") else None
            if li.used or consumer:
                fail(
                    f"{name} {role} GPIO{off} has consumer "
                    f"(used={li.used} consumer={li.consumer!r})"
                )
            if li.direction != Direction.INPUT:
                fail(f"{name} {role} GPIO{off} is {li.direction}, expected INPUT")


def request_pairs(path: str) -> gpiod.LineRequest:
    settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
        bias=Bias.AS_IS,
        debounce_period=DEBOUNCE,
    )
    offsets = [p for pair in PAIRS.values() for p in pair]
    return gpiod.request_lines(
        path,
        consumer="shieldxl-e2-e3-test",
        config={off: settings for off in offsets},
    )


def apply_edge(pair: PairState, event: EdgeEvent, t0: float, debug: bool) -> None:
    bit = (
        Value.ACTIVE
        if event.event_type == EdgeEvent.Type.RISING_EDGE
        else Value.INACTIVE
    )
    if event.line_offset == pair.gpio_a:
        pair.a = bit
    elif event.line_offset == pair.gpio_b:
        pair.b = bit
    else:
        return
    new = ab_int(pair.a, pair.b)
    old = pair.gray
    if new == old:
        return
    if (old, new) in CW:
        delta = 1
    elif (old, new) in CCW:
        delta = -1
    else:
        pair.invalid += 1
        if debug:
            print(
                f"RAW {pair.name} skip {old:02b}->{new:02b} "
                f"A={level(pair.a)} B={level(pair.b)}",
                flush=True,
            )
        pair.gray = new
        return
    if debug:
        print(
            f"RAW {pair.name} {old:02b}->{new:02b} "
            f"A={level(pair.a)} B={level(pair.b)} q={delta:+d}",
            flush=True,
        )
    pair.quarter += delta
    pair.gray = new
    dt = time.monotonic() - t0
    while pair.quarter >= EDGES_PER_DETENT:
        pair.quarter -= EDGES_PER_DETENT
        pair.cw += 1
        line = f"{pair.name} CW +1"
        pair.events.append(line)
        print(
            f"{line}  t+{dt:.3f}s  cw={pair.cw} ccw={pair.ccw}",
            flush=True,
        )
    while pair.quarter <= -EDGES_PER_DETENT:
        pair.quarter += EDGES_PER_DETENT
        pair.ccw += 1
        line = f"{pair.name} CCW -1"
        pair.events.append(line)
        print(
            f"{line}  t+{dt:.3f}s  cw={pair.cw} ccw={pair.ccw}",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chip", default=CHIP_PATH)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--timeout", type=float, default=0.0)
    args = parser.parse_args()

    offset_to_pair: dict[int, str] = {}
    for name, (ga, gb) in PAIRS.items():
        offset_to_pair[ga] = name
        offset_to_pair[gb] = name

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

    t0 = time.monotonic()
    deadline = None if args.timeout <= 0 else t0 + args.timeout

    with chip:
        preflight(chip)
        print(
            f"chip {chip.get_info().name} label={chip.get_info().label!r} "
            f"path={chip.path}",
            flush=True,
        )
        for name, (ga, gb) in PAIRS.items():
            print(f"{name}  A=GPIO{ga}  B=GPIO{gb}", flush=True)
        print(
            "software CW = A leads B on that pair; 4 gray steps = 1 detent",
            flush=True,
        )
        print("1) physical E2: 3 detents CW, then 3 CCW", flush=True)
        print("2) physical E3: 3 detents CW, then 3 CCW", flush=True)
        print("ready — Ctrl-C to stop", flush=True)

        try:
            request = request_pairs(chip.path)
        except OSError as exc:
            fail(f"request_lines failed: {exc}")

        states = {
            name: PairState(name=name, gpio_a=ga, gpio_b=gb)
            for name, (ga, gb) in PAIRS.items()
        }

        with request:
            for st in states.values():
                st.a = request.get_value(st.gpio_a)
                st.b = request.get_value(st.gpio_b)
                st.gray = ab_int(st.a, st.b)
                print(
                    f"IDLE {st.name} A={level(st.a)} B={level(st.b)} ab={st.gray:02b}",
                    flush=True,
                )

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
                    name = offset_to_pair.get(event.line_offset)
                    if name is None:
                        print(f"UNEXPECTED offset={event.line_offset}", flush=True)
                        continue
                    apply_edge(states[name], event, t0, args.debug)

    print("", flush=True)
    print("=== SUMMARY ===", flush=True)
    for st in states.values():
        print(
            f"{st.name} GPIO{st.gpio_a}/{st.gpio_b}: "
            f"CW={st.cw} CCW={st.ccw} invalid={st.invalid} leftover_q={st.quarter}",
            flush=True,
        )
    print(
        "physical E2 = the pair that moved first; physical E3 = the other pair",
        flush=True,
    )
    print(
        "physical CW = the software label (CW or CCW) seen during the 3 CW detents",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
