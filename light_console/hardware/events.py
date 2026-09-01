from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
