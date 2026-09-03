#!/usr/bin/env python3
"""Prove QLC 5.2.2 WebAccess POST /loadProject with show-a.qxw.

Reproduces the browser form: multipart/form-data field name=qlcprj.
Does not restart QLC. Does not load a production workspace.
"""

from __future__ import annotations

import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

QXW = Path("/home/light/shows/show-a.qxw")
BOUNDARY = "----LightConsoleFormBoundary7MA4YWxkTrZu0gW"
FORBIDDEN = ("192.168.88.201", "192.168.88.248", "192.168.88.246", "10.42.")


def ws_query() -> tuple[str, str, str]:
    s = socket.create_connection(("127.0.0.1", 9999), 3)
    key = __import__("base64").b64encode(os.urandom(16)).decode("ascii")
    req = (
        "GET /qlcplusWS HTTP/1.1\r\n"
        "Host: 127.0.0.1:9999\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    s.sendall(req.encode("ascii"))
    hdr = b""
    while b"\r\n\r\n" not in hdr:
        chunk = s.recv(4096)
        if not chunk:
            break
        hdr += chunk

    def send(text: str) -> None:
        payload = text.encode("utf-8")
        header = bytearray([0x81, 0x80 | len(payload), 0, 0, 0, 0])
        s.sendall(bytes(header) + payload)

    def recv() -> str:
        hdr2 = s.recv(2)
        if len(hdr2) < 2:
            return ""
        ln = hdr2[1] & 0x7F
        if ln == 126:
            ln = int.from_bytes(s.recv(2), "big")
        data = b""
        while len(data) < ln:
            chunk = s.recv(ln - len(data))
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


def http_status() -> int | str:
    try:
        return urllib.request.urlopen("http://127.0.0.1:9999/", timeout=3).status
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def main() -> int:
    if os.environ.get("CONFIRM_WEBACCESS_LOAD") != "1":
        print("refusing: this POST can wedge QLC WebAccess on offscreen QML")
        print("set CONFIRM_WEBACCESS_LOAD=1 only for an explicit research run")
        return 3
    xml = QXW.read_bytes()
    text = xml.decode("utf-8")
    for host in FORBIDDEN:
        if host in text:
            print("UNSAFE", host)
            return 2
    if 'outputIP="127.0.0.1"' not in text:
        print("UNSAFE missing loopback")
        return 2
    print("SHOW_A_SAFE bytes", len(xml))
    print("BEFORE_HTTP", http_status())
    print("BEFORE_WS", ws_query())

    body = (
        f"--{BOUNDARY}\r\n"
        'Content-Disposition: form-data; name="qlcprj"; filename="show-a.qxw"\r\n'
        "Content-Type: application/octet-stream\r\n"
        "\r\n"
    ).encode("utf-8") + xml + f"\r\n--{BOUNDARY}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:9999/loadProject",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={BOUNDARY}",
            "Content-Length": str(len(body)),
        },
    )
    t0 = time.monotonic()
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        payload = resp.read().decode("utf-8", "replace")
        print("LOAD_HTTP", resp.status, "elapsed", round(time.monotonic() - t0, 2))
        print("LOAD_BODY_HEAD", " | ".join(payload.splitlines()[:8]))
    except urllib.error.URLError as exc:
        print("LOAD_EXC", exc, "elapsed", round(time.monotonic() - t0, 2))

    after = None
    for i in range(16):
        time.sleep(0.5)
        code = http_status()
        try:
            after = ws_query()
        except OSError as exc:
            print("POLL", i, "http", code, "WS_FAIL", exc)
            continue
        print("POLL", i, "http", code, after)
        loaded, n, _lst = after
        if loaded.endswith("|true") or (n.rsplit("|", 1)[-1] not in ("", "0")):
            break
    print("FINAL_HTTP", http_status())
    print("FINAL_WS", after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
