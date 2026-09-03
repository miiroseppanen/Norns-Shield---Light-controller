from pathlib import Path
import shutil

import pytest

from light_console.qlc.launch import LaunchError, qml_argv, resolve_workspace
from light_console.qxw import QxwError
from light_console.shows import ShowCatalog, ShowLoad

ROOT = Path(__file__).resolve().parents[1]


def _seed(tmp_path: Path) -> ShowCatalog:
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(ROOT / "qlc/projects/show-a.qxw", shows / "show-a.qxw")
    shutil.copy(ROOT / "qlc/projects/show-b.qxw", shows / "show-b.qxw")
    catalog = ShowCatalog(shows)
    catalog.select("show-a.qxw")
    catalog.mark_good()
    return catalog


def test_resolve_workspace_and_argv(tmp_path):
    catalog = _seed(tmp_path)
    target = resolve_workspace(catalog.current_link, catalog.shows_dir)
    assert target.name == "show-a.qxw"
    argv = qml_argv(target)
    assert argv[0] == "/usr/bin/qlcplus-qml"
    assert argv[1] == "-w"
    assert argv[2] == str(target)
    assert "--open" not in argv


def test_resolve_rejects_broken_and_escape(tmp_path):
    shows = tmp_path / "shows"
    shows.mkdir()
    current = shows / "current.qxw"
    current.symlink_to("missing.qxw")
    with pytest.raises(LaunchError, match="broken"):
        resolve_workspace(current, shows)
    outside = tmp_path / "evil.qxw"
    shutil.copy(ROOT / "qlc/projects/show-a.qxw", outside)
    current.unlink()
    current.symlink_to(outside)
    with pytest.raises(LaunchError, match="outside"):
        resolve_workspace(current, shows)


def test_select_updates_current_not_last_good(tmp_path):
    catalog = _seed(tmp_path)
    catalog.select("show-b.qxw")
    assert catalog.current_name() == "show-b.qxw"
    assert catalog.last_good_name() == "show-a.qxw"
    catalog.mark_good()
    assert catalog.last_good_name() == "show-b.qxw"


def test_malformed_rejected_before_replacing_current(tmp_path):
    catalog = _seed(tmp_path)
    (catalog.shows_dir / "bad.qxw").write_text("not a workspace")
    with pytest.raises(QxwError):
        catalog.select("bad.qxw")
    assert catalog.current_name() == "show-a.qxw"


def test_last_known_good_restores_after_failed_load(tmp_path):
    catalog = _seed(tmp_path)
    loader = ShowLoad(catalog, timeout_s=1.0)
    err = loader.confirm("show-b.qxw", now=0.0)
    assert err == ""
    assert catalog.current_name() == "show-b.qxw"
    assert (catalog.shows_dir / ".reload-qlc").is_file()
    loader.tick(now=0.5, qlc_connected=False, project_loaded=False)
    assert catalog.current_name() == "show-b.qxw"
    loader.tick(now=1.1, qlc_connected=False, project_loaded=False)
    assert loader.status == "FAIL"
    assert catalog.current_name() == "show-a.qxw"
    loader.tick(now=2.2, qlc_connected=True, project_loaded=True)
    assert catalog.last_good_name() == "show-a.qxw"
    assert loader.status == "OK"
    assert loader.deadline is None


def test_success_marks_last_good(tmp_path):
    catalog = _seed(tmp_path)
    loader = ShowLoad(catalog, timeout_s=5.0)
    loader.confirm("show-b.qxw", now=0.0)
    loader.tick(now=1.0, qlc_connected=True, project_loaded=True)
    assert loader.status == "OK"
    assert catalog.current_name() == "show-b.qxw"
    assert catalog.last_good_name() == "show-b.qxw"
