"""Single-instance lock for the Shield GPIO/SPI backend.

One path only so systemd and an SSH foreground share the same lock.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

DEFAULT_LOCK = Path("/tmp/light-console.instance.lock")


class InstanceLockHeld(RuntimeError):
    """Another light-console --shield process owns GPIO/SPI."""


class InstanceLock:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_LOCK
        self._fd: int | None = None

    def acquire(self) -> Path:
        if self._fd is not None:
            return self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise InstanceLockHeld(
                "light-console --shield is already running (GPIO/SPI busy). "
                "Stop the other instance (sudo systemctl stop light-console)."
            ) from exc
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        self._fd = fd
        return self.path

    def close(self) -> None:
        fd = self._fd
        self._fd = None
        if fd is None:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
