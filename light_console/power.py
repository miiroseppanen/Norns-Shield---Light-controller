"""Host power actions. UI never shells out; it calls request_shutdown/request_restart."""

from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

LOG = logging.getLogger("light-console")

SUDO = "/usr/bin/sudo"
SHUTDOWN_CANDIDATES = ("/usr/sbin/shutdown", "/sbin/shutdown")
SHUTDOWN_ARGS = ("-h", "now")
RESTART_ARGS = ("-r", "now")


def _shutdown_bin() -> str:
    shutdown = "/usr/sbin/shutdown"
    if not Path(shutdown).exists():
        shutdown = next((p for p in SHUTDOWN_CANDIDATES if Path(p).exists()), shutdown)
    return shutdown


def shutdown_argv() -> tuple[str, ...]:
    """Prefer /usr/sbin/shutdown so it matches packaging/sudoers.d/light-console-shutdown."""
    return (SUDO, _shutdown_bin(), *SHUTDOWN_ARGS)


def restart_argv() -> tuple[str, ...]:
    """Prefer /usr/sbin/shutdown -r now so it matches packaging/sudoers.d/light-console-shutdown."""
    return (SUDO, _shutdown_bin(), *RESTART_ARGS)


class PowerService(ABC):
    @abstractmethod
    def request_shutdown(self) -> bool:
        """Start a halt. True if this call is the first accepted request."""
        ...

    @abstractmethod
    def request_restart(self) -> bool:
        """Start a reboot. True if this call is the first accepted request."""
        ...


class MockPowerService(PowerService):
    """Simulator / tests: never halt or reboot the host."""

    def __init__(self) -> None:
        self.shutdown_requested = False
        self.restart_requested = False
        self.request_count = 0
        self.restart_count = 0
        self.spawn_count = 0
        self.restart_spawn_count = 0

    def _busy(self) -> bool:
        return self.shutdown_requested or self.restart_requested

    def request_shutdown(self) -> bool:
        if self._busy():
            LOG.info("shutdown already requested (mock)")
            return False
        self.shutdown_requested = True
        self.request_count += 1
        LOG.info("shutdown requested (mock; host will not halt)")
        return True

    def request_restart(self) -> bool:
        if self._busy():
            LOG.info("restart already requested (mock)")
            return False
        self.restart_requested = True
        self.restart_count += 1
        LOG.info("restart requested (mock; host will not reboot)")
        return True


class LinuxPowerService(PowerService):
    """Shield: argv list only, no shell, no user-supplied strings."""

    def __init__(
        self,
        argv: tuple[str, ...] | None = None,
        restart_cmd: tuple[str, ...] | None = None,
    ) -> None:
        self.argv = argv or shutdown_argv()
        self.restart_cmd = restart_cmd or restart_argv()
        self.shutdown_requested = False
        self.restart_requested = False
        self.request_count = 0
        self.restart_count = 0
        self.spawn_count = 0
        self.restart_spawn_count = 0

    def _busy(self) -> bool:
        return self.shutdown_requested or self.restart_requested

    def request_shutdown(self) -> bool:
        if self._busy():
            LOG.info("shutdown already requested")
            return False
        self.shutdown_requested = True
        self.request_count += 1
        LOG.info("shutdown requested: %s", " ".join(self.argv))
        try:
            subprocess.run(self.argv, check=False, shell=False)
            self.spawn_count += 1
        except OSError:
            LOG.exception("shutdown spawn failed")
        return True

    def request_restart(self) -> bool:
        if self._busy():
            LOG.info("restart already requested")
            return False
        self.restart_requested = True
        self.restart_count += 1
        LOG.info("restart requested: %s", " ".join(self.restart_cmd))
        try:
            subprocess.run(self.restart_cmd, check=False, shell=False)
            self.restart_spawn_count += 1
        except OSError:
            LOG.exception("restart spawn failed")
        return True
