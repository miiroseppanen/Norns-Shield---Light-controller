from pathlib import Path

from light_console.qxw import QxwError, prepare_file, prepare_for_shield, safe_show_name
import pytest

ROOT = Path(__file__).resolve().parents[1]
QXW = ROOT / "qlc/projects/light-console-test.qxw"

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
