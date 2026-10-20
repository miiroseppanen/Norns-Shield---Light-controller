"""WIZ-LIGHTS AP profile, isolation, and netmode rollback protection.

No live nmcli. No PSK. No WiZ UDP.
"""

from __future__ import annotations

from pathlib import Path

from light_console.output.netmode import (
    AP_CONNECTION_ID,
    SSID_LIGHT_CONTROL,
    _restore_wifi,
)
from light_console.output.wiz_ap import (
    LIGHT_CONTROL_IFACE,
    LIGHT_CONTROL_NET,
    LOCAL_INPUT_TCP_PORTS,
    PRODUCTION_PI_IP,
    SSID_WIZ_LIGHTS,
    WIZ_AP_ADDRESS,
    WIZ_AP_BAND,
    WIZ_AP_CHANNEL,
    WIZ_AP_CONNECTION_ID,
    WIZ_AP_DHCP_RANGE,
    WIZ_AP_IFACE,
    WIZ_AP_IPV4_METHOD,
    WIZ_AP_NETWORK,
    WIZ_AP_PMF,
    WizApError,
    assert_wlan1_only,
    isolation_nft,
    is_wiz_lights_profile,
    parse_nmcli_key_values,
    parse_nmcli_name_uuid,
    profile_settings,
    restore_wifi_plan,
    select_wiz_lights_uuid,
    validate_existing_wiz_profile,
)

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "packaging/install-wiz-lights.sh"
NFT = ROOT / "packaging/nftables/shieldxl-wiz-lights.nft"
UNIT = ROOT / "packaging/systemd/shieldxl-wiz-isolation.service"
NETMODE = ROOT / "light_console/output/netmode.py"
BRIDGE = ROOT / "services/wiz/wiz_artnet_bridge.py"


def test_profile_is_wlan1_only_and_never_wlan0():
    keys = dict(profile_settings())
    assert keys["connection.interface-name"] == "wlan1"
    assert keys["connection.interface-name"] != LIGHT_CONTROL_IFACE
    assert keys["802-11-wireless.ssid"] == SSID_WIZ_LIGHTS
    assert keys["802-11-wireless.mode"] == "ap"
    assert keys["802-11-wireless.band"] == WIZ_AP_BAND == "bg"
    assert keys["802-11-wireless.channel"] == WIZ_AP_CHANNEL == "6"
    assert keys["ipv4.method"] == WIZ_AP_IPV4_METHOD == "shared"
    assert keys["ipv4.addresses"] == WIZ_AP_ADDRESS == "10.42.0.1/24"
    assert keys["ipv4.shared-dhcp-range"] == WIZ_AP_DHCP_RANGE == "10.42.0.20,10.42.0.199"
    assert keys["ipv4.never-default"] == "yes"
    assert keys["ipv6.method"] == "disabled"
    assert keys["connection.autoconnect"] == "no"
    assert keys["802-11-wireless-security.pmf"] == WIZ_AP_PMF == "disable"
    assert keys["802-11-wireless.ap-isolation"] == "no"
    assert "psk" not in {k.lower() for k in keys}
    assert "wlan0" not in str(profile_settings())
    assert WIZ_AP_CONNECTION_ID != AP_CONNECTION_ID
    assert WIZ_AP_IFACE != LIGHT_CONTROL_IFACE


def test_wlan0_rejected():
    try:
        assert_wlan1_only("wlan0")
    except WizApError as exc:
        assert "wlan0" in str(exc) or "wlan1" in str(exc)
    else:
        raise AssertionError("wlan0 must be rejected")


def test_isolation_blocks_forward_not_local_input():
    text = isolation_nft()
    assert WIZ_AP_NETWORK in text
    assert LIGHT_CONTROL_NET in text
    assert "iifname \"wlan1\"" in text
    assert "type filter hook forward" in text
    assert "drop" in text
    assert "chain input" not in text
    assert "tcp dport" not in text
    for port in LOCAL_INPUT_TCP_PORTS:
        assert str(port) not in text
    assert PRODUCTION_PI_IP not in text
    assert NFT.read_text(encoding="utf-8") == text
    src = INSTALL.read_text(encoding="utf-8")
    assert "192.168.88.248" not in src
    assert "ping" not in src


def test_restore_never_downs_wiz_lights():
    downs, ups = restore_wifi_plan(
        ["netplan-wlan0-LIGHT-CONTROL"],
        ["netplan-wlan0-LIGHT-CONTROL", WIZ_AP_CONNECTION_ID],
        {WIZ_AP_CONNECTION_ID},
    )
    assert WIZ_AP_CONNECTION_ID not in downs
    assert downs == []
    assert ups == []
    downs, ups = restore_wifi_plan(
        ["netplan-wlan0-LIGHT-CONTROL"],
        ["netplan-wlan0-LIGHT-CONTROL", AP_CONNECTION_ID],
        {WIZ_AP_CONNECTION_ID},
    )
    assert downs == [AP_CONNECTION_ID]
    assert is_wiz_lights_profile(WIZ_AP_CONNECTION_ID) is True
    assert is_wiz_lights_profile("other", SSID_WIZ_LIGHTS) is True
    assert is_wiz_lights_profile("netplan-wlan0-LIGHT-CONTROL", SSID_LIGHT_CONTROL) is False


