"""WiZ setPilot mapping copied from services/wiz/wiz_artnet_bridge.py.

White Mode > 0 is CCT/white: RGB is ignored. White Mode == 0 is RGB color.
Do not treat CTC as hue. Do not guess lamp calibration.
"""

from __future__ import annotations

MIN_TEMP_K = 2200
MAX_TEMP_K = 6500


def dmx_to_temp(v: int) -> int:
    return round(MIN_TEMP_K + (MAX_TEMP_K - MIN_TEMP_K) * (int(v) / 255.0))


def level_to_wiz_dimming(level: int) -> int:
    if level <= 0:
        return 0
    return round(10 + (int(level) - 1) * 90 / 254)


def build_on_params(master: int, r: int, g: int, b: int, white: int, temp: int) -> dict | None:
    if white > 0:
        effective = round(int(master) * int(white) / 255.0)
        if effective <= 0:
            return None
        return {
            "state": True,
            "temp": dmx_to_temp(temp),
            "dimming": level_to_wiz_dimming(effective),
        }
    return {
        "state": True,
        "r": int(r),
        "g": int(g),
        "b": int(b),
        "dimming": level_to_wiz_dimming(master),
    }
