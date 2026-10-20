"""Source → transform → mocked Art-Net / setPilot path. No physical TX."""

from __future__ import annotations

import time
from pathlib import Path

from light_console.artnet.packet import build_artdmx, parse_artnet
from light_console.fixture_roles import (
    SOURCE_CCT_WHITE,
    SOURCE_CHROMATIC,
    classify_wiz_slot,
    transform_par_channels,
    transform_wiz_channels,
)
from light_console.output.fixtures import PatchedFixture
from light_console.output.live_path import (
    LiveControlsCache,
    MockArtNetSink,
    emit_wired_frame,
    parse_live_controls,
    trace_fixture,
    transform_artdmx_packet,
    transform_dmx_universe,
    wiz_setpilot_params,
)
from light_console.output.wiz_pilot import build_on_params

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "services/wiz/wiz_artnet_bridge.py"

PAR = PatchedFixture(
    3,
    "PAR",
    1,
    0,
    8,
    manufacturer="Oloaxolx",
    model="60 W Battery LED Par Spot",
    mode="8ch",
)
WIZ = PatchedFixture(
    6,
    "WIZ",
    0,
    0,
    6,
    manufacturer="WiZ",
    model="WiZ RGB+CCT via Pi",
    mode="6 Channel",
)
FOG = PatchedFixture(
    0,
    "FOG",
    1,
    32,
    1,
    manufacturer="Eurolite",
    model="N-150 MK2",
    mode="1 channel mode",
)


def _uni(**channels: int) -> list[int]:
    out = [0] * 512
    for key, val in channels.items():
        out[int(key)] = val
    return out


def test_par_source_to_wired_artdmx_frame():
    src = _uni(**{"0": 200, "1": 40, "2": 255, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0})
    pkt = build_artdmx(bytes(src), sequence=9, port_address=1)
    sink = MockArtNetSink()
    out = emit_wired_frame(pkt, (PAR, FOG), sat=100, hue=120, sink=sink, dest=("192.168.88.242", 6454))
    assert sink.sent[0][0] == ("192.168.88.242", 6454)
    parsed = parse_artnet(out)
    assert parsed is not None
    assert parsed.port_address == 1
    assert parsed.sequence == 9
    dmx = list(parsed.data) + [0] * (512 - len(parsed.data))
    assert dmx[0] == 200
    assert dmx[1] == 40
    assert dmx[2:5] == [0, 255, 0]
    assert dmx[5:8] == [0, 0, 0]
    assert dmx[32] == 0
    ident = transform_artdmx_packet(pkt, (PAR,), sat=100, hue=0)
    assert ident == pkt
    trace = trace_fixture(src, PAR, sat=100, hue=120)
    assert trace.source == (200, 40, 255, 0, 0, 0, 0, 0)
    assert trace.transformed == (200, 40, 0, 255, 0, 0, 0, 0)
    assert trace.classification == SOURCE_CHROMATIC


def test_par_path_is_not_appstate_only():
    src = _uni(**{"0": 200, "2": 255})
    frame = transform_dmx_universe(src, (PAR,), sat=100, hue=120)
    assert frame[2:5] == [0, 255, 0]
    assert frame is not src
    assert src[2:5] == [255, 0, 0]


def test_dynamic_chaser_frames_are_independent():
    sink = MockArtNetSink()
    frames = [
        _uni(**{"0": 200, "2": 255}),
        _uni(**{"0": 200, "3": 255}),
        _uni(**{"0": 200, "4": 255}),
    ]
    outputs = []
    for src in frames:
        pkt = build_artdmx(bytes(src), port_address=1)
        out = emit_wired_frame(pkt, (PAR,), sat=100, hue=120, sink=sink, dest=("192.168.88.242", 6454))
        parsed = parse_artnet(out)
        outputs.append(tuple(parsed.data[2:5]))
    assert outputs[0] == (0, 255, 0)
    assert outputs[1] == (0, 0, 255)
    assert outputs[2] == (255, 0, 0)
    assert len(sink.sent) == 3


def test_reversibility_from_source_not_previous_output():
    src = (200, 0, 255, 40, 10, 0, 8, 9)
    once = transform_par_channels(src, sat=30, hue=90)
    twice = transform_par_channels(once, sat=150, hue=-20)
    restored = transform_par_channels(src, sat=100, hue=0)
    assert restored == src
    assert twice != src
    assert transform_par_channels(src, sat=100, hue=0) == src


