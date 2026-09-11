"""QLC function runtime is valid only while QLC is connected.

Desired service state, observed unit state, WebSocket connectivity, and
function RUNNING/STOPPED are separate. Function state is never inferred
after the QLC process is gone.
"""

from __future__ import annotations

from light_console.state import AppState
from light_console.ui.vocab import FAILED, RUNNING, STOPPED, STOPPING

STARTUP_NAME = "startup"
WAIT = "WAIT"

UNAVAILABLE_OBSERVED = frozenset({STOPPED, STOPPING, FAILED})


def function_runtime_available(connected: bool, observed: str) -> bool:
    """True only when QLC can answer function-status queries."""
    return bool(connected) and observed not in UNAVAILABLE_OBSERVED


def parse_startup_status_file(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("status="):
            return line.split("=", 1)[1].strip()
    return ""


def invalidate_function_runtime(state: AppState) -> None:
    """Drop cached function RUNNING immediately. No stale timeout."""
    state.startup_running = False
    state.startup_status = STOPPED
    state.active_function = None


def apply_live_startup_runtime(
    state: AppState,
    *,
    live_running: bool | None,
    file_status: str,
) -> None:
    """Apply startup OLED state from live QLC evidence.

    The helper status file may show WAIT/FAIL while connected. Its RUNNING
    line is never trusted on its own — that survives QLC stop.
    """
    word = (file_status or "").strip().upper()
    if live_running is True:
        state.startup_status = RUNNING
        state.startup_running = True
        return
    state.startup_running = False
    if word == WAIT:
        state.startup_status = WAIT
        return
    if word in {"FAIL", "FAILED"}:
        state.startup_status = FAILED
        return
    if live_running is False or word == RUNNING:
        state.startup_status = STOPPED
        return
    state.startup_status = WAIT
