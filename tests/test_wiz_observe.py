"""Fail-closed parse of the transient WiZ bridge status file."""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

from light_console.output.wiz_lifecycle import (
    OLED_AP_FAILED,
    OLED_BRIDGE_FAILED,
    OLED_NO_DEVICES,
    OLED_READY,
)
from light_console.status.wiz import apply_wiz_observed
from light_console.ui.pages import wiz_setting_detail
from light_console.ui.vocab import FAILED, READY
from light_console.wiz.observe import (
    MAX_OBSERVED_BYTES,
    Availability,
    DiscoveryKind,
    parse_observed_status,
    read_observed_status,
)

from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]
OBSERVE = ROOT / "light_console/wiz/observe.py"
CONTROLLER = ROOT / "light_console/ui/controller.py"
STATUS_WIZ = ROOT / "light_console/status/wiz.py"

MAC5 = "9877d5b20706"
MAC6 = "9877d548f1be"
MAC_NEW = "aabbccddeeff"


def _row(
    mac: str,
    *,
    configured: bool = True,
    availability: str = "ONLINE",
    discovery: str | None = None,
    ip: str | None = None,
    last_seen: float | None = 1.0,
    slot: int | None = None,
    dmx_active: object = False,
    dmx_last_change: float | None = None,
) -> dict:
    return {
        "id": mac,
        "configured": configured,
        "availability": availability,
        "discovery": discovery or ("KNOWN" if configured else "NEW"),
        "observed_ip": ip,
        "last_seen": last_seen,
        "slot": slot,
        "dmx_active": dmx_active,
        "dmx_last_change": dmx_last_change,
    }


def _dump(*devices, **extra) -> str:
    body = {"state": "READY", "wiz_tx": "on", "interface": "wlan1", "devices": list(devices)}
    body.update(extra)
    return json.dumps(body, separators=(",", ":")) + "\n"


def _write(path: Path, *devices, **extra) -> Path:
    path.write_text(_dump(*devices, **extra), encoding="utf-8")
    return path


def _live_controller(path: Path, **kw):
    defaults = dict(
        wiz_enabled=True,
        wiz_online=0,
        wiz_expected=6,
        wiz_observed_path=path,
    )
    defaults.update(kw)
    return make_controller(**defaults)


def test_missing_status_fail_closed(tmp_path: Path):
    missing = tmp_path / "absent.status"
    snap = read_observed_status(missing)
    assert snap.error == "missing"
    assert snap.online == 0
    assert snap.configured == 0
    assert snap.observations == ()
    c = _live_controller(missing, wiz_online=6)
    c._finish()
    assert c.state.wiz_online == 0
    assert wiz_setting_detail(c.state) == OLED_NO_DEVICES


def test_malformed_status_fail_closed(tmp_path: Path):
    path = tmp_path / "bad.status"
    for body in ("", "{", "[]", "null", '{"devices":{}}', '{"devices":"nope"}'):
        path.write_text(body, encoding="utf-8")
        snap = read_observed_status(path)
        assert snap.online == 0
        assert snap.configured == 0
        assert snap.error == "malformed"
    huge = tmp_path / "huge.status"
    huge.write_bytes(b"x" * (MAX_OBSERVED_BYTES + 1))
    assert read_observed_status(huge).error == "malformed"
    _write(path, _row(MAC5), {"id": "not-a-mac", "configured": True, "availability": "ONLINE"})
    snap = parse_observed_status(path.read_text(encoding="utf-8"))
    assert snap.error == ""
    assert snap.online == 1
    assert snap.configured == 1
    c = _live_controller(tmp_path / "truncated.status")
    (tmp_path / "truncated.status").write_text("{not json", encoding="utf-8")
    c._wiz_observed_mtime = None
    c._finish()
    assert c.state.wiz_online == 0
    assert wiz_setting_detail(c.state) == OLED_NO_DEVICES


def test_zero_configured(tmp_path: Path):
    path = _write(tmp_path / "empty.status")
    snap = read_observed_status(path)
    assert snap.error == ""
    assert snap.configured == 0
    assert snap.online == 0
    c = _live_controller(path)
    assert wiz_setting_detail(c.state) == OLED_NO_DEVICES


def test_configured_but_offline(tmp_path: Path):
    path = _write(
        tmp_path / "off.status",
        _row(MAC5, availability="OFFLINE", last_seen=1.0, slot=5),
        _row(MAC6, availability="UNKNOWN", last_seen=None, slot=6),
    )
    snap = read_observed_status(path)
    assert snap.configured == 2
    assert snap.online == 0
    c = _live_controller(path)
    assert c.state.wiz_online == 0
    assert wiz_setting_detail(c.state) == OLED_NO_DEVICES


