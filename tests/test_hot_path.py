"""UI tick must not wait on nmcli/systemctl/iw or other shell collectors."""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from light_console.config import load_config
from light_console.display.framebuffer import Framebuffer
from light_console.hardware.base import HardwareBackend
from light_console.hardware.events import HardwareEvent
from light_console.output.network import NetIface, collect_network
from light_console.output.observe import LiveDiagnostics
from light_console.state import AppState, ScreenId
from light_console.status.midi import launchpad_usb_present
from light_console.ui.controller import Controller

from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "light_console/ui/controller.py"


class _FakeHw(HardwareBackend):
    def read_events(self) -> list[HardwareEvent]:
        return []

    def set_display(self, fb: Framebuffer) -> None:
        del fb

    def set_display_brightness(self, level: int) -> None:
        del level

    def close(self) -> None:
        return


def test_tick_and_refresh_source_has_no_shell_collectors():
    src = CONTROLLER.read_text(encoding="utf-8")
    assert "collect_network(" not in src
    assert "launchpad_visible(" not in src
    assert "nmcli" not in src
    assert "systemctl" not in src
    assert "subprocess" not in src
    assert "iwgetid" not in src
    assert "fetch_config_html" not in src
    assert "/config" not in src
    ws = (ROOT / "light_console/qlc/ws_client.py").read_text(encoding="utf-8")
    assert "DRAIN_MAX_MSG" in ws
    assert "while True:" not in ws.split("def _drain")[1].split("def ")[0]


def test_controller_tick_does_not_invoke_subprocess(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError(f"hot-path subprocess {args[:1]}")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "check_output", boom)

    config = load_config()
    config.display.fps = 1000
    state = AppState(screen=ScreenId.PLAY, qlc_connected=True, qlc_project_loaded=True)
    from light_console.qlc.client import MockQLCClient

    qlc = MockQLCClient()
    qlc.simulate_link(True)
    c = Controller(config, state, _FakeHw(), qlc, live_diag=False)
    c.tick(now=0.0)
    c.tick(now=2.0)
    c.tick(now=4.0)
    c.tick(now=10.0)


def test_headless_tick_does_not_start_live_diag():
    c = make_controller()
    assert c._diag is None
    c.tick(now=3.0)
    c.tick(now=6.0)


def test_live_diagnostics_run_off_tick_thread():
    caller: list[int] = []

    def fake_collect():
        caller.append(threading.get_ident())
        return (NetIface("wlan0", True, "192.168.88.246", "LIGHT-CONTROL", 24),)

    diag = LiveDiagnostics(
        collect=fake_collect,
        usb_present=lambda usb_id: True,
        net_interval_s=0.05,
        start=True,
    )
    try:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not caller:
            time.sleep(0.01)
        ifaces, launchpad = diag.snapshot()
        assert caller
        assert threading.get_ident() not in caller
        assert ifaces[0].name == "wlan0"
        assert launchpad is True
    finally:
        diag.close()


def test_launchpad_usb_present_reads_sysfs(tmp_path, monkeypatch):
    dev = tmp_path / "1-1.2"
    dev.mkdir()
    (dev / "idVendor").write_text("1235\n")
    (dev / "idProduct").write_text("0036\n")
    monkeypatch.setattr("light_console.status.midi.USB_DEVICES", tmp_path)
    assert launchpad_usb_present("1235:0036") is True
    assert launchpad_usb_present("ffff:0000") is False


def test_live_collect_network_does_not_exec_udev_or_iw(monkeypatch):
    calls: list[tuple[str, ...]] = []

    def fake_cmd(argv):
        calls.append(tuple(argv))
        if argv[:1] == ["ip"]:
            return (
                "lo               UNKNOWN        127.0.0.1/8\n"
                "eth0             DOWN\n"
                "wlan0            UP             192.168.88.246/24\n"
                "wlan1            DOWN\n"
            )
        if argv[:1] == ["nmcli"] and "device" in argv:
            return (
                "wlan0:wifi:connected:netplan-wlan0-LIGHT-CONTROL\n"
                "lo:loopback:connected (externally):lo\n"
                "wlan1:wifi:disconnected:\n"
                "eth0:ethernet:unavailable:\n"
            )
        if argv[:1] == ["nmcli"] and "connection" in argv:
            return "802-11-wireless.ssid:LIGHT-CONTROL\n"
        raise AssertionError(f"unexpected cmd {argv}")

    monkeypatch.setattr("light_console.output.network._cmd", fake_cmd)
    monkeypatch.setattr(
        "light_console.output.network._live_sys_names",
        lambda: ("lo", "eth0", "wlan0", "wlan1"),
    )
    monkeypatch.setattr(
        "light_console.output.network._live_wireless", lambda name: name.startswith("wl")
    )
    monkeypatch.setattr(
        "light_console.output.network._live_driver",
        lambda name, udev: "brcmfmac" if name == "wlan0" else "",
    )
    monkeypatch.setattr("light_console.output.network._live_mac", lambda name: "aa:bb:cc:dd:ee:ff")
    monkeypatch.setattr(
        "light_console.output.network._sys_net_props",
        lambda name: {
            "DEVTYPE": "wlan",
            "ID_PATH": (
                "platform-fe300000.mmcnr"
                if name == "wlan0"
                else "platform-usb-0:1.1:1.0"
            ),
            "ID_BUS": "" if name == "wlan0" else "usb",
        }
        if name.startswith("wl")
        else {},
    )

    ifaces = collect_network()
    bins = [argv[0] for argv in calls]
    assert "udevadm" not in bins
    assert "iwgetid" not in bins
    assert "iw" not in bins
    by_name = {iface.name: iface for iface in ifaces}
    assert by_name["wlan0"].kind == "onboard"
    assert by_name["wlan0"].ssid == "LIGHT-CONTROL"
    assert by_name["wlan1"].kind == "usb"
