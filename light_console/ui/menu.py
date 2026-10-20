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
    MenuItem("status", "STATUS", action="play"),
    MenuItem("shows", "SHOWS", page_id=ScreenId.SHOWS.value),
    MenuItem("output", "OUTPUT", page_id=ScreenId.OUTPUT.value),
    MenuItem(
        "wiz",
        "WIZ",
        children=(
            MenuItem("wiz-devices", "DEVICES", page_id=ScreenId.WIZ_DEVICES.value),
            MenuItem("wiz-control", "CONTROL", page_id=ScreenId.WIZ_CONTROL.value),
            MenuItem("wiz-info", "INFO", page_id=ScreenId.WIZ_INFO.value),
        ),
    ),
    MenuItem("system", "SYSTEM", page_id=ScreenId.SYSTEM.value),
    MenuItem("shutdown", "SHUTDOWN", page_id=ScreenId.SHUTDOWN_CONFIRM.value),
)

# Implemented later. Hidden from the operator menu; screens stay in the tree.
DEFERRED_MENU_ITEMS: tuple[MenuItem, ...] = (
    MenuItem("scenes", "SCENES", page_id=ScreenId.SCENES.value),
    MenuItem("chasers", "CHASERS", page_id=ScreenId.CHASERS.value),
    MenuItem("params", "PARAMS", page_id=ScreenId.PARAMS.value),
)


def menu_index_of(label: str) -> int:
    for i, item in enumerate(MENU_ITEMS):
        if item.label == label:
            return i
    raise KeyError(label)


ROOT = MenuItem("root", "MENU", children=MENU_ITEMS)

__all__ = [
    "DEFERRED_MENU_ITEMS",
    "MENU_ITEMS",
    "MenuItem",
    "ROOT",
    "ScreenId",
    "menu_index_of",
]
