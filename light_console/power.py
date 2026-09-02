"""Host power actions. UI never shells out; it calls request_shutdown()."""

from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

LOG = logging.getLogger("light-console")

SUDO = "/usr/bin/sudo"
SHUTDOWN_CANDIDATES = ("/usr/sbin/shutdown", "/sbin/shutdown")
SHUTDOWN_ARGS = ("-h", "now")


def shutdown_argv() -> tuple[str, ...]:
    """Prefer /usr/sbin/shutdown so it matches packaging/sudoers.d/light-console-shutdown."""
    shutdown = "/usr/sbin/shutdown"
    if not Path(shutdown).exists():
        shutdown = next((p for p in SHUTDOWN_CANDIDATES if Path(p).exists()), shutdown)
    return (SUDO, shutdown, *SHUTDOWN_ARGS)


class PowerService(ABC):
    @abstractmethod
    def request_shutdown(self) -> bool:
        """Start a halt. True if this call is the first accepted request."""
        ...


class MockPowerService(PowerService):
    """Simulator / tests: never halt the host."""

    def __init__(self) -> None:
        self.shutdown_requested = False
        self.request_count = 0
        self.spawn_count = 0

    def request_shutdown(self) -> bool:
        if self.shutdown_requested:
            LOG.info("shutdown already requested (mock)")
            return False
        self.shutdown_requested = True
        self.request_count += 1
        LOG.info("shutdown requested (mock; host will not halt)")
        return True


class LinuxPowerService(PowerService):
    """Shield: argv list only, no shell, no user-supplied strings."""

    def __init__(self, argv: tuple[str, ...] | None = None) -> None:
        self.argv = argv or shutdown_argv()
        self.shutdown_requested = False
        self.request_count = 0
        self.spawn_count = 0

    def request_shutdown(self) -> bool:
        if self.shutdown_requested:
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
