"""Known fixture channel roles from the Shield QXF definitions. No guessed DMX.

PAR (Oloaxolx 8ch) SAT/HUE policy — no RGBW calibration is available, so this
is a deterministic source-reversible policy, not a measured emitter map.

  Dimmer  never rewritten by SAT/HUE (MASTER is QLC Grand Master on the live path)
  Strobe  never touched
  R,G,B   HSV SAT then HUE, HSV V preserved. SAT 100 / HUE 0 is byte-exact.
  White   never hue-rotated; never written by SAT (no uncalibrated RGB→W transfer)
  Amber   never touched
  UV      never touched

SAT 0   chromatic RGB → equal gray at original V; W/A/UV unchanged
SAT 50  RGB chroma at 50% of source S; W/A/UV unchanged
SAT 100 identity RGB; W/A/UV unchanged
SAT 200 RGB S' = min(1, 2S); W/A/UV unchanged

WiZ (6ch RGB+CCT) policy, matching services/wiz/wiz_artnet_bridge.build_on_params:

  White Mode > 0  explicit CCT/white. RGB ignored by the bridge. SAT/HUE no-op
                  on all six channels. CTC is not a hue parameter.
  White Mode == 0 RGB mode. SAT/HUE on R,G,B only. Dimmer / White Mode / CTC
                  unchanged. SAT 0 stays RGB gray (does not switch White Mode).
"""

from __future__ import annotations

from dataclasses import dataclass

from light_console.live_color import (
    MASTER_DEFAULT,
    SAT_DEFAULT,
    HUE_DEFAULT,
    scale_intensity,
    transform_rgb,
)
from light_console.output.fixtures import PatchedFixture

KIND_RGB = "rgb"
KIND_INTENSITY = "intensity-only"
KIND_NON_COLOR = "non-color"
KIND_UNSUPPORTED = "unsupported"

SOURCE_CHROMATIC = "chromatic-rgb"
SOURCE_NEUTRAL_RGB = "neutral-rgb"
SOURCE_BLACK = "black"
SOURCE_DEDICATED_WHITE = "dedicated-white"
SOURCE_CCT_WHITE = "cct-white"
SOURCE_MIXED_RGB_WHITE = "mixed-rgb-white"

PAR_DIMMER, PAR_STROBE, PAR_R, PAR_G, PAR_B, PAR_W, PAR_A, PAR_UV = range(8)
WIZ_DIMMER, WIZ_R, WIZ_G, WIZ_B, WIZ_WHITE_MODE, WIZ_CTC = range(6)


@dataclass(frozen=True)
class FixtureRole:
    kind: str
    dimmer: int | None = None
    red: int | None = None
    green: int | None = None
    blue: int | None = None
    white: int | None = None
    strobe: int | None = None
    amber: int | None = None
    uv: int | None = None
    ctc: int | None = None
    extras: tuple[int, ...] = ()
    color_model: str = ""


def _key(manufacturer: str, model: str, mode: str) -> tuple[str, str, str]:
    return (manufacturer.strip(), model.strip(), mode.strip())


# Channel indexes are Mode Channel Number from the installed custom QXFs.
ROLES: dict[tuple[str, str, str], FixtureRole] = {
    ("Eurolite", "N-150 MK2", "1 channel mode"): FixtureRole(
        kind=KIND_NON_COLOR,
        extras=(0,),
        color_model="fog/effect",
    ),
    ("Oloaxolx", "60 W Battery LED Par Spot", "8ch"): FixtureRole(
        kind=KIND_RGB,
        dimmer=0,
        strobe=1,
        red=2,
        green=3,
        blue=4,
        white=5,
        amber=6,
        uv=7,
        extras=(1, 6, 7),
        color_model="rgb+white/amber/uv",
    ),
    ("WiZ", "WiZ RGB+CCT via Pi", "6 Channel"): FixtureRole(
        kind=KIND_RGB,
        dimmer=0,
        red=1,
        green=2,
        blue=3,
        white=4,
        ctc=5,
        extras=(5,),
        color_model="rgb+white-mode/ctc",
    ),
}


def role_for(fixture: PatchedFixture) -> FixtureRole:
    key = _key(fixture.manufacturer, fixture.model, fixture.mode)
    if key in ROLES:
        return ROLES[key]
    return FixtureRole(kind=KIND_UNSUPPORTED, color_model="unknown")


def classify(fixture: PatchedFixture) -> str:
    role = role_for(fixture)
    if role.kind == KIND_RGB and role.white is not None:
        return "RGB (white excluded from HSV)"
    return role.kind


def _pad(ch: list[int] | tuple[int, ...], n: int) -> list[int]:
    out = [int(v) for v in ch[:n]]
    if len(out) < n:
        out.extend([0] * (n - len(out)))
    return out


