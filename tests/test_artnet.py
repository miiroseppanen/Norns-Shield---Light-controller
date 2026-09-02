from pathlib import Path

from light_console.artnet.destinations import (
    OutputKind,
    classify_destination,
    is_forbidden_host,
)
from light_console.artnet.packet import OP_DMX, OP_POLL, build_artdmx, parse_artnet
from light_console.qlc.fake import FakeTransport
from light_console.qlc.ws_client import QlcWebSocketClient

ROOT = Path(__file__).resolve().parents[1]
QXW = ROOT / "qlc/projects/light-console-test.qxw"


def test_parse_artdmx_roundtrip():
    raw = build_artdmx(bytes([0, 128, 255]), sequence=7, port_address=0)
    pkt = parse_artnet(raw)
    assert pkt is not None
    assert pkt.opcode == OP_DMX
    assert pkt.opcode_name == "ArtDMX"
    assert pkt.sequence == 7
    assert pkt.port_address == 0
    assert pkt.universe == 0
    assert pkt.net == 0
    assert pkt.subnet == 0
    assert pkt.data[0] == 0
    assert pkt.data[1] == 128
    assert pkt.data[2] == 255


def test_parse_rejects_garbage():
    assert parse_artnet(b"") is None
    assert parse_artnet(b"hello") is None
    assert parse_artnet(b"Art-Net\x00\x00\x50") is None


def test_parse_artpoll():
    raw = b"Art-Net\x00" + OP_POLL.to_bytes(2, "little") + b"\x00\x0e"
    pkt = parse_artnet(raw)
    assert pkt is not None
    assert pkt.opcode_name == "ArtPoll"


def test_classify_loopback_vs_real():
    assert classify_destination("127.0.0.1") is OutputKind.SAFE_LOOPBACK
    assert classify_destination("192.168.88.201") is OutputKind.REAL_OUTPUT
    assert is_forbidden_host("192.168.88.201")
    assert is_forbidden_host("192.168.88.248")
    assert is_forbidden_host("10.42.0.1")
    assert not is_forbidden_host("127.0.0.1")


def test_qxw_artnet_is_loopback_only():
    text = QXW.read_text()
    lower = text.lower()
    assert "outputip=\"127.0.0.1\"" in lower
    assert 'uid="127.0.0.1"' in lower
    assert "outputuni=\"0\"" in lower
    assert "192.168.88.201" not in text
    assert "192.168.88.248" not in text
    assert "192.168.88.255" not in text
    assert "192.168.88.246" not in text
    assert "10.42." not in text
    assert "pknight" not in lower
    assert "launchpad" not in lower
    assert "siirtyma" not in lower
    for line in text.splitlines():
        if "outputip" in line.lower():
            assert "127.0.0.1" in line


def test_ws_refuses_lan_artnet_line():
    fake = FakeTransport()
    qlc = QlcWebSocketClient(transport_factory=lambda: fake, reconnect_seconds=0.01)
    qlc.pump(0.0)
    qlc.patch_output(0, "ArtNet|1")
    assert not any("ArtNet|1" in s for s in fake.sent)
    qlc.patch_output(0, "ArtNet|0")
    qlc.set_simple_desk_channel(1, 255)
    assert "QLC+IO|OUTPUT|0|ArtNet|0" in fake.sent
    assert "CH|1|255" in fake.sent
    qlc.close()
