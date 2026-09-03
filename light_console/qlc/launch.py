"""QLC+ 5.2.2 argv. Positional workspace + WebAccess is unsupported on this image."""

from __future__ import annotations

from pathlib import Path

QLCPLUS_QML = "/usr/bin/qlcplus-qml"
SHOWS_DIR = Path("/home/light/shows")
MASTER_NAME = "master.qxw"


class LaunchError(ValueError):
    """master.qxw missing, broken, or outside the shows directory."""


def resolve_workspace(master: Path, shows_dir: Path) -> Path:
    if not master.is_symlink() and not master.exists():
        raise LaunchError(f"missing {master}")
    try:
        target = master.resolve(strict=True)
    except OSError as exc:
        raise LaunchError(f"broken {master}") from exc
    shows = shows_dir.resolve()
    if target.parent != shows:
        raise LaunchError(f"{target} is outside {shows}")
    if target.suffix.lower() != ".qxw":
        raise LaunchError(f"not a .qxw: {target}")
    return target


def qml_argv(workspace: Path | None = None) -> list[str]:
    """WebAccess only. Do not pass a workspace path, --open, or -9."""
    del workspace
    return [QLCPLUS_QML, "-w"]
