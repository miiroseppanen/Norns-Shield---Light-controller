from light_console.hardware.events import ButtonEvent, EncoderEvent, K1, K2, K3, E1, E2, E3
from light_console.state import ScreenId
from light_console.ui.menu import MENU_ITEMS, menu_index_of

from tests.conftest import make_controller


def test_play_k1_opens_menu():
    c = make_controller()
    assert c.state.screen == ScreenId.PLAY
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.MENU
    assert c.state.menu_index == 0


def test_menu_k1_returns_play():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.MENU
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.PLAY


def test_menu_e1_changes_selection():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.menu_index == 1
    assert MENU_ITEMS[c.state.menu_index].label == "SHOWS"
    c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.menu_index == 0
    c.inject_cooked(EncoderEvent(E1, -1))
    assert c.state.menu_index == len(MENU_ITEMS) - 1


def test_menu_e2_does_not_change_selection():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = 1
    c.inject_cooked(EncoderEvent(E2, 2))
    assert c.state.menu_index == 1
    assert c.state.screen == ScreenId.MENU


def test_menu_e3_does_not_change_selection():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = 1
    c.inject_cooked(EncoderEvent(E3, 2))
    assert c.state.menu_index == 1
    assert c.state.screen == ScreenId.MENU


def test_menu_k3_enters_selected_item():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.inject_cooked(EncoderEvent(E1, 1))
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHOWS


def test_menu_k3_forward_k2_back():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("SHOWS")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.SHOWS
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.MENU
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.PLAY


def test_menu_home_item_returns_play():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = 0
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.PLAY


def test_visit_all_menu_pages():
    c = make_controller()
    expected = (
        ScreenId.SHOWS,
        ScreenId.SCENES,
        ScreenId.CHASERS,
        ScreenId.PARAMS,
        ScreenId.OUTPUT,
        ScreenId.SYSTEM,
    )
    for i, screen in enumerate(expected):
        c.state.screen = ScreenId.PLAY
        c.inject_cooked(ButtonEvent(K1, "press"))
        c.state.menu_index = i + 1
        c.inject_cooked(ButtonEvent(K3, "press"))
        assert c.state.screen == screen
        c.inject_cooked(ButtonEvent(K2, "press"))
        assert c.state.screen == ScreenId.MENU
        c.inject_cooked(ButtonEvent(K1, "press"))
        assert c.state.screen == ScreenId.PLAY


def test_k1_from_params_returns_play():
    c = make_controller()
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("PARAMS")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.PARAMS
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.PLAY


def test_master_clamp_0_100():
    c = make_controller(master_dimmer=80)
    c.inject_cooked(EncoderEvent(1, 50))
    assert c.state.master == 100
    c.inject_cooked(EncoderEvent(1, -200))
    assert c.state.master == 0
    c.inject_cooked(EncoderEvent(1, 40))
    assert c.state.master == 40


def test_play_and_params_share_master():
    c = make_controller(master_dimmer=80)
    c.inject_cooked(EncoderEvent(1, -5))
    assert c.state.master == 75
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.state.menu_index = menu_index_of("PARAMS")
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.PARAMS
    c.state.param_index = 0
    c.params.index = 0
    c.inject_cooked(EncoderEvent(3, 10))
    assert c.state.master == 85
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.PLAY
    assert c.state.master == 85


def test_play_mapping_not_used_on_menu():
    c = make_controller(master_dimmer=50, scene_index=0, current_scene="WASH", bpm=124)
    c.inject_cooked(ButtonEvent(K1, "press"))
    c.inject_cooked(EncoderEvent(E1, 1))
    assert c.state.master == 50
    assert c.state.current_scene == "WASH"
    assert c.state.bpm == 124
    assert c.state.blackout is False
    assert c.state.menu_index == 1


def test_qlc_offline_does_not_block_ui():
    c = make_controller()
    c.qlc.simulate_link(False)
    c.tick(now=1.0)
    assert c.state.qlc_connected is False
    c.inject_cooked(EncoderEvent(1, 5))
    assert c.state.master == 85
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.MENU
    c.inject_cooked(ButtonEvent(K1, "press"))
    assert c.state.screen == ScreenId.PLAY
