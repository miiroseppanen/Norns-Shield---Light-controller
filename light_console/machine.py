"""Shield machine bindings. Not show content. No secrets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_MACHINE_PROFILE = (
    Path(__file__).resolve().parent.parent / "config" / "machine-profile.yaml"
)


class MachineProfileError(ValueError):
    """machine-profile.yaml is missing or incomplete."""


@dataclass(frozen=True)
class LaunchpadBinding:
    name: str
    uid: str
    profile: str
    usb_id: str = "1235:0036"
    line_fallback: str = "1"


@dataclass(frozen=True)
class ShieldMachineProfile:
    launchpad: LaunchpadBinding


def default_machine_profile_path() -> Path:
    return DEFAULT_MACHINE_PROFILE


def load_machine_profile(path: Path | None = None) -> ShieldMachineProfile:
    path = default_machine_profile_path() if path is None else path
    if not path.is_file():
        raise MachineProfileError(f"missing Shield machine profile: {path}")
    launchpad = _parse_launchpad_block(path.read_text(encoding="utf-8"))
    if not launchpad.get("name") or not launchpad.get("uid"):
        raise MachineProfileError("machine profile launchpad.name and launchpad.uid are required")
    profile = launchpad.get("profile") or "Novation Launchpad Mini"
    return ShieldMachineProfile(
        launchpad=LaunchpadBinding(
            name=launchpad["name"],
            uid=launchpad["uid"],
            profile=profile,
            usb_id=launchpad.get("usb_id") or "1235:0036",
            line_fallback=launchpad.get("line_fallback") or "1",
        )
    )


def _parse_launchpad_block(text: str) -> dict[str, str]:
    """Minimal YAML subset: launchpad: then indented key: value pairs."""
    in_block = False
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("launchpad:"):
            in_block = True
            continue
        if in_block and line and not line[0].isspace():
            break
        if not in_block:
            continue
        if ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out
