from pathlib import Path

from light_console.qxw import (
    QxwError,
    parse_functions,
    parse_functions_file,
    prepare_file,
    prepare_for_shield,
    safe_show_name,
)
import pytest

ROOT = Path(__file__).resolve().parents[1]
QXW = ROOT / "qlc/projects/light-console-test.qxw"
SHOW_A = ROOT / "qlc/projects/show-a.qxw"
SHOW_B = ROOT / "qlc/projects/show-b.qxw"

UNSAFE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Workspace>
<Workspace xmlns="http://www.qlcplus.org/Workspace">
 <Engine>
  <InputOutputMap>
   <Universe Name="U0" ID="0">
    <Output Plugin="ArtNet" UID="192.168.88.201" Line="1">
     <PluginParameters outputIP="192.168.88.201" outputUni="0"/>
    </Output>
   </Universe>
  </InputOutputMap>
 </Engine>
</Workspace>
"""

STUCK = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Workspace>
<Workspace xmlns="http://www.qlcplus.org/Workspace">
 <Engine>
  <InputOutputMap>
   <Universe Name="U0" ID="0">
    <Output Plugin="ArtNet" UID="127.0.0.1" Line="0">
     <PluginParameters outputIP="127.0.0.1" outputUni="0"/>
    </Output>
   </Universe>
  </InputOutputMap>
  <Note>production 192.168.88.248</Note>
 </Engine>
</Workspace>
"""


def test_safe_show_name():
    assert safe_show_name(Path("cues.qxw")) == "cues.qxw"
    assert safe_show_name(Path("/tmp/My Show.qxw")) == "My_Show.qxw"
    with pytest.raises(QxwError):
        safe_show_name(Path("notes.txt"))


def test_prepare_test_workspace_is_stable():
    text = QXW.read_text()
    patched = prepare_for_shield(text)
    assert 'outputIP="127.0.0.1"' in patched
    assert 'UID="127.0.0.1"' in patched
    assert "192.168.88.201" not in patched


def test_prepare_rewrites_artnet_and_leaves_source_alone(tmp_path):
    src = tmp_path / "show.qxw"
    dest = tmp_path / "patched.qxw"
    src.write_text(UNSAFE)
    original = src.read_text()
    prepare_file(src, dest)
    assert src.read_text() == original
    out = dest.read_text()
    assert "192.168.88.201" not in out
    assert 'UID="127.0.0.1"' in out
    assert 'Line="0"' in out
    assert 'outputIP="127.0.0.1"' in out


def test_prepare_refuses_forbidden_leftovers():
    with pytest.raises(QxwError, match="forbidden address"):
        prepare_for_shield(STUCK)


def test_prepare_refuses_garbage():
    with pytest.raises(QxwError):
        prepare_for_shield("not xml")
    with pytest.raises(QxwError):
        prepare_for_shield("<NotWorkspace/>")


def test_prepare_file_refuses_overwrite_source(tmp_path):
    src = tmp_path / "show.qxw"
    src.write_text(QXW.read_text())
    with pytest.raises(QxwError, match="overwrite"):
        prepare_file(src, src)


def test_show_a_and_b_have_distinct_safe_metadata():
    a = parse_functions_file(SHOW_A)
    b = parse_functions_file(SHOW_B)
    assert [fn.name for fn in a if fn.type_name == "Scene"] == ["Warm", "Blue", "Red"]
    assert [fn.name for fn in a if fn.type_name == "Chaser"] == ["Slow Pulse", "Color Sweep"]
    assert [fn.name for fn in b if fn.type_name == "Scene"] == ["Full", "Dim", "Blackout"]
    assert [fn.name for fn in b if fn.type_name == "Chaser"] == ["Fast Pulse", "Alternate"]
    for path in (SHOW_A, SHOW_B):
        text = path.read_text().lower()
        assert "192.168.88.201" not in text
        assert "pknight" not in text
        assert "launchpad" not in text
        assert 'outputip="127.0.0.1"' in text
        prepare_for_shield(path.read_text())


def test_prepare_rewrites_midi_none_uid_to_launchpad_port_name():
    text = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Workspace>
<Workspace xmlns="http://www.qlcplus.org/Workspace">
 <Engine>
  <InputOutputMap>
   <Universe Name="Universe 1" ID="0">
    <Input Plugin="MIDI" Name="None" UID="None" Line="0" Profile="Novation Launchpad Mini"/>
    <Output Plugin="ArtNet" Name="192.168.88.254" UID="" Line="1">
     <PluginParameters UniverseChannels="42" outputIP="192.168.88.248"/>
    </Output>
    <Feedback Plugin="MIDI" Name="None" UID="None" Line="0"/>
   </Universe>
  </InputOutputMap>
 </Engine>
</Workspace>
"""
    patched = prepare_for_shield(text)
    assert 'Name="Launchpad Mini MIDI 1"' in patched
    assert 'UID="1-1.2:0"' in patched
    assert 'UID="None"' not in patched
    assert 'Name="None"' not in patched
    assert 'Profile="Novation Launchpad Mini"' in patched
    assert 'outputIP="127.0.0.1"' in patched
    assert 'Line="1"' in patched
    assert "client 28" not in patched


def test_parse_functions_rejects_non_workspace():
    with pytest.raises(QxwError):
        parse_functions("<nope/>")

