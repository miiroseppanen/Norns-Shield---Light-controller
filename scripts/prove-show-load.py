#!/usr/bin/env python3
"""Prove QLC 5.2.2 loads current.qxw with HTTP+WS. Does not touch production Pi.

Stops qlcplus.service only. Light Console must stay running.
Restores qlcplus.service at the end.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from light_console.qlc.launch import qml_argv, resolve_workspace
from light_console.qlc.ws_client import QlcWebSocketClient

SHOWS = Path("/home/light/shows")
CURRENT = SHOWS / "current.qxw"


def _active(unit: str) -> str:
    p = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
    return p.stdout.strip()


def _http() -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:9999/", timeout=2) as r:
            return r.status, r.read(120).decode("utf-8", "replace")
    except Exception as exc:
        return None, str(exc)[:80]


def _ws() -> dict:
    q = QlcWebSocketClient("ws://127.0.0.1:9999/qlcplusWS", reconnect_seconds=0.2)
    for t in (0.0, 0.3, 0.6, 1.0, 1.5):
        q.pump(t)
    out = {
        "connected": q.connected(),
        "project": q.project_loaded(),
        "functions": [(fn.function_id, fn.name) for fn in q.list_functions()],
        "n": getattr(q, "functions_number", 0),
    }
    q.close()
    return out


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.kill(proc.pid, signal.SIGKILL)


def trial(argv: list[str], seconds: float = 20.0) -> dict:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_LOGGING_RULES"] = "qt.qpa.*=false"
    log = Path("/tmp/qlc-workspace-trial.log")
    fh = log.open("wb")
    proc = subprocess.Popen(
        argv,
        env=env,
        stdout=fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    http = None
    ws = None
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            status, _ = _http()
            if status == 200:
                ws = _ws()
                http = status
                break
            time.sleep(0.5)
        else:
            http, _ = _http()
            ws = _ws()
        return {
            "argv": argv,
            "exit": proc.poll(),
            "http": http,
            "ws": ws,
        }
    finally:
        fh.close()
        _kill(proc)
        time.sleep(0.5)


def main() -> int:
    print("LC", _active("light-console.service"))
    ws = resolve_workspace(CURRENT, SHOWS)
    print("current", ws)
    print("stopping qlcplus.service for workspace trial")
    subprocess.check_call(["sudo", "-n", "systemctl", "stop", "qlcplus.service"])
    try:
        candidates = [
            qml_argv(ws),
            ["/usr/bin/qlcplus-qml", "-w", "-3", str(ws)],
            ["/usr/bin/qlcplus-qml", "-w", "-k", "-3", "-m", str(ws)],
        ]
        results = []
        for argv in candidates:
            print("TRY", argv, flush=True)
            results.append(trial(argv))
            print(results[-1], flush=True)
            if (
                results[-1]["http"] == 200
                and results[-1]["ws"]
                and results[-1]["ws"]["connected"]
                and results[-1]["ws"]["project"]
            ):
                print("PASS", argv)
                return 0
        print("FAIL no candidate served HTTP+loaded project")
        return 1
    finally:
        print("restoring qlcplus.service")
        subprocess.call(["sudo", "-n", "systemctl", "start", "qlcplus.service"])
        time.sleep(2)
        print("LC", _active("light-console.service"), "QLC", _active("qlcplus.service"))


if __name__ == "__main__":
    raise SystemExit(main())
