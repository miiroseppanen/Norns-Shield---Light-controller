from __future__ import annotations

from light_console.state import AppState, ScreenId, UiMode
from light_console.ui.menu import MENU_ITEMS, ROOT, MenuItem
from light_console.controls.encoders import bound_index


class Navigation:
    """MENU stack: root → submenu → page. Independent of GPIO and QLC."""

    def __init__(self) -> None:
        self.stack: list[str] = []

    def go_play(self, state: AppState) -> None:
        if (
            state.shutdown_requested
            or state.screen == ScreenId.SHUTTING_DOWN
            or state.screen == ScreenId.STARTING_UP
        ):
            return
        state.mode = UiMode.PLAY
        state.screen = ScreenId.PLAY
        self.stack = []
        state.reset_list_window()

    def enter_menu(self, state: AppState) -> None:
        if (
            state.shutdown_requested
            or state.screen == ScreenId.SHUTTING_DOWN
            or state.screen == ScreenId.STARTING_UP
        ):
            return
        state.mode = UiMode.MENU
        state.screen = ScreenId.MENU
        self.stack = [ROOT.id]
        state.menu_index = 0
        state.reset_list_window()
        self.sync_menu_view(state)

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

    def sync_menu_view(self, state: AppState) -> None:
        """Publish the current MENU listing so OLED draw_menu matches nav."""
        node = self.current_node()
        if not node.children:
            return
        items = node.children
        state.menu_title = node.label
        state.menu_labels = tuple(item.label for item in items)
        state.menu_count = len(items)

    def _restore_child(self, state: AppState, child_id: str) -> None:
        items = self.current_items()
        state.menu_index = 0
        for i, item in enumerate(items):
            if item.id == child_id:
                state.menu_index = i
                break
        self.sync_menu_view(state)

    def forward(self, state: AppState) -> None:
        items = self.current_items()
        if not items:
            return
        item = items[bound_index(state.menu_index, len(items))]
        if item.action == "play":
            self.go_play(state)
            return
        if item.children:
            self.stack.append(item.id)
            state.menu_index = 0
            state.screen = ScreenId.MENU
            self.sync_menu_view(state)
            return
        if item.page_id:
            self.stack.append(item.id)
            state.screen = ScreenId(item.page_id)
            state.reset_list_window()

    def begin_shutdown(self, state: AppState) -> None:
        state.screen = ScreenId.SHUTTING_DOWN
        state.shutdown_requested = True

    def open_load_show_confirm(self, state: AppState) -> None:
        state.screen = ScreenId.LOAD_SHOW

    def back(self, state: AppState) -> None:
        if (
            state.screen == ScreenId.SHUTTING_DOWN
            or state.shutdown_requested
            or state.screen == ScreenId.STARTING_UP
        ):
            return
        if state.screen == ScreenId.LOAD_SHOW:
            state.screen = ScreenId.SHOWS
            return
        if state.screen == ScreenId.VERSION:
            state.screen = ScreenId.SYSTEM
            state.reset_list_window()
            return
        if state.screen == ScreenId.WIZ_DEVICES:
            if state.wiz_prompt:
                state.wiz_prompt = ""
                state.wiz_prompt_error = ""
                state.wiz_device_detail = False
                state.scroll_offset = 0
                return
            if state.wiz_device_detail:
                state.wiz_device_detail = False
                state.scroll_offset = 0
                return
            if not self.stack:
                state.screen = ScreenId.SYSTEM
                state.reset_list_window()
                return
        if state.screen != ScreenId.MENU:
            child_id = self.stack.pop() if self.stack else ""
            state.screen = ScreenId.MENU
            self._restore_child(state, child_id)
            state.reset_list_window()
            return
        if len(self.stack) <= 1:
            return
        child_id = self.stack.pop()
        self._restore_child(state, child_id)

    def at_root(self) -> bool:
        return len(self.stack) <= 1 and True
