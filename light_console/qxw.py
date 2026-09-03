"""QLC+ workspace (.qxw) validation and Shield-safe patching.

Never writes the operator's source file. Art-Net destinations are forced to
loopback (127.0.0.1, Line 0). MIDI Input/Feedback Name is set to the Shield
Launchpad ALSA port name (not a client number). A workspace that still
contains a forbidden address after patching is rejected so it cannot replace
a working show.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from light_console.artnet.destinations import FORBIDDEN_HOSTS

# Shield STA on LIGHT-CONTROL. Art-Net Line 1 bound this address in 0.6B.
SHIELD_LAN_HOST = "192.168.88.246"
# ALSA sequencer port name on this Shield (amidi -l / aconnect). Not a client number.
SHIELD_MIDI_PORT_NAME = "Launchpad Mini MIDI 1"

_ARTNET_OUTPUT_BLOCK = re.compile(
    r"<Output\b[^>]*\bPlugin=\"ArtNet\"[^>]*>.*?</Output>",
    re.IGNORECASE | re.DOTALL,
)
_MIDI_IO_TAG = re.compile(
    r"<(Input|Feedback)\b([^>]*\bPlugin=\"MIDI\"[^>]*)(/?)>",
    re.IGNORECASE,
)
_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)
_FUNCTION_BLOCK = re.compile(
    r"<Function\b([^>]*)>.*?</Function>",
    re.IGNORECASE | re.DOTALL,
)
_ATTR = re.compile(r'\b(ID|Type|Name)="([^"]*)"', re.IGNORECASE)


@dataclass(frozen=True)
class QxwFunction:
    function_id: int
    name: str
    type_name: str


class QxwError(ValueError):
    """Workspace is missing, malformed, or unsafe for the Shield."""


def safe_show_name(path: Path) -> str:
    name = path.name
    if not name.lower().endswith(".qxw"):
        raise QxwError(f"not a .qxw file: {path}")
    stem = name[:-4]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "show"
    return f"{safe}.qxw"


def _parse_workspace(text: str) -> ET.Element:
    stripped = _DOCTYPE.sub("", text, count=1)
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError as exc:
        raise QxwError(f"invalid XML: {exc}") from exc
    local = root.tag.rsplit("}", 1)[-1]
    if local != "Workspace":
        raise QxwError(f"root is <{local}>, not Workspace")
    return root


def _forbidden_leftovers(text: str) -> list[str]:
    found: list[str] = []
    for host in sorted(FORBIDDEN_HOSTS | {SHIELD_LAN_HOST}):
        if host in text:
            found.append(host)
    if "10.42." in text:
        found.append("10.42.*")
    return found


def _patch_artnet_block(block: str) -> str:
    opening_end = block.find(">")
    if opening_end == -1:
        return block
    opening, rest = block[: opening_end + 1], block[opening_end + 1 :]
    if re.search(r"\bUID=", opening, re.IGNORECASE):
        opening = re.sub(r'\bUID="[^"]*"', 'UID="127.0.0.1"', opening, count=1)
    else:
        opening = opening[:-1] + ' UID="127.0.0.1">'
    if re.search(r"\bName=", opening, re.IGNORECASE):
        opening = re.sub(r'\bName="[^"]*"', 'Name="127.0.0.1"', opening, count=1)
    if re.search(r"\bLine=", opening, re.IGNORECASE):
        opening = re.sub(r'\bLine="[^"]*"', 'Line="0"', opening, count=1)
    else:
        opening = opening[:-1] + ' Line="0">'
    rest = re.sub(r'\boutputIP="[^"]*"', 'outputIP="127.0.0.1"', rest)
    return opening + rest


def _set_attr(attrs: str, name: str, value: str) -> str:
    pattern = rf'\b{name}="[^"]*"'
    if re.search(pattern, attrs, re.IGNORECASE):
        return re.sub(pattern, f'{name}="{value}"', attrs, count=1, flags=re.IGNORECASE)
    return attrs.rstrip() + f' {name}="{value}"'


def _patch_midi_tag(match: re.Match[str]) -> str:
    kind, attrs, slash = match.group(1), match.group(2), match.group(3)
    attrs = _set_attr(attrs, "Name", SHIELD_MIDI_PORT_NAME)
    attrs = _set_attr(attrs, "UID", "")
    return f"<{kind}{attrs}{slash}>"


def prepare_for_shield(text: str) -> str:
    """Return a Shield-safe workspace string. Does not load QLC+."""
    if not text or not text.strip():
        raise QxwError("empty workspace")
    _parse_workspace(text)
    patched = _ARTNET_OUTPUT_BLOCK.sub(lambda m: _patch_artnet_block(m.group(0)), text)
    patched = _MIDI_IO_TAG.sub(_patch_midi_tag, patched)
    _parse_workspace(patched)
    leftover = _forbidden_leftovers(patched)
    if leftover:
        raise QxwError(
            "forbidden address remains after Shield patch: " + ", ".join(leftover)
        )
    return patched


def parse_functions(text: str) -> tuple[QxwFunction, ...]:
    """Read Scene/Chaser (and other) Function rows from workspace XML."""
    _parse_workspace(text)
    found: list[QxwFunction] = []
    for block in _FUNCTION_BLOCK.finditer(text):
        attrs = {k.lower(): v for k, v in _ATTR.findall(block.group(1))}
        try:
            fid = int(attrs["id"])
        except (KeyError, ValueError):
            continue
        name = (attrs.get("name") or "").strip()
        type_name = (attrs.get("type") or "Scene").strip() or "Scene"
        if not name:
            continue
        found.append(QxwFunction(fid, name, type_name))
    return tuple(found)


def parse_functions_file(path: Path) -> tuple[QxwFunction, ...]:
    return parse_functions(path.read_text(encoding="utf-8"))


def prepare_file(src: Path, dest: Path) -> str:
    """Read src, patch, write dest. Never writes src."""
    src = src.resolve()
    dest = dest.resolve()
    if src == dest:
        raise QxwError("refusing to overwrite the source file")
    text = src.read_text(encoding="utf-8")
    patched = prepare_for_shield(text)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(patched, encoding="utf-8")
    return patched
