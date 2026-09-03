from pathlib import Path

import pytest

from light_console.machine import (
    LaunchpadBinding,
    MachineProfileError,
    ShieldMachineProfile,
    load_machine_profile,
)
from light_console.midi_wait import wait_for_launchpad
from light_console.qxw import (
    format_midi_report,
    prepare_file,
    prepare_for_shield_report,
)

ROOT = Path(__file__).resolve().parents[1]
SHOW_A = ROOT / "qlc/projects/show-a.qxw"

LAUNCHPAD_SRC = """\
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

UNRELATED = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Workspace>
<Workspace xmlns="http://www.qlcplus.org/Workspace">
 <Engine>
  <InputOutputMap>
   <Universe Name="Universe 1" ID="0">
    <Input Plugin="MIDI" Name="APC mini MIDI 1" UID="usb-apc" Line="0" Profile="Akai APC Mini"/>
    <Output Plugin="ArtNet" UID="127.0.0.1" Line="0">
     <PluginParameters outputIP="127.0.0.1" outputUni="0"/>
    </Output>
    <Feedback Plugin="MIDI" Name="APC mini MIDI 1" UID="usb-apc" Line="0"/>
   </Universe>
  </InputOutputMap>
 </Engine>
</Workspace>
"""


def _profile(**kwargs) -> ShieldMachineProfile:
    data = dict(
        name="Launchpad Mini MIDI 1",
        uid="1-1.2:0",
        profile="Novation Launchpad Mini",
        usb_id="1235:0036",
        line_fallback="1",
    )
    data.update(kwargs)
    return ShieldMachineProfile(launchpad=LaunchpadBinding(**data))


def test_machine_profile_loads_repo_defaults():
    machine = load_machine_profile()
    assert machine.launchpad.name == "Launchpad Mini MIDI 1"
    assert machine.launchpad.uid == "1-1.2:0"
    assert machine.launchpad.profile == "Novation Launchpad Mini"


def test_missing_machine_profile_fails_safely(tmp_path):
    with pytest.raises(MachineProfileError, match="missing"):
        load_machine_profile(tmp_path / "nope.yaml")
    incomplete = tmp_path / "bad.yaml"
    incomplete.write_text("launchpad:\n  name: \"x\"\n")
    with pytest.raises(MachineProfileError, match="required"):
        load_machine_profile(incomplete)


def test_none_none_line0_rewrites_input_and_feedback():
    patched, changes = prepare_for_shield_report(LAUNCHPAD_SRC, profile=_profile())
    assert 'Name="Launchpad Mini MIDI 1"' in patched
    assert 'UID="1-1.2:0"' in patched
    assert 'Line="1"' in patched
    assert 'Profile="Novation Launchpad Mini"' in patched
    kinds = {c.kind: c for c in changes}
    assert kinds["INPUT"].old_name == "None"
    assert kinds["INPUT"].old_uid == "None"
    assert kinds["INPUT"].old_line == "0"
    assert kinds["INPUT"].new_name == "Launchpad Mini MIDI 1"
    assert kinds["INPUT"].new_uid == "1-1.2:0"
    assert kinds["FEEDBACK"].old_name == "None"
    assert kinds["FEEDBACK"].new_uid == "1-1.2:0"
    report = format_midi_report(changes)
    assert "MIDI INPUT:" in report
    assert "old: None / None / Line 0" in report
    assert "new: Launchpad Mini MIDI 1 / 1-1.2:0" in report
    assert "MIDI FEEDBACK:" in report
    assert "28" not in patched


def test_unrelated_midi_not_patched():
    patched, changes = prepare_for_shield_report(UNRELATED, profile=_profile())
    assert changes == ()
    assert 'Name="APC mini MIDI 1"' in patched
    assert 'UID="usb-apc"' in patched
    assert "Launchpad Mini MIDI 1" not in patched


def test_machine_profile_controls_name_and_uid():
    other = _profile(name="Other Pad MIDI 1", uid="9-9.9:0")
    patched, changes = prepare_for_shield_report(LAUNCHPAD_SRC, profile=other)
    assert changes[0].new_name == "Other Pad MIDI 1"
    assert 'UID="9-9.9:0"' in patched
    assert "1-1.2:0" not in patched


def test_existing_shield_binding_is_idempotent():
    first, _ = prepare_for_shield_report(LAUNCHPAD_SRC, profile=_profile())
    second, changes = prepare_for_shield_report(first, profile=_profile())
    assert second == first
    assert all(c.old_name == c.new_name and c.old_uid == c.new_uid for c in changes)


def test_dry_run_report_on_show_a_copy(tmp_path):
    src = tmp_path / "show-a.qxw"
    dest = tmp_path / "show-a-shield.qxw"
    original = SHOW_A.read_text()
    src.write_text(
        original.replace(
            '<Universe Name="Loopback" ID="0">',
            '<Universe Name="Loopback" ID="0">\n'
            '    <Input Plugin="MIDI" Name="None" UID="None" Line="0"'
            ' Profile="Novation Launchpad Mini"/>\n'
            '    <Feedback Plugin="MIDI" Name="None" UID="None" Line="0"/>',
            1,
        )
    )
    before = src.read_text()
    patched = prepare_file(src, dest, profile=_profile())
    assert src.read_text() == before
    assert SHOW_A.read_text() == original
    assert 'Plugin="MIDI"' in patched
    assert 'Name="Launchpad Mini MIDI 1"' in patched
    assert 'UID="1-1.2:0"' in patched
    assert 'Profile="Novation Launchpad Mini"' in patched
    assert 'outputIP="127.0.0.1"' in patched
    assert "192.168.88.201" not in patched
    assert "192.168.88.248" not in patched


def test_wait_for_launchpad_times_out_and_still_ok():
    seen = {"n": 0}

    def missing(_profile):
        seen["n"] += 1
        return False

    clock = {"t": 0.0}

    def now():
        return clock["t"]

    def sleep(dt):
        clock["t"] += dt

    present = wait_for_launchpad(
        _profile(), timeout_s=1.0, visible=missing, now=now, sleep=sleep
    )
    assert present is False
    assert seen["n"] >= 2


def test_wait_for_launchpad_returns_when_visible():
    assert wait_for_launchpad(_profile(), timeout_s=1.0, visible=lambda _p: True) is True
    wait_src = (ROOT / "light_console/midi_wait.py").read_text()
    assert "28" not in wait_src
    assert "client" not in wait_src.lower() or "client number" in wait_src