def test_master_not_applied_on_wired_color_path():
    src = _uni(**{"0": 200, "2": 255})
    out = transform_dmx_universe(src, (PAR,), sat=50, hue=0)
    assert out[0] == 200
    rgb = out[2:5]
    assert rgb[0] == rgb[1] == rgb[2] or rgb[1] > 0


def test_wiz_rgb_setpilot_path():
    slot = (200, 255, 0, 0, 0, 40)
    assert classify_wiz_slot(slot) == SOURCE_CHROMATIC
    params = wiz_setpilot_params(slot, sat=100, hue=120, wiz_enabled=True)
    assert params is not None
    assert params["state"] is True
    assert params["r"] == 0
    assert params["g"] == 255
    assert params["b"] == 0
    assert "temp" not in params
    sat0 = wiz_setpilot_params(slot, sat=0, hue=120, wiz_enabled=True)
    assert sat0["r"] == sat0["g"] == sat0["b"] == 255
    assert sat0.get("r") == 255
    identity = wiz_setpilot_params(slot, sat=100, hue=0, wiz_enabled=True)
    assert identity == build_on_params(*slot)
    assert wiz_setpilot_params(slot, sat=0, hue=90, wiz_enabled=False) is None


def test_wiz_cct_mode_is_not_colorized():
    slot = (200, 255, 0, 0, 90, 40)
    assert classify_wiz_slot(slot) == SOURCE_CCT_WHITE
    params = wiz_setpilot_params(slot, sat=0, hue=120, wiz_enabled=True)
    assert params is not None
    assert "temp" in params
    assert "r" not in params
    transformed = transform_wiz_channels(slot, sat=0, hue=120)
    assert transformed == slot
    off = wiz_setpilot_params((0, 255, 0, 0, 0, 0), sat=100, hue=0, wiz_enabled=True)
    assert off == {"state": False}


def test_wiz_bridge_wires_live_color():
    src = BRIDGE.read_text(encoding="utf-8")
    assert "transform_wiz_channels" in src
    assert "live_controls_cached" in src
    assert "_live_sat_hue_wiz" in src
    assert "wiz_tx_allowed" in src


def test_status_controls_cache(tmp_path):
    path = tmp_path / "light-console.status"
    path.write_text("sat=40\nhue=-15\nmaster=80\nwiz=off\n", encoding="utf-8")
    cache = LiveControlsCache(path)
    c = cache.read()
    assert c.sat == 40
    assert c.hue == -15
    assert c.master == 80
    assert c.wiz_enabled is False
    assert c.color_identity is False
    parsed = parse_live_controls("sat=100\nhue=0\nwiz=on\n")
    assert parsed.color_identity is True
    assert parsed.wiz_enabled is True
    assert parsed.identify_mac == ""
    ident = parse_live_controls("identify=98:77:d5:aa:41:30\nwiz=on\n")
    assert ident.identify_mac == "9877d5aa4130"
    assert parse_live_controls("identify=not-a-mac\n").identify_mac == ""
    assert parse_live_controls("identify=\n").identify_mac == ""
    assert parse_live_controls("wiz=on\ndiscover=1\n").discover is True
    assert parse_live_controls("wiz=on\ndiscover=on\n").discover is True
    assert parse_live_controls("wiz=on\ndiscover=\n").discover is False
    assert parse_live_controls("wiz=on\ndiscover=yes\n").discover is False
    assert parse_live_controls("wiz=on\n").discover is False


def test_frame_processing_is_bounded():
    src = _uni(**{"0": 200, "2": 255, "32": 180})
    pkt = build_artdmx(bytes(src), port_address=1)
    sink = MockArtNetSink()
    t0 = time.perf_counter()
    for i in range(3000):
        hue = (i % 360) - 180
        emit_wired_frame(pkt, (PAR, FOG), sat=80, hue=hue, sink=sink, dest=("127.0.0.1", 6454))
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.5
    assert len(sink.sent) == 3000


def test_live_path_has_no_shell_or_network_hot_path():
    text = (ROOT / "light_console/output/live_path.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "nmcli" not in text
    assert "import socket" not in text
    assert "urlopen" not in text
    roles = (ROOT / "light_console/fixture_roles.py").read_text(encoding="utf-8")
    assert "subprocess" not in roles
    assert "nmcli" not in roles
