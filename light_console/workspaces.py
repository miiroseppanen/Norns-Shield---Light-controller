"""Named QLC workspaces on the appliance. QLC still opens master.qxw."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from light_console.qlc.launch import MASTER_NAME
from light_console.qxw import QxwError, safe_show_name

OPEN_NAME = "open-show"
LAST_GOOD_NAME = "last-good.qxw"
ACTIVE_NAME = "active-show"
HIDDEN = frozenset(
    {
        MASTER_NAME,
        LAST_GOOD_NAME,
        "current.qxw",
        OPEN_NAME,
        ACTIVE_NAME,
        ".reload-qlc",
    }
)
_LABEL_JUNK = re.compile(r"[^A-Z0-9]+")


@dataclass(frozen=True)
class WorkspaceFile:
    filename: str
    path: Path
    label: str


def oled_workspace_label(filename: str) -> str:
    stem = Path(filename).stem
    label = _LABEL_JUNK.sub(" ", stem.upper()).strip()
    return label or "SHOW"


class WorkspaceCatalog:
    def __init__(self, shows_dir: Path) -> None:
        self.shows_dir = shows_dir
        self.master_path = shows_dir / MASTER_NAME
        self.open_path = shows_dir / OPEN_NAME
        self.last_good_path = shows_dir / LAST_GOOD_NAME

    def list_entries(self) -> tuple[WorkspaceFile, ...]:
        if not self.shows_dir.is_dir():
            return ()
        named = [self._entry(path) for path in sorted(self.shows_dir.glob("*.qxw")) if self._is_named(path)]
        if named:
            return tuple(named)
        if self.master_path.is_file():
            return (self._entry(self.master_path),)
        return ()

    def get(self, filename: str) -> WorkspaceFile:
        name = Path(filename).name
        for entry in self.list_entries():
            if entry.filename == name:
                return entry
        raise QxwError(f"unknown workspace: {name}")

    def open_filename(self) -> str | None:
        if self.open_path.is_file():
            text = self.open_path.read_text(encoding="utf-8").strip()
            if text and (self.shows_dir / text).is_file():
                return text
        if self.master_path.is_file():
            return MASTER_NAME
        return None

    def is_open(self, filename: str) -> bool:
        current = self.open_filename()
        return current is not None and Path(filename).name == current

    def remember_open(self, filename: str) -> None:
        name = Path(filename).name
        self.get(name)
        self.shows_dir.mkdir(parents=True, exist_ok=True)
        self.open_path.write_text(name + "\n", encoding="utf-8")

    def source_path(self, filename: str) -> Path:
        entry = self.get(filename)
        return entry.path

    def _is_named(self, path: Path) -> bool:
        name = path.name
        if name in HIDDEN:
            return False
        if name.startswith("."):
            return False
        if name.endswith(".bak"):
            return False
        if ".incoming." in name:
            return False
        try:
            return safe_show_name(path) == name
        except QxwError:
            return False

    def _entry(self, path: Path) -> WorkspaceFile:
        return WorkspaceFile(filename=path.name, path=path, label=oled_workspace_label(path.name))
