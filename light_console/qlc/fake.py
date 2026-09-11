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
        self.desk: list[tuple[int, int]] = []
        self.io: list[str] = []
        self.dmx: dict[int, dict[int, int]] = {}
        self.functions: list[tuple[int, str]] = [(0, "Warm"), (1, "Blue")]
        self.function_sends: list[tuple[int, int]] = []
        self.function_running: dict[int, str] = {}

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
        elif text == "QLC+API|getFunctionsNumber":
            self.inbox.append(f"QLC+API|getFunctionsNumber|{len(self.functions)}")
        elif text == "QLC+API|getFunctionsList":
            parts = ["QLC+API", "getFunctionsList"]
            for fid, name in self.functions:
                parts.extend([str(fid), name])
            self.inbox.append("|".join(parts))
        elif text.startswith("QLC+API|getFunctionStatus|"):
            bits = text.split("|")
            fid = int(bits[2]) if len(bits) > 2 else -1
            word = self.function_running.get(fid, "Stopped")
            self.inbox.append(f"QLC+API|getFunctionStatus|{word}")
        elif text.startswith("QLC+API|setFunctionStatus|"):
            bits = text.split("|")
            if len(bits) >= 4:
                fid = int(bits[2])
                bit = int(bits[3])
                self.function_sends.append((fid, bit))
                self.function_running[fid] = "Running" if bit else "Stopped"
        elif text.startswith("GM_VALUE|"):
            value = int(text.split("|", 1)[1])
            self.gm = value
            self.inbox.append(f"GM_VALUE|{value}|{value}")
        elif text.startswith("CH|"):
            parts = text.split("|")
            if len(parts) >= 3:
                self.desk.append((int(parts[1]), int(parts[2])))
        elif text.startswith("QLC+API|getChannelsValues|"):
            bits = text.split("|")
            uni = int(bits[2]) if len(bits) > 2 else 1
            start = int(bits[3]) if len(bits) > 3 else 1
            count = int(bits[4]) if len(bits) > 4 else 1
            values = getattr(self, "dmx", {}).get(uni - 1, {})
            parts = ["QLC+API", "getChannelsValues"]
            for ch in range(start, start + count):
                val = int(values.get(ch, 0))
                parts.extend([str(ch), str(val), "Intensity", "0"])
            self.inbox.append("|".join(parts))
        elif text.startswith("QLC+IO|"):
            self.io.append(text)
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
