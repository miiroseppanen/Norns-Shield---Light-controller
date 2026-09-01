from __future__ import annotations

from light_console.state import AppState


def apply_launchpad(state: AppState, connected: bool) -> None:
    state.launchpad_connected = connected
