"""Live SAT/HUE output path: source frame → transform → sink / setPilot params.

Wired PAR
---------
QLC currently unicasts Art-Net U2 directly to the armed node (AIR2DMX). This
module rewrites an ArtDMX payload in memory and hands it to a sink. Tests use
a mock sink so no UDP leaves the process.

This is the software output path. It does not:

- open sockets
- patch QLC Simple Desk
- write master.qxw
- change QLC outputIP / routing
- apply MASTER (QLC Grand Master already scaled intensity)

A live intercept/forwarder is a routing change (QLC must stop being the
direct sender to AIR2DMX). That is not armed here.

WiZ
---
transform_wiz_channels then build_on_params. wiz_enabled=False emits nothing.
The Art-Net bridge reads sat/hue/wiz/identify/discover from
/tmp/light-console.status (mtime cache) and applies the same functions
before setPilot. identify is a transient 12-hex MAC. discover=1 is a
one-shot rediscover pulse. The bridge is the sole WiZ UDP sender.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from light_console.artnet.packet import OP_DMX, build_artdmx, parse_artnet
from light_console.fixture_roles import (
    apply_roles_to_universe,
    classify_par_slot,
    classify_wiz_slot,
    role_for,
    transform_par_channels,
    transform_wiz_channels,
)
from light_console.live_color import (
    HUE_DEFAULT,
    MASTER_DEFAULT,
    SAT_DEFAULT,
    LiveControls,
    clamp_int,
    wrap_hue_deg,
)
from light_console.output.fixtures import PatchedFixture
from light_console.output.wiz_pilot import build_on_params

STATUS_PATH = Path("/tmp/light-console.status")


def parse_identify_mac(value: str) -> str:
    """Fail closed: only a compact 12-hex MAC is a target."""
    compact = "".join(ch for ch in (value or "").strip().lower() if ch not in ":-")
    if len(compact) != 12:
        return ""
    try:
        int(compact, 16)
    except ValueError:
        return ""
    return compact


def parse_live_controls(text: str) -> LiveControls:
    sat = SAT_DEFAULT
    hue = HUE_DEFAULT
    master = MASTER_DEFAULT
    wiz_enabled = True
    identify_mac = ""
    discover = False
    for raw in text.splitlines():
        if "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "sat":
            try:
                sat = clamp_int(int(value), 0, 200)
            except ValueError:
                continue
        elif key == "hue":
            try:
                hue = wrap_hue_deg(int(value))
            except ValueError:
                continue
        elif key == "master":
            try:
                master = clamp_int(int(value), 0, 100)
            except ValueError:
                continue
        elif key == "wiz":
            wiz_enabled = value.lower() in {"on", "true", "1", "yes"}
        elif key == "identify":
            identify_mac = parse_identify_mac(value)
        elif key == "discover":
            discover = value.lower() in {"1", "on"}
    return LiveControls(
        master=master,
        sat=sat,
        hue=hue,
        wiz_enabled=wiz_enabled,
        identify_mac=identify_mac,
        discover=discover,
    )


class LiveControlsCache:
    """mtime-cached status read for the WiZ worker. Not used on the OLED tick."""

    def __init__(self, path: str | os.PathLike[str] = STATUS_PATH) -> None:
        self.path = Path(path)
        self._mtime = -1.0
        self._controls = LiveControls()

    def read(self) -> LiveControls:
        try:
            st = self.path.stat()
        except OSError:
            return self._controls
        mtime = st.st_mtime
        if mtime == self._mtime:
            return self._controls
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return self._controls
        self._mtime = mtime
        self._controls = parse_live_controls(text)
        return self._controls


_CACHE = LiveControlsCache()


def live_controls_cached() -> LiveControls:
    return _CACHE.read()


@dataclass(frozen=True)
class FixtureFrameTrace:
    name: str
    classification: str
    source: tuple[int, ...]
    transformed: tuple[int, ...]
    sat: int
    hue: int
    master: int


def transform_dmx_universe(
    source: list[int] | tuple[int, ...],
    fixtures: tuple[PatchedFixture, ...],
    sat: int = SAT_DEFAULT,
    hue: int = HUE_DEFAULT,
) -> list[int]:
    """SAT/HUE only. MASTER is QLC Grand Master, not applied here."""
    return apply_roles_to_universe(
        source, fixtures, sat=sat, hue=hue, master=MASTER_DEFAULT
    )


def trace_fixture(
    source: list[int] | tuple[int, ...],
    fixture: PatchedFixture,
    sat: int = SAT_DEFAULT,
    hue: int = HUE_DEFAULT,
    master: int = MASTER_DEFAULT,
) -> FixtureFrameTrace:
    base = fixture.address
    n = max(0, int(fixture.channels))
    src = tuple(int(v) for v in source[base : base + n])
    role = role_for(fixture)
    if role.color_model == "rgb+white/amber/uv":
        classification = classify_par_slot(src)
    elif role.color_model == "rgb+white-mode/ctc":
        classification = classify_wiz_slot(src)
    else:
        classification = role.kind
    out_uni = apply_roles_to_universe(source, (fixture,), sat=sat, hue=hue, master=master)
    transformed = tuple(out_uni[base : base + n])
    return FixtureFrameTrace(
        name=fixture.name,
        classification=classification,
        source=src,
        transformed=transformed,
        sat=sat,
        hue=hue,
        master=master,
    )


def transform_artdmx_packet(
    payload: bytes,
    fixtures: tuple[PatchedFixture, ...],
    sat: int = SAT_DEFAULT,
    hue: int = HUE_DEFAULT,
) -> bytes:
    if sat == SAT_DEFAULT and hue == HUE_DEFAULT:
        return payload
    pkt = parse_artnet(payload)
    if pkt is None or pkt.opcode != OP_DMX:
        return payload
    dmx = list(pkt.data)
    if len(dmx) < 512:
        dmx.extend([0] * (512 - len(dmx)))
    out = transform_dmx_universe(dmx, fixtures, sat=sat, hue=hue)
    length = pkt.length if pkt.length else len(pkt.data)
    return build_artdmx(
        bytes(out[:length]),
        sequence=pkt.sequence,
        port_address=pkt.port_address,
        physical=pkt.physical,
    )


class MockArtNetSink:
    """Records rewritten ArtDMX datagrams. Never transmits."""

    def __init__(self) -> None:
        self.sent: list[tuple[tuple[str, int], bytes]] = []

    def send(self, payload: bytes, dest: tuple[str, int]) -> None:
        self.sent.append((dest, payload))


def emit_wired_frame(
    source_payload: bytes,
    fixtures: tuple[PatchedFixture, ...],
    sat: int,
    hue: int,
    sink: MockArtNetSink,
    dest: tuple[str, int],
) -> bytes:
    out = transform_artdmx_packet(source_payload, fixtures, sat=sat, hue=hue)
    sink.send(out, dest)
    return out


def wiz_setpilot_params(
    slot: list[int] | tuple[int, ...],
    sat: int = SAT_DEFAULT,
    hue: int = HUE_DEFAULT,
    *,
    wiz_enabled: bool,
) -> dict | None:
    """Final WiZ command representation. None means do not transmit."""
    if not wiz_enabled:
        return None
    dim, r, g, b, white, ctc = transform_wiz_channels(slot, sat, hue)
    if dim <= 0:
        return {"state": False}
    return build_on_params(dim, r, g, b, white, ctc)


def par_output_frame(
    slot: list[int] | tuple[int, ...],
    sat: int = SAT_DEFAULT,
    hue: int = HUE_DEFAULT,
) -> tuple[int, ...]:
    return tuple(transform_par_channels(slot, sat, hue))
