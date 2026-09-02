"""QLC+ 5 WebSocket client. Reconnects; never starts or restarts QLC+."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import socket
import struct
from urllib.parse import urlparse

from light_console.qlc.client import QLCClient
from light_console.qlc.functions import QlcFunction

LOG = logging.getLogger("light-console")


def _parse_ws_url(url: str) -> tuple[str, int, str]:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "wss" else 9999)
    path = parsed.path or "/qlcplusWS"
    return host, port, path


def _mask_payload(payload: bytes) -> bytes:
    key = os.urandom(4)
    masked = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
    n = len(payload)
    if n < 126:
        header = bytes([0x81, 0x80 | n])
    elif n < 65536:
        header = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
    else:
        header = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
    return header + key + masked


class QlcWebSocketClient(QLCClient):
    def __init__(self, url: str = "ws://127.0.0.1:9999/qlcplusWS", reconnect_seconds: float = 2.0) -> None:
        self.url = url
        self.reconnect_seconds = reconnect_seconds
        self.reconnect_attempts = 0
        self._sock: socket.socket | None = None
        self._connected = False
        self._project = False
        self._next_retry = 0.0
        self._functions: list[QlcFunction] = []
        self.grand_master = 0
        self.blackout = False
        self.speed_bpm = 124

    def connected(self) -> bool:
        return self._connected

    def project_loaded(self) -> bool:
        return self._project

    def list_functions(self) -> list[QlcFunction]:
        return list(self._functions)

    def function_by_name(self, name: str) -> QlcFunction | None:
        for fn in self._functions:
            if fn.name == name:
                return fn
        return None

    def start_function_by_name(self, name: str) -> bool:
        del name
        return False

    def stop_function_by_name(self, name: str) -> bool:
        del name
        return False

    def toggle_function_by_name(self, name: str) -> bool:
        del name
        return False

    def set_grand_master(self, value_0_255: int) -> None:
        self.grand_master = max(0, min(255, value_0_255))
        self._send(f"GM_VALUE|{self.grand_master}")

    def set_blackout(self, on: bool) -> None:
        self.blackout = on

    def set_speed(self, bpm: int) -> None:
        self.speed_bpm = bpm

    def all_off(self) -> None:
        return

    def pump(self, now: float) -> None:
        if self._connected:
            self._drain()
            return
        if now < self._next_retry:
            return
        self.reconnect_attempts += 1
        self._next_retry = now + self.reconnect_seconds
        self._try_connect()

    def close(self) -> None:
        self._drop()

    def _try_connect(self) -> None:
        host, port, path = _parse_ws_url(self.url)
        sock: socket.socket | None = None
        try:
            sock = socket.create_connection((host, port), timeout=0.4)
            sock.settimeout(0.4)
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            req = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "\r\n"
            )
            sock.sendall(req.encode("ascii"))
            header = _read_http_headers(sock)
            if "101" not in header.split("\r\n", 1)[0]:
                raise OSError("websocket handshake rejected")
            accept = ""
            for line in header.split("\r\n"):
                if line.lower().startswith("sec-websocket-accept:"):
                    accept = line.split(":", 1)[1].strip()
            expected = base64.b64encode(
                hashlib.sha1(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
                ).digest()
            ).decode("ascii")
            if accept and accept != expected:
                raise OSError("websocket accept mismatch")
            sock.settimeout(0.05)
            self._sock = sock
            self._connected = True
            self._send("QLC+API|isProjectLoaded")
            LOG.info("QLC websocket connected")
        except OSError as exc:
            LOG.debug("QLC connect failed: %s", exc)
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            self._drop()

    def _send(self, text: str) -> None:
        sock = self._sock
        if sock is None or not self._connected:
            return
        try:
            sock.sendall(_mask_payload(text.encode("utf-8")))
        except OSError:
            self._drop()

    def _drain(self) -> None:
        sock = self._sock
        if sock is None:
            return
        try:
            while True:
                msg = _read_text_frame(sock)
                if msg is None:
                    break
                self._on_message(msg)
        except TimeoutError:
            return
        except OSError:
            self._drop()

    def _on_message(self, msg: str) -> None:
        parts = msg.split("|")
        if len(parts) >= 3 and parts[0] == "QLC+API" and parts[1] == "isProjectLoaded":
            self._project = parts[2].lower() in ("true", "1", "yes")

    def _drop(self) -> None:
        sock = self._sock
        self._sock = None
        self._connected = False
        self._project = False
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def _read_http_headers(sock: socket.socket) -> str:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(1024)
        if not chunk:
            raise OSError("handshake closed")
        buf += chunk
        if len(buf) > 8192:
            raise OSError("handshake too large")
    return buf.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1", errors="replace")


def _read_text_frame(sock: socket.socket) -> str | None:
    header = _recv_exact(sock, 2)
    if header is None:
        return None
    opcode = header[0] & 0x0F
    masked = header[1] & 0x80
    length = header[1] & 0x7F
    if length == 126:
        ext = _recv_exact(sock, 2)
        if ext is None:
            raise OSError("short frame")
        length = struct.unpack(">H", ext)[0]
    elif length == 127:
        ext = _recv_exact(sock, 8)
        if ext is None:
            raise OSError("short frame")
        length = struct.unpack(">Q", ext)[0]
    mask = b""
    if masked:
        mask_b = _recv_exact(sock, 4)
        if mask_b is None:
            raise OSError("short mask")
        mask = mask_b
    payload = _recv_exact(sock, length) if length else b""
    if payload is None:
        raise OSError("short payload")
    if mask:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    if opcode == 0x8:
        raise OSError("websocket close")
    if opcode == 0x9:
        return None
    if opcode != 0x1:
        return None
    return payload.decode("utf-8", errors="replace")


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except TimeoutError:
            if not buf:
                return None
            raise
        except socket.timeout:
            if not buf:
                return None
            raise TimeoutError from None
        if not chunk:
            if not buf:
                raise OSError("socket closed")
            raise OSError("short read")
        buf += chunk
    return buf
