"""Canonical Shield XL Light Console product version.

Semantic version is the software identity. Optional revision is deploy
metadata, never live git.
"""

from __future__ import annotations

from pathlib import Path

VERSION = "0.5.0"
REVISION_FILENAME = "BUILD_REVISION"


def semantic_version() -> str:
    return VERSION


def revision_path(root: Path | None = None) -> Path:
    base = root if root is not None else Path(__file__).resolve().parent
    return base / REVISION_FILENAME


def read_build_revision(root: Path | None = None) -> str | None:
    """Lightweight deploy metadata. Missing file is valid. Never runs git."""
    path = revision_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    token = text.strip().split()[0] if text.strip() else ""
    if not token or len(token) > 40:
        return None
    if any(ch for ch in token if not (ch.isalnum() or ch in ".-_")):
        return None
    return token
