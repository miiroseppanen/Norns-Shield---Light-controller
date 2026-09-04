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

    def set_function_status(self, function_id: int, running: bool) -> bool:
        """QLC+API|setFunctionStatus|<id>|<0|1>. Returns False if offline."""
        del function_id, running
        return False

    def patch_output(self, universe: int, spec: str) -> None:
        """QLC+IO|OUTPUT|<uni>|<Plugin>|<line> as used by the 5.2.2 /config page."""
        del universe, spec

    def set_simple_desk_channel(self, address_1_based: int, value: int) -> None:
        """Documented Simple Desk: CH|<abs>|<0-255>."""
        del address_1_based, value

    def request_channels_values(
        self, universe_1based: int, start: int = 1, count: int = 512
    ) -> None:
        """QLC+API|getChannelsValues — read-only live DMX."""
        del universe_1based, start, count

    def dmx_snapshot(self, universe_0based: int) -> tuple[int, ...] | None:
        del universe_0based
        return None

    def clear_dmx(self) -> None:
        return

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
        self.function_sends: list[tuple[int, int]] = []
        self._closed = False
        self._dmx_cache = {}
        self.channel_requests: list[str] = []

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
            self.clear_dmx()
            LOG.warning("QLC connection lost")

    def simulate_drop(self) -> None:
        """WebSocket died; client still wants QLC (reconnect, never restart the process)."""
        self._state = ConnectionState.DISCONNECTED
        self._want_connected = True
        self.clear_dmx()
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
        return self.set_function_status(fn.function_id, True)

    def stop_function_by_name(self, name: str) -> bool:
        fn = self.function_by_name(name)
        if not fn or not self.connected():
            return False
        return self.set_function_status(fn.function_id, False)

    def set_function_status(self, function_id: int, running: bool) -> bool:
        if not self.connected():
            return False
        fn = next((f for f in self._functions if f.function_id == function_id), None)
        if fn is None:
            return False
        if running:
            for other in self._functions:
                other.running = False
            fn.running = True
        else:
            fn.running = False
        self.function_sends.append((function_id, 1 if running else 0))
        return True

    def replace_functions(self, functions: list[QlcFunction]) -> None:
        self._functions = list(functions)
        self._project = True

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

    def set_dmx_universe(self, universe_0based: int, values: dict[int, int]) -> None:
        from light_console.output.dmx import empty_universe

        buf = self._dmx_cache.setdefault(universe_0based, empty_universe())
        for channel, value in values.items():
            if 1 <= channel <= 512:
                buf[channel - 1] = value

    def request_channels_values(
        self, universe_1based: int, start: int = 1, count: int = 512
    ) -> None:
        from light_console.output.dmx import empty_universe

        self.channel_requests.append(
            f"QLC+API|getChannelsValues|{universe_1based}|{start}|{count}"
        )
        if not self.connected():
            return
        uni0 = universe_1based - 1
        buf = self._dmx_cache.setdefault(uni0, empty_universe())
        del start, count
        self._dmx_cache[uni0] = list(buf)

    def dmx_snapshot(self, universe_0based: int) -> tuple[int, ...] | None:
        buf = self._dmx_cache.get(universe_0based)
        if buf is None:
            return None
        return tuple(buf)

    def clear_dmx(self) -> None:
        self._dmx_cache.clear()

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
