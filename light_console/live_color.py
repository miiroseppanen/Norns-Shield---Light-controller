"""Live SAT/HUE/MASTER color math. Always from the current source; never mutates input.

Brightness model: HSV value (V = max(R,G,B)). Hue rotation and saturation
keep V; they do not preserve Rec.709 luminance. MASTER is a separate linear
scale of intensity bytes (or QLC Grand Master on the live path).

Neutral identity (SAT 100, HUE 0, MASTER 100) is a byte-exact bypass. Gray
and black skip hue/sat so rotation cannot invent chroma.
"""

from __future__ import annotations

from dataclasses import dataclass

MASTER_DEFAULT = 100
SAT_DEFAULT = 100
HUE_DEFAULT = 0
MASTER_MIN, MASTER_MAX = 0, 100
SAT_MIN, SAT_MAX = 0, 200
HUE_MIN, HUE_MAX = -180, 180


def clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def wrap_hue_deg(value: int) -> int:
    n = int(value)
    while n > HUE_MAX:
        n -= 360
    while n < HUE_MIN:
        n += 360
    return n


def rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx = max(rf, gf, bf)
    mn = min(rf, gf, bf)
    delta = mx - mn
    if delta == 0:
        h = 0.0
    elif mx == rf:
        h = (60.0 * ((gf - bf) / delta) + 360.0) % 360.0
    elif mx == gf:
        h = (60.0 * ((bf - rf) / delta) + 120.0) % 360.0
    else:
        h = (60.0 * ((rf - gf) / delta) + 240.0) % 360.0
    s = 0.0 if mx == 0 else delta / mx
    return h, s, mx


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    s = max(0.0, min(1.0, s))
    v = max(0.0, min(1.0, v))
    h = h % 360.0
    c = v * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = v - c
    if h < 60:
        rp, gp, bp = c, x, 0.0
    elif h < 120:
        rp, gp, bp = x, c, 0.0
    elif h < 180:
        rp, gp, bp = 0.0, c, x
    elif h < 240:
        rp, gp, bp = 0.0, x, c
    elif h < 300:
        rp, gp, bp = x, 0.0, c
    else:
        rp, gp, bp = c, 0.0, x
    return (
        int(round((rp + m) * 255.0)),
        int(round((gp + m) * 255.0)),
        int(round((bp + m) * 255.0)),
    )


def format_hue(deg: int) -> str:
    if deg > 0:
        return f"+{deg}°"
    if deg < 0:
        return f"{deg}°"
    return "0°"


def format_percent(value: int) -> str:
    return f"{int(value)}%"


@dataclass(frozen=True)
class LiveControls:
    master: int = MASTER_DEFAULT
    sat: int = SAT_DEFAULT
    hue: int = HUE_DEFAULT

    wiz_enabled: bool = True
    identify_mac: str = ""
    discover: bool = False

    @property
    def identity(self) -> bool:
        return self.master == MASTER_DEFAULT and self.sat == SAT_DEFAULT and self.hue == HUE_DEFAULT

    @property
    def color_identity(self) -> bool:
        return self.sat == SAT_DEFAULT and self.hue == HUE_DEFAULT


def transform_rgb(
    r: int,
    g: int,
    b: int,
    *,
    sat: int = SAT_DEFAULT,
    hue: int = HUE_DEFAULT,
    master: int = MASTER_DEFAULT,
    scale_value: bool = True,
) -> tuple[int, int, int]:
    """SAT then HUE on HSV, optional MASTER on the resulting RGB bytes.

    H' = (H + hue_offset) mod 360. S' = clamp(S * sat/100, 0, 1). V unchanged.
    Identity (sat=100, hue=0, master=100) is byte-exact. MASTER after RGB
    preserves channel ratios without a second HSV round-trip.
    """
    src = (clamp_int(r, 0, 255), clamp_int(g, 0, 255), clamp_int(b, 0, 255))
    sat_n = clamp_int(sat, SAT_MIN, SAT_MAX)
    hue_n = wrap_hue_deg(hue)
    master_n = clamp_int(master, MASTER_MIN, MASTER_MAX)
    color_identity = sat_n == SAT_DEFAULT and hue_n == HUE_DEFAULT
    if color_identity or src[0] == src[1] == src[2]:
        out = src
    else:
        h, s, v = rgb_to_hsv(*src)
        s = max(0.0, min(1.0, s * (sat_n / 100.0)))
        if s <= 0.0:
            gray = int(round(v * 255.0))
            out = (gray, gray, gray)
        else:
            h = (h + hue_n) % 360.0
            out = hsv_to_rgb(h, s, v)
    if scale_value and master_n != MASTER_DEFAULT:
        return (
            scale_intensity(out[0], master_n),
            scale_intensity(out[1], master_n),
            scale_intensity(out[2], master_n),
        )
    return out


def scale_intensity(value: int, master: int) -> int:
    if master == MASTER_DEFAULT:
        return clamp_int(value, 0, 255)
    return clamp_int(round(clamp_int(value, 0, 255) * (clamp_int(master, MASTER_MIN, MASTER_MAX) / 100.0)), 0, 255)
