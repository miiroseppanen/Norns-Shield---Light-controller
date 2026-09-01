from __future__ import annotations

from abc import ABC, abstractmethod

from light_console.display.framebuffer import Framebuffer
from light_console.hardware.events import HardwareEvent


class HardwareBackend(ABC):
    """Only this layer may touch GPIO, evdev, SPI, or the simulator window."""

    @abstractmethod
    def read_events(self) -> list[HardwareEvent]:
        ...

    @abstractmethod
    def set_display(self, fb: Framebuffer) -> None:
        ...

    @abstractmethod
    def set_display_brightness(self, level: int) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    def idle(self, timeout_s: float) -> None:
        """Pump native events / sleep. Simulator overrides this with pygame.time.wait."""
        del timeout_s