def test_one_configured_online(tmp_path: Path):
    path = _write(tmp_path / "one.status", _row(MAC5, ip="10.42.0.111", slot=5))
    snap = read_observed_status(path)
    assert snap.configured == 1
    assert snap.online == 1
    assert snap.observations[0].availability is Availability.ONLINE
    c = _live_controller(path)
    assert c.state.wiz_online == 1
    assert wiz_setting_detail(c.state) == OLED_READY


def test_one_online_and_one_offline(tmp_path: Path):
    path = _write(
        tmp_path / "mixed.status",
        _row(MAC5, ip="10.42.0.111", slot=5),
        _row(MAC6, availability="UNKNOWN", last_seen=None, slot=6),
    )
    snap = read_observed_status(path)
    assert snap.configured == 2
    assert snap.online == 1
    c = _live_controller(path)
    assert c.state.wiz_online == 1
    assert wiz_setting_detail(c.state) == OLED_READY


def test_discovered_new_only_does_not_count(tmp_path: Path):
    path = _write(
        tmp_path / "new.status",
        _row(MAC_NEW, configured=False, discovery="NEW", ip="10.42.0.55", availability="ONLINE"),
    )
    snap = read_observed_status(path)
    assert snap.configured == 0
    assert snap.online == 0
    assert snap.observations[0].discovery is DiscoveryKind.NEW
    assert snap.observations[0].configured is False
    c = _live_controller(path)
    assert c.state.wiz_online == 0
    assert wiz_setting_detail(c.state) == OLED_NO_DEVICES


def test_wiz_off_overrides_device_status(tmp_path: Path):
    path = _write(tmp_path / "on.status", _row(MAC5, slot=5))
    c = _live_controller(path, wiz_enabled=False)
    apply_wiz_observed(c.state, read_observed_status(path))
    assert c.state.wiz_online == 1
    assert wiz_setting_detail(c.state) is None


def test_ap_and_bridge_failure_override_device_status(tmp_path: Path):
    path = _write(tmp_path / "on.status", _row(MAC5, slot=5))
    c = _live_controller(path)
    assert wiz_setting_detail(c.state) == OLED_READY
    c.wiz_service.ap = FAILED
    c.wiz_service.bridge = READY
    c.wiz_service.busy = False
    c._finish()
    assert c.state.wiz_online == 1
    assert wiz_setting_detail(c.state) == OLED_AP_FAILED
    c.wiz_service.ap = READY
    c.wiz_service.bridge = FAILED
    c._finish()
    assert wiz_setting_detail(c.state) == OLED_BRIDGE_FAILED


def test_dmx_active_is_configured_only_and_fail_closed():
    snap = parse_observed_status(
        _dump(_row(MAC5, dmx_active=True, slot=5), _row(MAC_NEW, configured=False, dmx_active=True))
    )
    by_id = {item.id: item for item in snap.observations}
    assert by_id[MAC5].dmx_active is True
    assert by_id[MAC_NEW].dmx_active is False
    bad = parse_observed_status(_dump(_row(MAC5, dmx_active="yes", slot=5)))
    assert bad.observations[0].dmx_active is False


def test_parsing_is_local_file_only(tmp_path: Path, monkeypatch):
    src = OBSERVE.read_text(encoding="utf-8")
    for needle in ("subprocess", "nmcli", "systemctl", "sendto", "38899", "192.168.88.248"):
        assert needle not in src
    assert "read_text" in src or "Path" in src
    ctrl = CONTROLLER.read_text(encoding="utf-8")
    assert "read_observed_status" in ctrl
    assert "apply_wiz_observed" in ctrl
    assert "wizbridge" not in ctrl
    assert "38899" not in ctrl
    assert "apply_wiz_observed" in STATUS_WIZ.read_text(encoding="utf-8")

    def boom(*args, **kwargs):
        raise AssertionError(f"network/shell {args[:1]}")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "check_output", boom)
    monkeypatch.setattr(socket.socket, "sendto", boom)
    monkeypatch.setattr(socket.socket, "send", boom)
    path = _write(tmp_path / "live.status", _row(MAC5, ip="10.42.0.111", slot=5))
    before = path.read_bytes()
    mtime = path.stat().st_mtime
    snap = read_observed_status(path)
    assert snap.online == 1
    assert path.read_bytes() == before
    assert path.stat().st_mtime == mtime
    c = _live_controller(path)
    c.tick(now=1.0)
    c.tick(now=2.0)
    assert c.state.wiz_online == 1
    assert wiz_setting_detail(c.state) == OLED_READY
    assert path.read_bytes() == before
