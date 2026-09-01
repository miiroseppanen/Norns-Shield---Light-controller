from __future__ import annotations

from light_console.display.framebuffer import Framebuffer
from light_console.hardware.base import HardwareBackend
from light_console.hardware.events import HardwareEvent


class HardwareNotReady(RuntimeError):
    """GPIO/SPI path is intentionally disabled until Milestone 0.2."""


class ShieldXLBackend(HardwareBackend):
    """Real shield. Milestone 0.1 must not open GPIO."""

    def __init__(self) -> None:
        raise HardwareNotReady(
            "ShieldXLBackend is not enabled in 0.1.0. "
            "Use the Mac simulator. GPIO proof is Milestone 0.2 on a new microSD. "
            "Pin facts: research/shieldxl.md"
        )

    def read_events(self) -> list[HardwareEvent]:
        raise HardwareNotReady("no GPIO")

    def set_display(self, fb: Framebuffer) -> None:
        del fb
        raise HardwareNotReady("no SPI")

    def set_display_brightness(self, level: int) -> None:
        del level
        raise HardwareNotReady("no SPI")

    def close(self) -> None:
        return
