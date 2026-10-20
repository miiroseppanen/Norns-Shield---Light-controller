"""Compact OUTPUT summary for PLAY. Cached state only; no probes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from light_console.output.targets import TargetId, detect_target, label_for_output_ip

if TYPE_CHECKING:
    from light_console.state import AppState

UNKNOWN_SUMMARY = "--"


def _artnet_routes(state: AppState):
    return tuple(route for route in state.output_routes if route.plugin == "ARTNET")


def wired_output_label(state: AppState) -> str:
    """PLAY wired target. Loopback shows LOOPBACK; unknown never claims a node."""
    detected = detect_target(state.output_routes, nodes=state.artnet_nodes)
    if detected.target_id is TargetId.SAFE:
        return "LOOPBACK"
    if detected.target_id is TargetId.AIR2DMX:
        return TargetId.AIR2DMX.value
    if detected.target_id is TargetId.PKNIGHT:
        return TargetId.PKNIGHT.value
    if detected.target_id is TargetId.CUSTOM:
        return UNKNOWN_SUMMARY
    labels: list[str] = []
    for route in _artnet_routes(state):
        ip = (route.output_ip or route.line_uid or "").strip()
        if ip:
            labels.append(label_for_output_ip(ip))
    if TargetId.AIR2DMX.value in labels:
        return TargetId.AIR2DMX.value
    if TargetId.PKNIGHT.value in labels:
        return TargetId.PKNIGHT.value
    if labels and all(label == "LOOPBACK" for label in labels):
        return "LOOPBACK"
    return UNKNOWN_SUMMARY


def play_output_summary(state: AppState) -> str:
    """Human-readable current output. WiZ only when the enable flag is on."""
    wired = wired_output_label(state)
    if not state.wiz_enabled:
        return wired
    if wired == UNKNOWN_SUMMARY:
        return "WIZ"
    return f"WIZ + {wired}"
