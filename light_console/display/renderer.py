from __future__ import annotations

from light_console.display.framebuffer import Framebuffer
from light_console.display.screens import draw_screen
from light_console.state import AppState


class Renderer:
    def __init__(self, width: int = 128, height: int = 64) -> None:
        self.fb = Framebuffer(width, height)
        self._last: bytes | None = None

    def render(self, state: AppState) -> Framebuffer:
        draw_screen(self.fb, state)
        return self.fb

    def changed(self) -> bool:
        digest = self.fb.digest()
        if digest == self._last:
            return False
        self._last = digest
        return True

    def force_dirty(self) -> None:
        self._last = None