def classify_par_slot(ch: list[int] | tuple[int, ...]) -> str:
    dim, strobe, r, g, b, w, a, uv = _pad(ch, 8)
    del dim, strobe, a, uv
    if r == g == b == 0:
        return SOURCE_DEDICATED_WHITE if w > 0 else SOURCE_BLACK
    if r == g == b:
        return SOURCE_MIXED_RGB_WHITE if w > 0 else SOURCE_NEUTRAL_RGB
    return SOURCE_MIXED_RGB_WHITE if w > 0 else SOURCE_CHROMATIC


def classify_wiz_slot(ch: list[int] | tuple[int, ...]) -> str:
    dim, r, g, b, white, ctc = _pad(ch, 6)
    del dim, ctc
    if white > 0:
        return SOURCE_CCT_WHITE
    if r == g == b == 0:
        return SOURCE_BLACK
    if r == g == b:
        return SOURCE_NEUTRAL_RGB
    return SOURCE_CHROMATIC


def transform_par_channels(
    ch: list[int] | tuple[int, ...],
    sat: int = SAT_DEFAULT,
    hue: int = HUE_DEFAULT,
) -> tuple[int, int, int, int, int, int, int, int]:
    """8ch PAR: SAT/HUE on RGB only. Dimmer/strobe/W/A/UV copied from source."""
    dim, strobe, r, g, b, w, a, uv = _pad(ch, 8)
    r2, g2, b2 = transform_rgb(
        r, g, b, sat=sat, hue=hue, master=MASTER_DEFAULT, scale_value=False
    )
    return (dim, strobe, r2, g2, b2, w, a, uv)


def transform_wiz_channels(
    ch: list[int] | tuple[int, ...],
    sat: int = SAT_DEFAULT,
    hue: int = HUE_DEFAULT,
) -> tuple[int, int, int, int, int, int]:
    """6ch WiZ: SAT/HUE on RGB only when White Mode == 0. CCT mode is identity."""
    dim, r, g, b, white, ctc = _pad(ch, 6)
    if white > 0:
        return (dim, r, g, b, white, ctc)
    r2, g2, b2 = transform_rgb(
        r, g, b, sat=sat, hue=hue, master=MASTER_DEFAULT, scale_value=False
    )
    return (dim, r2, g2, b2, white, ctc)


def apply_roles_to_universe(
    source: list[int] | tuple[int, ...],
    fixtures: tuple[PatchedFixture, ...],
    *,
    sat: int = SAT_DEFAULT,
    hue: int = HUE_DEFAULT,
    master: int = MASTER_DEFAULT,
) -> list[int]:
    """Copy source, then SAT→HUE on known RGB and MASTER on known intensity."""
    out = [int(v) for v in source]
    color_identity = sat == SAT_DEFAULT and hue == HUE_DEFAULT
    master_identity = master == MASTER_DEFAULT
    if color_identity and master_identity:
        return out
    for fx in fixtures:
        role = role_for(fx)
        base = fx.address
        if not color_identity:
            n = max(0, int(fx.channels))
            if n and base < len(out):
                slot = source[base : min(len(source), base + n)]
                if role.color_model == "rgb+white/amber/uv":
                    new_slot = transform_par_channels(slot, sat, hue)
                elif role.color_model == "rgb+white-mode/ctc":
                    new_slot = transform_wiz_channels(slot, sat, hue)
                elif role.kind == KIND_RGB and None not in (role.red, role.green, role.blue):
                    r_i = role.red
                    g_i = role.green
                    b_i = role.blue
                    rgb = transform_rgb(
                        slot[r_i] if r_i < len(slot) else 0,
                        slot[g_i] if g_i < len(slot) else 0,
                        slot[b_i] if b_i < len(slot) else 0,
                        sat=sat,
                        hue=hue,
                        master=MASTER_DEFAULT,
                        scale_value=False,
                    )
                    new_slot = list(_pad(slot, n))
                    if r_i < len(new_slot):
                        new_slot[r_i] = rgb[0]
                    if g_i < len(new_slot):
                        new_slot[g_i] = rgb[1]
                    if b_i < len(new_slot):
                        new_slot[b_i] = rgb[2]
                    new_slot = tuple(new_slot)
                else:
                    new_slot = None
                if new_slot is not None:
                    for i, value in enumerate(new_slot):
                        idx = base + i
                        if idx < len(out):
                            out[idx] = int(value)
        if role.dimmer is not None and not master_identity:
            d_i = base + role.dimmer
            if d_i < len(out):
                out[d_i] = scale_intensity(source[d_i], master)
    return out
