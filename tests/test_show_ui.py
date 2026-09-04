from pathlib import Path
import shutil

from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K1, K2, K3
from light_console.merge import merge_files
from light_console.qlc.functions import QlcFunction
from light_console.state import ScreenId

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


def test_scenes_e1_k3_go_shared_with_play():
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


def test_play_k2_scene_go_k3_chaser_go():
    c = make_controller()
    c.qlc.function_sends.clear()
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.qlc.function_sends[-1] == (c.state.scene_function_ids[0], 1)
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.qlc.function_sends[-1] == (c.state.chaser_function_ids[0], 1)
    c.inject_cooked(EncoderEvent(E2, 1))
    c.inject_cooked(EncoderEvent(E3, 1))
    assert c.state.current_scene == c.state.scenes[1]
    assert c.state.current_chaser == c.state.chasers[1]


def test_offline_go_does_not_replay_after_reconnect():
    c = make_controller()
    c.qlc.simulate_link(False)
    c.tick(now=1.0)
    c.qlc.function_sends.clear()
    c.inject_cooked(ButtonEvent(K2, "press"))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.go_status == "QLC OFFLINE"
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
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.go_status == "NO PROJECT"
    assert c.qlc.function_sends == []


def test_show_switch_a_to_b_without_qlc_reload(tmp_path):
    c = _merged_controller(tmp_path)
    assert c.state.show_files == ("SHOW A", "SHOW B")
    assert c.state.show_ids == ("show-a", "show-b")
    assert c.state.scenes == ("Warm", "Blue", "Red")
    assert c.state.chasers == ("Slow Pulse", "Color Sweep")
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.screen = ScreenId.SHOWS
    assert c.state.screen == ScreenId.SHOWS
    c.state.show_index = list(c.state.show_ids).index("show-b")
    c.qlc.function_sends.clear()
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.LOAD_SHOW
    assert c.state.scenes == ("Full", "Dim", "Blackout")
    assert c.state.chasers == ("Fast Pulse", "Alternate")
    assert c.state.show_name == "SHOW B"
    assert c.state.show_status == "ACTIVE"
    assert c.state.current_scene == "Full"
    assert c.state.current_chaser == "Fast Pulse"
    assert c.state.scene_index == 0
    assert c.state.chaser_index == 0
    assert c.qlc.function_sends == []
    assert not (c.catalog.shows_dir / ".reload-qlc").exists()
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.SHOWS
    c.state.show_index = list(c.state.show_ids).index("show-a")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.scenes[0] == "Warm"
    assert c.state.show_name == "SHOW A"
    assert c.state.current_scene == "Warm"


def test_go_refuses_when_engine_ids_differ(tmp_path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(MASTER, shows / "master.qxw")
    merge_files(shows / "master.qxw", SHOW_A, show_id="show-a", show_name="SHOW A", apply=True)
    c = make_controller(shows_dir=shows)
    c.qlc.function_sends.clear()
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.go_status == "ID MISMATCH"
    assert c.qlc.function_sends == []


def test_go_refuses_when_live_name_differs(tmp_path):
    c = _merged_controller(tmp_path)
    c.qlc.replace_functions([QlcFunction(100, "Not Warm", "Scene")])
    c.qlc.function_sends.clear()
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.go_status == "ID MISMATCH"
    assert c.qlc.function_sends == []


def test_go_sends_when_engine_matches_parsed_ids(tmp_path):
    c = _merged_controller(tmp_path)
    c.qlc.function_sends.clear()
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.go_status == "GO"
    assert c.qlc.function_sends[-1] == (c.state.scene_function_ids[0], 1)
