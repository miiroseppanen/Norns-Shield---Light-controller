from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from light_console.display.framebuffer import Framebuffer
from light_console.hardware.base import HardwareBackend
from light_console.hardware.events import ButtonEvent, EncoderEvent, HardwareEvent
from light_console.hardware.pinout import ENCODER_OVERLAY, KEY_PINS

CHIP_PATH = "/dev/gpiochip0"
EDGES_PER_DETENT = 4
BTN_DEBOUNCE = timedelta(milliseconds=10)
ENC_DEBOUNCE = timedelta(milliseconds=2)
# Proven on shield: software CW when A leads B (gray 0→2→3→1).
CW = {(0, 2), (2, 3), (3, 1), (1, 0)}
CCW = {(0, 1), (1, 3), (3, 2), (2, 0)}


class HardwareNotReady(RuntimeError):
    """GPIO/SPI unavailable on this machine (Mac simulator, missing modules)."""


def _ab_int(a, b, value_active) -> int:
    return ((1 if a == value_active else 0) << 1) | (1 if b == value_active else 0)


@dataclass
class _Enc:
    encoder: int
    gpio_a: int
    gpio_b: int
    a: object = None
    b: object = None
    gray: int = 0
    quarter: int = 0


class ShieldXLBackend(HardwareBackend):
    """GPIO buttons/encoders + SSD1322. No QLC, no page mapping."""

    def __init__(self, spi_hz: int = 8_000_000) -> None:
        try:
            import gpiod
            from gpiod.edge_event import EdgeEvent
            from gpiod.line import Bias, Direction, Edge, Value
        except ImportError as exc:
            raise HardwareNotReady(
                "gpiod is not available. Use the Mac simulator."
            ) from exc
        if not Path("/dev/spidev0.0").exists() or not Path(CHIP_PATH).exists():
            raise HardwareNotReady(
                "Shield SPI/GPIO device nodes are missing. Use the Mac simulator."
            )

        from light_console.hardware.oled import Ssd1322
        from light_console.display.lifecycle import STARTING_UP_TEXT, render_lifecycle
        from light_console.logutil import LOG

        self._gpiod = gpiod
        self._EdgeEvent = EdgeEvent
        self._Value = Value
        self._oled = Ssd1322(hz=spi_hz)
        self.starting_up_at: float | None = None
        self._oled.init()
        try:
            self._oled.show_framebuffer(render_lifecycle(STARTING_UP_TEXT))
            self.starting_up_at = time.monotonic()
            LOG.info("STARTING UP painted")
        except Exception:
            LOG.exception("STARTING UP paint failed")
        self._closed = False
        self._encs: dict[int, _Enc] = {}

        btn_settings = gpiod.LineSettings(
            direction=Direction.INPUT,
            edge_detection=Edge.BOTH,
            bias=Bias.PULL_UP,
            debounce_period=BTN_DEBOUNCE,
        )
        enc_settings = gpiod.LineSettings(
            direction=Direction.INPUT,
            edge_detection=Edge.BOTH,
            bias=Bias.AS_IS,
            debounce_period=ENC_DEBOUNCE,
        )
        config: dict[int, object] = {}
        self._offset_kind: dict[int, str] = {}
        for button_id, fact in KEY_PINS.items():
            config[fact.bcm] = btn_settings
            self._offset_kind[fact.bcm] = f"K{button_id}"
        for enc_id, (pin_a, pin_b) in ENCODER_OVERLAY.items():
            self._encs[enc_id] = _Enc(enc_id, pin_a.bcm, pin_b.bcm)
            config[pin_a.bcm] = enc_settings
            config[pin_b.bcm] = enc_settings
            self._offset_kind[pin_a.bcm] = f"E{enc_id}"
            self._offset_kind[pin_b.bcm] = f"E{enc_id}"

        try:
            self._input = gpiod.request_lines(
                CHIP_PATH,
                consumer="light-console-in",
                config=config,
            )
        except OSError as exc:
            self._oled.close()
            raise HardwareNotReady(f"GPIO request failed: {exc}") from exc

        for st in self._encs.values():
            st.a = self._input.get_value(st.gpio_a)
            st.b = self._input.get_value(st.gpio_b)
            st.gray = _ab_int(st.a, st.b, Value.ACTIVE)

    def read_events(self) -> list[HardwareEvent]:
        if self._closed:
            return []
        out: list[HardwareEvent] = []
        try:
            pending = self._input.wait_edge_events(0)
        except OSError:
            return []
        if not pending:
            return []
        try:
            edges = self._input.read_edge_events()
        except OSError:
            return []
        Falling = self._EdgeEvent.Type.FALLING_EDGE
        Rising = self._EdgeEvent.Type.RISING_EDGE
        Value = self._Value
        for event in edges:
            kind = self._offset_kind.get(event.line_offset)
            if kind is None:
                continue
            if kind.startswith("K"):
                button = int(kind[1])
                if event.event_type == Falling:
                    out.append(ButtonEvent(button=button, action="press"))  # type: ignore[arg-type]
                elif event.event_type == Rising:
                    out.append(ButtonEvent(button=button, action="release"))  # type: ignore[arg-type]
                continue
            st = self._encs[int(kind[1])]
            bit = Value.ACTIVE if event.event_type == Rising else Value.INACTIVE
            if event.line_offset == st.gpio_a:
                st.a = bit
            elif event.line_offset == st.gpio_b:
                st.b = bit
            new = _ab_int(st.a, st.b, Value.ACTIVE)
            old = st.gray
            if new == old:
                continue
            if (old, new) in CW:
                delta = 1
            elif (old, new) in CCW:
                delta = -1
            else:
                st.gray = new
                continue
            st.quarter += delta
            st.gray = new
            while st.quarter >= EDGES_PER_DETENT:
                st.quarter -= EDGES_PER_DETENT
                out.append(EncoderEvent(encoder=st.encoder, delta=1))  # type: ignore[arg-type]
            while st.quarter <= -EDGES_PER_DETENT:
                st.quarter += EDGES_PER_DETENT
                out.append(EncoderEvent(encoder=st.encoder, delta=-1))  # type: ignore[arg-type]
        return out

    def set_display(self, fb: Framebuffer) -> None:
        if self._closed:
            return
        self._oled.show_framebuffer(fb)

    def set_display_brightness(self, level: int) -> None:
        del level

    def idle(self, timeout_s: float) -> None:
        if self._closed:
            return
        try:
            self._input.wait_edge_events(max(0.0, timeout_s))
        except OSError:
            return

    def close(self) -> None:
        """Drop SPI/GPIO. Never paint a blank frame; SHUTTING DOWN must remain."""
        if self._closed:
            return
        self._closed = True
        try:
            self._input.release()
        except Exception:
            pass
        try:
            self._oled.close()
        except Exception:
            pass
