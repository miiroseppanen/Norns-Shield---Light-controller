from __future__ import annotations

from light_console.hardware.events import EncoderEvent, HardwareEvent
from light_console.state import ScreenId

E1 = 1
E2 = 2
E3 = 3


def apply_encoder_delta(current: int, delta: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, current + delta))


def wrap_index(index: int, delta: int, count: int) -> int:
    if count <= 0:
        return 0
    return (index + delta) % count


def scale_encoder_event(event: EncoderEvent, gain: int = 1) -> EncoderEvent:
    if gain == 1:
        return event
    return EncoderEvent(encoder=event.encoder, delta=event.delta * gain)


def fold_encoder_stream(events: list[HardwareEvent]) -> list[HardwareEvent]:
    """Net same-encoder detents in one poll. No leftover across calls."""
    nets: dict[int, int] = {}
    for ev in events:
        if isinstance(ev, EncoderEvent):
            nets[ev.encoder] = nets.get(ev.encoder, 0) + ev.delta
    emitted: set[int] = set()
    out: list[HardwareEvent] = []
    for ev in events:
        if isinstance(ev, EncoderEvent):
            if ev.encoder in emitted:
                continue
            total = nets.get(ev.encoder, 0)
            emitted.add(ev.encoder)
            if total:
                out.append(EncoderEvent(encoder=ev.encoder, delta=total))
            continue
        out.append(ev)
    return out


def nav_steps(delta: int) -> int:
    """Isolated detent stays 1. Rapid burst in one poll is ~half as aggressive."""
    if delta == 0:
        return 0
    sign = 1 if delta > 0 else -1
    mag = abs(int(delta))
    if mag <= 1:
        return sign * mag
    return sign * max(1, (mag + 1) // 2)


def is_nav_encoder(screen: ScreenId, encoder: int) -> bool:
    """Discrete list/menu motion, not continuous parameter edit."""
    if screen in {ScreenId.STARTING_UP, ScreenId.SHUTTING_DOWN}:
        return False
    if screen == ScreenId.PLAY and encoder == E1:
        return False
    if screen == ScreenId.PARAMS and encoder == E3:
        return False
    return True


def scale_ui_delta(screen: ScreenId, encoder: int, delta: int) -> int:
    if is_nav_encoder(screen, encoder):
        return nav_steps(delta)
    return delta
