"""QLC systemd unit control. User stop uses systemctl stop, never SIGKILL."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from abc import ABC, abstractmethod

from light_console.ui.vocab import FAILED, RUNNING, STARTING, STOPPED, STOPPING

LOG = logging.getLogger("light-console")

UNIT = "qlcplus.service"
SUDO = "/usr/bin/sudo"
SYSTEMCTL = "/usr/bin/systemctl"
START_ARGV = (SUDO, "-n", SYSTEMCTL, "start", UNIT)
STOP_ARGV = (SUDO, "-n", SYSTEMCTL, "stop", UNIT)
SHOW_ARGV = (SYSTEMCTL, "show", UNIT, "-p", "ActiveState", "-p", "SubState")


class QlcService(ABC):
    desired_on: bool
    observed: str

    @abstractmethod
    def set_desired(self, on: bool) -> None:
        ...

    @abstractmethod
    def poll(self) -> str:
        ...


class MockQlcService(QlcService):
    """Tests / simulator: no systemd, no sudo."""

    def __init__(self, desired_on: bool = True, observed: str = RUNNING, auto_settle: bool = False) -> None:
        self.desired_on = desired_on
        self.observed = observed
        self.commands: list[str] = []
        self.auto_settle = auto_settle

    def set_desired(self, on: bool) -> None:
        self.desired_on = on
        cmd = "start" if on else "stop"
        self.commands.append(cmd)
        self.observed = STARTING if on else STOPPING

    def poll(self) -> str:
        if self.auto_settle:
            self.settle()
        return self.observed

    def settle(self) -> str:
        if self.observed == STARTING:
            self.observed = RUNNING
        elif self.observed == STOPPING:
            self.observed = STOPPED
        return self.observed

    def fail(self) -> str:
        self.observed = FAILED
        return self.observed


class LinuxQlcService(QlcService):
    """Narrow sudo: only start/stop qlcplus.service. Status needs no sudo."""

    def __init__(self, desired_on: bool = True) -> None:
        self.desired_on = desired_on
        self.observed = STOPPED
        self._pending: str | None = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="qlc-unit")
        self._thread.start()

    def set_desired(self, on: bool) -> None:
        self.desired_on = on
        argv = START_ARGV if on else STOP_ARGV
        self.observed = STARTING if on else STOPPING
        with self._lock:
            self._pending = "start" if on else "stop"
        worker = threading.Thread(target=self._spawn, args=(argv,), daemon=True)
        worker.start()

    def _spawn(self, argv: tuple[str, ...]) -> None:
        LOG.info("qlc service: %s", " ".join(argv))
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=25)
        except (OSError, subprocess.TimeoutExpired):
            LOG.exception("qlc service spawn failed")
            self.observed = FAILED
            with self._lock:
                self._pending = None
            return
        if proc.returncode != 0:
            LOG.warning("qlc service failed rc=%s %s", proc.returncode, (proc.stderr or "").strip())
            self.observed = FAILED
            with self._lock:
                self._pending = None

    def poll(self) -> str:
        return self.observed

    def _poll_loop(self) -> None:
        while True:
            try:
                self._refresh()
            except Exception:
                LOG.debug("qlc unit poll failed", exc_info=True)
            time.sleep(0.4)

    def _refresh(self) -> None:
        active, sub = _read_unit_state()
        with self._lock:
            pending = self._pending
        mapped = map_unit_state(active, sub)
        if pending == "start":
            if mapped == RUNNING:
                with self._lock:
                    self._pending = None
                self.observed = RUNNING
            elif mapped == FAILED:
                with self._lock:
                    self._pending = None
                self.observed = FAILED
            else:
                self.observed = STARTING
        elif pending == "stop":
            if mapped == STOPPED:
                with self._lock:
                    self._pending = None
                self.observed = STOPPED
            elif mapped == FAILED:
                with self._lock:
                    self._pending = None
                self.observed = FAILED
            else:
                self.observed = STOPPING
        else:
            self.observed = mapped


def _read_unit_state() -> tuple[str, str]:
    try:
        proc = subprocess.run(SHOW_ARGV, capture_output=True, text=True, timeout=0.4)
    except (OSError, subprocess.TimeoutExpired):
        return "", ""
    return parse_unit_show(proc.stdout or "")


def parse_unit_show(stdout: str) -> tuple[str, str]:
    active = ""
    sub = ""
    for raw in stdout.splitlines():
        line = raw.strip()
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().lower()
            if key == "ActiveState":
                active = value
            elif key == "SubState":
                sub = value
        elif not active:
            active = line.lower()
        elif not sub:
            sub = line.lower()
    return active, sub


def map_unit_state(active: str, sub: str) -> str:
    if active == "activating" or sub in {"start", "auto-restart"}:
        return STARTING
    if active == "deactivating":
        return STOPPING
    if active == "failed" or sub == "failed":
        return FAILED
    if active == "active":
        return RUNNING
    return STOPPED
