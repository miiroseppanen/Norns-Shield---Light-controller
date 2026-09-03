from pathlib import Path
import os
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/upload-show.sh"
QXW = ROOT / "qlc/projects/light-console-test.qxw"


def test_upload_show_is_executable_with_documented_flags():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & stat.S_IXUSR
    text = SCRIPT.read_text()
    assert "--dry-run" in text
    assert "--replace" in text
    assert "--list" in text
    assert "prepare_file" in text
    help_text = subprocess.check_output([SCRIPT, "--help"], text=True)
    assert "--dry-run" in help_text
    assert "--replace" in help_text
    assert "--list" in help_text
    assert "--force" not in help_text
    assert "--open" not in help_text


def test_dry_run_does_not_modify_source(tmp_path):
    src = tmp_path / "loopback.qxw"
    src.write_text(QXW.read_text())
    before = src.read_text()
    mtime = src.stat().st_mtime
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    out = subprocess.check_output(
        [SCRIPT, "--dry-run", str(src)],
        text=True,
        env=env,
        cwd=ROOT,
    )
    time.sleep(0.05)
    assert src.read_text() == before
    assert src.stat().st_mtime == mtime
    assert "dry-run: not copied to the Shield" in out
    assert "left unchanged" in out
    assert "loopback.qxw" in out


def test_dry_run_rejects_invalid_workspace(tmp_path):
    src = tmp_path / "bad.qxw"
    src.write_text("not a workspace")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.run(
        [SCRIPT, "--dry-run", str(src)],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )
    assert proc.returncode != 0
    assert src.read_text() == "not a workspace"
