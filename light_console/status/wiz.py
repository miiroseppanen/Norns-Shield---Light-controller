from __future__ import annotations

from light_console.state import AppState
from light_console.wiz.observe import WizObservedSnapshot


def apply_wiz_online(state: AppState, online: int) -> None:
    state.wiz_online = max(0, min(state.wiz_expected, int(online)))


def apply_wiz_observed(state: AppState, snapshot: WizObservedSnapshot) -> None:
    """Configured ONLINE count only. NEW/unconfigured devices do not count."""
    apply_wiz_online(state, snapshot.online)


def bump_wiz(state: AppState, delta: int) -> None:
    apply_wiz_online(state, state.wiz_online + delta)
