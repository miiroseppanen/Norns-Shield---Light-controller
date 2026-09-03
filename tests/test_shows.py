from pathlib import Path
import os
import shutil
import stat
import subprocess

import pytest

from light_console.merge import (
    apply_merge,
    empty_master_xml,
    format_merge_report,
    merge_files,
    plan_merge,
)
from light_console.qlc.client import MockQLCClient
from light_console.qlc.launch import LaunchError, qml_argv, resolve_workspace
from light_console.qxw import QxwError
from light_console.showdef import ShowDefinition, dump_show_yaml, load_show_yaml
from light_console.shows import ShowCatalog

ROOT = Path(__file__).resolve().parents[1]
SHOW_A = ROOT / "qlc/projects/show-a.qxw"
SHOW_B = ROOT / "qlc/projects/show-b.qxw"
MASTER = ROOT / "qlc/projects/master.qxw"
IMPORT = ROOT / "scripts/import-show.sh"


def test_qml_argv_is_web_only():
    argv = qml_argv(MASTER)
    assert argv == ["/usr/bin/qlcplus-qml", "-w"]
    assert "-9" not in argv
    assert "--open" not in argv


def test_resolve_master_workspace(tmp_path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(MASTER, shows / "master.qxw")
    target = resolve_workspace(shows / "master.qxw", shows)
    assert target.name == "master.qxw"
    missing = shows / "master.qxw"
    missing.unlink()
    missing.symlink_to("missing.qxw")
    with pytest.raises(LaunchError, match="broken"):
        resolve_workspace(missing, shows)


def test_logical_show_yaml_roundtrip(tmp_path):
    show = ShowDefinition(
        show_id="show-a",
        name="SHOW A",
        source="show-a.qxw",
        scenes=(),
        chasers=(),
    )
    path = tmp_path / "show-a.yaml"
    path.write_text(dump_show_yaml(show))
    loaded = load_show_yaml(path)
    assert loaded.show_id == "show-a"
    assert loaded.name == "SHOW A"


def test_merge_show_a_then_b_remaps_collisions():
    master = empty_master_xml()
    a = SHOW_A.read_text()
    b = SHOW_B.read_text()
    plan_a = plan_merge(master, a, show_id="show-a", show_name="SHOW A", source_name="show-a.qxw")
    merged = apply_merge(master, a, plan_a)
    assert plan_a.fixture_map[0] == 0
    assert plan_a.function_map[0] == 100
    assert plan_a.function_map[3] == 200
    assert plan_a.show.scenes[0].name == "Warm"
    assert plan_a.show.chasers[0].name == "Slow Pulse"
    assert 'Hold="1200" FadeOut="0">100</Step>' in merged
    plan_b = plan_merge(merged, b, show_id="show-b", show_name="SHOW B", source_name="show-b.qxw")
    merged = apply_merge(merged, b, plan_b)
    assert plan_b.fixture_map[0] == 1
    assert plan_b.function_map[0] == 103
    assert plan_b.function_map[3] == 202
    assert 'Hold="400" FadeOut="0">103</Step>' in merged
    assert 'Hold="600" FadeOut="0">105</Step>' in merged
    assert '<FixtureVal ID="0">0,60</FixtureVal>' in merged
    assert '<FixtureVal ID="1">0,255</FixtureVal>' in merged
    assert 'CurrentWindow="FunctionManager"' in merged
    assert 'UID="1-1.2:0"' in merged
    assert 'Name="Launchpad Mini MIDI 1"' in merged
    assert merged.count('outputIP="127.0.0.1"') == 1
    assert "192.168.88.201" not in merged
    report = format_merge_report(plan_a)
    assert "0 Warm -> 100" in report
    assert "4 Color Sweep -> 201" in report


def test_mapping_is_deterministic():
    master = empty_master_xml()
    a = SHOW_A.read_text()
    kwargs = dict(show_id="show-a", show_name="SHOW A", source_name="show-a.qxw")
    first = plan_merge(master, a, **kwargs)
    second = plan_merge(master, a, **kwargs)
    assert first.fixture_map == second.fixture_map
    assert first.function_map == second.function_map


def test_master_template_is_io_only():
    text = MASTER.read_text()
    assert "<Function" not in text
    assert 'UID="1-1.2:0"' in text
    assert 'Name="Launchpad Mini MIDI 1"' in text
    assert 'outputIP="127.0.0.1"' in text


def test_dry_run_does_not_write_master(tmp_path):
    dest = tmp_path / "master.qxw"
    shutil.copy(MASTER, dest)
    before = dest.read_text()
    plan, patched = merge_files(
        dest, SHOW_A, show_id="show-a", show_name="SHOW A", apply=False
    )
    assert dest.read_text() == before
    assert patched == before
    assert plan.function_map[0] == 100
    assert not (tmp_path / "show-a.yaml").exists()


def test_apply_writes_master_and_yaml(tmp_path):
    dest = tmp_path / "master.qxw"
    shutil.copy(MASTER, dest)
    src = tmp_path / "show-a.qxw"
    shutil.copy(SHOW_A, src)
    original = src.read_text()
    merge_files(dest, src, show_id="show-a", show_name="SHOW A", apply=True)
    assert src.read_text() == original
    assert 'ID="100"' in dest.read_text()
    meta = load_show_yaml(tmp_path / "show-a.yaml")
    assert meta.scenes[0].function_id == 100
    assert meta.scenes[0].name == "Warm"


def test_malformed_and_unsupported_rejected():
    master = empty_master_xml()
    with pytest.raises(QxwError):
        plan_merge(master, "not xml", show_id="x", show_name="X", source_name="x.qxw")
    vc = SHOW_A.read_text().replace(
        "<VirtualConsole>\n </VirtualConsole>",
        "<VirtualConsole>\n  <Frame/>\n </VirtualConsole>",
    )
    with pytest.raises(QxwError, match="Virtual Console"):
        plan_merge(master, vc, show_id="x", show_name="X", source_name="x.qxw")
    collection = SHOW_A.read_text().replace(
        'Type="Scene" Name="Warm"',
        'Type="Collection" Name="Warm"',
    )
    with pytest.raises(QxwError, match="unsupported"):
        plan_merge(master, collection, show_id="x", show_name="X", source_name="x.qxw")


def test_imported_io_discarded(tmp_path):
    dest = tmp_path / "master.qxw"
    shutil.copy(MASTER, dest)
    dirty = SHOW_A.read_text().replace(
        '<Universe Name="Loopback" ID="0">',
        '<Universe Name="Loopback" ID="0">\n'
        '    <Input Plugin="MIDI" Name="APC mini MIDI 1" UID="usb-apc" Line="0"/>',
        1,
    )
    src = tmp_path / "dirty.qxw"
    src.write_text(dirty)
    merge_files(dest, src, show_id="dirty", show_name="DIRTY", apply=True)
    text = dest.read_text()
    assert "APC mini" not in text
    assert 'UID="1-1.2:0"' in text


def test_catalog_activate_does_not_touch_qlc(tmp_path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(MASTER, shows / "master.qxw")
    merge_files(
        shows / "master.qxw", SHOW_A, show_id="show-a", show_name="SHOW A", apply=True
    )
    merge_files(
        shows / "master.qxw", SHOW_B, show_id="show-b", show_name="SHOW B", apply=True
    )
    catalog = ShowCatalog(shows)
    assert tuple(s.name for s in catalog.list_shows()) == ("SHOW A", "SHOW B")
    assert catalog.get("show-a").scenes[0].name == "Warm"
    assert catalog.get("show-b").scenes[0].name == "Full"
    qlc = MockQLCClient()
    qlc.simulate_link(True)
    before = list(qlc.function_sends)
    catalog.activate("show-b")
    assert catalog.current_show().name == "SHOW B"
    assert qlc.function_sends == before
    assert not hasattr(qlc, "load_project")
    assert not (shows / ".reload-qlc").exists()


def test_import_show_script_dry_run():
    assert IMPORT.stat().st_mode & stat.S_IXUSR
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["LIGHT_CONSOLE_MASTER"] = str(MASTER)
    out = subprocess.check_output(
        [str(IMPORT), "--name", "SHOW A", "--dry-run", str(SHOW_A)],
        text=True,
        env=env,
        cwd=ROOT,
    )
    assert "0 Warm -> 100" in out
    assert "dry-run:" in out
    assert MASTER.read_text().count("<Function") == 0
