"""Operator preferences. Overlay on AppConfig; default WiZ OFF."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from light_console.output.netmode import parse_network_mode

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

DEFAULT_PREFS_NAME = "prefs.yaml"


@dataclass
class OperatorPrefs:
    wiz_enabled: bool = False
    qlc_desired: bool = True
    network_mode: str = "network"


def default_prefs_path() -> Path:
    return Path.home() / ".config" / "light-console" / DEFAULT_PREFS_NAME


def load_prefs(path: Path | None) -> OperatorPrefs:
    if path is None or not path.is_file() or yaml is None:
        return OperatorPrefs()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return OperatorPrefs()
    if not isinstance(data, dict):
        return OperatorPrefs()
    return OperatorPrefs(
        wiz_enabled=bool(data.get("wiz_enabled", False)),
        qlc_desired=bool(data.get("qlc_desired", True)),
        network_mode=parse_network_mode(data.get("network_mode")),
    )


def save_prefs(path: Path | None, prefs: OperatorPrefs) -> None:
    if path is None or yaml is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        {
            "network_mode": parse_network_mode(prefs.network_mode),
            "qlc_desired": bool(prefs.qlc_desired),
            "wiz_enabled": bool(prefs.wiz_enabled),
        },
        sort_keys=True,
    )
    path.write_text(body, encoding="utf-8")
