"""Port of production /home/valot/start_qlc_chaser.py.

Waits for QLC WebSocket, finds function name `startup`, selects VC page 1,
starts the chaser if it is not already running. Never starts or restarts QLC.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from light_console.qlc.ws_client import SocketTransport, _parse_ws_url

LOG = logging.getLogger("qlc-startup")
URL = "ws://127.0.0.1:9999/qlcplusWS"
TARGET = "startup"
VC_PAGE_INDEX = 1
STATUS_PATH = Path("/tmp/qlc-startup.status")
ATTEMPTS = 90
RETRY_S = 2.0
CONNECT_TIMEOUT_S = 3.0
RECV_TIMEOUT_S = 5.0


class StartupError(RuntimeError):
    """QLC was reachable but startup could not be armed."""


def _write_status(status: str, **fields: str) -> None:
    lines = [f"status={status}"]
    for key, value in fields.items():
        lines.append(f"{key}={value}")
    try:
        STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        LOG.warning("could not write %s", STATUS_PATH)


def _recv_prefixed(transport: SocketTransport, prefix: str, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        sock = getattr(transport, "_sock", None)
        if sock is not None:
            sock.settimeout(min(0.4, remaining))
        msg = transport.recv_text()
        if msg is None:
            continue
        if msg.startswith(prefix):
            return msg
    raise StartupError(f"no reply: {prefix}")


def _select_vc_page(transport: SocketTransport, page: int) -> None:
    expected = f"VC_PAGE|{page}"
    try:
        transport.send_text(expected)
        msg = _recv_prefixed(transport, "VC_PAGE|", timeout=3.0)
        if msg == expected:
            LOG.warning("VC page %s selected", page)
            return
        raise StartupError(f"unexpected reply {msg!r}")
    except Exception as exc:
        LOG.warning("VC page %s selection failed (%s); continuing", page, exc)


def _function_list(transport: SocketTransport) -> list[tuple[str, str]]:
    transport.send_text("QLC+API|getFunctionsList")
    reply = _recv_prefixed(transport, "QLC+API|getFunctionsList|", timeout=RECV_TIMEOUT_S)
    parts = reply.split("|")[2:]
    found: list[tuple[str, str]] = []
    for i in range(0, len(parts) - 1, 2):
        found.append((parts[i], parts[i + 1]))
    return found


def _function_status(transport: SocketTransport, fid: str) -> str:
    transport.send_text(f"QLC+API|getFunctionStatus|{fid}")
    return _recv_prefixed(transport, "QLC+API|getFunctionStatus|", timeout=RECV_TIMEOUT_S)


def run_once(transport: SocketTransport, settle=time.sleep) -> str:
    functions = _function_list(transport)
    _select_vc_page(transport, VC_PAGE_INDEX)
    matches = [(fid, name) for fid, name in functions if name == TARGET]
    if len(matches) != 1:
        raise StartupError(f"Expected exactly one '{TARGET}', found {len(matches)}")
    fid, _name = matches[0]
    LOG.warning("Found %s: ID %s", TARGET, fid)
    transport.send_text(f"QLC+API|getFunctionType|{fid}")
    type_reply = _recv_prefixed(transport, "QLC+API|getFunctionType|", timeout=RECV_TIMEOUT_S)
    if "Chaser" not in type_reply:
        raise StartupError("startup is not a Chaser")
    status = _function_status(transport, fid)
    if "Running" in status:
        LOG.warning("startup already Running")
        _write_status("RUNNING", id=fid, name=TARGET, note="already-active")
        return "RUNNING"
    settle(2.0)
    transport.send_text(f"QLC+API|setFunctionStatus|{fid}|1")
    settle(1.0)
    status = _function_status(transport, fid)
    if "Running" not in status:
        raise StartupError(f"startup did not enter Running state: {status}")
    LOG.warning("STARTUP CHASER RUNNING")
    _write_status("RUNNING", id=fid, name=TARGET)
    return "RUNNING"


def connect(url: str = URL) -> SocketTransport:
    host, port, path = _parse_ws_url(url)
    transport = SocketTransport()
    transport.connect(host, port, path)
    sock = transport._sock
    if sock is not None:
        sock.settimeout(0.4)
    return transport


def main(argv: list[str] | None = None) -> int:
    del argv
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    _write_status("WAIT")
    last = "not attempted"
    for attempt in range(1, ATTEMPTS + 1):
        transport: SocketTransport | None = None
        try:
            transport = connect()
            run_once(transport)
            return 0
        except Exception as exc:
            last = str(exc)
            LOG.warning("Attempt %s/%s: %s", attempt, ATTEMPTS, exc)
            time.sleep(RETRY_S)
        finally:
            if transport is not None:
                transport.close()
    _write_status("FAIL", error=last[:120])
    LOG.warning("Could not start startup chaser")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
