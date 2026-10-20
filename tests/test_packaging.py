from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUDOERS = ROOT / "packaging/sudoers.d/light-console-shutdown"
UNIT = ROOT / "packaging/systemd/light-console.service"
QLC = ROOT / "packaging/systemd/qlcplus.service"
STARTUP = ROOT / "packaging/systemd/qlc-startup-chaser.service"
APPLIANCE = ROOT / "packaging/install-appliance.sh"
QXW = ROOT / "qlc/projects/light-console-test.qxw"


def test_sudoers_allows_only_halt_and_restart_now():
    text = SUDOERS.read_text()
    lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert lines == [
        "light ALL=(root) NOPASSWD: /usr/sbin/shutdown -h now",
        "light ALL=(root) NOPASSWD: /usr/sbin/shutdown -r now",
    ]
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
    assert "NetworkManager.service" in keys["After"]
    assert "network-online.target" not in keys["After"]
    live = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    assert not any("network-online" in ln for ln in live)
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


def test_sudoers_qlc_start_stop_only():
    path = ROOT / "packaging/sudoers.d/light-console-qlc"
    text = path.read_text()
    lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert lines == [
        "light ALL=(root) NOPASSWD: /usr/bin/systemctl start qlcplus.service",
        "light ALL=(root) NOPASSWD: /usr/bin/systemctl stop qlcplus.service",
    ]
    assert "NOPASSWD: ALL" not in text
    assert "restart" not in text
    assert "kill" not in text
    assert "shutdown" not in text
    appliance = APPLIANCE.read_text()
    assert "light-console-qlc" in appliance
    assert "shieldxl-oled-starting.service" in appliance
    assert "shieldxl-oled-shutdown.service" in appliance


def test_oled_lifecycle_install_does_not_touch_qlc_or_master():
    path = ROOT / "packaging/install-oled-lifecycle.sh"
    text = path.read_text()
    assert "shieldxl-oled-shutdown.service" in text
    assert "master.qxw" not in text
    assert "qlcplus" not in text
    assert "wizbridge" not in text
    assert "NetworkManager" not in text
    assert "systemctl restart light-console" not in text
    assert "systemctl restart qlcplus" not in text


def test_wiz_lifecycle_install_does_not_enable_or_start_bridge():
    path = ROOT / "packaging/install-wiz-lifecycle.sh"
    text = path.read_text()
    unit = (ROOT / "packaging/systemd/wizbridge.service").read_text()
    sudoers = (ROOT / "packaging/sudoers.d/light-console-wiz").read_text()
    helper = (ROOT / "packaging/light-console-wiz").read_text()
    assert "systemctl enable wizbridge" not in text
    assert "systemctl start wizbridge" not in text
    assert "systemctl disable wizbridge.service" in text
    assert "WantedBy=" not in unit
    assert "master.qxw" not in text
    assert "qlcplus.service" not in text
    assert "NOPASSWD: ALL" not in sudoers
    assert "nmcli" not in sudoers
    assert "wlan0" not in helper
    assert "setPilot" not in helper
    appliance = APPLIANCE.read_text()
    assert "systemctl enable wizbridge" not in appliance
    text = APPLIANCE.read_text()
    assert "siirtyma-shield.qxw" in text
    assert "qlc-startup-chaser.service" in text
    assert "systemctl enable wizbridge" not in text
    assert "systemctl start wizbridge" not in text


def test_wiz_lights_install_is_wlan1_shared_and_no_wizbridge():
    path = ROOT / "packaging/install-wiz-lights.sh"
    text = path.read_text()
    nft = (ROOT / "packaging/nftables/shieldxl-wiz-lights.nft").read_text()
    unit = (ROOT / "packaging/systemd/shieldxl-wiz-isolation.service").read_text()
    assert "wlan1" in text
    assert 'IFACE="wlan1"' in text
    assert "connection.interface-name" not in text or "wlan1" in text
    assert "systemctl enable wizbridge" not in text
    assert "systemctl start wizbridge" not in text
    assert "hostapd.service" not in text
    assert "-f connection.filename" not in text
    assert "master.qxw" not in text
    assert "10.42.0.0/24" in nft
    assert "192.168.88.0/24" in nft
    assert "tcp dport" not in nft
    assert "Wants=wizbridge" not in unit
    assert "dispatcher" not in text.lower()


def test_netmode_helper_install_is_light_control_only():
    helper = (ROOT / "packaging/light-console-net").read_text()
    sudoers = (ROOT / "packaging/sudoers.d/light-console-net").read_text()
    installer = (ROOT / "packaging/install-netmode.sh").read_text()
    lines = [
        ln.strip()
        for ln in sudoers.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert lines == [
        "light ALL=(root) NOPASSWD: /usr/sbin/light-console-net standalone",
        "light ALL=(root) NOPASSWD: /usr/sbin/light-console-net network",
    ]
    assert "nmcli" not in sudoers
    assert "NOPASSWD: ALL" not in sudoers
    assert "wlan1" not in helper
    assert "WIZ-LIGHTS" not in helper
    assert "192.168.88.248" not in helper
    assert "systemctl restart" not in installer
    assert "master.qxw" not in installer
    assert "light-console.service" in installer or "did not modify" in installer