def test_restore_wifi_skips_protected_nmcli(monkeypatch):
    calls: list[list[str]] = []

    def fake_nmcli(args, timeout=20.0):
        calls.append(list(args))
        if args[:3] == ["-t", "-f", "NAME,TYPE"] or (
            args[:2] == ["-t", "-f"] and "NAME,TYPE" in args[2]
        ):
            return 0, "WIZ-LIGHTS:802-11-wireless\nnetplan-wlan0-LIGHT-CONTROL:802-11-wireless\n", ""
        if "802-11-wireless.ssid" in args:
            name = args[-1]
            if name == WIZ_AP_CONNECTION_ID:
                return 0, "802-11-wireless.ssid:WIZ-LIGHTS\n802-11-wireless.mode:ap\n", ""
            return 0, "802-11-wireless.ssid:LIGHT-CONTROL\n802-11-wireless.mode:infrastructure\n", ""
        if args[:4] == ["-t", "-f", "NAME,TYPE,DEVICE", "connection"]:
            return (
                0,
                "netplan-wlan0-LIGHT-CONTROL:802-11-wireless:wlan0\n"
                "WIZ-LIGHTS:802-11-wireless:wlan1\n",
                "",
            )
        return 0, "", ""

    monkeypatch.setattr("light_console.output.netmode._nmcli", fake_nmcli)
    _restore_wifi(["netplan-wlan0-LIGHT-CONTROL"])
    downs = [c for c in calls if c[:2] == ["connection", "down"]]
    assert ["connection", "down", "WIZ-LIGHTS"] not in downs


def test_nmcli_name_uuid_select_is_idempotent():
    listed = (
        "netplan-wlan0-LIGHT-CONTROL:420b8d15-c651-354a-aede-31413799dcba\n"
        "WIZ-LIGHTS:a71df0ce-ff11-46a6-a37c-fb0e1ba45fcc\n"
        "lo:a1d536e7-b686-4610-881c-7db532d35e8e\n"
    )
    rows = parse_nmcli_name_uuid(listed)
    assert select_wiz_lights_uuid(rows) == "a71df0ce-ff11-46a6-a37c-fb0e1ba45fcc"
    assert select_wiz_lights_uuid(parse_nmcli_name_uuid("lo:abc\n")) is None
    try:
        select_wiz_lights_uuid(
            parse_nmcli_name_uuid(
                "WIZ-LIGHTS:a71df0ce-ff11-46a6-a37c-fb0e1ba45fcc\n"
                "WIZ-LIGHTS:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb\n"
            )
        )
    except WizApError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicates must stop")


def test_existing_profile_wrong_iface_stops():
    fields = parse_nmcli_key_values(
        "connection.id:WIZ-LIGHTS\n"
        "connection.interface-name:wlan0\n"
        "802-11-wireless.ssid:WIZ-LIGHTS\n"
        "802-11-wireless.mode:ap\n"
    )
    try:
        validate_existing_wiz_profile(fields)
    except WizApError as exc:
        assert "wlan0" in str(exc)
    else:
        raise AssertionError("wlan0-bound WIZ-LIGHTS must stop")
    ok = parse_nmcli_key_values(
        "connection.id:WIZ-LIGHTS\n"
        "connection.interface-name:wlan1\n"
        "802-11-wireless.ssid:WIZ-LIGHTS\n"
        "802-11-wireless.mode:ap\n"
    )
    validate_existing_wiz_profile(ok)
    try:
        validate_existing_wiz_profile(
            parse_nmcli_key_values(
                "connection.id:WIZ-LIGHTS\n"
                "connection.interface-name:\n"
                "802-11-wireless.ssid:WIZ-LIGHTS\n"
                "802-11-wireless.mode:ap\n"
            )
        )
    except WizApError as exc:
        assert "interface-name" in str(exc)
    else:
        raise AssertionError("empty interface-name must stop")


def test_installer_is_nm_shared_only():
    text = INSTALL.read_text(encoding="utf-8")
    unit = UNIT.read_text(encoding="utf-8")
    assert "hostapd.service" not in text
    assert "dnsmasq.service" not in text
    assert "dispatcher" not in text.lower()
    assert "systemctl enable wizbridge" not in text
    assert "systemctl start wizbridge" not in text
    assert "38899" not in text
    assert "master.qxw" not in text
    assert "qlcplus.service" not in text
    assert "netplan-wlan0-LIGHT-CONTROL" not in text
    assert "-f connection.filename" not in text
    assert "NAME,UUID" in text
    assert "ipv4.method shared" in text or "ipv4.method" in text
    assert "wlan1" in text
    assert "autoconnect no" in text
    assert "--up" in text
    assert "wizbridge" not in unit.lower() or "Do not start" in unit
    assert "Wants=wizbridge" not in unit
    assert "systemctl enable --now shieldxl-wiz-isolation.service" in text


def test_ap1_does_not_emit_wiz_udp():
    src = INSTALL.read_text(encoding="utf-8")
    assert "getPilot" not in src
    assert "setPilot" not in src
    assert "sendto" not in src
    bridge = BRIDGE.read_text(encoding="utf-8")
    assert "wiz_tx_allowed" in bridge
    netmode = NETMODE.read_text(encoding="utf-8")
    assert "38899" not in netmode
    assert "_protected_wifi_names" in netmode
    assert "restore_wifi_plan" in netmode
