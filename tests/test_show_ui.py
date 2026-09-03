from pathlib import Path
import shutil

from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, E3, K1, K2, K3
from light_console.state import ScreenId
from light_console.ui.menu import menu_index_of

from tests.conftest import make_controller

ROOT = Path(__file__).resolve().parents[1]


def _catalog_controller(tmp_path: Path):
    shows = tmp_path / "shows"
    shows.mkdir()
    shutil.copy(ROOT / "qlc/projects/show-a.qxw", shows / "show-a.qxw")
    shutil.copy(ROOT / "qlc/projects/show-b.qxw", shows / "show-b.qxw")
    c = make_controller(shows_dir=shows)
    c.catalog.select("show-a.qxw")
    c.catalog.mark_good()
    c._applied_show = None
    c._refresh_show_state(force=True)
    return c


def test_scenes_e1_k3_go_shared_with_play():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("SCENES")
    c.inject_cooked(ButtonEvent(K3, "press"))
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
    c.state.menu_index = menu_index_of("CHASERS")
    c.inject_cooked(ButtonEvent(K3, "press"))
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


def test_show_switch_a_to_b_and_back(tmp_path):
    c = _catalog_controller(tmp_path)
    assert c.state.scenes == ("Warm", "Blue", "Red")
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("SHOWS")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHOWS
    c.state.show_index = list(c.state.show_files).index("show-b.qxw")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.LOAD_SHOW
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.scenes == ("Full", "Dim", "Blackout")
    assert c.state.chasers == ("Fast Pulse", "Alternate")
    assert c.catalog.current_name() == "show-b.qxw"
    c.state.show_index = list(c.state.show_files).index("show-a.qxw")
    c.nav.open_load_show_confirm(c.state)
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.scenes[0] == "Warm"
    assert c.catalog.current_name() == "show-a.qxw"
    assert c.state.show_status == "WEB LOAD"
    assert c.state.screen == ScreenId.SHOWS


def test_show_k3_does_not_claim_qlc_load(tmp_path):
    c = _catalog_controller(tmp_path)
    c.qlc.function_sends.clear()
    c.nav.open_load_show_confirm(c.state)
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.show_status == "WEB LOAD"
    assert c.state.show_status != "OK"
    assert c.qlc.function_sends == []
    assert not (c.catalog.shows_dir / ".reload-qlc").exists()


def test_go_refuses_when_engine_ids_differ(tmp_path):
    c = _catalog_controller(tmp_path)
    c.qlc.function_sends.clear()
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.go_status == "ID MISMATCH"
    assert c.qlc.function_sends == []


def test_go_sends_when_engine_matches_parsed_ids(tmp_path):
    c = _catalog_controller(tmp_path)
    from light_console.qlc.functions import QlcFunction

    info = c.catalog.current_info()
    assert info is not None
    c.qlc.replace_functions(
        [QlcFunction(fn.function_id, fn.name, fn.type_name) for fn in info.functions]
    )
    c.qlc.function_sends.clear()
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.go_status == "GO"
    assert c.qlc.function_sends[-1] == (c.state.scene_function_ids[0], 1)
