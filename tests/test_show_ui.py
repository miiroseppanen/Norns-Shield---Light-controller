from pathlib import Path
import shutil
import time

from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K1, K2, K3
from light_console.merge import merge_files
from light_console.qlc.functions import QlcFunction
from light_console.state import ScreenId
from light_console.ui.menu import menu_index_of
from light_console.ui.vocab import LOAD, OPEN

from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]
SHOW_A = ROOT / "qlc/projects/show-a.qxw"
SHOW_B = ROOT / "qlc/projects/show-b.qxw"
MASTER = ROOT / "qlc/projects/master.qxw"


def _merged_controller(tmp_path: Path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(MASTER, shows / "master.qxw")
    merge_files(shows / "master.qxw", SHOW_A, show_id="show-a", show_name="SHOW A", apply=True)
    merge_files(shows / "master.qxw", SHOW_B, show_id="show-b", show_name="SHOW B", apply=True)
    c = make_controller(shows_dir=shows)
    live = []
    for show in c.catalog.list_shows():
        for ref, kind in (*( (s, "Scene") for s in show.scenes), *((ch, "Chaser") for ch in show.chasers)):
            live.append(QlcFunction(ref.function_id, ref.name, kind))
    c.qlc.replace_functions(live)
    c._applied_show = None
    c._refresh_show_state(force=True)
    return c


def test_scenes_e1_k3_go():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.screen = ScreenId.SCENES
    assert c.state.screen == ScreenId.SCENES
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.current_scene == c.state.scenes[1]
    c.qlc.function_sends.clear()
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.qlc.function_sends[-1] == (c.state.scene_function_ids[1], 1)
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.PLAY
    assert c.state.current_scene == c.state.scenes[1]


def test_chasers_e1_k3_go():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.screen = ScreenId.CHASERS
    c.inject_cooked(EncoderEvent(E1, 1))
    c.qlc.function_sends.clear()
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.qlc.function_sends[-1] == (c.state.chaser_function_ids[1], 1)


def test_play_k2_resets_sat_k3_resets_hue():
    c = make_controller()
    c.state.master = 80
    c.state.saturation = 40
    c.state.hue_shift = 90
    c.qlc.function_sends.clear()
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.saturation == 100
    assert c.state.hue_shift == 90
    assert c.state.master == 80
    assert c.qlc.function_sends == []
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.hue_shift == 0
    assert c.state.saturation == 100
    assert c.state.master == 80
    assert c.qlc.function_sends == []
    c.inject_cooked(ButtonEvent(K2, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.saturation == 100
    assert c.state.hue_shift == 0
    assert c.state.master == 80
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(EncoderEvent(E3, 1))
    assert c.state.current_scene == c.state.scenes[0]
    assert c.state.current_chaser == c.state.chasers[0]
    assert c.state.saturation == 101
    assert c.state.hue_shift == 1


def test_offline_go_does_not_replay_after_reconnect():
    c = make_controller()
    c.qlc.simulate_link(False)
    c.tick(now=1.0)
    c.qlc.function_sends.clear()
    c.state.screen = ScreenId.SCENES
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.go_status == "QLC OFFLINE"
    c.state.screen = ScreenId.CHASERS
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.qlc.function_sends == []
    c.qlc.simulate_link(True)
    c.tick(now=2.0)
    assert c.state.qlc_connected is True
    assert c.qlc.function_sends == []


def test_go_disabled_without_project():
    c = make_controller()
    c.qlc._project = False
    c.tick(now=1.0)
    c.qlc.function_sends.clear()
    c.state.screen = ScreenId.SCENES
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.go_status == "NO PROJECT"
    assert c.qlc.function_sends == []


def _wait_show_idle(c, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not c.state.show_busy:
            return
        time.sleep(0.02)
    raise AssertionError("workspace switch still busy")


def test_shows_menu_lists_files_and_loads_with_qlc_bounce(tmp_path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(SHOW_A, shows / "master.qxw")
    shutil.copy(SHOW_A, shows / "warm.qxw")
    shutil.copy(SHOW_B, shows / "full.qxw")
    before = (shows / "full.qxw").read_bytes()
    c = make_controller(shows_dir=shows)
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("SHOWS")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHOWS
    assert c.state.show_ids == ("full.qxw", "warm.qxw")
    assert c.state.show_files == ("FULL", "WARM")
    c.state.show_index = list(c.state.show_ids).index("full.qxw")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.LOAD_SHOW
    assert c.state.show_name == "FULL"
    assert c.state.show_status == LOAD
    c.inject_cooked(ButtonEvent(K3, "press"))
    _wait_show_idle(c)
    assert c.state.show_status == OPEN
    assert c.state.show_open_id == "full.qxw"
    assert c.state.screen == ScreenId.SHOWS
    assert (shows / "full.qxw").read_bytes() == before
    assert "light-console-show-b" in (shows / "master.qxw").read_text(encoding="utf-8")
    assert c.qlc_service.commands == ["stop", "start"]
    assert not (shows / ".reload-qlc").exists()
    c.state.show_index = list(c.state.show_ids).index("full.qxw")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.show_status == OPEN
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHOWS
    assert c.qlc_service.commands == ["stop", "start"]


def test_shows_empty_state():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("SHOWS")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHOWS
    assert c.state.show_files == ()
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHOWS


def test_go_refuses_when_engine_ids_differ(tmp_path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(MASTER, shows / "master.qxw")
    merge_files(shows / "master.qxw", SHOW_A, show_id="show-a", show_name="SHOW A", apply=True)
    c = make_controller(shows_dir=shows)
    c.qlc.function_sends.clear()
    c.state.screen = ScreenId.SCENES
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.go_status == "ID MISMATCH"
    assert c.qlc.function_sends == []


def test_go_refuses_when_live_name_differs(tmp_path):
    c = _merged_controller(tmp_path)
    c.qlc.replace_functions([QlcFunction(100, "Not Warm", "Scene")])
    c.qlc.function_sends.clear()
    c.state.screen = ScreenId.SCENES
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.go_status == "ID MISMATCH"
    assert c.qlc.function_sends == []


def test_go_sends_when_engine_matches_parsed_ids(tmp_path):
    c = _merged_controller(tmp_path)
    c.qlc.function_sends.clear()
    c.state.screen = ScreenId.SCENES
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.go_status == "GO"
    assert c.qlc.function_sends[-1] == (c.state.scene_function_ids[0], 1)
