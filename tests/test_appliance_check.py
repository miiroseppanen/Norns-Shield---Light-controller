from pathlib import Path

from light_console.appliance_check import (
    Check,
    format_report,
    inspect_workspace,
    _midi_bindings,
)

ROOT = Path(__file__).resolve().parents[1]
SHIELD = ROOT / "qlc/projects/siirtyma-shield.qxw"
MODULE = (ROOT / "light_console/appliance_check.py").read_text(encoding="utf-8")
WRAPPER = (ROOT / "packaging/light-appliance-check").read_text(encoding="utf-8")


def test_inspect_siirtyma_shield_is_safe():
    ws = inspect_workspace(SHIELD)
    assert ws["functions"] == 100
    assert ws["startup"] is True
    assert ws["startup_id"] == 0
    assert ws["loopback"] == 2
    assert ws["launchpad_uid"] is True
    assert ws["launchpad_name"] is True
    assert ws["forbidden"] == []
    assert ws["ok"] is True


def test_inspect_rejects_pknight_and_production_pi(tmp_path):
    text = SHIELD.read_text(encoding="utf-8")
    dirty = text.replace('outputIP="127.0.0.1"', 'outputIP="192.168.88.201"', 1)
    dirty = dirty.replace("127.0.0.1", "192.168.88.248", 1)
    path = tmp_path / "unsafe.qxw"
    path.write_text(dirty, encoding="utf-8")
    ws = inspect_workspace(path)
    assert "192.168.88.201" in ws["forbidden"]
    assert "192.168.88.248" in ws["forbidden"]
    assert ws["ok"] is False


def test_format_report_fail_and_warn():
    report = format_report(
        [
            Check("QLC", "http", "PASS", "200"),
            Check("QLC", "restarts", "WARN", "1"),
            Check("MIDI", "usb", "FAIL", "missing"),
        ],
        header={"uptime_s": "12"},
    )
    assert "SHIELD APPLIANCE CHECK" in report
    assert "uptime_s: 12" in report
    assert "RESULT: FAIL" in report
    assert "1 failing" in report
    assert "1 warnings" in report


def test_midi_bindings_parse_aconnect():
    sample = """
client 0: 'System' [type=kernel]
    0 'Timer           '
client 28: 'Launchpad Mini' [type=kernel,card=3]
    0 'Launchpad Mini MIDI 1'
	Connecting To: 128:0
	Connected From: 128:0
client 128: 'qlcplus' [type=user,pid=3514]
    0 '__QLC__         '
	Connecting To: 28:0
	Connected From: 28:0
"""
    midi_in, midi_fb = _midi_bindings(sample)
    assert midi_in is True
    assert midi_fb is True
    none_in, none_fb = _midi_bindings("client 28: 'Launchpad Mini'\n    0 'Launchpad Mini MIDI 1'\n")
    assert none_in is False
    assert none_fb is False


def test_check_is_read_only():
    for banned in (
        "systemctl start",
        "systemctl stop",
        "systemctl restart",
        "systemctl enable",
        "systemctl disable",
        "systemctl reload",
        "reboot",
        "shutdown",
        "setFunctionStatus",
        "nmcli",
    ):
        assert banned not in MODULE
        assert banned not in WRAPPER
    assert "python3 -m light_console.appliance_check" in WRAPPER
