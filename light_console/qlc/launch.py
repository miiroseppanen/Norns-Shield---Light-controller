"""QLC+ 5.2.2 argv. Match production: -w -o <workspace> (path is positional after -o)."""

from __future__ import annotations

from pathlib import Path

QLCPLUS_QML = "/usr/bin/qlcplus-qml"
SHOWS_DIR = Path("/home/light/shows")
MASTER_NAME = "master.qxw"
RUNTIME_MASTER = SHOWS_DIR / MASTER_NAME


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
    """WebAccess plus production-style workspace path.

    QLC+ 5.2.2 `-o/--open` is a boolean flag. The file is the positional
    argument. Production runs: qlcplus-qml -w -o /home/valot/siirtyma-startup.qxw
    Do not use -9 or POST /loadProject.
    """
    argv = [QLCPLUS_QML, "-w"]
    if workspace is not None:
        argv.extend(["-o", str(workspace)])
    return argv
