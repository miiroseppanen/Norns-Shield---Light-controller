"""Logical shows for the master workspace. Never loads or restarts QLC."""

from __future__ import annotations

from pathlib import Path

from light_console.qxw import QxwError
from light_console.showdef import ShowDefinition, load_show_yaml

MASTER_NAME = "master.qxw"
ACTIVE_NAME = "active-show"
RESERVED = frozenset({MASTER_NAME, ACTIVE_NAME, "current.qxw", "last-good.qxw", ".reload-qlc"})


class ShowCatalog:
    def __init__(self, shows_dir: Path) -> None:
        self.shows_dir = shows_dir
        self.master_path = shows_dir / MASTER_NAME
        self.active_path = shows_dir / ACTIVE_NAME

    def list_shows(self) -> tuple[ShowDefinition, ...]:
        if not self.shows_dir.is_dir():
            return ()
        found: list[ShowDefinition] = []
        for path in sorted(self.shows_dir.glob("*.yaml")):
            if path.name.startswith("."):
                continue
            found.append(load_show_yaml(path))
        return tuple(found)

    def get(self, show_id: str) -> ShowDefinition:
        for show in self.list_shows():
            if show.show_id == show_id:
                return show
        raise QxwError(f"unknown show: {show_id}")

    def active_id(self) -> str | None:
        if not self.active_path.is_file():
            shows = self.list_shows()
            return shows[0].show_id if shows else None
        text = self.active_path.read_text(encoding="utf-8").strip()
        return text or None

    def activate(self, show_id: str) -> ShowDefinition:
        show = self.get(show_id)
        self.shows_dir.mkdir(parents=True, exist_ok=True)
        self.active_path.write_text(show.show_id + "\n", encoding="utf-8")
        return show

    def current_show(self) -> ShowDefinition | None:
        show_id = self.active_id()
        if not show_id:
            return None
        try:
            return self.get(show_id)
        except QxwError:
            return None
