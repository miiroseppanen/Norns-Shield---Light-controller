#!/usr/bin/env python3
"""Listen for Art-Net on 127.0.0.1:6454 only. Never sends datagrams."""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from light_console.artnet.packet import OP_DMX, parse_artnet  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Localhost Art-Net monitor (receive only)")
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=6454)
    p.add_argument("--seconds", type=float, default=0.0, help="0 = until Ctrl-C")
    p.add_argument("--channels", default="1,2,3", help="1-based DMX slots to print")
    p.add_argument("--dmx-only", action="store_true")
    args = p.parse_args()
    if args.bind not in ("127.0.0.1", "::1", "localhost"):
        print("FAIL: this monitor only binds loopback", file=sys.stderr)
        return 2
    slots = [int(x) for x in args.channels.split(",") if x.strip()]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.bind, args.port))
    sock.settimeout(0.25)
    print(f"listening {args.bind}:{args.port} (send is disabled)", flush=True)
    t0 = time.monotonic()
    n_dmx = 0
    try:
        while True:
            if args.seconds and (time.monotonic() - t0) >= args.seconds:
                break
            try:
                payload, addr = sock.recvfrom(2048)
            except TimeoutError:
                continue
            except socket.timeout:
                continue
            pkt = parse_artnet(payload)
            if pkt is None:
                print(f"ignore malformed {len(payload)}B from {addr[0]}", flush=True)
                continue
            if args.dmx_only and pkt.opcode != OP_DMX:
                continue
            if pkt.opcode == OP_DMX:
                n_dmx += 1
                ch = []
                for s in slots:
                    i = s - 1
                    val = pkt.data[i] if 0 <= i < len(pkt.data) else None
                    ch.append(f"{s}={val}")
                print(
                    f"ArtDMX src={addr[0]}:{addr[1]} port={pkt.port_address} "
                    f"net={pkt.net} sub={pkt.subnet} uni={pkt.universe} "
                    f"seq={pkt.sequence} len={pkt.length} {' '.join(ch)}",
                    flush=True,
                )
            else:
                print(f"{pkt.opcode_name} src={addr[0]}:{addr[1]}", flush=True)
    except KeyboardInterrupt:
        print("stop", flush=True)
    finally:
        sock.close()
    print(f"artdmx_count={n_dmx}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
