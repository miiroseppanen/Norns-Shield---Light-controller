"""Independently known Art-Net nodes. Never treated as QLC destinations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtNetNode:
    name: str
    ipv4: str
    mac: str = ""
    wire_universe: int | None = None


# Identified 2026-09-11 on LIGHT-CONTROL. Not a QLC outputIP unless the
# workspace/runtime actually has outputIP equal to this address.
KNOWN_ARTNET_NODES: tuple[ArtNetNode, ...] = (
    ArtNetNode(
        name="AIR2DMX",
        ipv4="192.168.88.242",
        mac="3c:61:05:97:e1:93",
        wire_universe=1,
    ),
    ArtNetNode(
        name="PKNight",
        ipv4="192.168.88.201",
    ),
)
