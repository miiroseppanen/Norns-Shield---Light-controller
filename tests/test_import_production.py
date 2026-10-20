from pathlib import Path
import os
import shutil
import stat
import subprocess
import time

from light_console.output.mutate import patch_managed_artnet, universe_block
from light_console.output.routing import parse_output_routes
from light_console.output.targets import AIR2DMX_FALLBACK_IP, TargetId, apply_plan_for

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/import-production-workspace.sh"
SHIELD = ROOT / "qlc/projects/siirtyma-shield.qxw"


def _env(tmp_path: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["LIGHT_CONSOLE_HOST"] = "light@shieldxl-light.local"
    if tmp_path is not None:
        env["LIGHT_CONSOLE_MASTER"] = str(tmp_path / "siirtyma-shield.qxw")
    return env


def _run(args: list[str], env: dict[str, str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd or ROOT,
    )


def test_import_production_cli_and_help():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & stat.S_IXUSR
    help_text = subprocess.check_output([str(SCRIPT), "--help"], text=True)
    assert "--dry-run FILE.qxw" in help_text
    assert "--apply FILE.qxw" in help_text
    assert "--install FILE.qxw" in help_text
    assert "--install --dry-run FILE.qxw" in help_text
    assert "192.168.88.248" in help_text
    text = SCRIPT.read_text()
    assert "prepare_for_shield" in text
    assert "preserve_managed_universe" in text
    assert "/home/light/shows/master.qxw" in text
    assert "192.168.88.248" in text


def test_dry_run_does_not_write_source_or_dest(tmp_path):
    src = tmp_path / "startup.qxw"
    shutil.copy(SHIELD, src)
    before = src.read_text()
    dest = tmp_path / "siirtyma-shield.qxw"
    env = _env(tmp_path)
    out = subprocess.check_output(
        [str(SCRIPT), "--dry-run", str(src)],
        text=True,
        env=env,
        cwd=ROOT,
    )
    time.sleep(0.05)
    assert src.read_text() == before
    assert not dest.exists()
    assert "dry-run:" in out
    assert "source (unchanged):" in out


def test_apply_writes_local_dest_not_source(tmp_path):
    src = tmp_path / "startup.qxw"
    shutil.copy(SHIELD, src)
    before = src.read_bytes()
    dest = tmp_path / "siirtyma-shield.qxw"
    env = _env(tmp_path)
    out = subprocess.check_output(
        [str(SCRIPT), "--apply", str(src)],
        text=True,
        env=env,
        cwd=ROOT,
    )
    assert src.read_bytes() == before
    assert dest.is_file()
    assert "applied:" in out
    assert dest.read_text(encoding="utf-8").count('outputIP="127.0.0.1"') >= 2


def test_install_dry_run_preserves_u2_and_writes_nothing(tmp_path):
    src = tmp_path / "startup.qxw"
    shutil.copy(SHIELD, src)
    before = src.read_bytes()
    current = tmp_path / "current.qxw"
    plan = apply_plan_for(TargetId.AIR2DMX, AIR2DMX_FALLBACK_IP, lan_uid="192.168.88.246")
    current.write_text(
        patch_managed_artnet(SHIELD.read_text(encoding="utf-8"), plan),
        encoding="utf-8",
    )
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(current, shows / "master.qxw")
    env = _env(tmp_path)
    env["LIGHT_CONSOLE_CURRENT"] = str(current)
    env["LIGHT_CONSOLE_INSTALL_ROOT"] = str(shows)
    out = subprocess.check_output(
        [str(SCRIPT), "--install", "--dry-run", str(src)],
        text=True,
        env=env,
        cwd=ROOT,
    )
    assert src.read_bytes() == before
    assert "dry-run: not installed to the Shield" in out
    assert "u2 preserved: 192.168.88.242" in out
    assert "wiz loopback: 127.0.0.1" in out
    assert shows.joinpath("master.qxw").read_bytes() == current.read_bytes()
    assert not shows.joinpath("master.qxw.bak").exists()


def test_install_applies_locally_with_backup_and_u2(tmp_path):
    src = tmp_path / "startup.qxw"
    shutil.copy(SHIELD, src)
    before = src.read_bytes()
    current_xml = patch_managed_artnet(
        SHIELD.read_text(encoding="utf-8"),
        apply_plan_for(TargetId.AIR2DMX, AIR2DMX_FALLBACK_IP, lan_uid="192.168.88.246"),
    )
    shows = tmp_path / "shows"
    shows.mkdir()
    (shows / "master.qxw").write_text(current_xml, encoding="utf-8")
    env = _env(tmp_path)
    env["LIGHT_CONSOLE_INSTALL_ROOT"] = str(shows)
    out = subprocess.check_output(
        [str(SCRIPT), "--install", str(src)],
        text=True,
        env=env,
        cwd=ROOT,
    )
    assert src.read_bytes() == before
    assert "applied:" in out
    installed = (shows / "master.qxw").read_text(encoding="utf-8")
    assert universe_block(installed, 1) == universe_block(current_xml, 1)
    routes = parse_output_routes(installed)
    assert routes[0].output_ip == "127.0.0.1"
    assert routes[1].output_ip == AIR2DMX_FALLBACK_IP
    assert (shows / "master.qxw.bak").is_file()
    assert "192.168.88.248" not in installed


def test_install_refuses_production_host(tmp_path):
    src = tmp_path / "startup.qxw"
    shutil.copy(SHIELD, src)
    env = _env(tmp_path)
    env["LIGHT_CONSOLE_HOST"] = "light@192.168.88.248"
    proc = _run(["--install", "--dry-run", str(src)], env)
    assert proc.returncode != 0
    assert "refusing host" in proc.stderr
    assert src.read_text(encoding="utf-8") == SHIELD.read_text(encoding="utf-8")
