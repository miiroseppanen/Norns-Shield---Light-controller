from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum

from light_console.qlc.functions import QlcFunction
from light_console.state import DEFAULT_FUNCTIONS

LOG = logging.getLogger("light-console")


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class QLCClient(ABC):
    @abstractmethod
    def connected(self) -> bool:
        ...

    def connection_state(self) -> ConnectionState:
        return ConnectionState.CONNECTED if self.connected() else ConnectionState.DISCONNECTED

    @abstractmethod
    def project_loaded(self) -> bool:
        ...

    @abstractmethod
    def list_functions(self) -> list[QlcFunction]:
        ...

    @abstractmethod
    def function_by_name(self, name: str) -> QlcFunction | None:
        ...

    @abstractmethod
    def start_function_by_name(self, name: str) -> bool:
        ...

    @abstractmethod
    def stop_function_by_name(self, name: str) -> bool:
        ...

    @abstractmethod
    def toggle_function_by_name(self, name: str) -> bool:
        ...

    @abstractmethod
    def set_grand_master(self, value_0_255: int) -> None:
        ...

    @abstractmethod
    def set_blackout(self, on: bool) -> None:
        ...

    @abstractmethod
    def set_speed(self, bpm: int) -> None:
        ...

    @abstractmethod
    def all_off(self) -> None:
        ...

    def patch_output(self, universe: int, spec: str) -> None:
        """QLC+IO|OUTPUT|<uni>|<Plugin>|<line> as used by the 5.2.2 /config page."""
        del universe, spec

    def set_simple_desk_channel(self, address_1_based: int, value: int) -> None:
        """Documented Simple Desk: CH|<abs>|<0-255>."""
        del address_1_based, value

    def pump(self, now: float) -> None:
        """Background reconnect. Must never restart the QLC process."""
        del now

    def close(self) -> None:
        return

    def host_label(self) -> str:
        return "localhost"


class MockQLCClient(QLCClient):
    """In-process QLC stand-in for the Mac simulator and unit tests."""

    def __init__(self, names: tuple[str, ...] = DEFAULT_FUNCTIONS) -> None:
        self._state = ConnectionState.DISCONNECTED
        self._project = False
        self._want_connected = True
        self._functions = [
            QlcFunction(i, name, "Scene" if name != "CHASE" else "Chaser")
            for i, name in enumerate(names)
        ]
        self.grand_master = 204
        self.blackout = False
        self.speed_bpm = 124
        self._next_retry = 0.0
        self.reconnect_seconds = 2.0
        self.reconnect_attempts = 0
        self.gm_sends: list[int] = []
        self._closed = False

    def connection_state(self) -> ConnectionState:
        return self._state

    def simulate_link(self, up: bool) -> None:
        """Operator / test toggle of the mock QLC process. Does not spawn real QLC."""
        self._want_connected = up
        if up:
            self._state = ConnectionState.CONNECTED
            self._project = True
            LOG.info("QLC connected")
        else:
            self._state = ConnectionState.DISCONNECTED
            LOG.warning("QLC connection lost")

    def simulate_drop(self) -> None:
        """WebSocket died; client still wants QLC (reconnect, never restart the process)."""
        self._state = ConnectionState.DISCONNECTED
        self._want_connected = True
        LOG.warning("QLC connection lost")

    def simulate_error(self) -> None:
        self._state = ConnectionState.ERROR
        self._want_connected = True
        LOG.warning("QLC connection error")

    def connected(self) -> bool:
        return self._state is ConnectionState.CONNECTED

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
        fn = self.function_by_name(name)
        if not fn or not self.connected():
            return False
        for other in self._functions:
            other.running = False
        fn.running = True
        return True

    def stop_function_by_name(self, name: str) -> bool:
        fn = self.function_by_name(name)
        if not fn or not self.connected():
            return False
        fn.running = False
        return True

    def toggle_function_by_name(self, name: str) -> bool:
        fn = self.function_by_name(name)
        if not fn:
            return False
        if fn.running:
            return self.stop_function_by_name(name)
        return self.start_function_by_name(name)

    def set_grand_master(self, value_0_255: int) -> None:
        self.grand_master = max(0, min(255, value_0_255))
        if self.connected():
            self.gm_sends.append(self.grand_master)

    def set_blackout(self, on: bool) -> None:
        self.blackout = on

    def set_speed(self, bpm: int) -> None:
        self.speed_bpm = bpm

    def all_off(self) -> None:
        for fn in self._functions:
            fn.running = False

    def patch_output(self, universe: int, spec: str) -> None:
        del universe, spec

    def set_simple_desk_channel(self, address_1_based: int, value: int) -> None:
        del address_1_based, value

    def pump(self, now: float) -> None:
        if self._closed or self.connected() or not self._want_connected:
            return
        if now < self._next_retry:
            if self._state is ConnectionState.DISCONNECTED:
                self._state = ConnectionState.CONNECTING
            return
        self.reconnect_attempts += 1
        self._next_retry = now + self.reconnect_seconds
        self._state = ConnectionState.CONNECTING
        LOG.debug("QLC reconnect attempt %s (QLC process not restarted)", self.reconnect_attempts)

    def close(self) -> None:
        self._closed = True
        self._want_connected = False
        self._state = ConnectionState.DISCONNECTED
