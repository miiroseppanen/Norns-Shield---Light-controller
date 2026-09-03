"""Resolve current.qxw and build the QLC+ 5.2.2 argv.

Verified on Shield `qlcplus-qml --help` (5.2.2):

  Usage: qlcplus-qml [options] [file]
  -w, --web     Enable remote web access
  file          File to open.

`--open` is a valueless flag and is not used by qmlui/main.cpp to take a
path. The workspace is the positional [file] argument. Do not pass
`--open /path`. Do not POST /loadProject (blocks WebAccess on this image).
"""

from __future__ import annotations

from pathlib import Path

QLCPLUS_QML = "/usr/bin/qlcplus-qml"
SHOWS_DIR = Path("/home/light/shows")
CURRENT_NAME = "current.qxw"


class LaunchError(ValueError):
    """current.qxw missing, broken, or outside the shows directory."""


def resolve_workspace(current: Path, shows_dir: Path) -> Path:
    if not current.is_symlink() and not current.exists():
        raise LaunchError(f"missing {current}")
    try:
        target = current.resolve(strict=True)
    except OSError as exc:
        raise LaunchError(f"broken {current}") from exc
    shows = shows_dir.resolve()
    if target.parent != shows:
        raise LaunchError(f"{target} is outside {shows}")
    if target.suffix.lower() != ".qxw":
        raise LaunchError(f"not a .qxw: {target}")
    return target


def qml_argv(workspace: Path) -> list[str]:
    """WebAccess + positional workspace. No shell joining."""
    return [QLCPLUS_QML, "-w", str(workspace)]
