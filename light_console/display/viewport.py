"""Shared list viewport: focused row stays visible, no extra page jumps."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ListViewport:
    total: int = 0
    focused: int = 0
    offset: int = 0
    visible: int = 6

    def move(self, delta: int) -> None:
        if self.total <= 0:
            self.focused = 0
            self.offset = 0
            return
        self.focused = max(0, min(self.total - 1, self.focused + delta))
        self.reveal()

    def reveal(self) -> None:
        if self.total <= 0:
            self.focused = 0
            self.offset = 0
            return
        vis = max(1, self.visible)
        if self.focused < 0:
            self.focused = 0
        if self.focused >= self.total:
            self.focused = self.total - 1
        if self.total <= vis:
            self.offset = 0
            return
        if self.focused < self.offset:
            self.offset = self.focused
        elif self.focused >= self.offset + vis:
            self.offset = self.focused - vis + 1
        max_off = self.total - vis
        if self.offset > max_off:
            self.offset = max_off
        if self.offset < 0:
            self.offset = 0

    def stabilize(self, total: int) -> None:
        """Keep the window still when live data grows/shrinks."""
        focused = self.focused
        offset = self.offset
        self.total = max(0, int(total))
        if self.total == 0:
            self.focused = 0
            self.offset = 0
            return
        self.focused = min(focused, self.total - 1)
        self.offset = offset
        self.reveal()

    def window(self) -> range:
        vis = max(1, self.visible)
        start = max(0, self.offset)
        end = min(self.total, start + vis)
        return range(start, end)


def scrollbar_metrics(
    total: int,
    visible: int,
    offset: int,
    track_h: int,
    *,
    min_thumb: int = 4,
) -> tuple[int, int] | None:
    """Thumb (y, h) relative to the track, or None when the bar is hidden."""
    if track_h <= 0 or total <= 0 or visible <= 0 or total <= visible:
        return None
    thumb_h = max(min_thumb, int(round(track_h * visible / total)))
    thumb_h = min(thumb_h, track_h)
    max_offset = max(1, total - visible)
    clamped = max(0, min(offset, max_offset))
    travel = track_h - thumb_h
    if clamped <= 0:
        thumb_y = 0
    elif clamped >= max_offset:
        thumb_y = travel
    else:
        thumb_y = int(round(travel * clamped / max_offset))
    return thumb_y, thumb_h
