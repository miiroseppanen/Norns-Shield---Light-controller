from pathlib import Path
import xml.etree.ElementTree as ET

from light_console.output.mutate import (
    RoutePatchError,
    patch_managed_artnet,
    preserve_managed_universe,
    universe_block,
    universe_channels,
)
from light_console.output.routing import parse_output_routes
from light_console.output.targets import (
    AIR2DMX_FALLBACK_IP,
    MANAGED_QLC_UNIVERSE,
    TargetId,
    apply_plan_for,
)
from light_console.qxw import _DOCTYPE, parse_functions_file, _parse_workspace, prepare_for_shield

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
    assert len(fns) == 109
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
    assert universe_channels(text, 0) == 512
    assert universe_channels(text, 1) == 33
    wiz = [row for row in fixtures if row[1] == 0 and row[3] == 6]
    assert len(wiz) == 7
    assert {row[2] for row in wiz} == {0, 6, 12, 18, 24, 30, 36}
    assert 'Caption="PAR-GREEN"' in text
    ET.fromstring(_DOCTYPE.sub("", text, count=1))


def _u2(text: str, ip: str) -> str:
    plan = apply_plan_for(TargetId.AIR2DMX, ip, lan_uid="192.168.88.246")
    return patch_managed_artnet(text, plan)


def test_preserve_managed_universe_keeps_wiz_and_current_u2():
    original = SHIELD.read_text(encoding="utf-8")
    prepared = prepare_for_shield(original)
    current = _u2(original, AIR2DMX_FALLBACK_IP)
    merged = preserve_managed_universe(prepared, current)
    assert universe_block(merged, 0) == universe_block(prepared, 0)
    assert universe_block(merged, 1) == universe_block(current, 1)
    routes = parse_output_routes(merged)
    assert routes[0].output_ip == "127.0.0.1"
    assert routes[1].qlc_universe == MANAGED_QLC_UNIVERSE
    assert routes[1].output_ip == AIR2DMX_FALLBACK_IP
    assert "192.168.88.248" not in merged
    assert original.count("startup") >= 1


def test_preserve_managed_universe_refuses_production_pi():
    original = SHIELD.read_text(encoding="utf-8")
    poisoned = original.replace("PAR-GREEN", "192.168.88.248")
    try:
        preserve_managed_universe(original, poisoned)
        raise AssertionError("expected production Pi refusal")
    except RoutePatchError:
        pass
