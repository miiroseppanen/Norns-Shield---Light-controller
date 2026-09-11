from pathlib import Path
import xml.etree.ElementTree as ET

from light_console.qxw import _DOCTYPE, parse_functions_file, _parse_workspace

ROOT = Path(__file__).resolve().parents[1]
SHIELD = ROOT / "qlc/projects/siirtyma-shield.qxw"

FORBIDDEN_OUTPUT_HOSTS = (
    "192.168.88.201",
    "192.168.88.242",
    "192.168.88.244",
    "192.168.88.246",
    "192.168.88.248",
    "192.168.88.255",
    "255.255.255.255",
    "10.42.",
)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def test_siirtyma_shield_is_loopback_with_startup_and_launchpad():
    text = SHIELD.read_text(encoding="utf-8")
    root = _parse_workspace(text)
    for host in FORBIDDEN_OUTPUT_HOSTS:
        assert host not in text
    assert text.count('outputIP="127.0.0.1"') == 2
    assert 'Name="Launchpad Mini MIDI 1"' in text
    assert 'UID="1-1.2:0"' in text
    assert 'Profile="Novation Launchpad Mini"' in text
    fns = parse_functions_file(SHIELD)
    startup = [fn for fn in fns if fn.name == "startup"]
    assert len(startup) == 1
    assert startup[0].function_id == 0
    assert startup[0].type_name == "Chaser"
    assert len(fns) == 100
    assert [fn.name for fn in fns].count("startup") == 1
    ids = [fn.function_id for fn in fns]
    assert len(ids) == len(set(ids))

    fixtures = []
    for node in root.iter():
        if _local(node.tag) != "Fixture":
            continue
        fields = {_local(child.tag): (child.text or "").strip() for child in list(node)}
        universe = int(fields["Universe"])
        address = int(fields["Address"])
        channels = int(fields["Channels"])
        fixtures.append((int(fields["ID"]), universe, address, channels))
        assert universe >= 0
        assert address >= 0
        assert channels > 0
        assert address + channels <= 512
    assert fixtures
    assert len({row[0] for row in fixtures}) == len(fixtures)

    artnet = []
    for node in root.iter():
        if _local(node.tag) != "Universe":
            continue
        uid = node.attrib.get("ID")
        if uid is None:
            continue
        for child in list(node):
            if _local(child.tag) != "Output":
                continue
            if (child.attrib.get("Plugin") or "").lower() != "artnet":
                continue
            ip = ""
            for param in list(child):
                if _local(param.tag) == "PluginParameters":
                    ip = param.attrib.get("outputIP") or ""
            artnet.append(
                (
                    int(uid),
                    child.attrib.get("Line"),
                    child.attrib.get("UID"),
                    ip,
                )
            )
    assert artnet == [
        (0, "0", "127.0.0.1", "127.0.0.1"),
        (1, "0", "127.0.0.1", "127.0.0.1"),
    ]
    assert 'Caption="PAR-GREEN"' in text
    ET.fromstring(_DOCTYPE.sub("", text, count=1))
