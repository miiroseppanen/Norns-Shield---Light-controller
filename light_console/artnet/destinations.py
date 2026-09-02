"""Classify Art-Net destinations. Enforcement for REAL_OUTPUT is not in the UI."""

from __future__ import annotations

from enum import Enum

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

# Lighting LAN / nodes that must never be a 0.6B destination.
FORBIDDEN_HOSTS = frozenset(
    {
        "192.168.88.201",  # PKNight
        "192.168.88.248",  # production Pi
        "192.168.88.255",  # LIGHT-CONTROL broadcast
        "255.255.255.255",
    }
)


class OutputKind(str, Enum):
    SAFE_LOOPBACK = "safe_loopback"
    REAL_OUTPUT = "real_output"


def classify_destination(host: str) -> OutputKind:
    h = host.strip().lower()
    if h in LOOPBACK_HOSTS or h.startswith("127."):
        return OutputKind.SAFE_LOOPBACK
    return OutputKind.REAL_OUTPUT


def is_forbidden_host(host: str) -> bool:
    h = host.strip()
    if h in FORBIDDEN_HOSTS:
        return True
    if h.startswith("10.42."):  # WIZ-LIGHTS
        return True
    return False
