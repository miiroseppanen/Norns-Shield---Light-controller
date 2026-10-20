"""Canonical product version and SYSTEM -> VERSION page."""

from __future__ import annotations

import subprocess
from pathlib import Path

from light_console import VERSION as PKG_VERSION
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import CONTENT_Y, LABEL_X, ROW
from light_console.display.renderer import Renderer
from light_console.display.widgets import text
from light_console.hardware.events import ButtonEvent, EncoderEvent, E2, K2, K3
from light_console.state import ScreenId
from light_console.ui.pages import SYSTEM_VERSION, system_slots
from light_console.version import VERSION, read_build_revision, semantic_version

from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]
VERSION_PY = ROOT / "light_console/version.py"
SCREENS = ROOT / "light_console/display/screens.py"
PAGES = ROOT / "light_console/ui/pages.py"
CONTROLLER = ROOT / "light_console/ui/controller.py"


def _has_text(fb, x: int, y: int, s: str) -> bool:
    want = Framebuffer()
    text(want, x, y, s)
    found = False
    for yy in range(fb.height):
        for xx in range(fb.width):
            if not want.get(xx, yy):
                continue
            if fb.get(xx, yy) != 1:
                return False
            found = True
    return found


def test_one_canonical_semantic_version():
    assert VERSION == "0.6.0"
    assert semantic_version() == VERSION
    assert PKG_VERSION == VERSION
    source = VERSION_PY.read_text(encoding="utf-8")
    assert source.count('VERSION = "') == 1
    assert "0.5.0" not in source


def test_version_page_renders_without_git(tmp_path: Path, monkeypatch):
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = 0
    c.inject_cooked(EncoderEvent(E2, 2))
    assert c.state.system_index == SYSTEM_VERSION
    assert system_slots(c.state)[2].kind == "version"
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.VERSION
    fb = Renderer().render(c.state)
    assert _has_text(fb, 0, 0, "VERSION")
    assert _has_text(fb, LABEL_X, CONTENT_Y, "LIGHT CTRL")
    assert _has_text(fb, LABEL_X, CONTENT_Y + ROW, "VERSION")
    assert VERSION in c.state.version
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.SYSTEM

    def boom(*args, **kwargs):
        raise AssertionError("git/subprocess")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "check_output", boom)
    Renderer().render(c.state)
    c.tick(now=1.0)
    assert read_build_revision(tmp_path) is None
    (tmp_path / "BUILD_REVISION").write_text("abcdef1\n", encoding="utf-8")
    assert read_build_revision(tmp_path) == "abcdef1"
    c.state.build_revision = "abcdef1"
    c.state.screen = ScreenId.VERSION
    fb = Renderer().render(c.state)
    assert _has_text(fb, LABEL_X, CONTENT_Y + ROW * 2, "REV")


def test_no_git_in_render_or_tick_sources():
    for path in (SCREENS, PAGES, CONTROLLER, VERSION_PY):
        text = path.read_text(encoding="utf-8")
        assert "git " not in text
        assert "rev-parse" not in text
        assert 'subprocess' not in VERSION_PY.read_text(encoding="utf-8")
