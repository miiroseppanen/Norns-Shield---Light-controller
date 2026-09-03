from pathlib import Path

from light_console.qxw import parse_functions_file

ROOT = Path(__file__).resolve().parents[1]
SHIELD = ROOT / "qlc/projects/siirtyma-shield.qxw"


def test_siirtyma_shield_is_loopback_with_startup_and_launchpad():
    text = SHIELD.read_text(encoding="utf-8")
    assert "192.168.88.201" not in text
    assert "192.168.88.248" not in text
    assert "10.42." not in text
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
