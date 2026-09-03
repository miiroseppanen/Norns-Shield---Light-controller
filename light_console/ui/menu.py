from __future__ import annotations

from dataclasses import dataclass, field

from light_console.state import ScreenId


@dataclass(frozen=True)
class MenuItem:
    """Data-driven menu row. children = submenu; page_id = screen; action = shell command."""

    id: str
    label: str
    page_id: str | None = None
    action: str | None = None
    children: tuple[MenuItem, ...] = field(default_factory=tuple)


MENU_ITEMS: tuple[MenuItem, ...] = (
    MenuItem("home", "HOME", action="play"),
    MenuItem("shows", "SHOWS", page_id=ScreenId.SHOWS.value),
    MenuItem("scenes", "SCENES", page_id=ScreenId.SCENES.value),
    MenuItem("chasers", "CHASERS", page_id=ScreenId.CHASERS.value),
    MenuItem("params", "PARAMS", page_id=ScreenId.PARAMS.value),
    MenuItem("output", "OUTPUT", page_id=ScreenId.OUTPUT.value),
    MenuItem("system", "SYSTEM", page_id=ScreenId.SYSTEM.value),
)


def menu_index_of(label: str) -> int:
    for i, item in enumerate(MENU_ITEMS):
        if item.label == label:
            return i
    raise KeyError(label)

ROOT = MenuItem("root", "MENU", children=MENU_ITEMS)

__all__ = ["MenuItem", "MENU_ITEMS", "ROOT", "ScreenId", "menu_index_of"]
