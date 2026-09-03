"""Installed shows: current.qxw, last-good.qxw, OLED metadata, QLC reload stamp.

Light Console never calls systemctl. Touching .reload-qlc trips qlcplus-reload.path.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from light_console.qxw import QxwError, QxwFunction, parse_functions_file, prepare_for_shield

CURRENT_NAME = "current.qxw"
LAST_GOOD_NAME = "last-good.qxw"
RELOAD_STAMP = ".reload-qlc"
RESERVED = frozenset({CURRENT_NAME, LAST_GOOD_NAME, RELOAD_STAMP})


@dataclass(frozen=True)
class ShowInfo:
    filename: str
    scenes: tuple[str, ...]
    chasers: tuple[str, ...]
    functions: tuple[QxwFunction, ...]

    @property
    def label(self) -> str:
        return self.filename[:-4] if self.filename.lower().endswith(".qxw") else self.filename


def _atomic_symlink(shows_dir: Path, name: str, link: Path) -> None:
    tmp = shows_dir / f".{link.name}.{os.getpid()}.tmp"
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(name)
    os.replace(tmp, link)


class ShowCatalog:
    def __init__(self, shows_dir: Path) -> None:
        self.shows_dir = shows_dir
        self.current_link = shows_dir / CURRENT_NAME
        self.last_good_link = shows_dir / LAST_GOOD_NAME
        self.reload_stamp = shows_dir / RELOAD_STAMP

    def list_files(self) -> tuple[str, ...]:
        if not self.shows_dir.is_dir():
            return ()
        names = []
        for path in sorted(self.shows_dir.iterdir()):
            if path.name in RESERVED or path.name.startswith("."):
                continue
            if path.is_file() and path.suffix.lower() == ".qxw":
                names.append(path.name)
        return tuple(names)

    def current_name(self) -> str | None:
        if not self.current_link.is_symlink() and not self.current_link.exists():
            return None
        try:
            target = self.current_link.resolve(strict=True)
        except OSError:
            return None
        if target.parent.resolve() != self.shows_dir.resolve():
            return None
        return target.name

    def last_good_name(self) -> str | None:
        if not self.last_good_link.is_symlink() and not self.last_good_link.exists():
            return None
        try:
            target = self.last_good_link.resolve(strict=True)
        except OSError:
            return None
        return target.name

    def info_for(self, filename: str) -> ShowInfo:
        path = (self.shows_dir / filename).resolve()
        if path.parent != self.shows_dir.resolve():
            raise QxwError(f"show outside shows dir: {filename}")
        text = path.read_text(encoding="utf-8")
        prepare_for_shield(text)
        functions = parse_functions_file(path)
        scenes = tuple(fn.name for fn in functions if fn.type_name.lower() == "scene")
        chasers = tuple(fn.name for fn in functions if fn.type_name.lower() == "chaser")
        return ShowInfo(filename=path.name, scenes=scenes, chasers=chasers, functions=functions)

    def current_info(self) -> ShowInfo | None:
        name = self.current_name()
        if not name:
            return None
        return self.info_for(name)

    def select(self, filename: str) -> ShowInfo:
        """Validate and point current.qxw at filename. Does not retarget last-good."""
        if "/" in filename or "\\" in filename or filename.startswith(".") or filename in RESERVED:
            raise QxwError(f"unsafe show name: {filename}")
        info = self.info_for(filename)
        _atomic_symlink(self.shows_dir, filename, self.current_link)
        return info

    def mark_good(self) -> None:
        name = self.current_name()
        if not name:
            raise QxwError("cannot mark last-known-good: current.qxw missing")
        _atomic_symlink(self.shows_dir, name, self.last_good_link)

    def restore_last_good(self) -> ShowInfo:
        name = self.last_good_name()
        if not name:
            raise QxwError("no last-known-good show")
        return self.select(name)

    def request_reload(self) -> None:
        self.reload_stamp.write_text(f"{time.time()}\n", encoding="utf-8")


class ShowLoad:
    """Confirm → current.qxw → reload stamp → wait for QLC → last-good or restore."""

    def __init__(self, catalog: ShowCatalog, timeout_s: float = 20.0) -> None:
        self.catalog = catalog
        self.timeout_s = timeout_s
        self.status = ""
        self.deadline: float | None = None
        self.recovering = False
        self.pending: str | None = None

    def confirm(self, filename: str, now: float) -> str:
        try:
            info = self.catalog.select(filename)
        except (OSError, QxwError) as exc:
            self.status = "FAIL"
            self.deadline = None
            self.pending = None
            self.recovering = False
            return str(exc)
        self.catalog.request_reload()
        self.status = "LOADING"
        self.pending = info.filename
        self.recovering = False
        self.deadline = now + self.timeout_s
        return ""

    def tick(self, now: float, qlc_connected: bool, project_loaded: bool) -> None:
        if self.deadline is None:
            return
        if qlc_connected and project_loaded:
            try:
                self.catalog.mark_good()
            except QxwError:
                self.status = "FAIL"
            else:
                self.status = "OK"
            self.deadline = None
            self.recovering = False
            self.pending = None
            return
        if now < self.deadline:
            return
        if not self.recovering:
            try:
                self.catalog.restore_last_good()
                self.catalog.request_reload()
            except QxwError:
                self.status = "FAIL"
                self.deadline = None
                return
            self.recovering = True
            self.status = "FAIL"
            self.deadline = now + self.timeout_s
            return
        self.status = "FAIL"
        self.deadline = None
        self.recovering = False
