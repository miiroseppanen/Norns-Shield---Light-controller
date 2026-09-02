#!/usr/bin/env python3
"""0.6B localhost Art-Net proof. Does not send to PKNight / LAN / WiZ.

Requires QLC+ already serving ws://127.0.0.1:9999 (qlcplus.service -w).
Does not restart Light Console. May be run while qlcplus is up.
"""

from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from light_console.artnet.destinations import classify_destination  # noqa: E402
from light_console.artnet.packet import OP_DMX, parse_artnet  # noqa: E402
from light_console.qlc.ws_client import QlcWebSocketClient  # noqa: E402

LOOPBACK = "127.0.0.1"
PORT = 6454
# QLC+IO: universe index 0 = UI Universe 1; ArtNet line 0 = 127.0.0.1 (never line 1 = 192.168.88.246)
PATCH = "QLC+IO|OUTPUT|0|ArtNet|0"  # documented in research; client uses ArtNet|0 only
LEAK_IFACE = "192.168.88.246"


class Receiver:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.settimeout(0.2)
        self.frames: list[tuple[float, object, tuple]] = []

    def drain(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                payload, addr = self.sock.recvfrom(2048)
            except TimeoutError:
                continue
            except socket.timeout:
                continue
            pkt = parse_artnet(payload)
            if pkt is None or pkt.opcode != OP_DMX:
                continue
            self.frames.append((time.monotonic(), pkt, addr))

    def close(self) -> None:
        self.sock.close()


def wait_ch1(
    rx: Receiver, expected: int, mark: int, timeout: float = 8.0, slop: int = 2
) -> int | None:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        rx.drain(0.3)
        chunk = rx.frames[mark:]
        if not chunk:
            continue
        data = chunk[-1][1].data
        last = data[0] if data else None
        if last is not None and abs(last - expected) <= slop:
            return last
    return last


def main() -> int:
    assert classify_destination(LOOPBACK).value == "safe_loopback"
    leak = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    leak.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    leak_ok = False
    try:
        leak.bind((LEAK_IFACE, PORT))
        leak.settimeout(0.1)
        leak_ok = True
    except OSError as exc:
        print(f"leak_bind_skip {exc}")
        leak.close()
        leak = None

    rx = Receiver(LOOPBACK, PORT)
    print("monitor_bind", LOOPBACK, PORT)

    print("phase1_qlc_should_be_up_or_we_still_sample_idle")
    n0 = len(rx.frames)
    rx.drain(2.0)
    idle_new = len(rx.frames) - n0
    print(f"idle_artdmx_before_patch={idle_new}")

    qlc = QlcWebSocketClient("ws://127.0.0.1:9999/qlcplusWS", reconnect_seconds=0.2)
    qlc.pump(0.0)
    qlc.pump(0.4)
    print("ws", qlc.connection_state().value, "connected", qlc.connected())
    if not qlc.connected():
        rx.close()
        qlc.close()
        return 1

    qlc.patch_output(0, "ArtNet|0")
    qlc.set_grand_master(255)
    time.sleep(0.3)
    qlc.pump(time.monotonic())

    observed: list[tuple[int, int | None]] = []
    for value in (0, 128, 255, 0):
        before = len(rx.frames)
        qlc.set_simple_desk_channel(1, value)
        qlc.pump(time.monotonic())
        got = wait_ch1(rx, value, before)
        observed.append((value, got))
        print(f"ch1_set={value} ch1_art={got} new_frames={len(rx.frames) - before}")
        if rx.frames:
            pkt = rx.frames[-1][1]
            print(
                f"  last seq={pkt.sequence} len={pkt.length} port={pkt.port_address}"
            )

    # Rate: hold a non-zero slot and listen (QLC Standard = change + ~2s refresh)
    qlc.set_simple_desk_channel(1, 128)
    qlc.pump(time.monotonic())
    mark = len(rx.frames)
    t0 = time.monotonic()
    rx.drain(2.0)
    dt = time.monotonic() - t0
    n = len(rx.frames) - mark
    hz = n / dt if dt else 0.0
    print(f"rate_artdmx={n} in {dt:.2f}s ({hz:.1f}/s)")

    leak_count = 0
    if leak is not None:
        try:
            while True:
                leak.recvfrom(2048)
                leak_count += 1
        except (TimeoutError, socket.timeout, OSError):
            pass
        leak.close()
    print(f"wlan0_6454_datagrams={leak_count}")

    bad_src = [
        addr[0]
        for _, _, addr in rx.frames
        if addr[0] not in ("127.0.0.1", "::1")
    ]
    print("non_loopback_sources", bad_src[:5], "count", len(bad_src))
    unis = {pkt.port_address for _, pkt, _ in rx.frames[-20:]}
    print("port_addresses_tail", unis)

    qlc.close()
    rx.close()

    ok = all(v is not None and abs(v - gm) <= 2 for gm, v in observed)
    if leak_count:
        print("FAIL leak to wlan0:6454")
        return 1
    if bad_src:
        print("FAIL ArtDMX source not loopback")
        return 1
    if not ok:
        print("FAIL channel proof", observed)
        return 1
    print("PROOF_OK", observed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
