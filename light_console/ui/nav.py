from __future__ import annotations

from light_console.state import AppState, ScreenId, UiMode
from light_console.ui.menu import MENU_ITEMS, ROOT, MenuItem


class Navigation:
    """MENU stack: root → submenu → page. Independent of GPIO and QLC."""

    def __init__(self) -> None:
        self.stack: list[str] = []

    def go_play(self, state: AppState) -> None:
        state.mode = UiMode.PLAY
        state.screen = ScreenId.PLAY
        self.stack = []

    def enter_menu(self, state: AppState) -> None:
        state.mode = UiMode.MENU
        state.screen = ScreenId.MENU
        self.stack = [ROOT.id]
        state.menu_index = 0
        state.menu_count = len(self.current_items())

    def current_node(self) -> MenuItem:
        node = ROOT
        for nid in self.stack[1:]:
            found = next((c for c in node.children if c.id == nid), None)
            if found is None:
                break
            node = found
        return node

    def current_items(self) -> tuple[MenuItem, ...]:
        node = self.current_node()
        if node.children:
            return node.children
        return MENU_ITEMS

    def forward(self, state: AppState) -> None:
        items = self.current_items()
        if not items:
            return
        item = items[state.menu_index % len(items)]
        if item.action == "play":
            self.go_play(state)
            return
        if item.children:
            self.stack.append(item.id)
            state.menu_index = 0
            state.screen = ScreenId.MENU
            state.menu_count = len(item.children)
            return
        if item.page_id:
            self.stack.append(item.id)
            state.screen = ScreenId(item.page_id)

    def open_shutdown_confirm(self, state: AppState) -> None:
        state.screen = ScreenId.SHUTDOWN

    def open_load_show_confirm(self, state: AppState) -> None:
        state.screen = ScreenId.LOAD_SHOW

    def back(self, state: AppState) -> None:
        if state.screen == ScreenId.SHUTDOWN:
            state.screen = ScreenId.SYSTEM
            return
        if state.screen == ScreenId.LOAD_SHOW:
            state.screen = ScreenId.SHOWS
            return
        if state.screen != ScreenId.MENU:
            if self.stack:
                self.stack.pop()
            state.screen = ScreenId.MENU
            state.menu_count = len(self.current_items())
            return
        if len(self.stack) <= 1:
            return
        self.stack.pop()
        state.menu_index = 0
        state.menu_count = len(self.current_items())

    def at_root(self) -> bool:
        return len(self.stack) <= 1 and True
