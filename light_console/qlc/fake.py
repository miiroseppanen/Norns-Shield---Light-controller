"""Testable WebSocket transport. GPIO/UI never import this module."""

from __future__ import annotations

from abc import ABC, abstractmethod


class WsTransport(ABC):
    @abstractmethod
    def connect(self, host: str, port: int, path: str) -> None:
        ...

    @abstractmethod
    def send_text(self, text: str) -> None:
        ...

    @abstractmethod
    def recv_text(self) -> str | None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...


class FakeTransport(WsTransport):
    """In-memory QLC+ 5.2.2 WebSocket stand-in."""

    def __init__(self) -> None:
        self.fail_connect = False
        self.drop_after_send = False
        self.alive = False
        self.sent: list[str] = []
        self.inbox: list[str] = []
        self.connect_count = 0
        self.project_loaded = True
        self.gm: int | None = None

    def connect(self, host: str, port: int, path: str) -> None:
        del host, port, path
        self.connect_count += 1
        if self.fail_connect:
            raise OSError("connection refused")
        self.alive = True

    def send_text(self, text: str) -> None:
        if not self.alive:
            raise OSError("not connected")
        self.sent.append(text)
        if text == "QLC+API|isProjectLoaded":
            flag = "true" if self.project_loaded else "false"
            self.inbox.append(f"QLC+API|isProjectLoaded|{flag}")
        elif text.startswith("GM_VALUE|"):
            value = int(text.split("|", 1)[1])
            self.gm = value
            self.inbox.append(f"GM_VALUE|{value}|{value}")
        if self.drop_after_send:
            self.alive = False
            raise OSError("connection reset")

    def recv_text(self) -> str | None:
        if not self.alive:
            raise OSError("not connected")
        if not self.inbox:
            return None
        return self.inbox.pop(0)

    def close(self) -> None:
        self.alive = False

    def drop(self) -> None:
        self.alive = False
