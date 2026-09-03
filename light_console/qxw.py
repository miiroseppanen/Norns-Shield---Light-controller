"""QLC+ workspace (.qxw) validation and Shield-safe patching.

Never writes the operator's source file. Art-Net destinations are forced to
loopback (127.0.0.1, Line 0). A workspace that still contains a forbidden
address after patching is rejected so it cannot replace a working show.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from light_console.artnet.destinations import FORBIDDEN_HOSTS

# Shield STA on LIGHT-CONTROL. Art-Net Line 1 bound this address in 0.6B.
SHIELD_LAN_HOST = "192.168.88.246"

_ARTNET_OUTPUT_BLOCK = re.compile(
    r"<Output\b[^>]*\bPlugin=\"ArtNet\"[^>]*>.*?</Output>",
    re.IGNORECASE | re.DOTALL,
)
_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)


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
    if re.search(r"\bLine=", opening, re.IGNORECASE):
        opening = re.sub(r'\bLine="[^"]*"', 'Line="0"', opening, count=1)
    else:
        opening = opening[:-1] + ' Line="0">'
    rest = re.sub(r'\boutputIP="[^"]*"', 'outputIP="127.0.0.1"', rest)
    return opening + rest


def prepare_for_shield(text: str) -> str:
    """Return a Shield-safe workspace string. Does not load QLC+."""
    if not text or not text.strip():
        raise QxwError("empty workspace")
    _parse_workspace(text)
    patched = _ARTNET_OUTPUT_BLOCK.sub(lambda m: _patch_artnet_block(m.group(0)), text)
    _parse_workspace(patched)
    leftover = _forbidden_leftovers(patched)
    if leftover:
        raise QxwError(
            "forbidden address remains after Shield patch: " + ", ".join(leftover)
        )
    return patched


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
