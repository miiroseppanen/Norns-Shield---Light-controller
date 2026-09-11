"""Runtime activity animation. Movement means live signal is progressing now."""

from __future__ import annotations

# Left-to-right scan in the 9×8 activity slot. Wrap, never reverse.
FRAMES = 6
PERIOD_S = 0.16
SEG_W = 3
# Local x of the 3px segment. 1px pad from the status field; last pixel is slot 8.
SCAN_X = (1, 2, 3, 4, 5, 6)
SCAN_Y = 3  # vertically centered in 8px row


def activity_frame(now: float, active: bool) -> int | None:
    """Return 0..FRAMES-1 while active, else None (draw nothing)."""
    if not active:
        return None
    if now < 0:
        now = 0.0
    return int(now / PERIOD_S) % FRAMES


def dmx_output_active(dmx: dict[int, tuple[int, ...]] | None) -> bool:
    if not dmx:
        return False
    for buf in dmx.values():
        if any(buf):
            return True
    return False
