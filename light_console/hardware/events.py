from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Physical control names. Hardware IDs are these integers; UI code must use K1–K3 / E1–E3.
K1 = 1
K2 = 2
K3 = 3
E1 = 1
E2 = 2
E3 = 3

EncoderId = Literal[1, 2, 3]
ButtonId = Literal[1, 2, 3]
ButtonAction = Literal["press", "release", "long_press"]


@dataclass(frozen=True)
class EncoderEvent:
    encoder: EncoderId
    delta: int


@dataclass(frozen=True)
class ButtonEvent:
    button: ButtonId
    action: ButtonAction


@dataclass(frozen=True)
class SimCommandEvent:
    """Simulator-only: mock QLC/WiZ/MIDI/DMX/upstream. Never produced by ShieldXLBackend."""

    command: str
    value: int | None = None


HardwareEvent = EncoderEvent | ButtonEvent | SimCommandEvent
