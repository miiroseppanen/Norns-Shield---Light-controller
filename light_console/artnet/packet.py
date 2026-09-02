"""Art-Net / ArtDMX parse helpers. No sockets; no GPIO."""

from __future__ import annotations

from dataclasses import dataclass

ARTNET_HEADER = b"Art-Net\x00"
OP_POLL = 0x2000
OP_POLL_REPLY = 0x2100
OP_DMX = 0x5000

OPCODE_NAMES = {
    OP_POLL: "ArtPoll",
    OP_POLL_REPLY: "ArtPollReply",
    OP_DMX: "ArtDMX",
}


@dataclass(frozen=True)
class ArtNetPacket:
    opcode: int
    opcode_name: str
    protocol: int
    sequence: int
    physical: int
    port_address: int
    net: int
    subnet: int
    universe: int
    length: int
    data: bytes

    @property
    def dmx(self) -> bytes:
        return self.data


def parse_artnet(payload: bytes) -> ArtNetPacket | None:
    """Return a parsed packet, or None if malformed / too short / bad header."""
    if len(payload) < 10:
        return None
    if payload[:8] != ARTNET_HEADER:
        return None
    opcode = int.from_bytes(payload[8:10], "little")
    name = OPCODE_NAMES.get(opcode, f"0x{opcode:04x}")
    if opcode != OP_DMX:
        proto = int.from_bytes(payload[10:12], "big") if len(payload) >= 12 else 0
        return ArtNetPacket(
            opcode=opcode,
            opcode_name=name,
            protocol=proto,
            sequence=0,
            physical=0,
            port_address=0,
            net=0,
            subnet=0,
            universe=0,
            length=0,
            data=b"",
        )
    if len(payload) < 18:
        return None
    proto = int.from_bytes(payload[10:12], "big")
    sequence = payload[12]
    physical = payload[13]
    port = int.from_bytes(payload[14:16], "little")
    declared = int.from_bytes(payload[16:18], "big")
    if declared > 512:
        return None
    data = payload[18 : 18 + declared]
    net = (port >> 8) & 0x7F
    subnet = (port >> 4) & 0x0F
    universe = port & 0x0F
    return ArtNetPacket(
        opcode=opcode,
        opcode_name=name,
        protocol=proto,
        sequence=sequence,
        physical=physical,
        port_address=port,
        net=net,
        subnet=subnet,
        universe=universe,
        length=len(data),
        data=data,
    )


def build_artdmx(
    dmx: bytes,
    *,
    sequence: int = 1,
    port_address: int = 0,
    physical: int = 0,
) -> bytes:
    """Test helper: construct a minimal ArtDMX datagram."""
    body = bytes(dmx[:512])
    length = len(body)
    return (
        ARTNET_HEADER
        + OP_DMX.to_bytes(2, "little")
        + (14).to_bytes(2, "big")
        + bytes([sequence & 0xFF, physical & 0xFF])
        + (port_address & 0x7FFF).to_bytes(2, "little")
        + length.to_bytes(2, "big")
        + body
    )
