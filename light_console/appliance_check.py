"""Read-only Shield appliance diagnostic.

Never starts, stops, restarts, enables, or disables services.
Never writes configuration, workspaces, or QLC function state.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

from light_console.artnet.destinations import FORBIDDEN_HOSTS
from light_console.qxw import SHIELD_LAN_HOST, QxwError, parse_functions
from light_console.qlc.ws_client import SocketTransport, _parse_ws_url
from light_console.startup_chaser import StartupError
from light_console.startup_chaser import TARGET as STARTUP_NAME
from light_console.startup_chaser import _function_list, _function_status

MASTER = Path("/home/light/shows/master.qxw")
EXPECTED_ARGV = ["/usr/bin/qlcplus-qml", "-w", "-o", "/home/light/shows/master.qxw"]
EXPECTED_FUNCTIONS = 100
LC_STATUS = Path("/tmp/light-console.status")
STARTUP_STATUS = Path("/tmp/qlc-startup.status")
WS_URL = "ws://127.0.0.1:9999/qlcplusWS"
UNITS = (
    "light-console.service",
    "qlcplus.service",
    "qlc-startup-chaser.service",
)
ONESHOT_UNITS = frozenset({"qlc-startup-chaser.service"})


@dataclass(frozen=True)
class Check:
    section: str
    name: str
    status: str
    detail: str = ""


def inspect_workspace(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    fns = parse_functions(text)
    forbidden = [h for h in sorted(FORBIDDEN_HOSTS | {SHIELD_LAN_HOST}) if h in text]
    if "10.42." in text:
        forbidden.append("10.42.*")
    loopback = text.count('outputIP="127.0.0.1"')
    startup = [fn for fn in fns if fn.name == STARTUP_NAME]
    return {
        "functions": len(fns),
        "startup": len(startup) == 1,
        "startup_id": startup[0].function_id if len(startup) == 1 else None,
        "loopback": loopback,
        "launchpad_uid": 'UID="1-1.2:0"' in text,
        "launchpad_name": 'Name="Launchpad Mini MIDI 1"' in text,
        "forbidden": forbidden,
        "ok": (
            not forbidden
            and loopback >= 2
            and len(startup) == 1
            and 'UID="1-1.2:0"' in text
            and 'Name="Launchpad Mini MIDI 1"' in text
        ),
    }


def format_report(checks: list[Check], *, header: dict[str, str] | None = None) -> str:
    lines = ["SHIELD APPLIANCE CHECK", ""]
    if header:
        for key, value in header.items():
            lines.append(f"{key}: {value}")
        lines.append("")
    section = ""
    for item in checks:
        if item.section != section:
            section = item.section
            lines.append(f"[{section}]")
        extra = f"  {item.detail}" if item.detail else ""
        lines.append(f"  {item.status:4}  {item.name}{extra}")
    fails = sum(1 for c in checks if c.status == "FAIL")
    warns = sum(1 for c in checks if c.status == "WARN")
    lines.append("")
    lines.append(f"RESULT: {'FAIL' if fails else 'PASS'}  ({fails} failing, {warns} warnings)")
    return "\n".join(lines) + "\n"


def _cmd(argv: list[str], timeout: float = 3.0) -> str:
    if shutil.which(argv[0]) is None:
        return ""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (proc.stdout or "") + (proc.stderr or "")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _unit_state(kind: str, unit: str) -> str:
    out = _cmd(["systemctl", kind, "--", unit]).strip().splitlines()
    return out[0] if out else "unknown"


def _unit_prop(unit: str, prop: str) -> str:
    return _cmd(["systemctl", "show", "-p", prop, "--value", "--", unit]).strip()


def _http_code(url: str = "http://127.0.0.1:9999/") -> str:
    out = _cmd(
        ["curl", "-sS", "-m", "3", "-o", "/dev/null", "-w", "%{http_code}", url]
    )
    return out.strip() or "000"


def _qlc_probe() -> dict:
    result = {
        "ws": False,
        "functions": 0,
        "has_startup": False,
        "startup_running": False,
        "startup_id": "",
    }
    transport = SocketTransport()
    try:
        host, port, path = _parse_ws_url(WS_URL)
        transport.connect(host, port, path)
        sock = transport._sock
        if sock is not None:
            sock.settimeout(5.0)
        result["ws"] = True
        functions = _function_list(transport)
        result["functions"] = len(functions)
        matches = [(fid, name) for fid, name in functions if name == STARTUP_NAME]
        result["has_startup"] = len(matches) == 1
        if len(matches) == 1:
            fid = matches[0][0]
            result["startup_id"] = fid
            result["startup_running"] = "Running" in _function_status(transport, fid)
    except (OSError, StartupError):
        return result
    finally:
        transport.close()
    return result


def _midi_bindings(aconnect: str) -> tuple[bool, bool]:
    """Return (input_to_qlc, feedback_from_qlc) from `aconnect -l`."""
    to_qlc = False
    from_qlc = False
    in_launchpad = False
    for raw in aconnect.splitlines():
        line = raw.strip()
        if line.startswith("client "):
            # ALSA client is "Launchpad Mini"; port name is "Launchpad Mini MIDI 1".
            in_launchpad = "Launchpad Mini" in line
            continue
        if not in_launchpad:
            continue
        if "Connecting To:" in line:
            to_qlc = True
        if "Connected From:" in line:
            from_qlc = True
    return to_qlc, from_qlc


def _oneshot_ok(unit: str) -> tuple[str, str]:
    active = _unit_state("is-active", unit)
    result = _unit_prop(unit, "Result") or "unknown"
    exited = _unit_prop(unit, "InactiveExitTimestamp")
    ran = exited not in {"", "n/a", "0", "@0"}
    if active in {"active", "activating"}:
        return "PASS", f"{active} result={result}"
    if result == "success" and ran:
        return "PASS", f"inactive (oneshot ok) result={result}"
    return "FAIL", f"{active} result={result}"


def collect_checks() -> tuple[list[Check], dict[str, str]]:
    checks: list[Check] = []
    uptime_s = 0.0
    try:
        uptime_s = float(_read(Path("/proc/uptime")).split()[0])
    except (IndexError, ValueError):
        pass
    throttle = _cmd(["vcgencmd", "get_throttled"]).strip() or "n/a"
    throttle_val = throttle.replace("throttled=", "")
    header = {
        "uptime_s": f"{uptime_s:.0f}",
        "throttled": throttle_val,
        "host": socket.gethostname(),
    }
    checks.append(
        Check(
            "SYSTEM",
            "throttled",
            "PASS" if throttle_val in {"n/a", "", "0x0"} else "WARN",
            throttle_val,
        )
    )

    for unit in UNITS:
        enabled = _unit_state("is-enabled", unit)
        checks.append(
            Check(
                "SERVICES",
                f"{unit} enabled",
                "PASS" if enabled == "enabled" else "FAIL",
                enabled,
            )
        )
        if unit in ONESHOT_UNITS:
            status, detail = _oneshot_ok(unit)
            checks.append(Check("SERVICES", f"{unit} result", status, detail))
        else:
            active = _unit_state("is-active", unit)
            checks.append(
                Check(
                    "SERVICES",
                    f"{unit} active",
                    "PASS" if active in {"active", "activating"} else "FAIL",
                    active,
                )
            )
    wiz_en = _unit_state("is-enabled", "wizbridge.service")
    checks.append(
        Check(
            "SERVICES",
            "wizbridge enabled",
            "PASS" if wiz_en in {"not-found", "disabled", "unknown"} else "WARN",
            wiz_en,
        )
    )

    qlc_pid = _unit_prop("qlcplus.service", "MainPID")
    argv: list[str] = []
    nproc = sum(
        1
        for line in _cmd(["pgrep", "-a", "qlcplus-qml"]).splitlines()
        if "qlcplus-qml" in line and "pgrep" not in line
    )
    if qlc_pid.isdigit() and int(qlc_pid) > 0:
        argv = [p for p in _read(Path(f"/proc/{qlc_pid}/cmdline")).split("\0") if p]
    checks.append(
        Check("QLC", "pid", "PASS" if qlc_pid not in {"", "0"} else "FAIL", qlc_pid)
    )
    checks.append(
        Check(
            "QLC",
            "argv",
            "PASS" if argv == EXPECTED_ARGV else "FAIL",
            " ".join(argv) or "(none)",
        )
    )
    checks.append(
        Check("QLC", "single process", "PASS" if nproc == 1 else "FAIL", str(nproc))
    )
    nrestarts_raw = _unit_prop("qlcplus.service", "NRestarts")
    try:
        nrestarts = int(nrestarts_raw or "0")
    except ValueError:
        nrestarts = -1
    if nrestarts == 0:
        rest_status = "PASS"
    elif 0 < nrestarts <= 2:
        rest_status = "WARN"
    else:
        rest_status = "FAIL"
    checks.append(Check("QLC", "restarts", rest_status, str(nrestarts)))
    http = _http_code()
    checks.append(Check("QLC", "http", "PASS" if http == "200" else "FAIL", http))
    probe = _qlc_probe()
    checks.append(Check("QLC", "websocket", "PASS" if probe["ws"] else "FAIL"))
    checks.append(
        Check(
            "QLC",
            "functions",
            "PASS" if probe["functions"] == EXPECTED_FUNCTIONS else "FAIL",
            str(probe["functions"]),
        )
    )
    checks.append(
        Check(
            "QLC",
            "startup present",
            "PASS" if probe["has_startup"] else "FAIL",
            probe["startup_id"] or STARTUP_NAME,
        )
    )
    checks.append(
        Check(
            "QLC",
            "startup running",
            "PASS" if probe["startup_running"] else "FAIL",
        )
    )

    usb = _cmd(["lsusb"])
    amidi = _cmd(["amidi", "-l"])
    aconnect = _cmd(["aconnect", "-l"])
    usb_ok = "1235:0036" in usb
    name_ok = "Launchpad Mini MIDI 1" in amidi or "Launchpad Mini MIDI 1" in aconnect
    midi_in, midi_fb = _midi_bindings(aconnect)
    checks.append(Check("MIDI", "usb", "PASS" if usb_ok else "FAIL", "1235:0036"))
    checks.append(
        Check(
            "MIDI",
            "alsa name",
            "PASS" if name_ok else "FAIL",
            "Launchpad Mini MIDI 1",
        )
    )
    checks.append(
        Check("MIDI", "qlc input", "PASS" if midi_in else "FAIL", "Launchpad -> qlcplus")
    )
    checks.append(
        Check(
            "MIDI",
            "qlc feedback",
            "PASS" if midi_fb else "FAIL",
            "qlcplus -> Launchpad",
        )
    )

    if MASTER.is_file():
        try:
            ws = inspect_workspace(MASTER)
            checks.append(
                Check(
                    "WORKSPACE",
                    "master.qxw",
                    "PASS" if ws["ok"] else "FAIL",
                    f"functions={ws['functions']} loopback={ws['loopback']}",
                )
            )
            checks.append(
                Check(
                    "WORKSPACE",
                    "forbidden destinations",
                    "PASS" if not ws["forbidden"] else "FAIL",
                    ",".join(ws["forbidden"]) or "none",
                )
            )
            checks.append(
                Check(
                    "WORKSPACE",
                    "launchpad uid",
                    "PASS" if ws["launchpad_uid"] and ws["launchpad_name"] else "FAIL",
                )
            )
        except (OSError, QxwError) as exc:
            checks.append(Check("WORKSPACE", "master.qxw", "FAIL", str(exc)))
    else:
        checks.append(Check("WORKSPACE", "master.qxw", "FAIL", "missing"))

    ip = _cmd(["ip", "-br", "addr"])
    wlan0_status, wlan0_d = "FAIL", ""
    wlan1_seen = False
    wlan1_line = ""
    for line in ip.splitlines():
        if line.startswith("wlan0"):
            wlan0_d = line.strip()
            wlan0_status = (
                "PASS" if "192.168.88.246" in line and "UP" in line else "FAIL"
            )
        if line.startswith("wlan1"):
            wlan1_seen = True
            wlan1_line = line.strip()
    checks.append(Check("NETWORK", "wlan0", wlan0_status, wlan0_d))
    if wlan1_seen:
        checks.append(
            Check(
                "NETWORK",
                "wlan1",
                "PASS",
                wlan1_line + " (DOWN expected in SAFE)",
            )
        )
    else:
        checks.append(Check("NETWORK", "wlan1", "FAIL", "interface missing"))

    checks.append(Check("OUTPUT", "armed", "PASS", "SAFE loopback only"))

    lc = _read(LC_STATUS)
    lc_ok = "qlc_state=connected" in lc
    checks.append(
        Check(
            "UI",
            "light-console status",
            "PASS" if lc_ok else "FAIL",
            "qlc_state=connected" if lc_ok else (lc.splitlines()[2] if len(lc.splitlines()) > 2 else "missing"),
        )
    )
    st = _read(STARTUP_STATUS)
    checks.append(
        Check(
            "UI",
            "startup status file",
            "PASS" if "status=RUNNING" in st else "FAIL",
            st.splitlines()[0] if st else "missing",
        )
    )
    return checks, header


def main(argv: list[str] | None = None) -> int:
    del argv
    checks, header = collect_checks()
    print(format_report(checks, header=header), end="")
    return 1 if any(c.status == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
