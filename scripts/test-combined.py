#!/usr/bin/env python3
"""Shield XL combined hardware proof: OLED + K1–K3 + E1–E3.

Proven OLED packing (NHD-2.7-12864WDW3 / SSD1322): 128 bytes/row, 8192/frame,
remap 0x04,0x11 (enclosure 180°). SPI0 + DC=GPIO5 RESET=GPIO6.

Does not enable I2S/I2C, does not touch codec pins 2,3,17–21, no QLC.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import gpiod
import spidev
from gpiod.edge_event import EdgeEvent
from gpiod.line import Bias, Direction, Edge, Value

CHIP_PATH = "/dev/gpiochip0"
SPI_DEV = "/dev/spidev0.0"
GPIO_DC = 5
GPIO_RESET = 6
WIDTH, HEIGHT = 128, 64
COL_START, COL_END = 0x1C, 0x5B
BYTES_PER_ROW = 128
REMAP = (0x04, 0x11)

BUTTONS = {"K1": 22, "K2": 26, "K3": 13}
ENCODERS = {
    "E1": (4, 27),
    "E2": (12, 25),
    "E3": (24, 23),
}
EDGES_PER_DETENT = 4
BTN_DEBOUNCE = timedelta(milliseconds=10)
ENC_DEBOUNCE = timedelta(milliseconds=2)
CW = {(0, 2), (2, 3), (3, 1), (1, 0)}
CCW = {(0, 1), (1, 3), (3, 2), (2, 0)}

_RAW = {
    " ": 0x00000000000000,
    "+": 0x00041F04000000,
    "-": 0x00001F00000000,
    "0": 0x0E111315110E00,
    "1": 0x040C0404040E00,
    "2": 0x0E11020C101F00,
    "3": 0x0E11060E110E00,
    "4": 0x02060A1F020200,
    "5": 0x1F101E01110E00,
    "6": 0x0E101E11110E00,
    "7": 0x1F010204080800,
    "8": 0x0E110E11110E00,
    "9": 0x0E11110F010E00,
    "A": 0x0E11111F111100,
    "C": 0x0E111010110E00,
    "E": 0x1F101E10101F00,
    "G": 0x0E111017110E00,
    "H": 0x11111F11111100,
    "I": 0x0E040404040E00,
    "K": 0x11121418121100,
    "L": 0x10101010101F00,
    "N": 0x11191513111100,
    "O": 0x0E111111110E00,
    "P": 0x1E11111E101000,
    "R": 0x1E11111E121100,
    "S": 0x0E11100E110E00,
    "T": 0x1F040404040400,
    "W": 0x111111151B1100,
}
CELL_W = 6


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def glyph(ch: str) -> tuple[int, ...]:
    packed = _RAW.get(ch.upper() if ch.isalpha() else ch, _RAW[" "])
    return tuple((packed >> (8 * (6 - i))) & 0x1F for i in range(7))


def pack_row(pixels: list[int]) -> bytes:
    return bytes(0xFF if p else 0x00 for p in pixels)


def blit(fb: list[list[int]], text: str, x: int, y0: int) -> None:
    for ch in text:
        rows = glyph(ch)
        for row, bits in enumerate(rows):
            yy = y0 + row
            if not (0 <= yy < HEIGHT):
                continue
            for col in range(5):
                if bits & (0x10 >> col):
                    xx = x + col
                    if 0 <= xx < WIDTH:
                        fb[yy][xx] = 1
        x += CELL_W


class Oled:
    def __init__(self, hz: int) -> None:
        if not Path(SPI_DEV).exists():
            fail(f"{SPI_DEV} missing")
        self.gpio = gpiod.request_lines(
            CHIP_PATH,
            consumer="shieldxl-combined-oled",
            config={
                GPIO_DC: gpiod.LineSettings(
                    direction=Direction.OUTPUT, output_value=Value.ACTIVE
                ),
                GPIO_RESET: gpiod.LineSettings(
                    direction=Direction.OUTPUT, output_value=Value.ACTIVE
                ),
            },
        )
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.mode = 0
        self.spi.max_speed_hz = hz

    def close(self) -> None:
        try:
            self.spi.close()
        except Exception:
            pass
        try:
            self.gpio.release()
        except Exception:
            pass

    def _dc(self, data: bool) -> None:
        self.gpio.set_value(GPIO_DC, Value.ACTIVE if data else Value.INACTIVE)

    def cmd(self, code: int, *args: int) -> None:
        self._dc(False)
        self.spi.writebytes([code & 0xFF])
        if args:
            self._dc(True)
            self.spi.writebytes([a & 0xFF for a in args])

    def data(self, payload: bytes) -> None:
        self._dc(True)
        self.spi.writebytes(list(payload))

    def init(self) -> None:
        self.gpio.set_value(GPIO_RESET, Value.INACTIVE)
        time.sleep(0.001)
        self.gpio.set_value(GPIO_RESET, Value.ACTIVE)
        time.sleep(0.001)
        self.cmd(0xFD, 0x12)
        self.cmd(0xAE)
        self.cmd(0xB3, 0x91)
        self.cmd(0xCA, 0x3F)
        self.cmd(0xA2, 0x00)
        self.cmd(0xA1, 0x00)
        self.cmd(0xAB, 0x01)
        self.cmd(0xA0, REMAP[0], REMAP[1])
        self.cmd(0xC7, 0x0F)
        self.cmd(0xC1, 0x9F)
        self.cmd(0xB1, 0xF2)
        self.cmd(0xBB, 0x1F)
        self.cmd(0xB4, 0xA0, 0xFD)
        self.cmd(0xBE, 0x04)
        self.cmd(0xB9)
        self.cmd(0xA6)
        self.cmd(0xA9)
        self.cmd(0xAF)

    def show(self, fb: list[list[int]]) -> None:
        for y, pix in enumerate(fb):
            self.cmd(0x15, COL_START, COL_END)
            self.cmd(0x75, y, y)
            self.cmd(0x5C)
            self.data(pack_row(pix))


def ab_int(a: Value, b: Value) -> int:
    return ((1 if a == Value.ACTIVE else 0) << 1) | (1 if b == Value.ACTIVE else 0)


@dataclass
class Enc:
    name: str
    gpio_a: int
    gpio_b: int
    a: Value = Value.INACTIVE
    b: Value = Value.INACTIVE
    gray: int = 0
    quarter: int = 0
    net: int = 0


def make_fb(last: str, encs: dict[str, Enc], held: dict[str, bool]) -> list[list[int]]:
    fb = [[0] * WIDTH for _ in range(HEIGHT)]
    blit(fb, "LIGHT CONSOLE", max(0, (WIDTH - 13 * CELL_W) // 2), 2)
    k = "".join("*" if held[n] else "-" for n in ("K1", "K2", "K3"))
    blit(fb, f"K {k}", 4, 16)
    e = " ".join(f"{n[-1]}{encs[n].net:+d}" for n in ("E1", "E2", "E3"))
    blit(fb, e[:21], 4, 28)
    blit(fb, last[:21], 4, 44)
    return fb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hz", type=int, default=8_000_000)
    args = parser.parse_args()

    print("combined: OLED + K1/K2/K3 + E1/E2/E3  (Ctrl-C to stop)", flush=True)
    print(
        "press each key once; turn each encoder both ways; OLED should update",
        flush=True,
    )

    oled = Oled(hz=args.hz)
    oled.init()

    btn_settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
        bias=Bias.AS_IS,
        debounce_period=BTN_DEBOUNCE,
    )
    enc_settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.BOTH,
        bias=Bias.AS_IS,
        debounce_period=ENC_DEBOUNCE,
    )
    config: dict[int, gpiod.LineSettings] = {}
    offset_kind: dict[int, str] = {}
    for name, off in BUTTONS.items():
        config[off] = btn_settings
        offset_kind[off] = name
    encs = {n: Enc(n, a, b) for n, (a, b) in ENCODERS.items()}
    for st in encs.values():
        config[st.gpio_a] = enc_settings
        config[st.gpio_b] = enc_settings
        offset_kind[st.gpio_a] = st.name
        offset_kind[st.gpio_b] = st.name

    held = {n: False for n in BUTTONS}
    last = "READY"
    t0 = time.monotonic()

    stop = False

    def on_stop(_s: int, _f: object) -> None:
        nonlocal stop
        stop = True
        print("\nstopping (Ctrl-C)", flush=True)

    signal.signal(signal.SIGINT, on_stop)
    signal.signal(signal.SIGTERM, on_stop)

    def redraw() -> None:
        oled.show(make_fb(last, encs, held))

    try:
        request = gpiod.request_lines(
            CHIP_PATH,
            consumer="shieldxl-combined-in",
            config=config,
        )
    except OSError as exc:
        oled.close()
        fail(f"GPIO request failed: {exc}")

    with request:
        for st in encs.values():
            st.a = request.get_value(st.gpio_a)
            st.b = request.get_value(st.gpio_b)
            st.gray = ab_int(st.a, st.b)
        for name, off in BUTTONS.items():
            held[name] = request.get_value(off) == Value.INACTIVE
        redraw()
        print("ready", flush=True)

        while not stop:
            if not request.wait_edge_events(0.2):
                continue
            dirty = False
            for event in request.read_edge_events():
                kind = offset_kind.get(event.line_offset)
                if kind is None:
                    continue
                dt = time.monotonic() - t0
                if kind in BUTTONS:
                    pressed = event.event_type == EdgeEvent.Type.FALLING_EDGE
                    held[kind] = pressed
                    last = f"{kind} {'PRESS' if pressed else 'RELEASE'}"
                    print(f"{last}  t+{dt:.3f}s", flush=True)
                    dirty = True
                    continue
                st = encs[kind]
                bit = (
                    Value.ACTIVE
                    if event.event_type == EdgeEvent.Type.RISING_EDGE
                    else Value.INACTIVE
                )
                if event.line_offset == st.gpio_a:
                    st.a = bit
                elif event.line_offset == st.gpio_b:
                    st.b = bit
                new = ab_int(st.a, st.b)
                old = st.gray
                if new == old:
                    continue
                if (old, new) in CW:
                    delta = 1
                elif (old, new) in CCW:
                    delta = -1
                else:
                    st.gray = new
                    continue
                st.quarter += delta
                st.gray = new
                while st.quarter >= EDGES_PER_DETENT:
                    st.quarter -= EDGES_PER_DETENT
                    st.net += 1
                    last = f"{st.name} CW {st.net:+d}"
                    print(f"{st.name} CW +1  net={st.net}  t+{dt:.3f}s", flush=True)
                    dirty = True
                while st.quarter <= -EDGES_PER_DETENT:
                    st.quarter += EDGES_PER_DETENT
                    st.net -= 1
                    last = f"{st.name} CCW {st.net:+d}"
                    print(f"{st.name} CCW -1  net={st.net}  t+{dt:.3f}s", flush=True)
                    dirty = True
            if dirty:
                redraw()

    print("=== SUMMARY ===", flush=True)
    for n in BUTTONS:
        print(f"{n} held={held[n]}", flush=True)
    for n in ("E1", "E2", "E3"):
        print(f"{n} net={encs[n].net}", flush=True)
    oled.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
