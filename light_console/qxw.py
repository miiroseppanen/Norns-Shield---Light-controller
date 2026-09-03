"""QLC+ workspace (.qxw) validation and Shield-safe patching.

Never writes the operator's source file. Art-Net destinations are forced to
loopback (127.0.0.1, Line 0). Launchpad-intended MIDI Input/Feedback is rewritten
from the Shield machine profile (name + UID). A workspace that still contains a
forbidden address after patching is rejected so it cannot replace a working show.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from light_console.artnet.destinations import FORBIDDEN_HOSTS
from light_console.machine import (
    LaunchpadBinding,
    MachineProfileError,
    ShieldMachineProfile,
    load_machine_profile,
)

# Shield STA on LIGHT-CONTROL. Art-Net Line 1 bound this address in 0.6B.
SHIELD_LAN_HOST = "192.168.88.246"

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
_TAG_ATTR = re.compile(r'\b([A-Za-z]+)="([^"]*)"')
_UNSET = frozenset({"", "none"})
_CAPTION = re.compile(r'(Caption=")([^"]*)(")', re.IGNORECASE)


@dataclass(frozen=True)
class QxwFunction:
    function_id: int
    name: str
    type_name: str


@dataclass(frozen=True)
class MidiBindingChange:
    kind: str
    old_name: str
    old_uid: str
    old_line: str
    new_name: str
    new_uid: str
    new_line: str

    def report_lines(self) -> tuple[str, str, str]:
        label = "MIDI INPUT" if self.kind.lower() == "input" else "MIDI FEEDBACK"
        return (
            f"{label}:",
            f"  old: {self.old_name} / {self.old_uid} / Line {self.old_line}",
            f"  new: {self.new_name} / {self.new_uid}",
        )


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


def _sanitize_caption_hosts(text: str) -> str:
    """Rewrite operator Label captions that mention machine IPs. IO is patched separately."""

    def repl(match: re.Match[str]) -> str:
        caption = match.group(2)
        for host in sorted(FORBIDDEN_HOSTS | {SHIELD_LAN_HOST}, key=len, reverse=True):
            caption = caption.replace(host, "HOST")
        caption = re.sub(r"10\.42\.\d+\.\d+", "HOST", caption)
        return f"{match.group(1)}{caption}{match.group(3)}"

    return _CAPTION.sub(repl, text)


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


def _tag_attrs(attrs: str) -> dict[str, str]:
    return {k.lower(): v for k, v in _TAG_ATTR.findall(attrs)}


def _is_unset(value: str) -> bool:
    return value.strip().lower() in _UNSET


def _is_launchpad_input(attrs: dict[str, str], lp: LaunchpadBinding) -> bool:
    if attrs.get("profile") == lp.profile:
        return True
    if attrs.get("name") == lp.name:
        return True
    return False


def _is_launchpad_feedback(
    attrs: dict[str, str], lp: LaunchpadBinding, has_launchpad_input: bool
) -> bool:
    if attrs.get("profile") == lp.profile:
        return True
    if attrs.get("name") == lp.name:
        return True
    if has_launchpad_input and _is_unset(attrs.get("name", "")):
        return True
    return False


def format_midi_report(changes: tuple[MidiBindingChange, ...]) -> str:
    if not changes:
        return "MIDI: no Launchpad bindings rewritten"
    lines: list[str] = []
    for change in changes:
        lines.extend(change.report_lines())
    return "\n".join(lines)


def prepare_for_shield(
    text: str, *, profile: ShieldMachineProfile | None = None
) -> str:
    patched, _changes = prepare_for_shield_report(text, profile=profile)
    return patched


def prepare_for_shield_report(
    text: str, *, profile: ShieldMachineProfile | None = None
) -> tuple[str, tuple[MidiBindingChange, ...]]:
    """Return a Shield-safe workspace string and MIDI rewrite notes. Does not load QLC+."""
    if not text or not text.strip():
        raise QxwError("empty workspace")
    _parse_workspace(text)
    try:
        machine = profile if profile is not None else load_machine_profile()
    except MachineProfileError as exc:
        raise QxwError(str(exc)) from exc
    lp = machine.launchpad
    patched = _sanitize_caption_hosts(text)
    patched = _ARTNET_OUTPUT_BLOCK.sub(lambda m: _patch_artnet_block(m.group(0)), patched)
    has_lp_input = False
    for match in _MIDI_IO_TAG.finditer(patched):
        if match.group(1).lower() == "input" and _is_launchpad_input(
            _tag_attrs(match.group(2)), lp
        ):
            has_lp_input = True
            break
    changes: list[MidiBindingChange] = []

    def replace(match: re.Match[str]) -> str:
        kind, attrs, slash = match.group(1), match.group(2), match.group(3)
        if attrs.rstrip().endswith("/"):
            attrs = attrs.rstrip()[:-1]
            slash = "/"
        parsed = _tag_attrs(attrs)
        if kind.lower() == "input":
            if not _is_launchpad_input(parsed, lp):
                return match.group(0)
        elif not _is_launchpad_feedback(parsed, lp, has_lp_input):
            return match.group(0)
        old_name = parsed.get("name") or "None"
        old_uid = parsed.get("uid") or "None"
        old_line = parsed.get("line") or "0"
        attrs = _set_attr(attrs, "Name", lp.name)
        attrs = _set_attr(attrs, "UID", lp.uid)
        attrs = _set_attr(attrs, "Line", lp.line_fallback)
        if kind.lower() == "input":
            attrs = _set_attr(attrs, "Profile", parsed.get("profile") or lp.profile)
        changes.append(
            MidiBindingChange(
                kind=kind.upper(),
                old_name=old_name,
                old_uid=old_uid,
                old_line=old_line,
                new_name=lp.name,
                new_uid=lp.uid,
                new_line=lp.line_fallback,
            )
        )
        return f"<{kind}{attrs}{slash}>"

    patched = _MIDI_IO_TAG.sub(replace, patched)
    _parse_workspace(patched)
    leftover = _forbidden_leftovers(patched)
    if leftover:
        raise QxwError(
            "forbidden address remains after Shield patch: " + ", ".join(leftover)
        )
    return patched, tuple(changes)


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


def prepare_file(
    src: Path,
    dest: Path,
    *,
    profile: ShieldMachineProfile | None = None,
) -> str:
    """Read src, patch, write dest. Never writes src."""
    src = src.resolve()
    dest = dest.resolve()
    if src == dest:
        raise QxwError("refusing to overwrite the source file")
    text = src.read_text(encoding="utf-8")
    patched, _changes = prepare_for_shield_report(text, profile=profile)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(patched, encoding="utf-8")
    return patched


def prepare_file_report(
    src: Path,
    dest: Path,
    *,
    profile: ShieldMachineProfile | None = None,
) -> tuple[str, tuple[MidiBindingChange, ...]]:
    src = src.resolve()
    dest = dest.resolve()
    if src == dest:
        raise QxwError("refusing to overwrite the source file")
    text = src.read_text(encoding="utf-8")
    patched, changes = prepare_for_shield_report(text, profile=profile)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(patched, encoding="utf-8")
    return patched, changes
