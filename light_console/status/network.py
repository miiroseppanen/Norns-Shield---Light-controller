from __future__ import annotations

from light_console.state import AppState


def apply_upstream(state: AppState, connected: bool, ssid: str = "") -> None:
    state.upstream_connected = connected
    state.upstream_ssid = ssid if connected else ""


def apply_wiz_ap(state: AppState, up: bool) -> None:
    state.wiz_ap_up = up
