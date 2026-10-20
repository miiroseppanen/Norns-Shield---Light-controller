"""LIGHT-CONTROL NETWORK / STANDALONE mode. Independent of QLC Art-Net target.

WIZ-LIGHTS is a separate SSID on a dedicated radio. This module never
merges the two networks and never auto-failovers between modes.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from abc import ABC, abstractmethod

from light_console.output.network import KIND_LOOPBACK, KIND_ONBOARD, KIND_USB, NetIface
from light_console.output.wiz_ap import (
    WIZ_AP_CONNECTION_ID,
    WIZ_AP_IFACE,
    is_wiz_lights_profile,
    restore_wifi_plan,
)
from light_console.ui.vocab import FAILED, NETWORK, STANDALONE, SWITCHING

LOG = logging.getLogger("light-console")

MODE_NETWORK = "network"
MODE_STANDALONE = "standalone"

NET_HELPER = "/usr/sbin/light-console-net"
SUDO = "/usr/bin/sudo"
NET_HELPER_ACTIONS = (MODE_STANDALONE, MODE_NETWORK)

SSID_LIGHT_CONTROL = "LIGHT-CONTROL"
SSID_WIZ_LIGHTS = "WIZ-LIGHTS"

AP_CONNECTION_ID = "light-console-ap-LIGHT-CONTROL"
AP_ADDRESS = "192.168.88.246/24"
AP_IPV4 = "192.168.88.246"
AP_BAND = "bg"
AP_CHANNEL = "6"
DHCP_RANGE = "192.168.88.100,192.168.88.199"

RESERVED_HOSTS = (
    "192.168.88.201",  # PKNight
    "192.168.88.242",  # AIR2DMX
    "192.168.88.246",  # Shield
    "192.168.88.248",  # production Pi historical — never assign, never probe
)
PRODUCTION_PI_IP = "192.168.88.248"
AIR2DMX_MAC = "3c:61:05:97:e1:93"


class NetHelperError(ValueError):
    """Invalid LIGHT-CONTROL helper argv."""


def net_helper_argv(action: str) -> tuple[str, ...]:
    """Exact sudo argv. Connection/iface names are not caller-supplied."""
    if action not in NET_HELPER_ACTIONS:
        raise NetHelperError(f"unsupported net helper action {action!r}")
    return (SUDO, "-n", NET_HELPER, action)


def validate_net_helper_argv(argv: list[str] | tuple[str, ...]) -> str:
    args = [str(part) for part in argv]
    if len(args) != 2 or args[1] not in NET_HELPER_ACTIONS:
        raise NetHelperError("usage: light-console-net standalone|network")
    return args[1]


def apply_network_mode(target: str) -> None:
    """Root helper entry. LIGHT-CONTROL / wlan0 only. Never WIZ-LIGHTS."""
    if target == MODE_STANDALONE:
        _apply_standalone()
        return
    if target == MODE_NETWORK:
        _apply_network()
        return
    raise NetHelperError(f"unsupported network mode {target!r}")


def parse_network_mode(raw: object) -> str:
    """Missing or unknown keys fall back to NETWORK. Never boot AP by accident."""
    if isinstance(raw, str) and raw.strip().lower() == MODE_STANDALONE:
        return MODE_STANDALONE
    return MODE_NETWORK


def oled_mode_word(mode: str) -> str:
    return STANDALONE if mode == MODE_STANDALONE else NETWORK


def toggle_filled(mode: str) -> bool:
    """Filled = NETWORK (user choice), outline = STANDALONE."""
    return mode != MODE_STANDALONE


def dhcp_range_excludes_reserved(range_text: str = DHCP_RANGE) -> bool:
    start_s, _, end_s = range_text.partition(",")
    try:
        start = int(start_s.rsplit(".", 1)[1])
        end = int(end_s.rsplit(".", 1)[1])
    except (IndexError, ValueError):
        return False
    prefix = start_s.rsplit(".", 1)[0]
    for host in RESERVED_HOSTS:
        if not host.startswith(prefix + "."):
            continue
        octet = int(host.rsplit(".", 1)[1])
        if start <= octet <= end:
            return False
    return True


def should_auto_failover() -> bool:
    return False


def light_control_iface(ifaces: tuple[NetIface, ...]) -> NetIface | None:
    for iface in ifaces:
        if iface.ssid == SSID_LIGHT_CONTROL:
            return iface
    onboard = [iface for iface in ifaces if iface.kind == KIND_ONBOARD]
    if onboard:
        return onboard[0]
    return None


def wiz_lights_iface(ifaces: tuple[NetIface, ...]) -> NetIface | None:
    for iface in ifaces:
        if iface.ssid == SSID_WIZ_LIGHTS:
            return iface
    return None


def onboard_wifi(ifaces: tuple[NetIface, ...]) -> NetIface | None:
    for iface in ifaces:
        if iface.kind == KIND_ONBOARD:
            return iface
    return None


def usb_wifi(ifaces: tuple[NetIface, ...]) -> NetIface | None:
    for iface in ifaces:
        if iface.kind == KIND_USB:
            return iface
    return None


def wiz_lights_role() -> str:
    return "AP"


def light_control_role(mode: str) -> str:
    return "AP" if mode == MODE_STANDALONE else "CLIENT"


class NetworkModeService(ABC):
    mode: str
    observed: str
    busy: bool

    @abstractmethod
    def set_desired(self, mode: str) -> bool:
        """Start an async switch. False if busy or invalid. Never mutates QLC XML."""

    @abstractmethod
    def poll(self) -> str:
        ...


class MockNetworkModeService(NetworkModeService):
    """Tests / simulator. No NetworkManager, no Wi-Fi secrets."""

    def __init__(self, mode: str = MODE_NETWORK, auto_settle: bool = False) -> None:
        self.mode = parse_network_mode(mode)
        self.desired = self.mode
        self.observed = oled_mode_word(self.mode)
        self.busy = False
        self.commands: list[str] = []
        self.auto_settle = auto_settle
        self.fail_next = False
        self.workspace_writes = 0
        self.wiz_toggles = 0
        self.probed_hosts: list[str] = []
        self._fail_since = 0.0

    def set_desired(self, mode: str) -> bool:
        target = parse_network_mode(mode)
        if self.busy:
            return False
        if target == self.mode:
            self.observed = oled_mode_word(self.mode)
            return True
        self.desired = target
        self.busy = True
        self.observed = SWITCHING
        self.commands.append(target)
        if self.auto_settle:
            self.settle()
        return True

    def poll(self) -> str:
        if self.auto_settle and self.busy:
            self.settle()
        if self.observed == FAILED and not self.busy and self._fail_since:
            if time.monotonic() - self._fail_since > 3.0:
                self.observed = oled_mode_word(self.mode)
                self._fail_since = 0.0
        return self.observed

    def settle(self) -> str:
        if not self.busy:
            return self.observed
        if self.fail_next:
            self.fail_next = False
            self.desired = self.mode
            self.busy = False
            self.observed = FAILED
            self._fail_since = time.monotonic()
            return self.observed
        self.mode = self.desired
        self.busy = False
        self.observed = oled_mode_word(self.mode)
        return self.observed


class LinuxNetworkModeService(NetworkModeService):
    """Root helper LIGHT-CONTROL STA/AP switch. Never reads or logs Wi-Fi secrets."""

    def __init__(self, mode: str = MODE_NETWORK, *, run_helper: object | None = None) -> None:
        self.mode = parse_network_mode(mode)
        self.desired = self.mode
        self.observed = oled_mode_word(self.mode)
        self.busy = False
        self._lock = threading.Lock()
        self._fail_since = 0.0
        self.workspace_writes = 0
        self.probed_hosts: list[str] = []
        self._run_helper = run_helper or _sudo_net_helper

    def set_desired(self, mode: str) -> bool:
        target = parse_network_mode(mode)
        with self._lock:
            if self.busy:
                return False
            if target == self.mode:
                self.observed = oled_mode_word(self.mode)
                return True
            self.desired = target
            self.busy = True
            self.observed = SWITCHING
        worker = threading.Thread(target=self._run, args=(target,), daemon=True, name="net-mode")
        worker.start()
        return True

    def poll(self) -> str:
        with self._lock:
            if self.observed == FAILED and not self.busy and self._fail_since:
                if time.monotonic() - self._fail_since > 3.0:
                    self.observed = oled_mode_word(self.mode)
                    self._fail_since = 0.0
            return self.observed

    def _run(self, target: str) -> None:
        try:
            rc = int(self._run_helper(target))
            if rc != 0:
                raise RuntimeError(f"network mode {target} helper rc={rc}")
            with self._lock:
                self.mode = target
                self.desired = target
                self.busy = False
                self.observed = oled_mode_word(target)
                self._fail_since = 0.0
            LOG.info("network mode applied %s", target)
        except Exception as exc:
            LOG.warning("network mode switch failed: %s", exc)
            with self._lock:
                self.desired = self.mode
                self.busy = False
                self.observed = FAILED
                self._fail_since = time.monotonic()


def _sudo_net_helper(action: str) -> int:
    argv = net_helper_argv(action)
    LOG.info("net helper: %s", " ".join(argv))
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        LOG.exception("net helper spawn failed")
        return 1
    if proc.returncode != 0:
        LOG.warning(
            "net helper rc=%s %s",
            proc.returncode,
            (proc.stderr or proc.stdout or "").strip(),
        )
    return int(proc.returncode)


def _guard_light_control(*, name: str = "", iface: str = "") -> None:
    if name and (name == WIZ_AP_CONNECTION_ID or is_wiz_lights_profile(name, "")):
        raise RuntimeError("refusing WIZ-LIGHTS in LIGHT-CONTROL switch")
    if iface and iface == WIZ_AP_IFACE:
        raise RuntimeError("refusing wlan1 in LIGHT-CONTROL switch")


def _nmcli(args: list[str], timeout: float = 20.0) -> tuple[int, str, str]:
    if shutil.which("nmcli") is None:
        return 127, "", "nmcli missing"
    try:
        proc = subprocess.run(
            ["nmcli", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _nmcli_ok(args: list[str], timeout: float = 20.0) -> str:
    rc, out, err = _nmcli(args, timeout=timeout)
    if rc != 0:
        raise RuntimeError((err or out or "nmcli failed").splitlines()[0][:120])
    return out


def _field(text: str, key: str) -> str:
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        name, _, value = raw.partition(":")
        if name.strip() == key:
            return value.strip()
    return ""


def _connections() -> list[str]:
    rc, out, _err = _nmcli(["-t", "-f", "NAME,TYPE", "connection", "show"])
    if rc != 0:
        return []
    names: list[str] = []
    for raw in out.splitlines():
        name, _, rest = raw.partition(":")
        if "wireless" in rest or rest.startswith("802-11"):
            names.append(name)
    return names


def _ssid_and_mode(name: str) -> tuple[str, str]:
    rc, out, _err = _nmcli(
        [
            "-t",
            "-f",
            "802-11-wireless.ssid,802-11-wireless.mode",
            "connection",
            "show",
            name,
        ]
    )
    if rc != 0:
        return "", ""
    return _field(out, "802-11-wireless.ssid"), _field(out, "802-11-wireless.mode")


def _sta_connection() -> str:
    for name in _connections():
        ssid, mode = _ssid_and_mode(name)
        if ssid == SSID_LIGHT_CONTROL and mode in {"", "infrastructure"}:
            _guard_light_control(name=name)
            return name
    raise RuntimeError("LIGHT-CONTROL station profile missing")


def _ap_exists() -> bool:
    return AP_CONNECTION_ID in _connections()


def _ensure_ap_profile(sta: str, iface: str) -> None:
    _guard_light_control(name=sta, iface=iface)
    _guard_light_control(name=AP_CONNECTION_ID)
    if not _ap_exists():
        _nmcli_ok(["connection", "clone", sta, AP_CONNECTION_ID])
    _nmcli_ok(
        [
            "connection",
            "modify",
            AP_CONNECTION_ID,
            "connection.interface-name",
            iface,
            "connection.autoconnect",
            "no",
            "802-11-wireless.mode",
            "ap",
            "802-11-wireless.ssid",
            SSID_LIGHT_CONTROL,
            "802-11-wireless.band",
            AP_BAND,
            "802-11-wireless.channel",
            AP_CHANNEL,
            "ipv4.method",
            "shared",
            "ipv4.addresses",
            AP_ADDRESS,
            "ipv4.shared-dhcp-range",
            DHCP_RANGE,
            "ipv6.method",
            "disabled",
        ]
    )


def _active_wifi_connections() -> list[str]:
    rc, out, _err = _nmcli(["-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"])
    if rc != 0:
        return []
    names: list[str] = []
    for raw in out.splitlines():
        parts = raw.split(":")
        if len(parts) < 2:
            continue
        if "wireless" in parts[1] or parts[1].startswith("802-11"):
            names.append(parts[0])
    return names


def _down(name: str) -> None:
    _guard_light_control(name=name)
    _nmcli(["connection", "down", name], timeout=15.0)


def _up(name: str) -> None:
    _guard_light_control(name=name)
    _nmcli_ok(["connection", "up", name], timeout=25.0)


def _wait_ipv4(iface: str, timeout: float = 20.0) -> None:
    _guard_light_control(iface=iface)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rc, out, _err = _nmcli(["-t", "-f", "IP4.ADDRESS", "device", "show", iface])
        if rc == 0 and "192.168.88." in out:
            return
        time.sleep(0.4)
    raise RuntimeError(f"{iface} did not get 192.168.88.x")


def _onboard_ifname() -> str:
    from pathlib import Path

    sysnet = Path("/sys/class/net")
    wifi: list[str] = []
    onboard: list[str] = []
    if sysnet.is_dir():
        try:
            names = sorted(p.name for p in sysnet.iterdir())
        except OSError:
            names = []
        for name in names:
            if name.startswith("p2p-dev-"):
                continue
            wireless = sysnet / name / "wireless"
            if not wireless.is_dir():
                continue
            wifi.append(name)
            try:
                dev = str((sysnet / name / "device").resolve())
            except OSError:
                onboard.append(name)
                continue
            if "/usb" in dev.lower():
                continue
            onboard.append(name)
    if onboard:
        _guard_light_control(iface=onboard[0])
        return onboard[0]
    if wifi:
        _guard_light_control(iface=wifi[0])
        return wifi[0]
    raise RuntimeError("no wifi device")


def _apply_standalone() -> None:
    if not dhcp_range_excludes_reserved():
        raise RuntimeError("dhcp range overlaps reserved addresses")
    sta = _sta_connection()
    _guard_light_control(name=sta)
    iface = _onboard_ifname()
    _guard_light_control(iface=iface)
    _ensure_ap_profile(sta, iface)
    _down(sta)
    _up(AP_CONNECTION_ID)
    _wait_ipv4(iface)


def _apply_network() -> None:
    sta = _sta_connection()
    _guard_light_control(name=sta)
    iface = _onboard_ifname()
    _guard_light_control(iface=iface)
    if _ap_exists():
        _down(AP_CONNECTION_ID)
    _up(sta)
    _wait_ipv4(iface)


def _protected_wifi_names() -> set[str]:
    """WIZ-LIGHTS must survive LIGHT-CONTROL NETWORK/STANDALONE rollback."""
    names = {WIZ_AP_CONNECTION_ID}
    for name in _connections():
        ssid, _mode = _ssid_and_mode(name)
        if is_wiz_lights_profile(name, ssid):
            names.add(name)
    return names


def _restore_wifi(snapshot: list[str]) -> None:
    active = _active_wifi_connections()
    downs, ups = restore_wifi_plan(snapshot, active, _protected_wifi_names())
    for name in downs:
        _down(name)
    for name in ups:
        _up(name)


def network_page_records(
    ifaces: tuple[NetIface, ...],
    *,
    network_mode: str = MODE_NETWORK,
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """(title, status, detail_lines) for OUTPUT -> NETWORK. Loopback omitted."""
    shown = tuple(iface for iface in ifaces if iface.kind != KIND_LOOPBACK)
    used: set[str] = set()
    rows: list[tuple[str, str, tuple[str, ...]]] = []
    lc = light_control_iface(ifaces)
    role = light_control_role(network_mode)
    if lc is not None:
        used.add(lc.name)
        detail = [SSID_LIGHT_CONTROL, role, lc.name]
        if lc.ipv4:
            detail.append(lc.ipv4)
        rows.append((SSID_LIGHT_CONTROL, role, tuple(detail)))
    wiz = wiz_lights_iface(ifaces)
    if wiz is not None:
        used.add(wiz.name)
        detail = [SSID_WIZ_LIGHTS, "AP", wiz.name]
        if wiz.ipv4:
            detail.append(wiz.ipv4)
        rows.append((SSID_WIZ_LIGHTS, "AP", tuple(detail)))
    for iface in shown:
        if iface.name in used:
            continue
        from light_console.output.network import network_list_status, oled_iface_lines

        rows.append((iface.name, network_list_status(iface), oled_iface_lines(iface)))
    return tuple(rows)
