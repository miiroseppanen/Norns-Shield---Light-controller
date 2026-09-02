from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUDOERS = ROOT / "packaging/sudoers.d/light-console-shutdown"
UNIT = ROOT / "packaging/systemd/light-console.service"
QLC = ROOT / "packaging/systemd/qlcplus.service"
QXW = ROOT / "qlc/projects/light-console-test.qxw"


def test_sudoers_allows_only_halt_now():
    text = SUDOERS.read_text()
    lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert lines == ["light ALL=(root) NOPASSWD: /usr/sbin/shutdown -h now"]
    assert "NOPASSWD: ALL" not in text
    assert "/usr/bin/systemctl" not in text
    assert "reboot" not in text


def test_unit_is_light_user_shield_only():
    text = UNIT.read_text()
    keys = {
        ln.split("=", 1)[0]: ln.split("=", 1)[1]
        for ln in text.splitlines()
        if ln and not ln.startswith("#") and not ln.startswith("[") and "=" in ln
    }
    assert keys["User"] == "light"
    assert keys["WorkingDirectory"] == "/home/light/light-console"
    assert keys["ExecStart"] == "/usr/bin/python3 -u -m light_console.main --shield"
    assert keys["Restart"] == "on-failure"
    assert keys["WantedBy"] == "multi-user.target"
    assert "PYTHONPATH=/home/light/light-console" in text
    assert "qlcplus" not in keys["ExecStart"]
    assert not any(ln.startswith("After=dev-spidev") or ln.startswith("Wants=dev-spidev") for ln in text.splitlines())
    unit_section, rest = text.split("\n[Service]\n", 1)
    service_section = rest.split("\n[Install]\n", 1)[0]
    assert "StartLimitIntervalSec=60" in unit_section
    assert "StartLimitBurst=5" in unit_section
    assert "StartLimitIntervalSec" not in service_section
    assert "StartLimitBurst" not in service_section


def test_qlcplus_unit_is_independent():
    text = QLC.read_text()
    assert "User=light" in text
    assert "QT_QPA_PLATFORM=offscreen" in text
    assert "/usr/bin/qlcplus-qml" in text
    assert "-w" in text
    exec_start = next(ln for ln in text.splitlines() if ln.startswith("ExecStart="))
    assert exec_start == "ExecStart=/usr/bin/qlcplus-qml -w"
    assert "--open" not in exec_start
    assert "light-console.service" not in [
        ln for ln in text.splitlines() if ln.startswith(("After=", "Requires=", "Wants=", "BindsTo="))
    ]
    lc = UNIT.read_text()
    assert "qlcplus.service" not in [
        ln for ln in lc.splitlines() if ln.startswith(("After=", "Requires=", "Wants=", "BindsTo="))
    ]


def test_test_workspace_has_no_show_outputs():
    text = QXW.read_text().lower()
    assert "artnet" not in text
    assert "art-net" not in text
    assert "launchpad" not in text
    assert "pknight" not in text
    assert "wiz" not in text
    assert "<!doctype workspace>" in text
