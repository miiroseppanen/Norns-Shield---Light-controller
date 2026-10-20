"""WIZ CONTROL owns WIZ-LIGHTS AP + wizbridge lifecycle."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from light_console.hardware.events import ButtonEvent, K3
from light_console.output.netmode import (
    MODE_NETWORK,
    MODE_STANDALONE,
    restore_wifi_plan,
)
from light_console.output.network import NetIface
from light_console.output.pages import pack_network_pages
from light_console.output.wiz_ap import WIZ_AP_CONNECTION_ID, WIZ_AP_IFACE
from light_console.output.wiz_lifecycle import (
    BRIDGE_UNIT,
    HELPER_ACTIONS,
    ISOLATION_UNIT,
    LinuxWizLifecycleService,
    MockWizLifecycleService,
    OLED_AP_FAILED,
    OLED_AP_STARTING,
    OLED_BRIDGE_FAILED,
    OLED_NO_DEVICES,
    OLED_READY,
    WizInspect,
    default_route_uses_iface,
    helper_argv,
    isolation_is_active,
    oled_wiz_detail,
    parse_ip_addr_ipv4,
    parse_nm_device_ready,
    parse_wifi_mode,
    patch_status_wiz,
    validate_helper_argv,
)
from light_console.state import ScreenId
from light_console.ui.pages import wiz_setting_detail
from light_console.ui.vocab import DOWN, FAILED, READY, STARTING, STOPPED

from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "packaging/light-console-wiz"
SUDOERS = ROOT / "packaging/sudoers.d/light-console-wiz"
INSTALL = ROOT / "packaging/install-wiz-lifecycle.sh"
UNIT = ROOT / "packaging/systemd/wizbridge.service"
CONTROLLER = ROOT / "light_console/ui/controller.py"
NETMODE = ROOT / "light_console/output/netmode.py"


class _World:
    def __init__(self, *, up: bool = False, bridge: bool = False, isolation: bool = True) -> None:
        self.up = up
        self.bridge = bridge
        self.isolation = isolation
        self.ops: list[str] = []
        self.wlan0_ops: list[str] = []
        self.ap_up_rc = 0
        self.bridge_start_rc = 0
        self.bridge_failed = False

    def run(self, action: str) -> int:
        assert action in HELPER_ACTIONS
        self.ops.append(action)
        if action == "ap-up":
            if self.ap_up_rc != 0:
                return self.ap_up_rc
            self.up = True
            return 0
        if action == "ap-down":
            self.up = False
            return 0
        if action == "bridge-start":
            if self.bridge_start_rc != 0:
                return self.bridge_start_rc
            self.bridge = True
            return 0
        if action == "bridge-stop":
            self.bridge = False
            return 0
        return 2

    def inspect(self) -> WizInspect:
        return WizInspect(
            wlan1_exists=True,
            connection="WIZ-LIGHTS" if self.up else "",
            connected=self.up,
            mode="ap" if self.up else "",
            ipv4="10.42.0.1" if self.up else "",
            prefix=24 if self.up else 0,
            wlan1_default_route=False,
            isolation_active=self.isolation and self.up,
            bridge_active=self.bridge,
            bridge_failed=self.bridge_failed,
            wlan0_touched=False,
            nm_device_seen=True,
        )


def _wait(svc: LinuxWizLifecycleService, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not svc.snapshot().busy:
            return
        time.sleep(0.01)
    raise AssertionError("lifecycle stayed busy")


def test_helper_argv_is_exact_and_hardcoded():
    assert helper_argv("ap-up") == (
        "/usr/bin/sudo",
        "-n",
        "/usr/sbin/light-console-wiz",
        "ap-up",
    )
    try:
        helper_argv("nmcli")
    except Exception as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("generic helper action must fail")
    assert validate_helper_argv(["light-console-wiz", "ap-down"]) == "ap-down"
    try:
        validate_helper_argv(["light-console-wiz", "ap-up", "wlan0"])
    except Exception:
        pass
    else:
        raise AssertionError("extra argv must fail")


def test_helper_script_never_takes_arbitrary_targets():
    src = HELPER.read_text(encoding="utf-8")
    assert "shell=True" not in src
    assert "connection up" in src or '"connection", "up"' in src
    assert "WIZ-LIGHTS" in src
    assert 'IFACE = "wlan1"' in src
    assert "not an active" in src
    assert "LIGHT-CONTROL" not in src
    assert "nmcli radio" not in src
    assert "nmcli networking" not in src
    for forbidden in ("wlan0", "hostapd", "dnsmasq.service", "38899", "setPilot"):
        assert forbidden not in src


def test_off_disarms_before_bridge_stop_before_ap_down():
    svc = MockWizLifecycleService(desired=True, auto_settle=True)
    svc.set_desired(False)
    snap = svc.snapshot()
    assert snap.commands[:3] == ["disarm-tx", "bridge-stop", "ap-down"]
    assert snap.tx_armed is False
    assert snap.bridge == STOPPED
    assert snap.ap == DOWN
    assert svc.wlan0_ops == []


def test_on_ap_before_arm_before_bridge():
    svc = MockWizLifecycleService(desired=False, auto_settle=False)
    svc.set_desired(True)
    snap = svc.snapshot()
    assert snap.tx_armed is False
    assert snap.ap == STARTING
    assert "bridge-start" not in snap.commands
    svc.settle()
    snap = svc.snapshot()
    assert snap.commands.index("ap-up") < snap.commands.index("arm-tx")
    assert snap.commands.index("arm-tx") < snap.commands.index("bridge-start")
    assert snap.ap == READY
    assert snap.bridge == READY
    assert snap.tx_armed is True


def test_controller_off_writes_wiz_off_before_bridge_stop(tmp_path, monkeypatch):
    from light_console.ui import controller as ctl

    path = tmp_path / "light-console.status"
    monkeypatch.setattr(ctl, "STATUS_PATH", path)
    svc = MockWizLifecycleService(desired=True, auto_settle=True)
    c = make_controller(wiz_enabled=True, wiz_service=svc)
    c.tick(now=0.1)
    assert "wiz=on" in path.read_text()
    svc.auto_settle = False
    c.set_wiz_enabled(False)
    c._finish()
    text = path.read_text()
    assert "wiz=off" in text
    assert svc.snapshot().commands[-3:] == ["disarm-tx", "bridge-stop", "ap-down"]
    assert svc.wlan0_ops == []


def test_controller_on_does_not_arm_tx_until_ready(tmp_path, monkeypatch):
    from light_console.ui import controller as ctl

    path = tmp_path / "light-console.status"
    monkeypatch.setattr(ctl, "STATUS_PATH", path)
    svc = MockWizLifecycleService(desired=False, auto_settle=False)
    c = make_controller(wiz_service=svc)
    c.set_wiz_enabled(True)
    c._finish()
    assert c.state.wiz_enabled is True
    assert c.state.wiz_ap_state == STARTING
    assert "wiz=off" in path.read_text()
    assert "bridge-start" not in svc.commands
    svc.settle()
    c._finish()
    assert "wiz=on" in path.read_text()
    assert c.state.wiz_ap_state == READY
    assert c.state.wiz_bridge_state == READY


def test_ap_and_isolation_failure_do_not_start_bridge_or_touch_wlan0():
    ap = MockWizLifecycleService(desired=False, auto_settle=True)
    ap.fail_ap = True
    ap.set_desired(True)
    assert ap.snapshot().ap == FAILED
    assert ap.snapshot().bridge == STOPPED
    assert "bridge-start" not in ap.commands
    assert ap.commands.count("ap-up") == 1
    iso = MockWizLifecycleService(desired=False, auto_settle=True)
    iso.fail_isolation = True
    iso.set_desired(True)
    assert iso.snapshot().ap == FAILED
    assert iso.snapshot().fail_reason == "isolation"
    assert "bridge-start" not in iso.commands
    assert iso.wlan0_ops == []


def test_bridge_failure_is_explicit_and_does_not_retry():
    svc = MockWizLifecycleService(desired=False, auto_settle=True)
    svc.fail_bridge = True
    svc.set_desired(True)
    snap = svc.snapshot()
    assert snap.ap == READY
    assert snap.bridge == FAILED
    assert snap.commands.count("bridge-start") == 1
    assert snap.commands.count("ap-up") == 1
    assert wiz_setting_detail(
        type("S", (), {
            "wiz_enabled": True,
            "wiz_ap_state": snap.ap,
            "wiz_bridge_state": snap.bridge,
            "wiz_lifecycle_busy": False,
            "wiz_online": 0,
        })()
    ) == OLED_BRIDGE_FAILED


def test_no_devices_is_ready_infrastructure():
    c = make_controller(wiz_enabled=True, wiz_online=0)
    c._finish()
    assert c.state.wiz_ap_state == READY
    assert c.state.wiz_bridge_state == READY
    assert wiz_setting_detail(c.state) == OLED_NO_DEVICES
    assert not any("WAIT" in w for w in c.state.warnings)
    assert not any("WIZ 0/" in w for w in c.state.warnings)


def test_oled_labels_and_wiz_lights_is_ap():
    c = make_controller(wiz_enabled=True, wiz_online=6)
    assert wiz_setting_detail(c.state) == OLED_READY
    c.wiz_service.ap = STARTING
    c.wiz_service.bridge = STOPPED
    c.wiz_service.busy = True
    c._sync_wiz_runtime()
    assert wiz_setting_detail(c.state) == OLED_AP_STARTING
    c.wiz_service.ap = FAILED
    c.wiz_service.busy = False
    c._sync_wiz_runtime()
    c._finish()
    assert wiz_setting_detail(c.state) == OLED_AP_FAILED
    assert any("AP FAILED" in w for w in c.state.warnings)
    ifaces = (
        NetIface("wlan0", True, "192.168.88.246", "LIGHT-CONTROL", 24, kind="onboard"),
        NetIface("wlan1", True, "10.42.0.1", "WIZ-LIGHTS", 24, kind="usb"),
    )
    page = pack_network_pages(ifaces, network_mode=MODE_NETWORK)
    by_name = {item.title: item.status for item in page[0].items}
    assert by_name["LIGHT-CONTROL"] == "CLIENT"
    assert by_name["WIZ-LIGHTS"] == "AP"
    assert "CLIENT" != by_name["WIZ-LIGHTS"]


def test_busy_lock_ignores_second_toggle():
    svc = MockWizLifecycleService(desired=False, auto_settle=False)
    c = make_controller(wiz_service=svc)
    c.state.screen = ScreenId.WIZ_CONTROL
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_enabled is True
    assert svc.busy is True
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.wiz_enabled is True
    assert svc.apply_count == 1


def test_network_mode_does_not_down_wiz_lights():
    downs, ups = restore_wifi_plan(
        ["LIGHT-CONTROL"],
        ["LIGHT-CONTROL", "WIZ-LIGHTS"],
        {WIZ_AP_CONNECTION_ID},
    )
    assert "WIZ-LIGHTS" not in downs
    src = NETMODE.read_text(encoding="utf-8")
    assert "_protected_wifi_names" in src
    assert "WIZ-LIGHTS" in src
    c = make_controller(wiz_enabled=True)
    before = list(c.wiz_service.commands)
    c.set_network_mode(MODE_STANDALONE)
    c.net_service.settle()
    c._sync_network_mode()
    assert c.state.wiz_enabled is True
    assert c.wiz_service.commands == before


def test_parsers_require_correct_iface_ip_mode_isolation():
    ip, prefix = parse_ip_addr_ipv4(
        "3: wlan1    inet 10.42.0.1/24 brd 10.42.0.255 scope global noprefixroute wlan1\n"
    )
    assert ip == "10.42.0.1"
    assert prefix == 24
    assert default_route_uses_iface(
        "default via 192.168.88.1 dev wlan0 proto dhcp metric 600\n", "wlan1"
    ) is False
    assert default_route_uses_iface(
        "default via 10.42.0.1 dev wlan1\n", "wlan1"
    ) is True
    assert parse_wifi_mode("802-11-wireless.mode:ap\n") == "ap"
    assert isolation_is_active("active\n") is True
    assert isolation_is_active("inactive\n") is False
    facts = WizInspect(
        wlan1_exists=True,
        connection="WIZ-LIGHTS",
        connected=True,
        mode="ap",
        ipv4="10.42.0.1",
        prefix=24,
        isolation_active=True,
    )
    assert facts.ap_ready is True
    bad = WizInspect(
        wlan1_exists=True,
        connection="WIZ-LIGHTS",
        connected=True,
        mode="ap",
        ipv4="10.42.0.1",
        prefix=24,
        isolation_active=False,
    )
    assert bad.ap_ready is False


def test_linux_on_off_order_and_no_wlan0(tmp_path):
    world = _World()
    svc = LinuxWizLifecycleService(
        desired=False,
        run_helper=world.run,
        inspect=world.inspect,
        sleep=lambda _s: None,
        ready_timeout_s=1.0,
        poll_s=0,
        status_path=tmp_path / "light-console.status",
    )
    t0 = time.monotonic()
    assert svc.set_desired(True) is True
    assert time.monotonic() - t0 < 0.05
    _wait(svc)
    snap = svc.snapshot()
    assert world.ops == ["ap-up", "bridge-start"]
    assert snap.commands[:4] == ["disarm-tx", "ap-up", "arm-tx", "bridge-start"]
    assert snap.ap == READY
    assert snap.bridge == READY
    assert snap.tx_armed is True
    assert world.wlan0_ops == []
    svc.set_desired(False)
    _wait(svc)
    snap = svc.snapshot()
    assert snap.commands[-3:] == ["disarm-tx", "bridge-stop", "ap-down"]
    assert world.ops[-2:] == ["bridge-stop", "ap-down"]
    assert snap.tx_armed is False
    assert snap.bridge == STOPPED
    assert snap.ap == DOWN
    assert world.up is False
    assert world.bridge is False


def test_linux_failures_do_not_bounce_or_touch_wlan0():
    world = _World()
    world.ap_up_rc = 1
    svc = LinuxWizLifecycleService(
        run_helper=world.run,
        inspect=world.inspect,
        sleep=lambda _s: None,
        ready_timeout_s=0.2,
        poll_s=0,
    )
    svc.set_desired(True)
    _wait(svc)
    assert svc.snapshot().ap == FAILED
    assert "bridge-start" not in world.ops
    assert world.ops.count("ap-up") == 1
    world2 = _World()
    world2.isolation = False
    svc2 = LinuxWizLifecycleService(
        run_helper=world2.run,
        inspect=world2.inspect,
        sleep=lambda _s: None,
        ready_timeout_s=0.2,
        poll_s=0,
    )
    svc2.set_desired(True)
    _wait(svc2)
    assert svc2.snapshot().ap == FAILED
    assert svc2.snapshot().fail_reason == "isolation"
    assert "bridge-start" not in world2.ops
    world3 = _World()
    world3.bridge_start_rc = 1
    svc3 = LinuxWizLifecycleService(
        run_helper=world3.run,
        inspect=world3.inspect,
        sleep=lambda _s: None,
        ready_timeout_s=0.2,
        poll_s=0,
    )
    svc3.set_desired(True)
    _wait(svc3)
    assert svc3.snapshot().ap == READY
    assert svc3.snapshot().bridge == FAILED
    assert world3.ops.count("bridge-start") == 1
    assert world3.ops.count("ap-up") == 1


def test_linux_set_desired_does_not_block_ui_thread():
    started = threading.Event()
    release = threading.Event()

    def slow(action: str) -> int:
        started.set()
        release.wait(timeout=1.0)
        return 0

    def inspect() -> WizInspect:
        return WizInspect(wlan1_exists=True, nm_device_seen=True)

    svc = LinuxWizLifecycleService(
        run_helper=slow,
        inspect=inspect,
        sleep=lambda _s: None,
        ready_timeout_s=0.2,
        wlan1_ready_timeout_s=0.2,
        poll_s=0,
    )
    t0 = time.monotonic()
    svc.set_desired(True)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.05
    assert started.wait(timeout=0.5)
    release.set()
    _wait(svc, timeout=1.0)


def test_startup_persisted_off_and_on():
    off_world = _World(up=True, bridge=True)
    off = LinuxWizLifecycleService(
        desired=True,
        run_helper=off_world.run,
        inspect=off_world.inspect,
        sleep=lambda _s: None,
        ready_timeout_s=1.0,
        poll_s=0,
    )
    off.set_desired(False)
    _wait(off)
    assert off_world.ops[0] == "bridge-stop" or off.snapshot().commands[0] == "disarm-tx"
    assert off_world.ops == ["bridge-stop", "ap-down"]
    assert off.snapshot().ap == DOWN
    assert off.snapshot().bridge == STOPPED
    on_world = _World()
    on = LinuxWizLifecycleService(
        desired=False,
        run_helper=on_world.run,
        inspect=on_world.inspect,
        sleep=lambda _s: None,
        ready_timeout_s=1.0,
        poll_s=0,
    )
    on.set_desired(True)
    _wait(on)
    assert on_world.ops == ["ap-up", "bridge-start"]
    assert on.snapshot().ap == READY
    assert on.snapshot().bridge == READY


def test_controller_source_stays_off_the_hot_path():
    src = CONTROLLER.read_text(encoding="utf-8")
    assert "nmcli" not in src
    assert "systemctl" not in src
    assert "subprocess" not in src
    assert "wizbridge" not in src
    assert "38899" not in src


def test_status_patch_fail_closed(tmp_path):
    path = tmp_path / "light-console.status"
    path.write_text("screen=play\nwiz=on\n", encoding="utf-8")
    patch_status_wiz(path, False)
    assert "wiz=off" in path.read_text()
    assert "screen=play" in path.read_text()


def test_packaging_helper_sudoers_unit():
    sudoers = [
        ln.strip()
        for ln in SUDOERS.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert sudoers == [
        "light ALL=(root) NOPASSWD: /usr/sbin/light-console-wiz ap-up",
        "light ALL=(root) NOPASSWD: /usr/sbin/light-console-wiz ap-down",
        "light ALL=(root) NOPASSWD: /usr/sbin/light-console-wiz bridge-start",
        "light ALL=(root) NOPASSWD: /usr/sbin/light-console-wiz bridge-stop",
    ]
    assert "NOPASSWD: ALL" not in SUDOERS.read_text()
    assert "nmcli" not in SUDOERS.read_text()
    unit = UNIT.read_text()
    assert "WantedBy=" not in unit
    assert "127.0.0.1" not in unit or "Art-Net" in unit
    assert WIZ_AP_IFACE in unit
    assert BRIDGE_UNIT.split(".")[0] in unit.lower() or "wiz_artnet_bridge.py" in unit
    inst = INSTALL.read_text()
    assert "systemctl enable wizbridge" not in inst
    assert "systemctl start wizbridge" not in inst
    assert "master.qxw" not in inst
    assert "siirtyma" not in inst
    assert "qlcplus.service" not in inst
    assert "light-console.service" in inst or "did not modify" in inst
    assert "systemctl disable wizbridge.service" in inst
    assert "systemctl stop wizbridge.service" in inst
    assert ISOLATION_UNIT not in inst or "isolation" in inst.lower()
    assert "hostapd" not in inst
    assert "dispatcher" not in inst.lower()
    assert oled_wiz_detail(
        desired=False, ap=DOWN, bridge=STOPPED, busy=False, online=0
    ) is None


def test_nm_device_ready_requires_managed_state():
    assert parse_nm_device_ready({}) is False
    assert parse_nm_device_ready({"GENERAL.CONNECTION": "--"}) is False
    assert parse_nm_device_ready({"GENERAL.STATE": "10 (unmanaged)"}) is False
    assert parse_nm_device_ready({"GENERAL.STATE": "20 (unavailable)"}) is False
    assert parse_nm_device_ready({"GENERAL.STATE": "30 (disconnected)"}) is True
    assert parse_nm_device_ready({"GENERAL.STATE": "100 (connected)"}) is True


def test_radio_ready_is_not_ap_up():
    waiting = WizInspect(wlan1_exists=True, nm_device_seen=True)
    assert waiting.radio_ready is True
    assert waiting.ap_ready is False
    missing = WizInspect(wlan1_exists=False, nm_device_seen=False)
    assert missing.radio_ready is False


def test_linux_waits_for_wlan1_then_one_ap_up(tmp_path):
    n = {"inspects": 0}

    class Delayed(_World):
        def inspect(self) -> WizInspect:
            n["inspects"] += 1
            ready = n["inspects"] >= 3
            if self.up:
                return super().inspect()
            return WizInspect(wlan1_exists=ready, nm_device_seen=ready)

    world = Delayed()
    svc = LinuxWizLifecycleService(
        run_helper=world.run,
        inspect=world.inspect,
        sleep=lambda _s: None,
        ready_timeout_s=1.0,
        wlan1_ready_timeout_s=1.0,
        poll_s=0,
        status_path=tmp_path / "light-console.status",
    )
    svc.set_desired(True)
    _wait(svc)
    snap = svc.snapshot()
    assert n["inspects"] >= 3
    assert world.ops.count("ap-up") == 1
    assert world.ops == ["ap-up", "bridge-start"]
    assert snap.ap == READY
    assert snap.bridge == READY
    assert snap.tx_armed is True
    assert world.wlan0_ops == []


def test_linux_wlan1_timeout_fail_closed_no_ap_up():
    world = _World()

    def inspect() -> WizInspect:
        return WizInspect(wlan1_exists=False, nm_device_seen=False)

    svc = LinuxWizLifecycleService(
        run_helper=world.run,
        inspect=inspect,
        sleep=lambda _s: None,
        ready_timeout_s=0.2,
        wlan1_ready_timeout_s=0.05,
        poll_s=0,
    )
    svc.set_desired(True)
    _wait(svc)
    snap = svc.snapshot()
    assert snap.ap == FAILED
    assert snap.tx_armed is False
    assert "bridge-start" not in world.ops
    assert world.ops == []


def test_linux_retries_ap_up_only_while_radio_not_ready():
    class Race(_World):
        def __init__(self) -> None:
            super().__init__()
            self.ap_tries = 0
            self.saw_unready = False

        def inspect(self) -> WizInspect:
            if self.up:
                return super().inspect()
            if self.ap_tries == 1 and not self.saw_unready:
                self.saw_unready = True
                return WizInspect(wlan1_exists=True, nm_device_seen=False)
            return WizInspect(wlan1_exists=True, nm_device_seen=True)

        def run(self, action: str) -> int:
            if action == "ap-up":
                self.ap_tries += 1
                if self.ap_tries == 1:
                    self.ops.append(action)
                    return 1
            return super().run(action)

    world = Race()
    svc = LinuxWizLifecycleService(
        run_helper=world.run,
        inspect=world.inspect,
        sleep=lambda _s: None,
        ready_timeout_s=1.0,
        wlan1_ready_timeout_s=1.0,
        ap_up_attempts=5,
        poll_s=0,
    )
    svc.set_desired(True)
    _wait(svc)
    assert world.ops.count("ap-up") == 2
    assert world.ops.count("ap-up") < 5
    assert svc.snapshot().ap == READY
    assert svc.snapshot().tx_armed is True


def test_linux_ap_up_fail_when_radio_ready_is_one_shot():
    world = _World()
    world.ap_up_rc = 1
    svc = LinuxWizLifecycleService(
        run_helper=world.run,
        inspect=world.inspect,
        sleep=lambda _s: None,
        ready_timeout_s=0.2,
        wlan1_ready_timeout_s=0.2,
        ap_up_attempts=5,
        poll_s=0,
    )
    svc.set_desired(True)
    _wait(svc)
    assert world.ops.count("ap-up") == 1
    assert svc.snapshot().ap == FAILED
    assert svc.snapshot().tx_armed is False
    assert "bridge-start" not in world.ops


def test_linux_wiz_on_ignores_wlan0_and_default_route():
    src = Path(__file__).resolve().parents[1] / "light_console/output/wiz_lifecycle.py"
    text = src.read_text(encoding="utf-8")
    inspect_fn = text.split("def inspect_wiz_runtime()", 1)[1].split("\ndef ", 1)[0]
    assert "WIZ_AP_IFACE" in inspect_fn
    assert '"wlan0"' not in inspect_fn
    assert "'wlan0'" not in inspect_fn
    world = _World()

    def inspect() -> WizInspect:
        facts = world.inspect()
        return WizInspect(
            wlan1_exists=facts.wlan1_exists,
            connection=facts.connection,
            connected=facts.connected,
            mode=facts.mode,
            ipv4=facts.ipv4,
            prefix=facts.prefix,
            wlan1_default_route=False,
            isolation_active=facts.isolation_active,
            bridge_active=facts.bridge_active,
            bridge_failed=facts.bridge_failed,
            wlan0_touched=False,
            nm_device_seen=True,
        )

    svc = LinuxWizLifecycleService(
        run_helper=world.run,
        inspect=inspect,
        sleep=lambda _s: None,
        ready_timeout_s=1.0,
        wlan1_ready_timeout_s=1.0,
        poll_s=0,
    )
    svc.set_desired(True)
    _wait(svc)
    assert world.ops == ["ap-up", "bridge-start"]
    assert world.wlan0_ops == []
    assert svc.snapshot().tx_armed is True
    assert svc.snapshot().ap == READY


def test_linux_does_not_arm_tx_until_ap_verified():
    world = _World()
    world.isolation = False
    svc = LinuxWizLifecycleService(
        run_helper=world.run,
        inspect=world.inspect,
        sleep=lambda _s: None,
        ready_timeout_s=0.2,
        wlan1_ready_timeout_s=0.2,
        poll_s=0,
    )
    svc.set_desired(True)
    _wait(svc)
    assert world.ops == ["ap-up"]
    assert svc.snapshot().tx_armed is False
    assert svc.snapshot().ap == FAILED
    assert "bridge-start" not in world.ops


def test_unit_after_networkmanager_not_network_online():
    unit = (Path(__file__).resolve().parents[1] / "packaging/systemd/light-console.service").read_text()
    live = [ln for ln in unit.splitlines() if ln and not ln.startswith("#")]
    after = next(ln for ln in live if ln.startswith("After="))
    wants = next(ln for ln in live if ln.startswith("Wants="))
    assert "NetworkManager.service" in after
    assert "network-online.target" not in after
    assert "NetworkManager.service" in wants
    assert not any("network-online" in ln for ln in live)

