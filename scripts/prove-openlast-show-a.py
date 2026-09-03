#!/usr/bin/env python3
"""One bounded qlcplus-qml -w -9 trial with show-a. Does not change systemd unit."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

SHOW_A = Path("/home/light/shows/show-a.qxw")
CONF = Path("/home/light/.config/qlcplus/Q Light Controller Plus.conf")
BACKUP = Path("/tmp/qlcplus-qsettings.pre-openlast.conf")
LOG = Path("/tmp/qlcplus-openlast-trial.log")
EXPECTED = {
    0: "Warm",
    1: "Blue",
    2: "Red",
    3: "Slow Pulse",
    4: "Color Sweep",
}
FORBIDDEN = ("192.168.88.201", "192.168.88.248", "192.168.88.246", "10.42.")


def http_status() -> int | None:
    try:
        return urllib.request.urlopen("http://127.0.0.1:9999/", timeout=2).status
    except Exception:
        return None


def port_owner() -> str:
    p = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if ":9999" in line:
            return line.strip()
    return "(free)"


def ws_query() -> tuple[str, str, str] | str:
    try:
        s = socket.create_connection(("127.0.0.1", 9999), 3)
    except OSError as exc:
        return str(exc)
    key = __import__("base64").b64encode(os.urandom(16)).decode("ascii")
    s.sendall(
        (
            "GET /qlcplusWS HTTP/1.1\r\nHost: 127.0.0.1:9999\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
    )
    hdr = b""
    while b"\r\n\r\n" not in hdr:
        chunk = s.recv(4096)
        if not chunk:
            break
        hdr += chunk

    def send(text: str) -> None:
        payload = text.encode()
        s.sendall(bytes([0x81, 0x80 | len(payload), 0, 0, 0, 0]) + payload)

    def recv() -> str:
        h = s.recv(2)
        if len(h) < 2:
            return ""
        n = h[1] & 0x7F
        if n == 126:
            n = int.from_bytes(s.recv(2), "big")
        data = b""
        while len(data) < n:
            chunk = s.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        return data.decode("utf-8", "replace")

    send("QLC+API|isProjectLoaded")
    a = recv()
    send("QLC+API|getFunctionsNumber")
    b = recv()
    send("QLC+API|getFunctionsList")
    c = recv()
    s.close()
    return a, b, c


def unit_pid() -> str:
    p = subprocess.run(
        ["systemctl", "show", "-p", "MainPID", "--value", "qlcplus"],
        capture_output=True,
        text=True,
    )
    return p.stdout.strip()


def stop_unit() -> None:
    subprocess.check_call(["sudo", "-n", "systemctl", "stop", "qlcplus"])
    for _ in range(20):
        pid = unit_pid()
        if pid in ("", "0") and http_status() is None:
            return
        time.sleep(0.3)
    raise RuntimeError(f"qlcplus still running pid={unit_pid()} port={port_owner()}")


def start_unit() -> None:
    subprocess.check_call(["sudo", "-n", "systemctl", "start", "qlcplus"])
    for _ in range(40):
        if http_status() == 200 and unit_pid() not in ("", "0"):
            return
        time.sleep(0.5)
    raise RuntimeError("systemd qlcplus did not return HTTP 200")


def terminate(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    time.sleep(0.3)


def main() -> int:
    if os.environ.get("CONFIRM_OPENLAST_TRIAL") != "1":
        print("refusing: -w -9 can wedge QLC before :9999 binds")
        print("set CONFIRM_OPENLAST_TRIAL=1 only for an explicit research run")
        return 3
    xml = SHOW_A.read_text(encoding="utf-8")
    for host in FORBIDDEN:
        if host in xml:
            print("UNSAFE", host)
            return 2
    if 'outputIP="127.0.0.1"' not in xml:
        print("UNSAFE missing loopback")
        return 2
    print("SHOW_A_SAFE", SHOW_A, SHOW_A.stat().st_size)
    print("BASELINE_PID", unit_pid())
    print("BASELINE_PORT", port_owner())
    print("BASELINE_HTTP", http_status())
    orig = CONF.read_text(encoding="utf-8")
    BACKUP.write_text(orig, encoding="utf-8")
    print("QSETTINGS_BEFORE")
    print(orig)
    configured = orig.rstrip() + "\n\n[workspace]\nrecent0=/home/light/shows/show-a.qxw\n"
    CONF.write_text(configured, encoding="utf-8")
    print("QSETTINGS_CONFIGURED recent0=/home/light/shows/show-a.qxw")

    print("STOP_UNIT")
    stop_unit()
    print("PORT_AFTER_STOP", port_owner())

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_LOGGING_RULES"] = "qt.qpa.*=false"
    logf = LOG.open("wb")
    proc = subprocess.Popen(
        ["/usr/bin/qlcplus-qml", "-w", "-9"],
        cwd="/home/light/light-console",
        env=env,
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    test_pid = proc.pid
    print("TRIAL_PID", test_pid, "argv=qlcplus-qml -w -9")
    http = None
    ws: tuple[str, str, str] | str | None = None
    try:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                print("TRIAL_EXIT", proc.returncode)
                break
            http = http_status()
            if http == 200:
                ws = ws_query()
                print("BOUND_HTTP", http, "elapsed", round(20.0 - (deadline - time.monotonic()), 2))
                print("WS", ws)
                break
            time.sleep(0.5)
        else:
            print("HTTP_NEVER_BOUND timeout=20s")
            print("TRIAL_STILL_RUNNING", proc.poll() is None)
    finally:
        logf.close()
        print("TERMINATE_TRIAL_PID", test_pid)
        terminate(test_pid)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        CONF.write_text(BACKUP.read_text(encoding="utf-8"), encoding="utf-8")
        print("QSETTINGS_RESTORED")
        print("START_UNIT")
        start_unit()
        print("RESTORED_PID", unit_pid())
        print("RESTORED_PORT", port_owner())
        print("RESTORED_HTTP", http_status())
        print("RESTORED_WS", ws_query())
        exec_start = subprocess.check_output(
            ["systemctl", "show", "-p", "ExecStart", "--value", "qlcplus"],
            text=True,
        )
        print("RESTORED_EXEC", exec_start.strip())
        if "-9" in exec_start:
            print("FAIL unit still has -9")
            return 3

    if http != 200:
        print("RESULT HTTP_FAIL")
        return 1
    if not isinstance(ws, tuple):
        print("RESULT WS_FAIL", ws)
        return 1
    loaded, number, flist = ws
    print("LOADED", loaded)
    print("NUMBER", number)
    print("LIST", flist)
    ok = True
    if not loaded.endswith("|true"):
        ok = False
    parts = flist.split("|")
    rest = parts[2:] if len(parts) >= 2 else []
    got: dict[int, str] = {}
    for i in range(0, len(rest) - 1, 2):
        try:
            got[int(rest[i])] = rest[i + 1]
        except ValueError:
            continue
    print("PARSED", got)
    if got != EXPECTED:
        ok = False
        print("FUNCTION_MISMATCH expected", EXPECTED)
    print("RESULT", "PASS" if ok else "PARTIAL_HTTP")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
