from pathlib import Path
import shutil

from light_console.output.mutate import patch_managed_artnet, universe_block
from light_console.output.routing import parse_output_routes
from light_console.output.targets import AIR2DMX_FALLBACK_IP, TargetId, apply_plan_for
from light_console.output.workspace_switch import WorkspaceSwitchError, switch_workspace
from light_console.qlc.service import MockQlcService
from light_console.ui.vocab import RUNNING
from light_console.workspaces import WorkspaceCatalog

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHIELD = ROOT / "qlc/projects/siirtyma-shield.qxw"
SHOW_A = ROOT / "qlc/projects/show-a.qxw"
SWITCH_PY = ROOT / "light_console/output/workspace_switch.py"


def _u2(text: str) -> str:
    plan = apply_plan_for(TargetId.AIR2DMX, AIR2DMX_FALLBACK_IP, lan_uid="192.168.88.246")
    return patch_managed_artnet(text, plan)


def test_switch_copies_named_file_preserves_u2_and_bounces_qlc(tmp_path: Path):
    shows = tmp_path / "shows"
    shows.mkdir()
    current = _u2(SHIELD.read_text(encoding="utf-8"))
    (shows / "master.qxw").write_text(current, encoding="utf-8")
    named = shows / "halloween.qxw"
    shutil.copy(SHIELD, named)
    before = named.read_bytes()
    cat = WorkspaceCatalog(shows)
    qlc = MockQlcService(desired_on=True, observed=RUNNING)
    opened = switch_workspace(cat, "halloween.qxw", qlc_service=qlc)
    assert opened == "halloween.qxw"
    assert named.read_bytes() == before
    installed = (shows / "master.qxw").read_text(encoding="utf-8")
    assert universe_block(installed, 1) == universe_block(current, 1)
    routes = parse_output_routes(installed)
    assert routes[0].output_ip == "127.0.0.1"
    assert routes[1].output_ip == AIR2DMX_FALLBACK_IP
    assert "192.168.88.248" not in installed
    assert cat.open_filename() == "halloween.qxw"
    assert (shows / "last-good.qxw").read_text(encoding="utf-8") == current
    assert qlc.commands == ["stop", "start"]
    assert qlc.desired_on is True
    assert qlc.observed == RUNNING


def test_switch_already_open_does_not_bounce(tmp_path: Path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(SHOW_A, shows / "warm.qxw")
    shutil.copy(SHOW_A, shows / "master.qxw")
    cat = WorkspaceCatalog(shows)
    cat.remember_open("warm.qxw")
    qlc = MockQlcService(desired_on=True, observed=RUNNING)
    switch_workspace(cat, "warm.qxw", qlc_service=qlc)
    assert qlc.commands == []


def test_switch_refuses_forbidden_leftover_without_stopping_qlc(tmp_path: Path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(SHOW_A, shows / "master.qxw")
    dirty = SHOW_A.read_text(encoding="utf-8").replace(
        "TEST-CH1", "note 192.168.88.248"
    )
    (shows / "dirty.qxw").write_text(dirty, encoding="utf-8")
    cat = WorkspaceCatalog(shows)
    qlc = MockQlcService(desired_on=True, observed=RUNNING)
    with pytest.raises(WorkspaceSwitchError, match="forbidden address"):
        switch_workspace(cat, "dirty.qxw", qlc_service=qlc)
    assert qlc.commands == []
    assert "192.168.88.248" not in (shows / "master.qxw").read_text(encoding="utf-8")
    assert (shows / "dirty.qxw").read_text(encoding="utf-8") == dirty


def test_switch_never_posts_loadproject():
    text = SWITCH_PY.read_text(encoding="utf-8")
    assert "loadProject" not in text
    assert "192.168.88.248" in text
