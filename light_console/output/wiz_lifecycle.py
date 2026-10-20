"""WIZ CONTROL owns WIZ-LIGHTS AP + wizbridge. No generic sudo. No UI I/O.

Desired state is the operator preference (prefs / OLED toggle).
Actual AP/bridge/TX are observed separately. Status `wiz=` is TX-armed only.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from light_console.output.wiz_ap import (
    LIGHT_CONTROL_IFACE,
    WIZ_AP_ADDRESS,
    WIZ_AP_CONNECTION_ID,
    WIZ_AP_IFACE,
    WIZ_AP_IPV4,
    WIZ_AP_PREFIX,
)
from light_console.ui.vocab import DOWN, FAILED, READY, STARTING, STOPPED

LOG = logging.getLogger("light-console")

HELPER_PATH = "/usr/sbin/light-console-wiz"
SUDO = "/usr/bin/sudo"
HELPER_ACTIONS = ("ap-up", "ap-down", "bridge-start", "bridge-stop")
ISOLATION_UNIT = "shieldxl-wiz-isolation.service"
BRIDGE_UNIT = "wizbridge.service"
STATUS_PATH = Path("/tmp/light-console.status")
READY_TIMEOUT_S = 25.0
WLAN1_READY_TIMEOUT_S = 30.0
AP_UP_ATTEMPTS = 5
POLL_S = 0.4

OLED_AP_STARTING = "AP STARTING"
OLED_READY = "READY"
OLED_NO_DEVICES = "NO DEVICES"
OLED_AP_FAILED = "AP FAILED"
OLED_BRIDGE_FAILED = "BRIDGE FAILED"


class WizHelperError(ValueError):
    """Invalid helper argv or hardcoded target."""


@dataclass(frozen=True)
class WizInspect:
    wlan1_exists: bool = False
    connection: str = ""
    connected: bool = False
    mode: str = ""
    ipv4: str = ""
    prefix: int = 0
    wlan1_default_route: bool = False
    isolation_active: bool = False
    bridge_active: bool = False
    bridge_failed: bool = False
    wlan0_touched: bool = False
    nm_device_seen: bool = False

    @property
    def radio_ready(self) -> bool:
        """wlan1 exists and NetworkManager is answering for it. Not AP-up."""
        return self.wlan1_exists and self.nm_device_seen

    @property
    def ap_ready(self) -> bool:
        return (
            self.wlan1_exists
            and self.connection == WIZ_AP_CONNECTION_ID
            and self.connected
            and self.mode == "ap"
            and self.ipv4 == WIZ_AP_IPV4
            and self.prefix == WIZ_AP_PREFIX
            and not self.wlan1_default_route
            and self.isolation_active
        )


@dataclass
class WizLifecycleSnapshot:
    desired: bool = False
    busy: bool = False
    ap: str = DOWN
    bridge: str = STOPPED
    tx_armed: bool = False
    fail_reason: str = ""
    commands: list[str] = field(default_factory=list)


def helper_argv(action: str) -> tuple[str, ...]:
    """Exact sudo argv. Connection/iface/unit names are not caller-supplied."""
    if action not in HELPER_ACTIONS:
        raise WizHelperError(f"unsupported wiz helper action {action!r}")
    return (SUDO, "-n", HELPER_PATH, action)


def validate_helper_argv(argv: list[str] | tuple[str, ...]) -> str:
    """Root helper: exactly one hardcoded action. No extra args, no names."""
    args = [str(part) for part in argv]
    if len(args) != 2 or args[1] not in HELPER_ACTIONS:
        raise WizHelperError("usage: light-console-wiz ap-up|ap-down|bridge-start|bridge-stop")
    return args[1]


def patch_status_wiz(path: Path, armed: bool) -> None:
    """Write the TX gate immediately. Missing file is created with wiz= only."""
    line = f"wiz={'on' if armed else 'off'}"
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        text = ""
    out: list[str] = []
    found = False
    for raw in text.splitlines():
        if raw.startswith("wiz="):
            out.append(line)
            found = True
        else:
            out.append(raw)
    if not found:
        out.append(line)
    try:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError:
        LOG.debug("wiz status patch failed", exc_info=True)


def parse_ip_addr_ipv4(text: str) -> tuple[str, int]:
    """Parse `ip -4 -o addr show` for the first inet address."""
    for raw in (text or "").splitlines():
        parts = raw.split()
        if "inet" not in parts:
            continue
        idx = parts.index("inet")
        if idx + 1 >= len(parts):
            continue
        token = parts[idx + 1]
        ip, _, prefix_s = token.partition("/")
        if ip == WIZ_AP_IPV4:
            try:
                prefix = int(prefix_s) if prefix_s else 0
            except ValueError:
                prefix = 0
            return ip, prefix
        if not prefix_s:
            continue
        try:
            return ip, int(prefix_s)
        except ValueError:
            continue
    return "", 0


def default_route_uses_iface(text: str, iface: str) -> bool:
    needle = (iface or "").strip()
    if not needle:
        return False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line.startswith("default"):
            continue
        parts = line.split()
        if "dev" not in parts:
            continue
        idx = parts.index("dev")
        if idx + 1 < len(parts) and parts[idx + 1] == needle:
            return True
    return False


def parse_nmcli_device_fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in (text or "").splitlines():
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        if key:
            out[key] = value.strip()
    return out


def parse_connection_name(fields: dict[str, str]) -> str:
    return (fields.get("GENERAL.CONNECTION") or "").strip()


def parse_device_connected(fields: dict[str, str]) -> bool:
    state = (fields.get("GENERAL.STATE") or "").strip().lower()
    return state.startswith("100") or "connected" in state


def parse_nm_device_ready(fields: dict[str, str]) -> bool:
    """True when NM is managing the iface. Disconnected is ready; unmanaged is not."""
    state = (fields.get("GENERAL.STATE") or "").strip()
    if not state:
        return False
    lowered = state.lower()
    if "unmanaged" in lowered or "unavailable" in lowered:
        return False
    code = state.split(None, 1)[0]
    if code.isdigit():
        return int(code) >= 30
    return True


def parse_wifi_mode(text: str) -> str:
    for raw in (text or "").splitlines():
        line = raw.strip().lower()
        if line.startswith("802-11-wireless.mode:"):
            return line.split(":", 1)[1].strip()
        if line.startswith("type ") or line.startswith("type:"):
            value = line.split(None, 1)[-1].replace(":", " ").split()[-1]
            if value == "ap":
                return "ap"
        if "type ap" in line:
            return "ap"
    fields = parse_nmcli_device_fields(text)
    mode = (fields.get("802-11-wireless.mode") or "").strip().lower()
    return mode


def isolation_is_active(text: str) -> bool:
    return (text or "").strip().lower() == "active"


def map_bridge_unit(active: str) -> str:
    word = (active or "").strip().lower()
    if word == "active":
        return READY
    if word in {"activating", "reloading"}:
        return STARTING
    if word == "failed":
        return FAILED
    return STOPPED


def oled_wiz_detail(
    *,
    desired: bool,
    ap: str,
    bridge: str,
    busy: bool,
    online: int,
) -> str | None:
    if not desired:
        return None
    if ap == FAILED:
        return OLED_AP_FAILED
    if bridge == FAILED:
        return OLED_BRIDGE_FAILED
    if ap == READY and bridge == READY:
        if online <= 0:
            return OLED_NO_DEVICES
        return OLED_READY
    if ap == STARTING or (ap == DOWN and busy) or bridge == STARTING:
        return OLED_AP_STARTING
    if ap == READY:
        return OLED_AP_STARTING
    return OLED_AP_STARTING


class WizLifecycleService(ABC):
    desired: bool
    busy: bool

    @abstractmethod
    def set_desired(self, on: bool) -> bool:
        ...

    @abstractmethod
    def snapshot(self) -> WizLifecycleSnapshot:
        ...


class MockWizLifecycleService(WizLifecycleService):
    """Tests / simulator: no nmcli, no systemd, no WiZ UDP."""

    def __init__(
        self,
        desired: bool = False,
        *,
        auto_settle: bool = True,
    ) -> None:
        self.desired = desired
        self.busy = False
        self.ap = READY if desired else DOWN
        self.bridge = READY if desired else STOPPED
        self.tx_armed = bool(desired)
        self.fail_reason = ""
        self.commands: list[str] = []
        self.wlan0_ops: list[str] = []
        self.auto_settle = auto_settle
        self.fail_ap = False
        self.fail_isolation = False
        self.fail_bridge = False
        self.apply_count = 0

    def set_desired(self, on: bool) -> bool:
        if self.busy:
            return False
        if on == self.desired and not self._failed():
            return True
        self.desired = on
        self.busy = True
        self.fail_reason = ""
        self.apply_count += 1
        if on:
            self._begin_on()
        else:
            self._begin_off()
        if self.auto_settle:
            self.settle()
        return True

    def _failed(self) -> bool:
        return self.ap == FAILED or self.bridge == FAILED

    def _begin_on(self) -> None:
        self.tx_armed = False
        self.bridge = STOPPED
        self.ap = STARTING
        self.commands.append("disarm-tx")
        self.commands.append("ap-up")

    def _begin_off(self) -> None:
        self.tx_armed = False
        self.commands.append("disarm-tx")
        self.commands.append("bridge-stop")
        self.bridge = STOPPED
        self.commands.append("ap-down")
        self.ap = DOWN

    def settle(self) -> WizLifecycleSnapshot:
        if self.desired:
            if self.fail_ap:
                self.ap = FAILED
                self.bridge = STOPPED
                self.tx_armed = False
                self.fail_reason = "ap"
                self.busy = False
                return self.snapshot()
            self.ap = READY
            if self.fail_isolation:
                self.ap = FAILED
                self.bridge = STOPPED
                self.tx_armed = False
                self.fail_reason = "isolation"
                self.busy = False
                return self.snapshot()
            self.tx_armed = True
            self.commands.append("arm-tx")
            self.commands.append("bridge-start")
            if self.fail_bridge:
                self.bridge = FAILED
                self.fail_reason = "bridge"
                self.busy = False
                return self.snapshot()
            self.bridge = READY
        else:
            self.tx_armed = False
            self.bridge = STOPPED
            self.ap = DOWN
        self.busy = False
        return self.snapshot()

    def snapshot(self) -> WizLifecycleSnapshot:
        return WizLifecycleSnapshot(
            desired=self.desired,
            busy=self.busy,
            ap=self.ap,
            bridge=self.bridge,
            tx_armed=self.tx_armed,
            fail_reason=self.fail_reason,
            commands=list(self.commands),
        )


class LinuxWizLifecycleService(WizLifecycleService):
    """Worker-thread lifecycle. poll/snapshot never call nmcli/systemctl."""

    apply_persisted = True

    def __init__(
        self,
        desired: bool = False,
        *,
        status_path: Path | None = None,
        run_helper: object | None = None,
        inspect: object | None = None,
        ready_timeout_s: float = READY_TIMEOUT_S,
        wlan1_ready_timeout_s: float = WLAN1_READY_TIMEOUT_S,
        ap_up_attempts: int = AP_UP_ATTEMPTS,
        poll_s: float = POLL_S,
        sleep: object | None = None,
    ) -> None:
        self.desired = desired
        self.busy = False
        self.ap = DOWN
        self.bridge = STOPPED
        self.tx_armed = False
        self.fail_reason = ""
        self.commands: list[str] = []
        self.status_path = status_path or STATUS_PATH
        self.ready_timeout_s = ready_timeout_s
        self.wlan1_ready_timeout_s = wlan1_ready_timeout_s
        self.ap_up_attempts = max(1, int(ap_up_attempts))
        self.poll_s = poll_s
        self._run_helper = run_helper or _sudo_helper
        self._inspect = inspect or inspect_wiz_runtime
        self._sleep = sleep or time.sleep
        self._lock = threading.Lock()
        self._gen = 0

    def set_desired(self, on: bool) -> bool:
        with self._lock:
            if self.busy:
                return False
            self.desired = on
            self.busy = True
            self.fail_reason = ""
            self._gen += 1
            gen = self._gen
            if on:
                self.ap = STARTING
                self.bridge = STOPPED
                self.tx_armed = False
            else:
                self.tx_armed = False
        worker = threading.Thread(
            target=self._run, args=(on, gen), daemon=True, name="wiz-lifecycle"
        )
        worker.start()
        return True

    def snapshot(self) -> WizLifecycleSnapshot:
        with self._lock:
            return WizLifecycleSnapshot(
                desired=self.desired,
                busy=self.busy,
                ap=self.ap,
                bridge=self.bridge,
                tx_armed=self.tx_armed,
                fail_reason=self.fail_reason,
                commands=list(self.commands),
            )

    def _record(self, command: str) -> None:
        with self._lock:
            self.commands.append(command)

    def _arm_tx(self, armed: bool) -> None:
        with self._lock:
            self.tx_armed = armed
        self._record("arm-tx" if armed else "disarm-tx")
        patch_status_wiz(self.status_path, armed)

    def _stale(self, gen: int) -> bool:
        with self._lock:
            return gen != self._gen

    def _wait_radio(self, gen: int) -> bool:
        """Bounded wait for wlan1 + NM. Does not activate the AP. Does not use wlan0."""
        deadline = time.monotonic() + self.wlan1_ready_timeout_s
        while True:
            if self._stale(gen):
                return False
            facts = self._inspect()
            if getattr(facts, "wlan0_touched", False):
                LOG.error("wiz inspect claimed wlan0 touch; abort")
                return False
            if facts.radio_ready:
                return True
            if time.monotonic() >= deadline:
                return False
            self._sleep(self.poll_s)

    def _ap_up_bounded(self, gen: int) -> bool:
        """One AP activation, with retries only while the radio/NM is not ready."""
        last_rc = 1
        for attempt in range(self.ap_up_attempts):
            if self._stale(gen):
                return False
            facts = self._inspect()
            if not facts.radio_ready:
                if not self._wait_radio(gen):
                    return False
                facts = self._inspect()
            if facts.radio_ready:
                self._record("ap-up")
                last_rc = int(self._run_helper("ap-up"))
                if last_rc == 0:
                    return True
                LOG.warning("WIZ-LIGHTS ap-up rc=%s attempt=%s", last_rc, attempt + 1)
                facts = self._inspect()
                if facts.radio_ready:
                    return False
            self._sleep(self.poll_s)
        return last_rc == 0

    def _finish(self, gen: int, *, ap: str, bridge: str, reason: str = "") -> None:
        if self._stale(gen):
            return
        with self._lock:
            self.ap = ap
            self.bridge = bridge
            self.fail_reason = reason
            self.busy = False

    def _run(self, on: bool, gen: int) -> None:
        try:
            if on:
                self._on(gen)
            else:
                self._off(gen)
        except Exception:
            LOG.exception("wiz lifecycle failed")
            self._arm_tx(False)
            self._finish(gen, ap=FAILED, bridge=STOPPED, reason="error")

    def _on(self, gen: int) -> None:
        self._arm_tx(False)
        if self._stale(gen):
            return
        if not self._wait_radio(gen):
            LOG.warning("WIZ-LIGHTS radio not ready before ap-up")
            self._finish(gen, ap=FAILED, bridge=STOPPED, reason="ap")
            return
        if not self._ap_up_bounded(gen):
            LOG.warning("WIZ-LIGHTS ap-up failed after bounded retries")
            self._finish(gen, ap=FAILED, bridge=STOPPED, reason="ap")
            return
        deadline = time.monotonic() + self.ready_timeout_s
        facts = WizInspect()
        while time.monotonic() < deadline:
            if self._stale(gen):
                return
            facts = self._inspect()
            if getattr(facts, "wlan0_touched", False):
                LOG.error("wiz inspect claimed wlan0 touch; abort")
                self._finish(gen, ap=FAILED, bridge=STOPPED, reason="ap")
                return
            if facts.ap_ready:
                break
            self._sleep(self.poll_s)
        else:
            reason = "isolation" if facts.wlan1_exists and facts.connected and not facts.isolation_active else "ap"
            LOG.warning("WIZ-LIGHTS not ready (%s)", reason)
            self._finish(gen, ap=FAILED, bridge=STOPPED, reason=reason)
            return
        if self._stale(gen):
            return
        with self._lock:
            self.ap = READY
        self._arm_tx(True)
        self._record("bridge-start")
        with self._lock:
            self.bridge = STARTING
        rc = int(self._run_helper("bridge-start"))
        if rc != 0:
            LOG.warning("wiz bridge-start failed rc=%s", rc)
            self._finish(gen, ap=READY, bridge=FAILED, reason="bridge")
            return
        facts = self._inspect()
        if facts.bridge_failed or not facts.bridge_active:
            wait_deadline = time.monotonic() + min(8.0, self.ready_timeout_s)
            while time.monotonic() < wait_deadline:
                if self._stale(gen):
                    return
                facts = self._inspect()
                if facts.bridge_active and not facts.bridge_failed:
                    break
                self._sleep(self.poll_s)
            else:
                self._finish(gen, ap=READY, bridge=FAILED, reason="bridge")
                return
        self._finish(gen, ap=READY, bridge=READY)

    def _off(self, gen: int) -> None:
        self._arm_tx(False)
        if self._stale(gen):
            return
        self._record("bridge-stop")
        with self._lock:
            self.bridge = STOPPED
        self._run_helper("bridge-stop")
        facts = self._inspect()
        if facts.bridge_active:
            self._sleep(self.poll_s)
            facts = self._inspect()
        if facts.bridge_active:
            LOG.warning("wiz bridge still active after stop")
            self._finish(gen, ap=self.ap, bridge=FAILED, reason="bridge")
            return
        self._record("ap-down")
        self._run_helper("ap-down")
        facts = self._inspect()
        if facts.ipv4 == WIZ_AP_IPV4:
            self._sleep(self.poll_s)
            facts = self._inspect()
        ap = DOWN
        if facts.ipv4 == WIZ_AP_IPV4:
            LOG.warning("wlan1 still has %s after ap-down", WIZ_AP_ADDRESS)
            ap = FAILED
        self._finish(gen, ap=ap, bridge=STOPPED, reason="ap" if ap == FAILED else "")


def _sudo_helper(action: str) -> int:
    argv = helper_argv(action)
    LOG.info("wiz helper: %s", " ".join(argv))
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=40)
    except (OSError, subprocess.TimeoutExpired):
        LOG.exception("wiz helper spawn failed")
        return 1
    if proc.returncode != 0:
        LOG.warning(
            "wiz helper rc=%s %s",
            proc.returncode,
            (proc.stderr or proc.stdout or "").strip(),
        )
    return int(proc.returncode)


def _run_text(argv: tuple[str, ...], timeout: float = 0.8) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout or ""


def inspect_wiz_runtime() -> WizInspect:
    """Unprivileged facts. Never downs/ups connections. Never touches wlan0."""
    link = _run_text(("/sbin/ip", "link", "show", "dev", WIZ_AP_IFACE))
    if not link:
        link = _run_text(("/usr/sbin/ip", "link", "show", "dev", WIZ_AP_IFACE))
    if not link:
        link = _run_text(("/bin/ip", "link", "show", "dev", WIZ_AP_IFACE))
    exists = bool(link.strip()) and "does not exist" not in link.lower()
    addr = _run_text(("/sbin/ip", "-4", "-o", "addr", "show", "dev", WIZ_AP_IFACE))
    if not addr:
        addr = _run_text(("/usr/sbin/ip", "-4", "-o", "addr", "show", "dev", WIZ_AP_IFACE))
    if not addr:
        addr = _run_text(("/bin/ip", "-4", "-o", "addr", "show", "dev", WIZ_AP_IFACE))
    ipv4, prefix = parse_ip_addr_ipv4(addr)
    routes = _run_text(("/sbin/ip", "-4", "route", "show", "default"))
    if not routes:
        routes = _run_text(("/usr/sbin/ip", "-4", "route", "show", "default"))
    if not routes:
        routes = _run_text(("/bin/ip", "-4", "route", "show", "default"))
    device = _run_text(
        (
            "/usr/bin/nmcli",
            "-t",
            "-f",
            "GENERAL.CONNECTION,GENERAL.STATE",
            "device",
            "show",
            WIZ_AP_IFACE,
        )
    )
    fields = parse_nmcli_device_fields(device)
    nm_device_seen = parse_nm_device_ready(fields)
    mode_text = _run_text(
        (
            "/usr/bin/nmcli",
            "-t",
            "-f",
            "802-11-wireless.mode,connection.interface-name",
            "connection",
            "show",
            WIZ_AP_CONNECTION_ID,
        )
    )
    isolation = _run_text(("/usr/bin/systemctl", "is-active", ISOLATION_UNIT))
    bridge = _run_text(("/usr/bin/systemctl", "is-active", BRIDGE_UNIT))
    bridge_word = (bridge or "").strip().lower()
    return WizInspect(
        wlan1_exists=exists,
        connection=parse_connection_name(fields),
        connected=parse_device_connected(fields),
        mode=parse_wifi_mode(mode_text),
        ipv4=ipv4,
        prefix=prefix,
        wlan1_default_route=default_route_uses_iface(routes, WIZ_AP_IFACE),
        isolation_active=isolation_is_active(isolation),
        bridge_active=bridge_word == "active",
        bridge_failed=bridge_word == "failed",
        wlan0_touched=LIGHT_CONTROL_IFACE in (WIZ_AP_IFACE,),
        nm_device_seen=nm_device_seen,
    )
