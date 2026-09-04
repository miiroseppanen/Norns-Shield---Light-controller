"""Read-only network snapshot for OUTPUT diagnostics. Never changes NetworkManager."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

WATCH = ("wlan0", "wlan1")
OPTIONAL = ("eth0",)


@dataclass(frozen=True)
class NetIface:
    name: str
    up: bool
    ipv4: str = ""
    ssid: str = ""


def parse_ip_br(text: str) -> dict[str, tuple[bool, str]]:
    found: dict[str, tuple[bool, str]] = {}
    for raw in text.splitlines():
        parts = raw.split()
        if len(parts) < 2:
            continue
        name, flags = parts[0], parts[1]
        ipv4 = ""
        for token in parts[2:]:
            if "." in token and "/" in token:
                ipv4 = token.split("/", 1)[0]
                break
            if token.count(".") == 3 and ":" not in token:
                ipv4 = token
                break
        found[name] = ("UP" in flags.upper(), ipv4)
    return found


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


def _cmd(argv: list[str]) -> str:
    if shutil.which(argv[0]) is None:
        return ""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=2.0)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout or ""


def collect_network(
    *,
    ip_text: str | None = None,
    ssid_for: Callable[[str], str] | None = None,
) -> tuple[NetIface, ...]:
    parsed = parse_ip_br(ip_text if ip_text is not None else _cmd(["ip", "-br", "addr"]))
    links: list[NetIface] = []
    names = list(WATCH)
    for extra in OPTIONAL:
        if extra in parsed and extra not in names:
            names.append(extra)
    for name in names:
        up, ipv4 = parsed.get(name, (False, ""))
        ssid = ""
        if name.startswith("wl"):
            if ssid_for is not None:
                ssid = ssid_for(name)
            else:
                ssid = parse_ssid(_cmd(["iwgetid", name, "--raw"])) or parse_ssid(
                    _cmd(["iw", "dev", name, "info"])
                )
        links.append(NetIface(name=name, up=up, ipv4=ipv4, ssid=ssid))
    return tuple(links)
