from pathlib import Path
import shutil

from light_console.qxw import QxwError
from light_console.workspaces import WorkspaceCatalog, oled_workspace_label

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOW_A = ROOT / "qlc/projects/show-a.qxw"
SHOW_B = ROOT / "qlc/projects/show-b.qxw"


def test_oled_workspace_label_is_uppercase_words():
    assert oled_workspace_label("Pirkkala.qxw") == "PIRKKALA"
    assert oled_workspace_label("master.qxw") == "MASTER"


def test_catalog_lists_named_files_not_reserved(tmp_path: Path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(SHOW_A, shows / "master.qxw")
    shutil.copy(SHOW_A, shows / "warm.qxw")
    shutil.copy(SHOW_B, shows / "full.qxw")
    (shows / "last-good.qxw").write_text("x", encoding="utf-8")
    (shows / "current.qxw").write_text("x", encoding="utf-8")
    (shows / "master.qxw.bak").write_text("x", encoding="utf-8")
    cat = WorkspaceCatalog(shows)
    names = tuple(entry.filename for entry in cat.list_entries())
    assert names == ("full.qxw", "warm.qxw")
    assert cat.open_filename() == "master.qxw"
    assert cat.is_open("master.qxw")
    assert not cat.is_open("warm.qxw")


def test_catalog_falls_back_to_master_when_no_named_files(tmp_path: Path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(SHOW_A, shows / "master.qxw")
    cat = WorkspaceCatalog(shows)
    entries = cat.list_entries()
    assert len(entries) == 1
    assert entries[0].filename == "master.qxw"
    assert entries[0].label == "MASTER"


def test_catalog_empty_dir(tmp_path: Path):
    shows = tmp_path / "shows"
    shows.mkdir()
    cat = WorkspaceCatalog(shows)
    assert cat.list_entries() == ()
    assert cat.open_filename() is None
    with pytest.raises(QxwError):
        cat.get("missing.qxw")


def test_remember_open_round_trips(tmp_path: Path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(SHOW_A, shows / "warm.qxw")
    cat = WorkspaceCatalog(shows)
    cat.remember_open("warm.qxw")
    assert cat.open_filename() == "warm.qxw"
    assert cat.is_open("warm.qxw")
    assert (shows / "open-show").read_text(encoding="utf-8").strip() == "warm.qxw"
