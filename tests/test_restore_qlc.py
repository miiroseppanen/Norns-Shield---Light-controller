from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/restore-qlc.sh"


def test_restore_qlc_uses_systemd_mainpid_not_command_line_match():
    text = SCRIPT.read_text()
    assert SCRIPT.exists()
    assert "#!/bin/bash" in text
    assert "set -euo pipefail" in text
    assert "systemctl start" in text
    assert "qlcplus.service" in text
    assert "systemctl is-active" in text
    assert "MainPID" in text
    for banned in ("pgrep", "pkill", "killall", "kill ", "light-console.service"):
        assert banned not in text
