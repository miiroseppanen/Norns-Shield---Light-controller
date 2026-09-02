"""Verified pin facts for shieldXL / norns-shield 210330. Not a driver.

See research/shieldxl.md. Encoder E2 vs E3 physical identity is UNKNOWN until evtest.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PinFact:
    bcm: int
    role: str
    active_low: bool = False
    confidence: str = "HIGH"
    note: str = ""


# OLED SSD1322, 4-wire SPI
OLED_DC = PinFact(5, "oled_dc")
OLED_RESET = PinFact(6, "oled_reset", active_low=True)
OLED_CS = PinFact(8, "oled_cs", active_low=True, note="SPI0 CE0")
OLED_MOSI = PinFact(10, "oled_mosi", note="SPI0 MOSI")
OLED_SCLK = PinFact(11, "oled_sclk", note="SPI0 SCLK")

# Keys — schematic and norns overlay agree
KEY_PINS: dict[int, PinFact] = {
    1: PinFact(22, "k1", active_low=True),
    2: PinFact(26, "k2", active_low=True),
    3: PinFact(13, "k3", active_low=True),
}

# Overlay names from shieldXL install/boot/config.txt
ENCODER_OVERLAY: dict[int, tuple[PinFact, PinFact]] = {
    1: (
        PinFact(4, "e1_a"),
        PinFact(27, "e1_b"),
    ),
    2: (
        PinFact(12, "e2_a", note="physical E2 A; schematic part E3 A"),
        PinFact(25, "e2_b", note="physical E2 B; schematic part E3 B"),
    ),
    3: (
        PinFact(24, "e3_a", note="physical E3 A; schematic part E2 A"),
        PinFact(23, "e3_b", note="physical E3 B; schematic part E2 B"),
    ),
}

RESERVED_AUDIO = (17, 18, 19, 20, 21, 2, 3)
RESERVED_UART_MIDI = (14, 15)
