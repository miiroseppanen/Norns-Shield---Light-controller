"""QLC+ 5.2.2 WebSocket client. Reconnects; never starts or restarts QLC+."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import socket
import struct
import time
from collections.abc import Callable
from urllib.parse import urlparse

from light_console.output.dmx import DmxCache
from light_console.qlc.client import ConnectionState, QLCClient
from light_console.qlc.fake import WsTransport
from light_console.qlc.functions import QlcFunction
from light_console.qlc.runtime import STARTUP_NAME

LOG = logging.getLogger("light-console")

BACKOFF_CAP = 16.0
DRAIN_MAX_MSG = 64
DRAIN_BUDGET_S = 0.008
RECV_IDLE_S = 0.005


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


class SocketTransport(WsTransport):
    def __init__(self) -> None:
        self._sock: socket.socket | None = None

    def connect(self, host: str, port: int, path: str) -> None:
        sock = socket.create_connection((host, port), timeout=0.4)
        sock.settimeout(0.4)
        try:
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
            sock.settimeout(RECV_IDLE_S)
            self._sock = sock
        except OSError:
            try:
                sock.close()
            except OSError:
                pass
            raise

    def send_text(self, text: str) -> None:
        sock = self._sock
        if sock is None:
            raise OSError("not connected")
        sock.sendall(_mask_payload(text.encode("utf-8")))

    def recv_text(self) -> str | None:
        sock = self._sock
        if sock is None:
            raise OSError("not connected")
        try:
            msg = _read_text_frame(sock)
        except TimeoutError:
            return None
        except socket.timeout:
            return None
        return msg

    def close(self) -> None:
        sock = self._sock
        self._sock = None
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass


class QlcWebSocketClient(QLCClient):
    def __init__(
        self,
        url: str = "ws://127.0.0.1:9999/qlcplusWS",
        reconnect_seconds: float = 2.0,
        transport_factory: Callable[[], WsTransport] | None = None,
    ) -> None:
        self.url = url
        self.reconnect_seconds = reconnect_seconds
        self.reconnect_attempts = 0
        self._factory = transport_factory or SocketTransport
        self._transport: WsTransport | None = None
        self._state = ConnectionState.DISCONNECTED
        self._project = False
        self._next_retry = 0.0
        self._backoff = reconnect_seconds
        self._functions: list[QlcFunction] = []
        self.grand_master = 0
        self.blackout = False
        self.speed_bpm = 124
        self._closed = False
        self.gm_sends: list[int] = []
        self.function_sends: list[tuple[int, int]] = []
        self.functions_number = 0
        self._dmx = DmxCache()
        self.channel_requests: list[str] = []
        self._pending_status_id: int | None = None

    def connection_state(self) -> ConnectionState:
        return self._state

    def connected(self) -> bool:
        return self._state is ConnectionState.CONNECTED

    def project_loaded(self) -> bool:
        return self._project

    def host_label(self) -> str:
        host, _, _ = _parse_ws_url(self.url)
        if host in ("127.0.0.1", "::1"):
            return "localhost"
        return host

    def list_functions(self) -> list[QlcFunction]:
        return list(self._functions)

    def function_by_name(self, name: str) -> QlcFunction | None:
        for fn in self._functions:
            if fn.name == name:
                return fn
        return None

    def start_function_by_name(self, name: str) -> bool:
        fn = self.function_by_name(name)
        if fn is None:
            return False
        return self.set_function_status(fn.function_id, True)

    def stop_function_by_name(self, name: str) -> bool:
        fn = self.function_by_name(name)
        if fn is None:
            return False
        return self.set_function_status(fn.function_id, False)

    def toggle_function_by_name(self, name: str) -> bool:
        fn = self.function_by_name(name)
        if fn is None:
            return False
        return self.set_function_status(fn.function_id, not fn.running)

    def set_function_status(self, function_id: int, running: bool) -> bool:
        if not self.connected():
            return False
        bit = 1 if running else 0
        self.function_sends.append((int(function_id), bit))
        self._send(f"QLC+API|setFunctionStatus|{int(function_id)}|{bit}")
        for fn in self._functions:
            if fn.function_id == function_id:
                fn.running = running
        return True

    def set_grand_master(self, value_0_255: int) -> None:
        self.grand_master = max(0, min(255, value_0_255))
        if self.connected():
            self._send(f"GM_VALUE|{self.grand_master}")
            self.gm_sends.append(self.grand_master)

    def set_blackout(self, on: bool) -> None:
        self.blackout = on

    def set_speed(self, bpm: int) -> None:
        self.speed_bpm = bpm

    def all_off(self) -> None:
        self.clear_function_runtime()

    def clear_function_runtime(self) -> None:
        for fn in self._functions:
            fn.running = False
        self._pending_status_id = None

    def request_function_status(self, function_id: int) -> None:
        if not self.connected():
            return
        self._pending_status_id = int(function_id)
        self._send(f"QLC+API|getFunctionStatus|{int(function_id)}")

    def patch_output(self, universe: int, spec: str) -> None:
        if not spec.startswith("ArtNet|0"):
            LOG.warning("refusing non-loopback QLC+IO spec %s", spec)
            return
        self._send(f"QLC+IO|OUTPUT|{int(universe)}|{spec}")

    def set_simple_desk_channel(self, address_1_based: int, value: int) -> None:
        addr = max(1, int(address_1_based))
        val = max(0, min(255, int(value)))
        self._send(f"CH|{addr}|{val}")

    def request_channels_values(
        self, universe_1based: int, start: int = 1, count: int = 512
    ) -> None:
        if not self.connected():
            return
        uni = max(1, int(universe_1based))
        start = max(1, int(start))
        count = max(1, min(512, int(count)))
        self._dmx.begin_request(uni - 1)
        msg = f"QLC+API|getChannelsValues|{uni}|{start}|{count}"
        self.channel_requests.append(msg)
        self._send(msg)

    def dmx_snapshot(self, universe_0based: int) -> tuple[int, ...] | None:
        return self._dmx.snapshot(universe_0based)

    def clear_dmx(self) -> None:
        self._dmx.clear()

    def pump(self, now: float) -> None:
        if self._closed:
            return
        if self.connected():
            self._drain()
            return
        if now < self._next_retry:
            return
        self.reconnect_attempts += 1
        self._try_connect()
        if not self.connected():
            self._next_retry = now + self._backoff
            self._backoff = min(self._backoff * 2.0, BACKOFF_CAP)

    def close(self) -> None:
        self._closed = True
        self._drop(ConnectionState.DISCONNECTED)

    def _try_connect(self) -> None:
        host, port, path = _parse_ws_url(self.url)
        self._state = ConnectionState.CONNECTING
        transport = self._factory()
        try:
            transport.connect(host, port, path)
            self._transport = transport
            self._state = ConnectionState.CONNECTED
            self._backoff = self.reconnect_seconds
            self._send("QLC+API|isProjectLoaded")
            self._send("QLC+API|getFunctionsNumber")
            self._send("QLC+API|getFunctionsList")
            LOG.info("QLC websocket connected")
        except OSError as exc:
            LOG.debug("QLC connect failed: %s", exc)
            try:
                transport.close()
            except OSError:
                pass
            self._transport = None
            self._state = ConnectionState.ERROR
            self._project = False

    def _send(self, text: str) -> None:
        transport = self._transport
        if transport is None or not self.connected():
            return
        try:
            transport.send_text(text)
        except OSError:
            self._drop(ConnectionState.ERROR)

    def _drain(self) -> None:
        transport = self._transport
        if transport is None:
            return
        deadline = time.monotonic() + DRAIN_BUDGET_S
        n = 0
        try:
            while n < DRAIN_MAX_MSG and time.monotonic() < deadline:
                msg = transport.recv_text()
                if msg is None:
                    break
                self._on_message(msg)
                n += 1
        except OSError:
            self._drop(ConnectionState.ERROR)

    def _on_message(self, msg: str) -> None:
        parts = msg.split("|")
        if len(parts) >= 3 and parts[0] == "QLC+API" and parts[1] == "isProjectLoaded":
            loaded = parts[2].lower() in ("true", "1", "yes")
            if loaded:
                self._project = True
            elif not self._functions and self.functions_number == 0:
                self._project = False
        elif len(parts) >= 3 and parts[0] == "QLC+API" and parts[1] == "getFunctionsNumber":
            try:
                self.functions_number = int(parts[2])
            except ValueError:
                return
            if self.functions_number > 0:
                self._project = True
        elif len(parts) >= 2 and parts[0] == "QLC+API" and parts[1] == "getFunctionsList":
            funcs: list[QlcFunction] = []
            rest = parts[2:]
            for i in range(0, len(rest) - 1, 2):
                try:
                    fid = int(rest[i])
                except ValueError:
                    continue
                funcs.append(QlcFunction(fid, rest[i + 1], "Unknown"))
            self._functions = funcs
            if funcs:
                self._project = True
            for fn in funcs:
                if fn.name == STARTUP_NAME:
                    self.request_function_status(fn.function_id)
                    break
        elif len(parts) >= 3 and parts[0] == "FUNCTION":
            try:
                fid = int(parts[1])
            except ValueError:
                return
            word = parts[2]
            running = "Running" in word or word.upper() == "RUNNING"
            for fn in self._functions:
                if fn.function_id == fid:
                    fn.running = running
                    break
        elif len(parts) >= 3 and parts[0] == "QLC+API" and parts[1] == "getFunctionStatus":
            fid = self._pending_status_id
            word = parts[2]
            if len(parts) >= 4:
                try:
                    fid = int(parts[2])
                except ValueError:
                    fid = self._pending_status_id
                word = parts[3]
            if fid is None:
                return
            running = "Running" in word or word.upper() == "RUNNING"
            for fn in self._functions:
                if fn.function_id == fid:
                    fn.running = running
                    break
        elif len(parts) >= 4 and parts[0] == "QLC+API" and parts[1] == "getFunctionType":
            try:
                fid = int(parts[2])
            except ValueError:
                return
            type_name = parts[3]
            for fn in self._functions:
                if fn.function_id == fid:
                    fn.type = type_name
        elif len(parts) >= 2 and parts[0] == "GM_VALUE":
            try:
                self.grand_master = int(parts[1])
            except ValueError:
                return
        elif len(parts) >= 2 and parts[0] == "QLC+API" and parts[1] == "getChannelsValues":
            self._dmx.ingest(msg)

    def _drop(self, state: ConnectionState) -> None:
        transport = self._transport
        self._transport = None
        self._state = state
        self._project = False
        self._dmx.clear()
        self.clear_function_runtime()
        if transport is not None:
            try:
                transport.close()
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
