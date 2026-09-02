#!/usr/bin/env python3
"""Read-only boot persistence check for Shield XL Milestone 0.2 Phase 7/8.

Does not request GPIO lines, does not talk SPI, does not reboot.
"""
from __future__ import annotations

import sys
from pathlib import Path

import gpiod

CHIP = "/dev/gpiochip0"
CONFIG = Path("/boot/firmware/config.txt")
SPIDEV = Path("/dev/spidev0.0")
LINES = (
    (22, "K1"),
    (26, "K2"),
    (13, "K3"),
    (4, "E1A"),
    (27, "E1B"),
    (12, "E2A"),
    (25, "E2B"),
    (24, "E3A"),
    (23, "E3B"),
    (5, "OLED_DC"),
    (6, "OLED_RESET"),
)


def main() -> int:
    fails: list[str] = []
    text = CONFIG.read_text(encoding="utf-8", errors="replace")
    active = any(
        ln.strip() == "dtparam=spi=on" for ln in text.splitlines()
    )
    print(f"config {CONFIG}: dtparam=spi=on {'YES' if active else 'NO'}", flush=True)
    if not active:
        fails.append("spi not persistently enabled in config.txt")

    print(f"{SPIDEV}: {'YES' if SPIDEV.exists() else 'NO'}", flush=True)
    if not SPIDEV.exists():
        fails.append("missing /dev/spidev0.0")

    chip = gpiod.Chip(CHIP)
    info = chip.get_info()
    print(f"chip {info.name} label={info.label!r}", flush=True)
    if info.label != "pinctrl-bcm2711":
        fails.append(f"unexpected chip label {info.label!r}")
    for off, name in LINES:
        li = chip.get_line_info(off)
        consumer = li.consumer if li.consumer not in (None, "None", "") else None
        print(
            f"  {name:11} GPIO{off:<3} used={li.used} consumer={consumer!r}",
            flush=True,
        )
        if li.used or consumer:
            fails.append(f"{name} GPIO{off} has consumer {consumer!r}")
    chip.close()

    if fails:
        print("BOOT_CHECK FAIL: " + "; ".join(fails), flush=True)
        return 1
    print("BOOT_CHECK PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
