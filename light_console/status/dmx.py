from __future__ import annotations

from light_console.state import AppState


def apply_dmx(state: AppState, net_ok: bool, node_ok: bool) -> None:
    """Art-Net transmit is not enough for NODE OK."""
    state.dmx_net_ok = net_ok
    state.dmx_node_reachable = node_ok and net_ok
