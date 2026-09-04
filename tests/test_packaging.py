from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUDOERS = ROOT / "packaging/sudoers.d/light-console-shutdown"
UNIT = ROOT / "packaging/systemd/light-console.service"
QLC = ROOT / "packaging/systemd/qlcplus.service"
STARTUP = ROOT / "packaging/systemd/qlc-startup-chaser.service"
APPLIANCE = ROOT / "packaging/install-appliance.sh"
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
    assert "-w" in text
    exec_start = next(ln for ln in text.splitlines() if ln.startswith("ExecStart="))
    assert exec_start == "ExecStart=/usr/bin/qlcplus-qml -w -o /home/light/shows/master.qxw"
    assert "ExecStartPre=/usr/bin/python3 -m light_console.midi_wait" in text
    assert "PYTHONPATH=/home/light/light-console" in text
    assert "TimeoutStartSec=30" in text
    assert "qlc-startup-chaser.service" in text
    assert "--open" not in exec_start
    assert "-9" not in exec_start
    assert "qlc-launch" not in exec_start
    assert "/usr/bin/systemctl" not in SUDOERS.read_text()
    sudoers = SUDOERS.read_text()
    assert "qlcplus" not in sudoers
    assert "NOPASSWD: ALL" not in sudoers
    assert "light-console.service" not in [
        ln for ln in text.splitlines() if ln.startswith(("After=", "Requires=", "Wants=", "BindsTo="))
    ]
    lc = UNIT.read_text()
    assert "qlcplus.service" not in [
        ln for ln in lc.splitlines() if ln.startswith(("After=", "Requires=", "Wants=", "BindsTo="))
    ]


def test_test_workspace_has_no_show_outputs():
    text = QXW.read_text().lower()
    assert "launchpad" not in text
    assert "pknight" not in text
    assert "192.168.88.201" not in text
    assert "<!doctype workspace>" in text
    assert "outputip=\"127.0.0.1\"" in text
    assert "plugin=\"artnet\"" in text


def test_startup_unit_waits_for_webaccess():
    text = STARTUP.read_text()
    assert "TimeoutStartSec=360" in text
    assert "python3 -m light_console.startup_chaser" in text
    assert "Requires=qlcplus.service" in text


def test_appliance_check_wrapper_is_read_only():
    text = (ROOT / "packaging/light-appliance-check").read_text()
    assert "python3 -m light_console.appliance_check" in text
    assert "systemctl start" not in text
    assert "systemctl restart" not in text
    assert "reboot" not in text


def test_appliance_install_does_not_enable_wiz():
    text = APPLIANCE.read_text()
    assert "siirtyma-shield.qxw" in text
    assert "qlc-startup-chaser.service" in text
    assert "systemctl enable wizbridge" not in text
    assert "systemctl start wizbridge" not in text
