from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from light_console.qlc.functions import QlcFunction
from light_console.state import DEFAULT_FUNCTIONS

LOG = logging.getLogger("light-console")


class QLCClient(ABC):
    @abstractmethod
    def connected(self) -> bool:
        ...

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

    def pump(self, now: float) -> None:
        """Background reconnect. Must never restart the QLC process."""
        del now


class MockQLCClient(QLCClient):
    """In-process QLC stand-in for the Mac simulator and unit tests."""

    def __init__(self, names: tuple[str, ...] = DEFAULT_FUNCTIONS) -> None:
        self._connected = False
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

    def simulate_link(self, up: bool) -> None:
        """Operator / test toggle of the mock QLC process. Does not spawn real QLC."""
        self._want_connected = up
        if up:
            self._connected = True
            self._project = True
            LOG.info("QLC connected")
        else:
            self._connected = False
            LOG.warning("QLC connection lost")

    def simulate_drop(self) -> None:
        """WebSocket died; client still wants QLC (reconnect, never restart the process)."""
        self._connected = False
        self._want_connected = True
        LOG.warning("QLC connection lost")

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
        fn = self.function_by_name(name)
        if not fn or not self._connected:
            return False
        for other in self._functions:
            other.running = False
        fn.running = True
        return True

    def stop_function_by_name(self, name: str) -> bool:
        fn = self.function_by_name(name)
        if not fn or not self._connected:
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

    def set_blackout(self, on: bool) -> None:
        self.blackout = on

    def set_speed(self, bpm: int) -> None:
        self.speed_bpm = bpm

    def all_off(self) -> None:
        for fn in self._functions:
            fn.running = False

    def pump(self, now: float) -> None:
        if self._connected or not self._want_connected:
            return
        if now < self._next_retry:
            return
        self.reconnect_attempts += 1
        self._next_retry = now + self.reconnect_seconds
        # Still down until simulate_link(True). We only *try*.
        LOG.debug("QLC reconnect attempt %s (QLC process not restarted)", self.reconnect_attempts)
