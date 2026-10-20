"""QLC fixture patch metadata. Observe only; never invent channel meaning."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from light_console.qxw import QxwError
from light_console.ui.vocab import ACTIVE, IDLE, SEEN

_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)
_TRAILING_INDEX = re.compile(r"\s*\[\d+\]\s*$")


@dataclass(frozen=True)
class PatchedFixture:
    fixture_id: int
    name: str
    universe_id: int
    address: int
    channels: int
    manufacturer: str = ""
    model: str = ""
    mode: str = ""

    @property
    def start_1(self) -> int:
        return self.address + 1

    @property
    def qlc_universe(self) -> int:
        return self.universe_id + 1

    def display_name(self) -> str:
        raw = " ".join(self.name.split())
        return _TRAILING_INDEX.sub("", raw)

    def short_name(self, width: int = 14) -> str:
        raw = self.display_name()
        if len(raw) <= width:
            return raw
        return raw[: width - 1] + "."


def parse_fixtures(text: str) -> tuple[PatchedFixture, ...]:
    stripped = _DOCTYPE.sub("", text, count=1)
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError as exc:
        raise QxwError(f"invalid XML: {exc}") from exc
    found: list[PatchedFixture] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "Fixture":
            continue
        fields = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in node}
        try:
            fixture_id = int(fields.get("ID", "0"))
            universe_id = int(fields.get("Universe", "0"))
            address = int(fields.get("Address", "0"))
            channels = int(fields.get("Channels", "0"))
        except ValueError:
            continue
        name = fields.get("Name") or fields.get("Model") or f"FIX {fixture_id}"
        found.append(
            PatchedFixture(
                fixture_id=fixture_id,
                name=name,
                universe_id=universe_id,
                address=max(0, address),
                channels=max(0, channels),
                manufacturer=fields.get("Manufacturer", ""),
                model=fields.get("Model", ""),
                mode=fields.get("Mode", ""),
            )
        )
    found.sort(key=lambda fx: (fx.universe_id, fx.address, fx.fixture_id))
    return tuple(found)


def parse_fixtures_file(path: Path) -> tuple[PatchedFixture, ...]:
    return parse_fixtures(path.read_text(encoding="utf-8"))


def fixture_activity(
    fixture: PatchedFixture,
    dmx: dict[int, tuple[int, ...]],
    seen_ids: set[int],
) -> str:
    buf = dmx.get(fixture.universe_id, ())
    start = fixture.address
    end = start + fixture.channels
    live = False
    if buf and start < len(buf):
        live = any(buf[start:end])
    if live:
        seen_ids.add(fixture.fixture_id)
        return ACTIVE
    if fixture.fixture_id in seen_ids:
        return SEEN
    return IDLE


def update_seen(fixtures: tuple[PatchedFixture, ...], dmx: dict[int, tuple[int, ...]], seen_ids: set[int]) -> None:
    for fixture in fixtures:
        fixture_activity(fixture, dmx, seen_ids)
