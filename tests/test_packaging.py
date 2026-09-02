from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUDOERS = ROOT / "packaging/sudoers.d/light-console-shutdown"
UNIT = ROOT / "packaging/systemd/light-console.service"


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
