from __future__ import annotations

from light_console.hardware.events import EncoderEvent


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
