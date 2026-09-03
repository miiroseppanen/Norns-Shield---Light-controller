"""Logical show definitions. Independent of QLC workspace loading."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from light_console.qxw import QxwError

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class FunctionRef:
    function_id: int
    name: str


@dataclass(frozen=True)
class ShowDefinition:
    show_id: str
    name: str
    source: str
    scenes: tuple[FunctionRef, ...]
    chasers: tuple[FunctionRef, ...]

    @property
    def label(self) -> str:
        return self.name or self.show_id


def dump_show_yaml(show: ShowDefinition) -> str:
    lines = [
        f"id: {show.show_id}",
        f"name: {show.name}",
        f"source: {show.source}",
        "scenes:",
    ]
    for ref in show.scenes:
        lines.append(f"  - id: {ref.function_id}")
        lines.append(f"    name: {ref.name}")
    lines.append("chasers:")
    for ref in show.chasers:
        lines.append(f"  - id: {ref.function_id}")
        lines.append(f"    name: {ref.name}")
    return "\n".join(lines) + "\n"


def load_show_yaml(path: Path) -> ShowDefinition:
    if not path.is_file():
        raise QxwError(f"missing show metadata: {path}")
    show_id = path.stem
    if not _SAFE_ID.match(show_id) or show_id.startswith("."):
        raise QxwError(f"unsafe show id: {show_id}")
    data = _parse_show_yaml(path.read_text(encoding="utf-8"))
    name = data.get("name") or show_id.replace("-", " ").upper()
    source = data.get("source") or ""
    if data.get("id"):
        show_id = data["id"]
        if not _SAFE_ID.match(show_id):
            raise QxwError(f"unsafe show id: {show_id}")
    return ShowDefinition(
        show_id=show_id,
        name=name,
        source=source,
        scenes=tuple(data["scenes"]),
        chasers=tuple(data["chasers"]),
    )


def _parse_show_yaml(text: str) -> dict:
    out: dict = {"scenes": [], "chasers": []}
    section: str | None = None
    current: dict[str, str] | None = None

    def finish() -> None:
        nonlocal current
        if current is None or section is None:
            return
        try:
            fid = int(current["id"])
        except (KeyError, ValueError) as exc:
            raise QxwError("show metadata function missing id") from exc
        name = (current.get("name") or "").strip()
        if not name:
            raise QxwError(f"show metadata function {fid} missing name")
        out[section].append(FunctionRef(fid, name))
        current = None

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped in ("scenes:", "chasers:"):
            finish()
            section = stripped[:-1]
            continue
        if section and stripped.startswith("- "):
            finish()
            current = {}
            rest = stripped[2:]
            if ":" in rest:
                key, value = rest.split(":", 1)
                current[key.strip()] = value.strip().strip("'\"")
            continue
        if ":" not in line:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if current is not None and line[:1].isspace():
            current[key] = value
            continue
        if not line[:1].isspace():
            finish()
            section = None
            if key in ("id", "name", "source"):
                out[key] = value
    finish()
    return out
