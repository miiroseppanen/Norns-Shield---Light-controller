from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HELP = ROOT / "packaging/light-help"
PROFILE = ROOT / "packaging/profile.d/light-help.sh"
INSTALL = ROOT / "packaging/install-light-help.sh"


def test_light_help_prints_operator_guide():
    out = subprocess.check_output([HELP], text=True)
    for needle in (
        "SHIELD XL LIGHT CONSOLE",
        "ssh light@shieldxl-light.local",
        "192.168.88.246",
        "http://shieldxl-light.local:9999",
        "systemctl status light-console --no-pager",
        "sudo systemctl restart light-console",
        "journalctl -u light-console -n 100 --no-pager",
        "systemctl status qlcplus --no-pager",
        "sudo systemctl stop qlcplus",
        "sudo systemctl start qlcplus",
        "sudo systemctl restart qlcplus",
        "journalctl -u qlcplus -n 100 --no-pager",
        "/home/light/shows/",
        "/home/light/shows/current.qxw",
        "readlink /home/light/shows/current.qxw",
        "ls -l /home/light/shows/",
        "./scripts/upload-show.sh --list",
        './scripts/upload-show.sh "/path/to/show.qxw"',
        "./scripts/upload-show.sh --dry-run",
        "./scripts/upload-show.sh --replace",
        "not a Git checkout",
        "from light_console import VERSION",
        "git describe --tags --always",
        "git rev-parse --short HEAD",
        "SYSTEM -> SHUTDOWN -> CONFIRM",
        "sudo /usr/sbin/shutdown -h now",
        "valot@192.168.88.248",
        "MENU -> SHOWS -> E1 select -> K3 -> LOAD SHOW?",
        "last-good.qxw",
        "/usr/bin/qlcplus-qml -w",
        "Automatic selected-show -> QLC load is not implemented",
        "scripts/restore-qlc.sh",
        "sudo systemctl start qlcplus",
        "Launchpad Mini MIDI 1",
        "1235:0036",
        "QLC 5.2.2 does not hotplug-rescan MIDI devices",
        "light-help",
    ):
        assert needle in out
    assert "git rev-parse --short HEAD" in out
    # Shield copy is not git; help must not tell operators to git there.
    assert "cd /home/light/light-console\n  git rev-parse" not in out
    assert "WIZ-LIGHTS" not in out
    assert "password" not in out.lower() or "passwordlessly" in out
    assert "/tmp/" not in out


def test_login_hook_is_quiet():
    text = PROFILE.read_text()
    assert "SSH_CONNECTION" in text
    assert "PS1" in text
    assert "LIGHT_HELP_SHOWN" in text
    assert "/usr/local/bin/light-help" in text
    for banned in ("systemctl", "journalctl", "ping", "curl", "nmcli", "restart"):
        assert banned not in text


def test_installer_is_reproducible_and_side_effect_free():
    text = INSTALL.read_text()
    assert 'HELP_DST="/usr/local/bin/light-help"' in text
    assert 'PROFILE_DST="/etc/profile.d/light-help.sh"' in text
    assert 'SHOWS_DIR="/home/light/shows"' in text
    assert "current.qxw" in text
    assert "systemctl" not in text
    assert "reboot" not in text
    appliance = (ROOT / "packaging/install-appliance.sh").read_text()
    assert 'bash "$ROOT/packaging/install-light-help.sh"' in appliance
