from __future__ import annotations

from dataclasses import dataclass, field

from light_console.hardware.events import ButtonEvent, ButtonId


@dataclass
class _Held:
    t0: float
    long_sent: bool = False


@dataclass
class ButtonTracker:
    """Userspace short vs long. Hardware is only press/release (active low on the shield)."""

    long_press_s: float = 0.6
    _held: dict[int, _Held] = field(default_factory=dict)

    def on_hardware_press(self, button: ButtonId, now: float) -> list[ButtonEvent]:
        self._held[int(button)] = _Held(t0=now)
        return []

    def on_hardware_release(self, button: ButtonId, now: float) -> list[ButtonEvent]:
        held = self._held.pop(int(button), None)
        if held is None:
            return [ButtonEvent(button=button, action="release")]
        out: list[ButtonEvent] = []
        if not held.long_sent:
            out.append(ButtonEvent(button=button, action="press"))
        out.append(ButtonEvent(button=button, action="release"))
        return out

    def poll(self, now: float) -> list[ButtonEvent]:
        out: list[ButtonEvent] = []
        for bid, held in self._held.items():
            if not held.long_sent and (now - held.t0) >= self.long_press_s:
                held.long_sent = True
                out.append(ButtonEvent(button=bid, action="long_press"))  # type: ignore[arg-type]
        return out
