"""Phase C: wizbridge fail-closed UDP gate, no auto-enroll, loopback Art-Net.

Tests mock socket sendto/recvfrom. They must never emit real WiZ packets.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "services/wiz/wiz_artnet_bridge.py"
MAC_A = "aabbccddeeff"
MAC_B = "bbccddeeff00"
MAC_NEW = "ccddeeff0011"


def _load_bridge():
    spec = importlib.util.spec_from_file_location("wiz_artnet_bridge_phase_c", BRIDGE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


BRIDGE = _load_bridge()


class _BridgeHarness:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self.mod = BRIDGE
        self.monkeypatch = monkeypatch
        self.tmp = tmp_path
        self.status = tmp_path / "light-console.status"
        self.observed = tmp_path / "wizbridge.status"
        self.map_path = tmp_path / "map.json"
        self.fixtures_path = tmp_path / "fixtures.json"
        self.sends: list[tuple[bytes, object]] = []
        self.replies: list[tuple[bytes, tuple]] = []
        monkeypatch.setenv("WIZBRIDGE_STATUS", str(self.status))
        monkeypatch.setenv("WIZBRIDGE_OBSERVED", str(self.observed))
        monkeypatch.setenv("WIZBRIDGE_MAP", str(self.map_path))
        monkeypatch.setenv("WIZBRIDGE_FIXTURES", str(self.fixtures_path))
        monkeypatch.setattr(self.mod, "WIZ_INTERFACE", "")
        monkeypatch.setattr(self.mod, "DISCOVERY_TIMEOUT", 0.01)
        monkeypatch.setattr(self.mod, "ACK_TIMEOUT", 0.01)
        monkeypatch.setattr(self.mod, "RETRY_DELAY", 0.0)
        monkeypatch.setattr(self.mod, "RETRIES", 0)
        monkeypatch.setattr(self.mod, "OFF_POLL", 0.01)
        monkeypatch.setattr(self.mod, "MIN_SEND_INTERVAL", 0.0)
        monkeypatch.setattr(self.mod, "OFF_DELAY_MS", 0)
        monkeypatch.setattr(
            self.mod,
            "map_config_paths",
            lambda: [str(self.map_path)],
        )
        monkeypatch.setattr(
            self.mod,
            "fixture_config_paths",
            lambda: [str(self.fixtures_path)],
        )

        def spy_sendto(sock, data, addr=None, flags=0):
            dest = addr if not isinstance(addr, int) else flags
            self.sends.append((bytes(data), dest))
            return len(data)

        def spy_recvfrom(sock, bufsize, flags=0):
            if self.replies:
                return self.replies.pop(0)
            raise socket.timeout("test-no-reply")

        def spy_send(sock, data, flags=0):
            raise AssertionError("UDP must use sendto, not send")

        monkeypatch.setattr(socket.socket, "sendto", spy_sendto)
        monkeypatch.setattr(socket.socket, "recvfrom", spy_recvfrom)
        monkeypatch.setattr(socket.socket, "send", spy_send)
        self.mod.reset_runtime_for_tests()

    def write_status(self, body: str | None = None, *, wiz: str | None = None):
        if body is not None:
            self.status.write_bytes(body.encode("utf-8") if isinstance(body, str) else body)
            return
        if wiz is None:
            if self.status.exists():
                self.status.unlink()
            return
        self.status.write_text(f"sat=100\nhue=0\nmaster=100\nwiz={wiz}\n", encoding="utf-8")

    def payloads(self) -> list[dict]:
        out = []
        for data, _dest in self.sends:
            try:
                out.append(json.loads(data.decode()))
            except (UnicodeDecodeError, json.JSONDecodeError):
                out.append({"raw": data})
        return out

    def methods(self) -> list[str]:
        return [item.get("method") for item in self.payloads() if isinstance(item, dict)]


@pytest.fixture
def harness(tmp_path, monkeypatch):
    h = _BridgeHarness(tmp_path, monkeypatch)
    yield h
    h.mod.reset_runtime_for_tests()


def _legacy_doc(*macs: str) -> dict:
    fixtures = []
    for i, mac in enumerate(macs):
        fixtures.append({"slot": i + 1, "mac": mac, "ip": f"10.42.0.{10 + i}"})
    return {
        "start_channel": 1,
        "channels_per_fixture": 6,
        "fixtures": fixtures,
    }


def _map_doc(*pairs: tuple[str, int]) -> dict:
    return {
        "version": 1,
        "start_channel": 1,
        "channels_per_fixture": 6,
        "devices": [{"id": mac, "slot": slot, "enabled": True, "label": ""} for mac, slot in pairs],
    }


def test_fail_closed_missing_status(harness):
    assert harness.status.exists() is False
    assert harness.mod.parse_wiz_enabled_fail_closed("") is False
    assert harness.mod.read_wiz_enabled() is False
    assert harness.mod.wiz_tx_allowed() is False
    harness.mod.discover_wiz()
    harness.mod.wiz_exchange("10.42.0.20", "getPilot")
    harness.mod.wiz_exchange("10.42.0.20", "setPilot", {"state": True})
    harness.mod.verify_remembered_ip(MAC_A, "10.42.0.20")
    harness.mod.restore_remembered_ips([MAC_A])
    harness.mod.keepalive_once()
    harness.mod.discovery_once()
    harness.mod.identify_once()
    assert harness.sends == []


def test_fail_closed_malformed_status(harness):
    harness.status.write_bytes(b"\xff\xfe not utf-8 \x00")
    assert harness.mod.wiz_tx_allowed() is False
    harness.mod.discover_wiz()
    harness.status.write_text("{not key value\nwiz\n", encoding="utf-8")
    harness.mod.wiz_exchange("10.42.0.20", "getPilot")
    harness.mod.setpilot_with_retry("10.42.0.20", {"state": True})
    assert harness.sends == []


def test_fail_closed_unknown_wiz_value(harness):
    for value in ("true", "1", "yes", "TRUE", "", "maybe", "offf", "enabled"):
        harness.write_status(wiz=value)
        assert harness.mod.wiz_tx_allowed() is False, value
        harness.mod.discover_wiz()
        harness.mod.wiz_exchange("10.42.0.20", "setPilot", {"state": False})
    harness.status.write_text("sat=100\nhue=0\n", encoding="utf-8")
    assert harness.mod.wiz_tx_allowed() is False
    harness.mod.keepalive_once()
    harness.mod.identify_once()
    assert harness.sends == []


def test_explicit_on_allows_and_off_forbids(harness):
    harness.write_status(wiz="on")
    assert harness.mod.wiz_tx_allowed() is True
    harness.mod.discover_wiz()
    assert harness.methods() == ["getPilot"]
    dests = [item[1] for item in harness.sends]
    assert all(isinstance(d, tuple) and d[1] == 38899 for d in dests)
    harness.sends.clear()
    harness.write_status(wiz="off")
    assert harness.mod.wiz_tx_allowed() is False
    harness.mod.discover_wiz()
    harness.mod.wiz_exchange("10.42.0.20", "getPilot")
    harness.mod.setpilot_with_retry("10.42.0.20", {"r": 1})
    harness.mod.verify_remembered_ip(MAC_A, "10.42.0.20")
    harness.mod.restore_remembered_ips([MAC_A])
    harness.mod.keepalive_once()
    harness.mod.discovery_once()
    harness.mod.identify_once()
    assert harness.sends == []
    assert "getPilot" not in harness.methods()
    assert "setPilot" not in harness.methods()


def test_off_blocks_every_udp_source(harness):
    harness.write_status(wiz="off")
    harness.mod.apply_configured([MAC_A], ips={MAC_A: "10.42.0.20"})
    with harness.mod.devices_lock:
        harness.mod.devices[MAC_A] = {"ip": "10.42.0.20", "last_seen": 0.0}
    harness.mod.discover_wiz()
    harness.mod.discovery_once()
    harness.mod.keepalive_once()
    harness.mod.verify_remembered_ip(MAC_A, "10.42.0.20")
    harness.mod.restore_remembered_ips([MAC_A])
    harness.mod.wiz_exchange("10.42.0.20", "getPilot")
    harness.mod.setpilot_with_retry("10.42.0.20", {"state": True})
    harness.status.write_text("wiz=off\nidentify=aabbccddeeff\n", encoding="utf-8")
    harness.mod.identify_once()
    worker = harness.mod.FixtureWorker(MAC_A, 1, autostart=False)
    loops = {"n": 0}

    def fake_sleep(_dt):
        loops["n"] += 1
        if loops["n"] > 6:
            worker.stop()

    harness.monkeypatch.setattr(harness.mod.time, "sleep", fake_sleep)
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[0:6] = bytes([255, 255, 0, 0, 0, 0])
    worker.run()
    assert harness.sends == []
    assert loops["n"] > 6


def test_on_to_off_discovery_stops_without_restart(harness):
    harness.write_status(wiz="on")
    harness.monkeypatch.setattr(harness.mod, "DISCOVERY_INTERVAL", 0.01)
    harness.monkeypatch.setattr(harness.mod, "FAST_DISCOVERY_INTERVAL", 0.01)
    thread = threading.Thread(target=harness.mod.discovery_loop, daemon=True)
    thread.start()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not harness.sends:
        time.sleep(0.01)
    assert harness.sends, "expected discovery TX while ON"
    assert "getPilot" in harness.methods()
    harness.write_status(wiz="off")
    time.sleep(0.03)
    frozen = list(harness.sends)
    time.sleep(0.12)
    assert harness.sends == frozen
    harness.mod._loop_stop.set()
    thread.join(timeout=1.0)
    assert thread.is_alive() is False


def test_on_to_off_keepalive_stops_without_restart(harness):
    harness.write_status(wiz="on")
    harness.mod.apply_configured([MAC_A], ips={MAC_A: "10.42.0.20"})
    with harness.mod.devices_lock:
        harness.mod.devices[MAC_A] = {"ip": "10.42.0.20", "last_seen": 0.0}
    harness.monkeypatch.setattr(harness.mod, "KEEPALIVE_INTERVAL", 0.01)
    thread = threading.Thread(target=harness.mod.keepalive_loop, daemon=True)
    thread.start()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not harness.sends:
        time.sleep(0.01)
    assert harness.methods() == ["getPilot"] or "getPilot" in harness.methods()
    harness.write_status(wiz="off")
    time.sleep(0.03)
    frozen = list(harness.sends)
    time.sleep(0.12)
    assert harness.sends == frozen
    harness.mod._loop_stop.set()
    thread.join(timeout=1.0)
    assert thread.is_alive() is False


def test_worker_queued_dmx_while_off_does_not_send(harness):
    harness.write_status(wiz="on")
    harness.mod.apply_configured([MAC_A])
    with harness.mod.devices_lock:
        harness.mod.devices[MAC_A] = {"ip": "10.42.0.20", "last_seen": time.time()}
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[0:6] = bytes([200, 10, 20, 30, 0, 0])
    worker = harness.mod.FixtureWorker(MAC_A, 1, autostart=False)
    n = {"i": 0}
    sent_at_off = []

    def fake_sleep(_dt):
        n["i"] += 1
        if n["i"] == 4:
            sent_at_off.append(len(harness.sends))
            harness.write_status(wiz="off")
        if n["i"] > 16:
            worker.stop()

    harness.monkeypatch.setattr(harness.mod.time, "sleep", fake_sleep)
    worker.run()
    assert n["i"] > 16
    assert sent_at_off
    assert len(harness.sends) == sent_at_off[0]
    harness.sends.clear()
    harness.write_status(wiz="off")
    worker = harness.mod.FixtureWorker(MAC_A, 1, autostart=False)
    n["i"] = 0

    def fake_sleep_off(_dt):
        n["i"] += 1
        if n["i"] > 8:
            worker.stop()

    harness.monkeypatch.setattr(harness.mod.time, "sleep", fake_sleep_off)
    worker.run()
    assert harness.sends == []
    assert "setPilot" not in harness.methods()
    assert "getPilot" not in harness.methods()


def test_discovery_cadence_while_off_waits_without_tx(harness):
    harness.write_status(wiz="off")
    waits = []

    def fake_wait(timeout=None):
        waits.append(timeout)
        if len(waits) >= 4:
            harness.mod._loop_stop.set()
        return True

    harness.monkeypatch.setattr(harness.mod._loop_stop, "wait", fake_wait)
    harness.mod.discovery_loop()
    assert waits
    assert all(w == harness.mod.OFF_POLL or w == 0.01 for w in waits)
    assert harness.sends == []


def test_open_wiz_socket_and_sendto_are_gated(harness):
    harness.write_status(wiz="off")
    with pytest.raises(harness.mod.WizTxForbidden):
        harness.mod.open_wiz_socket(0.01)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(harness.mod.WizTxForbidden):
            harness.mod.wiz_sendto(sock, b"{}", ("10.42.0.20", 38899))
    finally:
        sock.close()
    assert harness.sends == []


def test_forbidden_dest_never_reaches_production_pi(harness):
    harness.write_status(wiz="on")
    assert harness.mod.wiz_dest_allowed("192.168.88.248") is False
    assert harness.mod.wiz_dest_allowed("192.168.88.201") is False
    assert harness.mod.wiz_dest_allowed("10.42.0.20") is True
    harness.mod.wiz_exchange("192.168.88.248", "getPilot")
    harness.mod.wiz_exchange("192.168.88.1", "setPilot", {"state": True})
    assert harness.sends == []


def test_auto_enroll_does_not_persist_or_assign_slot(harness):
    body = json.dumps(_legacy_doc(MAC_A, MAC_B), indent=2) + "\n"
    harness.fixtures_path.write_text(body, encoding="utf-8")
    before = harness.fixtures_path.read_bytes()
    macs = harness.mod.load_configured_devices()
    assert macs == [MAC_A, MAC_B]
    order_before = list(harness.mod.fixture_order)
    slots_before = dict(harness.mod.fixture_slots)
    harness.mod.apply_discovery(
        {
            MAC_NEW: {"ip": "10.42.0.99", "rssi": -40, "last_seen": time.time()},
            MAC_B: {"ip": "10.42.0.11", "rssi": -50, "last_seen": time.time()},
        }
    )
    assert MAC_NEW not in harness.mod.fixture_order
    assert MAC_NEW not in harness.mod.fixture_slots
    assert harness.mod.fixture_order == order_before
    assert harness.mod.fixture_slots == slots_before
    assert harness.fixtures_path.read_bytes() == before
    assert not harness.map_path.exists()
    with harness.mod.devices_lock:
        assert MAC_NEW in harness.mod.devices
        assert harness.mod.devices[MAC_B]["ip"] == "10.42.0.11"


def test_discovery_order_cannot_change_slot_order(harness):
    harness.map_path.write_text(json.dumps(_map_doc((MAC_A, 1), (MAC_B, 3))) + "\n", encoding="utf-8")
    before = harness.map_path.read_bytes()
    harness.mod.load_configured_devices()
    assert harness.mod.fixture_order == [MAC_A, MAC_B]
    assert harness.mod.fixture_slots == {MAC_A: 1, MAC_B: 3}
    found = {
        MAC_NEW: {"ip": "10.42.0.40", "last_seen": 1.0},
        MAC_B: {"ip": "10.42.0.12", "last_seen": 1.0},
        MAC_A: {"ip": "10.42.0.10", "last_seen": 1.0},
    }
    harness.mod.apply_discovery(found)
    assert harness.mod.fixture_order == [MAC_A, MAC_B]
    assert harness.mod.fixture_slots[MAC_B] == 3
    assert 2 not in harness.mod.fixture_slots.values()
    assert harness.map_path.read_bytes() == before
    doc = json.loads(harness.observed.read_text(encoding="utf-8"))
    ids = [row["id"] for row in doc["devices"]]
    assert MAC_A in ids and MAC_NEW in ids
    new_row = next(row for row in doc["devices"] if row["id"] == MAC_NEW)
    assert new_row["configured"] is False
    assert new_row["slot"] is None
    assert new_row["discovery"] == "NEW"


def test_missing_device_does_not_shift_slots(harness):
    harness.map_path.write_text(
        json.dumps(_map_doc((MAC_A, 1), (MAC_B, 2), (MAC_NEW, 7))) + "\n",
        encoding="utf-8",
    )
    harness.mod.load_configured_devices()
    harness.mod.apply_discovery({MAC_A: {"ip": "10.42.0.10", "last_seen": 1.0}})
    assert harness.mod.fixture_slots == {MAC_A: 1, MAC_B: 2, MAC_NEW: 7}
    assert harness.mod.fixture_order == [MAC_A, MAC_B, MAC_NEW]


def test_corrupt_map_is_not_replaced_with_empty_file(harness):
    harness.map_path.write_text("{not json", encoding="utf-8")
    before = harness.map_path.read_bytes()
    macs = harness.mod.load_configured_devices()
    assert macs == []
    assert harness.map_path.read_bytes() == before
    assert harness.mod.map_source == "invalid"


def test_failed_reload_keeps_previous_map(harness):
    harness.map_path.write_text(json.dumps(_map_doc((MAC_A, 1), (MAC_B, 3))) + "\n", encoding="utf-8")
    harness.mod.load_configured_devices()
    previous = list(harness.mod.fixture_order)
    slots = dict(harness.mod.fixture_slots)
    harness.map_path.write_text("{bad", encoding="utf-8")
    st = harness.map_path.stat()
    os.utime(harness.map_path, (st.st_mtime + 5, st.st_mtime + 5))
    assert harness.mod.try_reload_map() is False
    assert harness.mod.fixture_order == previous
    assert harness.mod.fixture_slots == slots


def test_legacy_load_does_not_write_map(harness):
    harness.fixtures_path.write_text(json.dumps(_legacy_doc(MAC_A)) + "\n", encoding="utf-8")
    before = harness.fixtures_path.read_bytes()
    harness.mod.load_configured_devices()
    assert harness.mod.map_source == "legacy"
    assert harness.mod.fixture_order == [MAC_A]
    assert harness.fixtures_path.read_bytes() == before
    assert not harness.map_path.exists()


def test_observed_status_has_no_credentials_and_is_atomic(harness):
    harness.write_status(wiz="off")
    harness.mod.apply_configured([MAC_A])
    harness.mod.publish_observed_status(force=True)
    text = harness.observed.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["state"] == "STOPPED"
    assert doc["wiz_tx"] == "off"
    blob = json.dumps(doc)
    assert "psk" not in blob.lower()
    assert "password" not in blob.lower()
    assert "secret" not in blob.lower()


def test_artnet_bind_is_loopback():
    src = BRIDGE_PATH.read_text(encoding="utf-8")
    assert 'ARTNET_BIND="127.0.0.1"' in src
    assert "s.bind((ARTNET_BIND,ARTNET_PORT))" in src
    assert 's.bind(("0.0.0.0",ARTNET_PORT))' not in src
    assert "enroll_new_fixtures" not in src
    assert "wiz_sendto" in src


def test_source_has_no_scattered_38899_sendto():
    src = BRIDGE_PATH.read_text(encoding="utf-8")
    sendto_lines = [ln.strip() for ln in src.splitlines() if ".sendto(" in ln]
    assert sendto_lines == ["return sock.sendto(payload,dest)"]
    assert src.count("wiz_sendto(") >= 3
    assert "enroll_new_fixtures" not in src


def test_first_map_created_after_empty_start_loads(harness):
    harness.mod.load_configured_devices()
    assert harness.mod.map_path is None
    assert harness.mod.fixture_order == []
    harness.map_path.write_text(
        json.dumps(_map_doc((MAC_A, 5), (MAC_B, 6))) + "\n", encoding="utf-8"
    )
    assert harness.mod.try_reload_map() is True
    assert harness.mod.map_path == str(harness.map_path)
    assert harness.mod.fixture_order == [MAC_A, MAC_B]
    assert harness.mod.fixture_slots == {MAC_A: 5, MAC_B: 6}
    assert harness.mod._map_mtime is not None
    st = harness.map_path.stat()
    os.utime(harness.map_path, (st.st_mtime + 5, st.st_mtime + 5))
    harness.map_path.write_text(
        json.dumps(_map_doc((MAC_A, 5), (MAC_B, 6), (MAC_NEW, 1))) + "\n",
        encoding="utf-8",
    )
    assert harness.mod.try_reload_map() is True
    assert MAC_NEW in harness.mod.fixture_slots
    assert harness.mod.fixture_slots[MAC_NEW] == 1


def test_invalid_first_map_is_rejected(harness):
    harness.mod.load_configured_devices()
    harness.map_path.write_text("{not json", encoding="utf-8")
    assert harness.mod.try_reload_map() is False
    assert harness.mod.fixture_order == []
    assert harness.mod.map_path is None
    assert harness.mod.map_source is None


def test_dmx_activity_from_artnet_changes_not_idle_frames(harness):
    harness.map_path.write_text(
        json.dumps(_map_doc((MAC_A, 5), (MAC_B, 6))) + "\n", encoding="utf-8"
    )
    before = harness.map_path.read_bytes()
    harness.mod.load_configured_devices()
    base = (5 - 1) * 6
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[base:base + 6] = bytes([10, 0, 0, 0, 0, 0])
    harness.mod.note_dmx_activity(now=100.0)
    active, last = harness.mod.slot_dmx_fields(MAC_A, now=100.0)
    assert active is False
    assert last is None
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[base] = 20
    sends_before = list(harness.sends)
    harness.mod.note_dmx_activity(now=100.2)
    assert harness.sends == sends_before
    active, last = harness.mod.slot_dmx_fields(MAC_A, now=100.2)
    assert active is True
    assert last == 100.2
    harness.mod.note_dmx_activity(now=100.5)
    active, _ = harness.mod.slot_dmx_fields(MAC_A, now=100.5)
    assert active is True
    hold = harness.mod.DMX_ACTIVITY_HOLD_S
    active, _ = harness.mod.slot_dmx_fields(MAC_A, now=100.2 + hold)
    assert active is False
    lost_base = (6 - 1) * 6
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[lost_base:lost_base + 6] = bytes([1, 2, 3, 4, 5, 6])
    harness.mod.note_dmx_activity(now=200.0)
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[lost_base] = 9
    harness.mod.note_dmx_activity(now=200.1)
    active, _ = harness.mod.slot_dmx_fields(MAC_B, now=200.1)
    assert active is True
    disabled = json.loads(harness.map_path.read_text(encoding="utf-8"))
    for item in disabled["devices"]:
        if item["id"] == MAC_A:
            item["enabled"] = False
    harness.map_path.write_text(json.dumps(disabled) + "\n", encoding="utf-8")
    st = harness.map_path.stat()
    os.utime(harness.map_path, (st.st_mtime + 5, st.st_mtime + 5))
    assert harness.mod.try_reload_map() is True
    harness.mod.note_dmx_activity(now=300.0)
    active, _ = harness.mod.slot_dmx_fields(MAC_A, now=300.0)
    assert active is False
    doc = harness.mod.observed_status_document()
    by_id = {row["id"]: row for row in doc["devices"]}
    assert "dmx_active" in by_id[MAC_A]
    assert by_id[MAC_A]["dmx_active"] is False
    assert "dmx_active" not in json.loads(before.decode())["devices"][0]
    live_map = json.loads(harness.map_path.read_text(encoding="utf-8"))
    assert "dmx_active" not in live_map["devices"][0]


def _pilot_calls(harness):
    out = []
    for data, dest in harness.sends:
        payload = json.loads(data.decode())
        ip = dest[0] if isinstance(dest, tuple) else dest
        out.append((payload.get("method"), payload.get("params") or {}, ip))
    return out


def _arm_device(harness, mac, ip, *, slot=None):
    if slot is not None:
        existing = list(harness.mod.fixture_order)
        slots = dict(harness.mod.fixture_slots)
        ips = dict(harness.mod.fixture_ips)
        if mac not in existing:
            existing.append(mac)
        slots[mac] = slot
        ips[mac] = ip
        enabled = {item: True for item in existing}
        harness.mod.apply_configured(existing, slots=slots, enabled=enabled, ips=ips)
    with harness.mod.devices_lock:
        harness.mod.devices[mac] = {"ip": ip, "last_seen": time.time()}


def test_identify_configured_white_then_restore_latest_dmx(harness):
    _arm_device(harness, MAC_A, "10.42.0.20", slot=1)
    _arm_device(harness, MAC_B, "10.42.0.21", slot=2)
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[0:6] = bytes([200, 10, 20, 30, 0, 0])
        harness.mod.latest_dmx[6:12] = bytes([80, 1, 2, 3, 0, 0])
    harness.status.write_text("wiz=on\nidentify=aabbccddeeff\n", encoding="utf-8")
    harness.mod.identify_once()
    assert harness.mod._identify_mac == MAC_A
    first = _pilot_calls(harness)
    assert first[-1] == ("setPilot", harness.mod.IDENTIFY_PARAMS, "10.42.0.20")
    assert all(item[0] != "getPilot" for item in first)

    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[0:6] = bytes([50, 9, 8, 7, 0, 0])
    latest = harness.mod.current_dmx_pilot_params(MAC_A)
    assert latest != harness.mod.IDENTIFY_PARAMS
    harness.sends.clear()
    harness.status.write_text("wiz=on\nidentify=bbccddeeff00\n", encoding="utf-8")
    harness.mod.identify_once()
    moved = _pilot_calls(harness)
    assert moved[0] == ("setPilot", latest, "10.42.0.20")
    assert moved[-1] == ("setPilot", harness.mod.IDENTIFY_PARAMS, "10.42.0.21")
    assert harness.mod._identify_mac == MAC_B
    whites = [item for item in moved if item[1] == harness.mod.IDENTIFY_PARAMS]
    assert whites == [("setPilot", harness.mod.IDENTIFY_PARAMS, "10.42.0.21")]


def test_identify_new_captures_getpilot_and_restores(harness):
    ip_a, ip_b = "10.42.0.40", "10.42.0.41"
    with harness.mod.devices_lock:
        harness.mod.devices[MAC_NEW] = {"ip": ip_a, "last_seen": time.time()}
        harness.mod.devices["ddeeff001122"] = {"ip": ip_b, "last_seen": time.time()}
    captured_a = {"state": True, "r": 10, "g": 20, "b": 30, "dimming": 40}
    captured_b = {"state": True, "temp": 2700, "dimming": 55}
    harness.replies.append(
        (json.dumps({"result": {"mac": MAC_NEW, "rssi": -40, **captured_a}}).encode(), (ip_a, 38899))
    )
    harness.replies.append((json.dumps({"result": {"success": True}}).encode(), (ip_a, 38899)))
    harness.status.write_text(f"wiz=on\nidentify={MAC_NEW}\n", encoding="utf-8")
    before_slots = dict(harness.mod.fixture_slots)
    harness.mod.identify_once()
    assert MAC_NEW not in harness.mod.fixture_slots
    assert harness.mod.fixture_slots == before_slots
    calls = _pilot_calls(harness)
    assert calls[0][0] == "getPilot" and calls[0][2] == ip_a
    assert calls[-1] == ("setPilot", harness.mod.IDENTIFY_PARAMS, ip_a)

    harness.sends.clear()
    harness.replies.append((json.dumps({"result": {"success": True}}).encode(), (ip_a, 38899)))
    harness.replies.append(
        (json.dumps({"result": {"mac": "ddeeff001122", **captured_b}}).encode(), (ip_b, 38899))
    )
    harness.replies.append((json.dumps({"result": {"success": True}}).encode(), (ip_b, 38899)))
    harness.status.write_text("wiz=on\nidentify=ddeeff001122\n", encoding="utf-8")
    harness.mod.identify_once()
    moved = _pilot_calls(harness)
    assert moved[0] == ("setPilot", captured_a, ip_a)
    assert ("getPilot", {}, ip_b) in [(m, p if m == "getPilot" else p, i) for m, p, i in moved] or any(
        item[0] == "getPilot" and item[2] == ip_b for item in moved
    )
    assert moved[-1] == ("setPilot", harness.mod.IDENTIFY_PARAMS, ip_b)
    assert harness.mod._identify_mac == "ddeeff001122"


def test_identify_wiz_off_sends_nothing(harness):
    _arm_device(harness, MAC_A, "10.42.0.20", slot=1)
    harness.status.write_text("wiz=off\nidentify=aabbccddeeff\n", encoding="utf-8")
    harness.mod.identify_once()
    assert harness.sends == []
    assert harness.mod._identify_mac == ""


def test_identify_lost_without_ip_does_not_tx_or_crash(harness):
    harness.mod.apply_configured([MAC_A], slots={MAC_A: 1}, enabled={MAC_A: True}, ips={})
    with harness.mod.devices_lock:
        harness.mod.devices[MAC_A] = {"last_seen": 0.0}
    harness.status.write_text("wiz=on\nidentify=aabbccddeeff\n", encoding="utf-8")
    harness.mod.identify_once()
    assert harness.sends == []
    assert harness.mod._identify_mac == MAC_A


def test_identify_does_not_mutate_map_or_enroll(harness):
    body = json.dumps(_map_doc((MAC_A, 1), (MAC_B, 2))) + "\n"
    harness.map_path.write_text(body, encoding="utf-8")
    before = harness.map_path.read_bytes()
    harness.mod.load_configured_devices()
    with harness.mod.devices_lock:
        harness.mod.devices[MAC_NEW] = {"ip": "10.42.0.99", "last_seen": time.time()}
    harness.status.write_text(f"wiz=on\nidentify={MAC_NEW}\n", encoding="utf-8")
    harness.mod.identify_once()
    harness.status.write_text("wiz=on\nidentify=\n", encoding="utf-8")
    harness.mod.identify_once()
    assert harness.map_path.read_bytes() == before
    assert MAC_NEW not in harness.mod.fixture_order
    assert MAC_NEW not in harness.mod.fixture_slots


def test_identify_dmx_activity_stays_independent(harness):
    harness.map_path.write_text(json.dumps(_map_doc((MAC_A, 1))) + "\n", encoding="utf-8")
    harness.mod.load_configured_devices()
    _arm_device(harness, MAC_A, "10.42.0.20", slot=1)
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[0:6] = bytes([1, 2, 3, 4, 5, 6])
    harness.mod.note_dmx_activity(now=50.0)
    harness.status.write_text("wiz=on\nidentify=aabbccddeeff\n", encoding="utf-8")
    harness.mod.identify_once()
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[0] = 9
    harness.mod.note_dmx_activity(now=50.2)
    active, _ = harness.mod.slot_dmx_fields(MAC_A, now=50.2)
    assert active is True
    assert harness.mod._identify_mac == MAC_A


def test_identify_worker_skips_dmx_while_selected(harness):
    _arm_device(harness, MAC_A, "10.42.0.20", slot=1)
    with harness.mod.dmx_lock:
        harness.mod.latest_dmx[0:6] = bytes([255, 10, 20, 30, 0, 0])
    harness.status.write_text("wiz=on\nidentify=aabbccddeeff\n", encoding="utf-8")
    worker = harness.mod.FixtureWorker(MAC_A, 1, autostart=False)
    n = {"i": 0}

    def fake_sleep(_dt):
        n["i"] += 1
        if n["i"] > 8:
            worker.stop()

    harness.monkeypatch.setattr(harness.mod.time, "sleep", fake_sleep)
    worker.run()
    assert n["i"] > 8
    assert harness.sends == []


def test_identify_parse_fail_closed():
    assert BRIDGE.parse_identify_mac("") == ""
    assert BRIDGE.parse_identify_mac("wiz=on\n") == ""
    assert BRIDGE.parse_identify_mac("identify=\n") == ""
    assert BRIDGE.parse_identify_mac("identify=notmac\n") == ""
    assert BRIDGE.parse_identify_mac("identify=98:77:d5:aa:41:30\n") == "9877d5aa4130"
    assert BRIDGE.parse_identify_mac("identify=9877d5aa4130\n") == "9877d5aa4130"

