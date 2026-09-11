"""Read-only network snapshot for OUTPUT diagnostics. Never changes NetworkManager."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

KIND_ONBOARD = "onboard"
KIND_USB = "usb"
KIND_WIFI = "wifi"
KIND_ETHERNET = "ethernet"
KIND_LOOPBACK = "loopback"

SKIP_PREFIXES = ("p2p-dev-", "docker", "veth", "br-", "virbr")
SYS_CLASS_NET = Path("/sys/class/net")


@dataclass(frozen=True)
class NetIface:
    name: str
    up: bool
    ipv4: str = ""
    ssid: str = ""
    prefix: int | None = None
    kind: str = ""
    driver: str = ""
    usb_id: str = ""
    manufacturer: str = ""
    product: str = ""
    mac: str = ""
    perm_mac: str = ""
    nm_state: str = ""
    nm_connection: str = ""
    managed: bool | None = None


@dataclass(frozen=True)
class NmDevice:
    name: str
    dev_type: str = ""
    state: str = ""
    connection: str = ""


def _parse_cidr(token: str) -> tuple[str, int | None]:
    if "/" in token:
        ip, _, raw_pfx = token.partition("/")
        try:
            return ip, int(raw_pfx)
        except ValueError:
            return ip, None
    return token, None


def parse_ip_br_rows(text: str) -> dict[str, tuple[bool, str, int | None]]:
    found: dict[str, tuple[bool, str, int | None]] = {}
    for raw in text.splitlines():
        parts = raw.split()
        if len(parts) < 2:
            continue
        name, flags = parts[0], parts[1]
        ipv4 = ""
        prefix: int | None = None
        for token in parts[2:]:
            if "." in token and "/" in token:
                ipv4, prefix = _parse_cidr(token)
                break
            if token.count(".") == 3 and ":" not in token:
                ipv4, prefix = _parse_cidr(token)
                break
        found[name] = ("UP" in flags.upper() or flags.upper() == "UNKNOWN", ipv4, prefix)
    return found


def parse_ip_br(text: str) -> dict[str, tuple[bool, str]]:
    return {name: (up, ipv4) for name, (up, ipv4, _) in parse_ip_br_rows(text).items()}


def parse_ip_br_link_mac(text: str) -> dict[str, str]:
    """Parse `ip -br link` MAC column (field 3)."""
    macs: dict[str, str] = {}
    for raw in text.splitlines():
        parts = raw.split()
        if len(parts) < 3:
            continue
        mac = parts[2].lower()
        if mac.count(":") == 5:
            macs[parts[0]] = mac
    return macs


def parse_ssid(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("ssid:"):
            return line.split(":", 1)[1].strip().strip('"')
        if "ssid" in line.lower() and ":" in line:
            return line.split(":", 1)[1].strip().strip('"')
        if line and " " not in line and "=" not in line:
            return line
    return ""


def parse_udev_properties(text: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for raw in text.splitlines():
        if "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        props[key.strip()] = value.strip()
    return props


def parse_nmcli_device_status(text: str) -> dict[str, NmDevice]:
    found: dict[str, NmDevice] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, dev_type, state = parts[0], parts[1], parts[2]
        connection = ":".join(parts[3:]) if len(parts) > 3 else ""
        found[name] = NmDevice(name, dev_type, state, connection)
    return found


def parse_nmcli_device_show(text: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        props[key.strip()] = value.strip()
    return props


def classify_kind(name: str, udev: Mapping[str, str], *, wireless: bool = False) -> str:
    n = name.strip()
    devtype = (udev.get("DEVTYPE") or "").lower()
    bus = (udev.get("ID_BUS") or "").lower()
    path = (udev.get("ID_PATH") or "").lower()
    nm_type = (udev.get("NM_TYPE") or "").lower()
    if n == "lo" or nm_type == "loopback":
        return KIND_LOOPBACK
    wifi = wireless or devtype == "wlan" or nm_type == "wifi" or n.startswith("wl")
    if wifi:
        if bus == "usb" or "/usb" in path or "usb-" in path:
            return KIND_USB
        if "mmcnr" in path or "sdio" in path or bus == "sdio":
            return KIND_ONBOARD
        return KIND_WIFI
    if n.startswith("eth") or nm_type == "ethernet":
        return KIND_ETHERNET
    return nm_type or ""


def usb_id_from_udev(udev: Mapping[str, str]) -> str:
    vendor = (udev.get("ID_USB_VENDOR_ID") or udev.get("ID_VENDOR_ID") or "").lower()
    product = (udev.get("ID_USB_MODEL_ID") or udev.get("ID_MODEL_ID") or "").lower()
    if vendor and product:
        return f"{vendor}:{product}"
    return ""


def _cmd(argv: list[str]) -> str:
    if shutil.which(argv[0]) is None:
        return ""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=2.0)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout or ""


def _read_sys(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _live_sys_names() -> tuple[str, ...]:
    if not SYS_CLASS_NET.is_dir():
        return ()
    try:
        return tuple(sorted(p.name for p in SYS_CLASS_NET.iterdir()))
    except OSError:
        return ()


def _sys_net_props(name: str) -> dict[str, str]:
    """Classify from sysfs so live snapshots do not exec udevadm/iw on USB."""
    props: dict[str, str] = {}
    if _live_wireless(name) or name.startswith("wl"):
        props["DEVTYPE"] = "wlan"
    try:
        path = str((SYS_CLASS_NET / name / "device").resolve()).lower()
    except OSError:
        path = ""
    if path:
        props["ID_PATH"] = path
        if "usb" in path:
            props["ID_BUS"] = "usb"
        elif "mmcnr" in path or "sdio" in path:
            props["ID_BUS"] = "sdio"
    return props


def _skip_name(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in SKIP_PREFIXES)


def _live_wireless(name: str) -> bool:
    return (SYS_CLASS_NET / name / "wireless").is_dir()


def _live_driver(name: str, udev: Mapping[str, str]) -> str:
    driver = udev.get("ID_NET_DRIVER") or udev.get("ID_USB_DRIVER") or ""
    if driver:
        return driver
    link = SYS_CLASS_NET / name / "device" / "driver"
    try:
        return Path(link.resolve()).name
    except OSError:
        return ""


def _live_mac(name: str) -> str:
    return _read_sys(SYS_CLASS_NET / name / "address").lower()


def _live_usb_parent(name: str) -> tuple[str, str, str, str]:
    """vendor, product, manufacturer, product-string from USB parent device."""
    dev = SYS_CLASS_NET / name / "device"
    try:
        current = dev.resolve()
    except OSError:
        return "", "", "", ""
    for _ in range(6):
        vendor = _read_sys(current / "idVendor").lower()
        product = _read_sys(current / "idProduct").lower()
        if vendor and product:
            return (
                vendor,
                product,
                _read_sys(current / "manufacturer"),
                _read_sys(current / "product"),
            )
        if current.parent == current:
            break
        current = current.parent
    return "", "", "", ""


def _ssid_from_nm_connection(connection: str) -> str:
    if not connection:
        return ""
    text = _cmd(["nmcli", "-t", "-f", "802-11-wireless.ssid", "connection", "show", connection])
    for raw in text.splitlines():
        if ":" in raw:
            _, _, value = raw.partition(":")
            return value.strip().strip('"')
        if raw.strip() and "802-11-wireless.ssid" not in raw.lower():
            return raw.strip().strip('"')
    return ""


def _sort_key(iface: NetIface) -> tuple[int, str]:
    rank = {
        KIND_ONBOARD: 0,
        KIND_USB: 1,
        KIND_WIFI: 2,
        KIND_ETHERNET: 3,
        KIND_LOOPBACK: 4,
    }
    return (rank.get(iface.kind, 9), iface.name)


def network_list_status(iface: NetIface) -> str:
    """List-row status word. SSID and IP belong in detail, not the status slot."""
    from light_console.ui.vocab import OK

    if iface.ipv4:
        return OK
    lines = oled_iface_lines(iface)
    reserved = {
        "DISCONNECTED",
        "UNMANAGED",
        "UNAVAILABLE",
        "LOOPBACK",
        "DOWN",
        "UP",
        OK,
        "OFFLINE",
    }
    for line in lines[1:]:
        if line in reserved:
            return line
    return lines[1] if len(lines) > 1 else ""


def oled_iface_lines(iface: NetIface) -> tuple[str, ...]:
    lines = [iface.name]
    nm = (iface.nm_state or "").lower()
    wifiish = iface.kind in {KIND_ONBOARD, KIND_USB, KIND_WIFI} or iface.name.startswith("wl")
    if iface.ssid:
        lines.append(iface.ssid)
        if iface.ipv4:
            lines.append(iface.ipv4)
        elif iface.driver:
            lines.append(iface.driver)
        return tuple(lines)
    if iface.managed is False or "unmanaged" in nm:
        lines.append("UNMANAGED")
    elif "unavailable" in nm:
        lines.append("UNAVAILABLE")
    elif iface.kind == KIND_LOOPBACK:
        lines.append("LOOPBACK")
    elif "disconnect" in nm or (wifiish and not iface.ipv4):
        lines.append("DISCONNECTED")
    elif not iface.up:
        lines.append("DOWN")
    elif iface.ipv4:
        lines.append(iface.ipv4)
    else:
        lines.append("UP")
    if iface.ipv4 and lines[-1] != iface.ipv4:
        lines.append(iface.ipv4)
    elif iface.driver and lines[-1] != iface.driver:
        lines.append(iface.driver)
    return tuple(lines)


def collect_network(
    *,
    ip_text: str | None = None,
    ssid_for: Callable[[str], str] | None = None,
    sys_names: tuple[str, ...] | None = None,
    udev_for: Callable[[str], Mapping[str, str]] | dict[str, Mapping[str, str]] | None = None,
    nm_status_text: str | None = None,
    wireless_for: Callable[[str], bool] | None = None,
    driver_for: Callable[[str], str] | None = None,
    mac_for: Callable[[str], str] | None = None,
    usb_for: Callable[[str], tuple[str, str, str, str]] | None = None,
    link_text: str | None = None,
) -> tuple[NetIface, ...]:
    parsed = parse_ip_br_rows(ip_text if ip_text is not None else _cmd(["ip", "-br", "addr"]))
    link_macs = parse_ip_br_link_mac(link_text if link_text is not None else "")
    if sys_names is not None:
        names = sys_names
    elif ip_text is not None:
        names = tuple(parsed)
    else:
        names = _live_sys_names() or tuple(parsed)
    nm_map = parse_nmcli_device_status(
        nm_status_text if nm_status_text is not None else _cmd(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"]
        )
    )

    def udev_props(name: str) -> Mapping[str, str]:
        if udev_for is None:
            return _sys_net_props(name) if ip_text is None else {}
        if callable(udev_for):
            return udev_for(name)
        return udev_for.get(name, {})

    links: list[NetIface] = []
    for name in names:
        if _skip_name(name):
            continue
        udev = dict(udev_props(name))
        nm = nm_map.get(name)
        if nm and not udev.get("NM_TYPE"):
            udev["NM_TYPE"] = nm.dev_type
        wireless = False
        if wireless_for is not None:
            wireless = wireless_for(name)
        elif ip_text is None:
            wireless = _live_wireless(name)
        else:
            wireless = (udev.get("DEVTYPE") == "wlan") or name.startswith("wl")
        kind = classify_kind(name, udev, wireless=wireless)
        up, ipv4, prefix = parsed.get(name, (False, "", None))
        if nm and "unavailable" in nm.state.lower():
            up = False
        driver = ""
        if driver_for is not None:
            driver = driver_for(name)
        elif ip_text is None:
            driver = _live_driver(name, udev)
        else:
            driver = udev.get("ID_NET_DRIVER") or udev.get("ID_USB_DRIVER") or ""
        mac = ""
        if mac_for is not None:
            mac = mac_for(name)
        elif ip_text is None:
            mac = _live_mac(name)
        else:
            mac = link_macs.get(name, "") or (udev.get("GENERAL.HWADDR") or "").lower()
        usb_id = usb_id_from_udev(udev)
        manufacturer = udev.get("ID_USB_VENDOR") or udev.get("ID_VENDOR") or ""
        product = (udev.get("ID_USB_MODEL") or udev.get("ID_MODEL") or "").replace("_", " ")
        if usb_for is not None:
            vendor, prod_id, manufacturer_s, product_s = usb_for(name)
            if vendor and prod_id:
                usb_id = usb_id or f"{vendor}:{prod_id}"
            manufacturer = manufacturer_s or manufacturer
            product = product_s or product
        elif ip_text is None and kind == KIND_USB and not usb_id:
            vendor, prod_id, manufacturer_s, product_s = _live_usb_parent(name)
            if vendor and prod_id:
                usb_id = f"{vendor}:{prod_id}"
            manufacturer = manufacturer_s or manufacturer
            product = product_s or product
        ssid = ""
        if name.startswith("wl") or kind in {KIND_ONBOARD, KIND_USB, KIND_WIFI}:
            if ssid_for is not None:
                ssid = ssid_for(name)
            elif ip_text is None:
                ssid = ""
                if nm and nm.connection:
                    ssid = _ssid_from_nm_connection(nm.connection)
        managed: bool | None = None
        nm_state = nm.state if nm else ""
        if nm:
            if "unmanaged" in nm.state.lower():
                managed = False
            elif nm.state:
                managed = True
        perm_mac = mac
        links.append(
            NetIface(
                name=name,
                up=up,
                ipv4=ipv4,
                ssid=ssid,
                prefix=prefix,
                kind=kind,
                driver=driver,
                usb_id=usb_id,
                manufacturer=manufacturer,
                product=product,
                mac=mac,
                perm_mac=perm_mac,
                nm_state=nm_state,
                nm_connection=nm.connection if nm else "",
                managed=managed,
            )
        )
    links.sort(key=_sort_key)
    return tuple(links)
