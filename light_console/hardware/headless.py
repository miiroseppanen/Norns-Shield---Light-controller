from __future__ import annotations

from dataclasses import dataclass, field

from light_console.display.framebuffer import Framebuffer
from light_console.hardware.base import HardwareBackend
from light_console.hardware.events import ButtonEvent, EncoderEvent, HardwareEvent


@dataclass
class HeadlessBackend(HardwareBackend):
    """In-memory hardware for unit tests. No pygame, no GPIO."""

    events: list[HardwareEvent] = field(default_factory=list)
    last_frame: bytes | None = None
    frames: list[bytes] = field(default_factory=list)
    brightness: int = 15
    closed: bool = False
    cleared_on_close: bool = False

    def push(self, *events: HardwareEvent) -> None:
        self.events.extend(events)

    def read_events(self) -> list[HardwareEvent]:
        batch = self.events
        self.events = []
        return batch

    def set_display(self, fb: Framebuffer) -> None:
        self.last_frame = bytes(fb.pixels)
        self.frames.append(self.last_frame)

    def set_display_brightness(self, level: int) -> None:
        self.brightness = level

    def close(self) -> None:
        self.closed = True

    def idle(self, timeout_s: float) -> None:
        del timeout_s


def tap(button: int) -> list[HardwareEvent]:
    return [
        ButtonEvent(button=button, action="press"),  # type: ignore[arg-type]
        ButtonEvent(button=button, action="release"),  # type: ignore[arg-type]
    ]


def enc(encoder: int, delta: int) -> EncoderEvent:
    return EncoderEvent(encoder=encoder, delta=delta)  # type: ignore[arg-type]
