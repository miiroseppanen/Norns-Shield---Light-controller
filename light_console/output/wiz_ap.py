"""WIZ-LIGHTS AP profile and isolation policy. No Wi-Fi secrets. No nmcli.

wlan1 only. Never targets LIGHT-CONTROL / wlan0. Does not start wizbridge
or emit WiZ UDP. PSK is supplied only by the root installer at apply time.
"""

from __future__ import annotations

SSID_WIZ_LIGHTS = "WIZ-LIGHTS"
WIZ_AP_CONNECTION_ID = "WIZ-LIGHTS"
WIZ_AP_IFACE = "wlan1"
WIZ_AP_BAND = "bg"
WIZ_AP_CHANNEL = "6"
WIZ_AP_ADDRESS = "10.42.0.1/24"
WIZ_AP_IPV4 = "10.42.0.1"
WIZ_AP_PREFIX = 24
WIZ_AP_NETWORK = "10.42.0.0/24"
WIZ_AP_DHCP_RANGE = "10.42.0.20,10.42.0.199"
WIZ_AP_IPV4_METHOD = "shared"
LIGHT_CONTROL_IFACE = "wlan0"
LIGHT_CONTROL_NET = "192.168.88.0/24"
PRODUCTION_PI_IP = "192.168.88.248"
# Production allows SSH and QLC :9999 on 10.42.0.1. Isolation is FORWARD only.
LOCAL_INPUT_TCP_PORTS = (22, 9999)

# NM 1.52 wifi-sec.pmf: disable matches production / rtw88 AP-safe target.
WIZ_AP_PMF = "disable"


class WizApError(ValueError):
    """Invalid WIZ-LIGHTS profile request."""


def parse_nmcli_terse_rows(text: str, columns: int) -> list[tuple[str, ...]]:
    """Parse `nmcli -t` rows. NM 1.52.1 uses ':' separators; NAME is first."""
    rows: list[tuple[str, ...]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(":", columns - 1)
        if len(parts) < columns:
            continue
        rows.append(tuple(parts[:columns]))
    return rows


def parse_nmcli_name_uuid(text: str) -> list[tuple[str, str]]:
    return [(str(name), str(uuid)) for name, uuid in parse_nmcli_terse_rows(text, 2)]


def parse_nmcli_key_values(text: str) -> dict[str, str]:
    """Parse `nmcli -t connection show NAME` key:value lines. No secrets expected."""
    out: dict[str, str] = {}
    for raw in (text or "").splitlines():
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        if not key:
            continue
        out[key] = value.strip()
    return out


def select_wiz_lights_uuid(name_uuid: list[tuple[str, str]]) -> str | None:
    """None = create. One UUID = reuse. Duplicates are fatal."""
    matches = [uuid for name, uuid in name_uuid if name == WIZ_AP_CONNECTION_ID]
    if not matches:
        return None
    if len(matches) > 1:
        raise WizApError(
            f"duplicate {WIZ_AP_CONNECTION_ID} profiles: {', '.join(matches)}"
        )
    return matches[0]


def validate_existing_wiz_profile(fields: dict[str, str]) -> None:
    """STOP if an existing WIZ-LIGHTS profile is on the wrong iface or not AP."""
    iface = (fields.get("connection.interface-name") or "").strip()
    ssid = (fields.get("802-11-wireless.ssid") or "").strip()
    mode = (fields.get("802-11-wireless.mode") or "").strip()
    if iface and iface != WIZ_AP_IFACE:
        raise WizApError(
            f"{WIZ_AP_CONNECTION_ID} is bound to {iface!r}, expected {WIZ_AP_IFACE}"
        )
    if ssid and ssid != SSID_WIZ_LIGHTS:
        raise WizApError(f"{WIZ_AP_CONNECTION_ID} SSID is {ssid!r}, expected {SSID_WIZ_LIGHTS}")
    if mode and mode not in {"ap", ""}:
        raise WizApError(f"{WIZ_AP_CONNECTION_ID} mode is {mode!r}, expected ap")
    if not iface:
        raise WizApError(
            f"{WIZ_AP_CONNECTION_ID} has empty interface-name; refusing to guess"
        )


def assert_wlan1_only(iface: str) -> str:
    name = (iface or "").strip()
    if name != WIZ_AP_IFACE:
        raise WizApError(f"WIZ-LIGHTS AP must use {WIZ_AP_IFACE}, not {name!r}")
    if name == LIGHT_CONTROL_IFACE:
        raise WizApError("WIZ-LIGHTS must never target wlan0")
    return name


def is_wiz_lights_profile(name: str, ssid: str = "") -> bool:
    ident = (name or "").strip()
    wireless = (ssid or "").strip()
    if ident == WIZ_AP_CONNECTION_ID:
        return True
    return wireless == SSID_WIZ_LIGHTS


def restore_wifi_plan(
    snapshot: list[str],
    active: list[str],
    protected: set[str] | frozenset[str] = frozenset(),
) -> tuple[list[str], list[str]]:
    """Which Wi-Fi profiles rollback may down/up. Never downs protected names."""
    snap = list(snapshot)
    act = list(active)
    hold = set(protected)
    downs = [name for name in act if name not in snap and name not in hold]
    ups = [name for name in snap if name not in act]
    return downs, ups


def profile_settings(iface: str = WIZ_AP_IFACE) -> tuple[tuple[str, str], ...]:
    """nmcli connection.modify key/value pairs. No PSK, no wlan0 keys."""
    assert_wlan1_only(iface)
    return (
        ("connection.id", WIZ_AP_CONNECTION_ID),
        ("connection.interface-name", WIZ_AP_IFACE),
        ("connection.autoconnect", "no"),
        ("802-11-wireless.mode", "ap"),
        ("802-11-wireless.ssid", SSID_WIZ_LIGHTS),
        ("802-11-wireless.band", WIZ_AP_BAND),
        ("802-11-wireless.channel", WIZ_AP_CHANNEL),
        ("802-11-wireless.ap-isolation", "no"),
        ("ipv4.method", WIZ_AP_IPV4_METHOD),
        ("ipv4.addresses", WIZ_AP_ADDRESS),
        ("ipv4.shared-dhcp-range", WIZ_AP_DHCP_RANGE),
        ("ipv4.never-default", "yes"),
        ("ipv6.method", "disabled"),
        ("802-11-wireless-security.key-mgmt", "wpa-psk"),
        ("802-11-wireless-security.proto", "rsn"),
        ("802-11-wireless-security.pairwise", "ccmp"),
        ("802-11-wireless-security.group", "ccmp"),
        ("802-11-wireless-security.pmf", WIZ_AP_PMF),
    )


def isolation_nft() -> str:
    """FORWARD-only isolation. Local INPUT to 10.42.0.1 stays open (SSH, QLC :9999)."""
    return (
        "#!/usr/sbin/nft -f\n"
        "destroy table inet shieldxl_wiz_lights\n"
        "table inet shieldxl_wiz_lights {\n"
        "  chain forward {\n"
        "    type filter hook forward priority -10; policy accept;\n"
        f"    iifname \"{WIZ_AP_IFACE}\" ip saddr {WIZ_AP_NETWORK} "
        f"ip daddr {LIGHT_CONTROL_NET} drop\n"
        "  }\n"
        "}\n"
    )
