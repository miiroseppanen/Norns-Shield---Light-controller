"""Shared OLED UX: viewport, scrollbar, toggle, status, activity."""

from __future__ import annotations

from light_console.display.activity import activity_frame, dmx_output_active
from light_console.display.components import (
    draw_activity,
    draw_empty_state,
    draw_focus_rail,
    draw_page_header,
    draw_scrollbar,
    draw_status_row,
    draw_subordinate_status,
    draw_toggle,
    draw_toggle_row,
    region_on_count,
)
from light_console.display.framebuffer import Framebuffer
from light_console.display.layout import (
    ACTIVITY_W,
    ACTIVITY_X,
    CONTENT_H,
    CONTENT_Y,
    FOCUS_W,
    ROW,
    SCROLL_X,
    TOGGLE_D,
    TOGGLE_LABEL_X,
    TOGGLE_X,
)
from light_console.display.renderer import Renderer
from light_console.display.viewport import ListViewport, scrollbar_metrics
from light_console.hardware.events import ButtonEvent, EncoderEvent, E1, E2, K2, K3
from light_console.output.dmx import empty_universe
from light_console.output.fixtures import PatchedFixture, fixture_activity
from light_console.output.network import NetIface
from light_console.output.nodes import KNOWN_ARTNET_NODES
from light_console.output.pages import build_output_pages
from light_console.output.routing import parse_output_routes
from light_console.prefs import OperatorPrefs, load_prefs, save_prefs
from light_console.qlc.service import MockQlcService, map_unit_state
from light_console.state import ScreenId
from light_console.ui.pages import (
    SYSTEM_NET_TOGGLE,
    SYSTEM_QLC_TOGGLE,
    SYSTEM_ROW_COUNT,
    SYSTEM_VERSION,
    system_slots,
    wiz_setting_detail,
)
from light_console.ui.vocab import (
    ACTIVE,
    DISCONNECTED,
    FAILED,
    IDLE,
    OFF,
    OK,
    RUNNING,
    SEEN,
    STARTING,
    STOPPED,
    STOPPING,
)

from tests.conftest import make_controller
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIELD = ROOT / "qlc/projects/siirtyma-shield.qxw"


def _toggle_match(fb: Framebuffer, y: int, on: bool) -> bool:
    ref = Framebuffer()
    draw_toggle(ref, TOGGLE_X, y, on)
    for dy in range(ROW):
        for dx in range(TOGGLE_D):
            if fb.get(TOGGLE_X + dx, y + dy) != ref.get(TOGGLE_X + dx, y + dy):
                return False
    return True


def _render_system(**state_kw):
    c = make_controller(**state_kw)
    c.qlc_service.desired_on = c.state.qlc_desired
    c.qlc_service.observed = c.state.qlc_observed
    c.state.screen = ScreenId.SYSTEM
    r = Renderer()
    r.force_dirty()
    return r.render(c.state), c


def test_scrollbar_hidden_when_content_fits():
    assert scrollbar_metrics(5, 7, 0, 56) is None
    assert scrollbar_metrics(0, 7, 0, 56) is None
    assert scrollbar_metrics(1, 7, 0, 56) is None
    fb = Framebuffer()
    draw_scrollbar(fb, 5, 7, 0)
    assert region_on_count(fb, SCROLL_X, CONTENT_Y, 3, CONTENT_H) == 0


def test_scrollbar_visible_proportional_and_min_thumb():
    top = scrollbar_metrics(20, 7, 0, 56)
    mid = scrollbar_metrics(20, 7, 6, 56)
    bot = scrollbar_metrics(20, 7, 13, 56)
    assert top is not None and mid is not None and bot is not None
    assert top[0] == 0
    assert bot[0] + bot[1] == 56
    assert 0 < mid[0] < bot[0]
    assert top[1] == mid[1] == bot[1]
    assert top[1] >= 4
    long_list = scrollbar_metrics(400, 7, 0, 56)
    assert long_list is not None
    assert long_list[1] == 4
    one_past = scrollbar_metrics(8, 7, 1, 56)
    assert one_past is not None
    assert one_past[0] + one_past[1] == 56


def test_viewport_keeps_focus_visible_without_page_jumps():
    vp = ListViewport(total=20, focused=0, offset=0, visible=7)
    vp.move(1)
    assert vp.focused == 1
    assert vp.offset == 0
    vp.focused = 6
    vp.offset = 0
    vp.reveal()
    assert vp.offset == 0
    vp.move(1)
    assert vp.focused == 7
    assert vp.offset == 1
    vp.move(-1)
    assert vp.focused == 6
    assert vp.offset == 1
    vp.move(-1)
    assert vp.focused == 5
    assert vp.offset == 1


def test_viewport_stable_when_live_data_grows():
    vp = ListViewport(total=3, focused=2, offset=0, visible=7)
    vp.stabilize(10)
    assert vp.focused == 2
    assert vp.offset == 0
    vp = ListViewport(total=10, focused=9, offset=3, visible=7)
    vp.stabilize(4)
    assert vp.focused == 3
    assert vp.focused >= vp.offset
    assert vp.focused < vp.offset + vp.visible


def test_viewport_empty_one_exact_fit_and_overflow():
    empty = ListViewport(total=0, focused=3, offset=2, visible=7)
    empty.reveal()
    assert empty.focused == 0
    assert empty.offset == 0
    assert scrollbar_metrics(0, 7, 0, 56) is None
    one = ListViewport(total=1, focused=0, offset=0, visible=7)
    one.reveal()
    assert one.offset == 0
    assert scrollbar_metrics(1, 7, 0, 56) is None
    exact = ListViewport(total=7, focused=6, offset=0, visible=7)
    exact.reveal()
    assert exact.offset == 0
    assert scrollbar_metrics(7, 7, 0, 56) is None
    over = ListViewport(total=8, focused=0, offset=0, visible=7)
    over.reveal()
    assert over.offset == 0
    over.move(7)
    assert over.focused == 7
    assert over.offset == 1
    assert scrollbar_metrics(8, 7, 1, 56) is not None


def test_viewport_long_lists_clamp_at_ends():
    vp = ListViewport(total=40, focused=0, offset=0, visible=7)
    vp.move(20)
    assert vp.focused == 20
    assert vp.offset == 20 - 7 + 1
    assert vp.focused >= vp.offset
    assert vp.focused < vp.offset + vp.visible
    vp.focused = 39
    vp.reveal()
    assert vp.offset == 33
    vp.move(1)
    assert vp.focused == 39
    assert vp.offset == 33
    vp.move(20)
    assert vp.focused == 39
    assert vp.offset == 33
    vp.move(-100)
    assert vp.focused == 0
    assert vp.offset == 0
    huge = scrollbar_metrics(400, 7, 393, 56)
    assert huge is not None
    assert huge[0] + huge[1] == 56
    assert huge[1] == 4


def test_device_rows_are_logical_items_not_text_lines():
    from light_console.display.layout import CONTENT_H, CONTENT_ROWS
    from light_console.output.pages import pack_device_pages

    fx = PatchedFixture(1, "60 W Battery LED", 0, 24, 14)
    page = pack_device_pages((fx,), {}, set())[0]
    assert len(page.items) == 1
    assert page.items[0].prefix == "025 "
    visible = max(1, CONTENT_ROWS // 2)
    assert visible == 3
    assert scrollbar_metrics(1, visible, 0, CONTENT_H) is None
    many = pack_device_pages(
        tuple(PatchedFixture(i, f"FIX {i}", 0, i * 10, 7) for i in range(12)),
        {},
        set(),
    )[0]
    assert len(many.items) == 12
    metrics = scrollbar_metrics(12, visible, 0, CONTENT_H)
    assert metrics is not None


def test_toggle_enabled_disabled_and_focus_are_distinct():
    on_fb = Framebuffer()
    off_fb = Framebuffer()
    draw_toggle(on_fb, TOGGLE_X, 16, True)
    draw_toggle(off_fb, TOGGLE_X, 16, False)
    on_n = region_on_count(on_fb, TOGGLE_X, 16, TOGGLE_D, TOGGLE_D)
    off_n = region_on_count(off_fb, TOGGLE_X, 16, TOGGLE_D, TOGGLE_D)
    assert on_n > off_n * 2
    focused = Framebuffer()
    draw_toggle_row(focused, 16, "WIZ CONTROL", True, focused=True)
    unfocused = Framebuffer()
    draw_toggle_row(unfocused, 16, "WIZ CONTROL", True, focused=False)
    assert region_on_count(focused, 0, 16, FOCUS_W, 8) > 0
    assert region_on_count(unfocused, 0, 16, FOCUS_W, 8) == 0
    disabled_focus = Framebuffer()
    draw_toggle_row(disabled_focus, 16, "WIZ CONTROL", False, focused=True)
    assert region_on_count(disabled_focus, 0, 16, FOCUS_W, 8) > 0
    assert region_on_count(disabled_focus, TOGGLE_X, 16, TOGGLE_D, TOGGLE_D) == off_n


def test_toggle_glyph_precedes_label():
    assert TOGGLE_X < TOGGLE_LABEL_X
    fb = Framebuffer()
    draw_toggle_row(fb, 16, "QLC SERVICE", True)
    assert _toggle_match(fb, 16, True)
    assert region_on_count(fb, TOGGLE_LABEL_X, 16, 48, ROW) > 0
    assert region_on_count(fb, 0, 16, FOCUS_W, ROW) == 0


def test_status_row_is_not_a_toggle():
    fb = Framebuffer()
    draw_status_row(fb, 16, "QLC", RUNNING, focused=True)
    assert not _toggle_match(fb, 16, True)
    assert not _toggle_match(fb, 16, False)
    assert region_on_count(fb, 0, 16, FOCUS_W, 8) > 0


def test_activity_idle_vs_frames_and_stop():
    from light_console.display.activity import FRAMES, PERIOD_S, SCAN_X, SEG_W

    assert activity_frame(0.0, False) is None
    assert activity_frame(0.0, True) == 0
    assert activity_frame(PERIOD_S, True) == 1
    assert activity_frame(PERIOD_S * 2, True) == 2
    assert activity_frame(PERIOD_S * (FRAMES - 1), True) == FRAMES - 1
    assert activity_frame(PERIOD_S * FRAMES, True) == 0
    idle = Framebuffer()
    active = Framebuffer()
    draw_activity(active, ACTIVITY_X, 16, 0)
    assert region_on_count(idle, ACTIVITY_X, 16, ACTIVITY_W, 8) == 0
    assert region_on_count(active, ACTIVITY_X, 16, ACTIVITY_W, 8) > 0
    f0 = Framebuffer()
    f1 = Framebuffer()
    draw_activity(f0, ACTIVITY_X, 16, 0)
    draw_activity(f1, ACTIVITY_X, 16, 1)
    assert f0.digest() != f1.digest()
    assert len(SCAN_X) == FRAMES == 6
    assert SEG_W == 3
    assert SCAN_X[-1] + SEG_W <= ACTIVITY_W


def test_activity_scan_moves_left_to_right_and_stays_in_slot():
    from light_console.display.activity import FRAMES, SCAN_X, SCAN_Y, SEG_W

    starts = list(SCAN_X)
    assert starts == sorted(starts)
    assert starts[0] < starts[-1]
    y = 16
    prev_min = -1
    ys: set[int] = set()
    for frame in range(FRAMES):
        fb = Framebuffer()
        draw_activity(fb, ACTIVITY_X, y, frame)
        xs: list[int] = []
        for yy in range(fb.height):
            for xx in range(fb.width):
                if not fb.get(xx, yy):
                    continue
                assert ACTIVITY_X <= xx < ACTIVITY_X + ACTIVITY_W
                assert y <= yy < y + ROW
                xs.append(xx)
                ys.add(yy)
        assert xs
        assert max(xs) - min(xs) + 1 == SEG_W
        assert min(xs) == ACTIVITY_X + SCAN_X[frame]
        assert min(xs) > prev_min
        prev_min = min(xs)
    assert ys == {y + SCAN_Y}
    first = Framebuffer()
    last = Framebuffer()
    wrap = Framebuffer()
    draw_activity(first, ACTIVITY_X, y, 0)
    draw_activity(last, ACTIVITY_X, y, FRAMES - 1)
    draw_activity(wrap, ACTIVITY_X, y, 0)
    assert first.digest() == wrap.digest()
    assert last.digest() != first.digest()
    assert ACTIVITY_X + SCAN_X[-1] > ACTIVITY_X + SCAN_X[0]


def test_activity_ignores_focus_and_marquee_time():
    from light_console.display.components import draw_status_row
    from light_console.display.marquee import START_PAUSE_S
    from light_console.ui.vocab import ACTIVE

    a = Framebuffer()
    b = Framebuffer()
    draw_status_row(a, 16, "FIX", ACTIVE, focused=False, activity=True, now=0.6)
    draw_status_row(b, 16, "FIX", ACTIVE, focused=True, activity=True, now=0.6)
    act_a = bytes(
        a.get(ACTIVITY_X + dx, 16 + dy) for dy in range(ROW) for dx in range(ACTIVITY_W)
    )
    act_b = bytes(
        b.get(ACTIVITY_X + dx, 16 + dy) for dy in range(ROW) for dx in range(ACTIVITY_W)
    )
    assert act_a == act_b
    assert activity_frame(START_PAUSE_S + 1.0, True) is not None
    assert activity_frame(0.0, True) == 0
    from light_console.display.activity import FRAMES, PERIOD_S

    assert activity_frame(PERIOD_S * FRAMES, True) == 0
    assert region_on_count(a, 0, 16, FOCUS_W, ROW) == 0
    assert region_on_count(b, 0, 16, FOCUS_W, ROW) > 0


def test_qlc_running_and_wiz_enabled_do_not_animate_alone():
    from light_console.display.wordmark import OUTPUT_Y, QLC_Y

    c = make_controller(qlc_observed=RUNNING, wiz_enabled=True, wiz_tx_active=False)
    c.state.dmx_by_universe = {}
    c.state.screen = ScreenId.PLAY
    r = Renderer()
    fb = r.render(c.state)
    assert region_on_count(fb, ACTIVITY_X, OUTPUT_Y, ACTIVITY_W, ROW) == 0
    assert region_on_count(fb, ACTIVITY_X, QLC_Y, ACTIVITY_W, ROW) == 0
    c.state.screen = ScreenId.SYSTEM
    r.force_dirty()
    fb = r.render(c.state)
    assert region_on_count(fb, ACTIVITY_X, CONTENT_Y, ACTIVITY_W, CONTENT_H) == 0
    assert activity_frame(c.state.ui_now, False) is None


def test_status_vocab_and_ssid_fit_without_clipping():
    from light_console.display.components import draw_named_status_row
    from light_console.display.layout import CONTENT_RIGHT, LABEL_X, VALUE_RIGHT
    from light_console.display.widgets import CELL_W, text, text_right

    fb = Framebuffer()
    draw_status_row(fb, 16, "wlan1", DISCONNECTED)
    expected = Framebuffer()
    text(expected, LABEL_X, 16, "wlan1")
    text_right(expected, VALUE_RIGHT, 16, DISCONNECTED)
    assert fb.digest() == expected.digest()

    named = Framebuffer()
    draw_named_status_row(named, 16, "NET", "LIGHT-CONTROL", OK)
    want = Framebuffer()
    text(want, LABEL_X, 16, "NET")
    text(want, LABEL_X + 4 * CELL_W, 16, "LIGHT-CONTROL")
    text_right(want, CONTENT_RIGHT, 16, OK)
    assert named.digest() == want.digest()


def test_scrollbar_track_marks_remainder_when_thumb_is_large():
    fb = Framebuffer()
    draw_scrollbar(fb, 8, 7, 0)
    metrics = scrollbar_metrics(8, 7, 0, CONTENT_H)
    assert metrics is not None
    thumb_y, thumb_h = metrics
    remainder = 0
    for yy in range(CONTENT_Y, CONTENT_Y + CONTENT_H):
        local = yy - CONTENT_Y
        if local < thumb_y or local >= thumb_y + thumb_h:
            remainder += fb.get(SCROLL_X + 1, yy)
    assert remainder > 0


def test_empty_state_has_no_scrollbar():
    fb = Framebuffer()
    draw_page_header(fb, "LIVE DMX U2")
    draw_empty_state(fb, "NO LIVE DMX")
    assert region_on_count(fb, SCROLL_X, CONTENT_Y, 3, CONTENT_H) == 0


def test_qlc_desired_and_observed_matrix():
    cases = (
        (True, RUNNING),
        (True, STARTING),
        (False, STOPPING),
        (False, STOPPED),
        (True, FAILED),
    )
    for desired, observed in cases:
        c = make_controller(qlc_desired=desired, qlc_observed=observed)
        c.qlc_service.desired_on = desired
        c.qlc_service.observed = observed
        c.state.qlc_desired = desired
        c.state.qlc_observed = observed
        c.state.screen = ScreenId.SYSTEM
        c.state.system_index = SYSTEM_QLC_TOGGLE
        r = Renderer()
        r.force_dirty()
        r.render(c.state)
        assert c.state.qlc_desired is desired
        assert c.state.qlc_observed == observed
        c._finish()
        if observed == FAILED and desired:
            assert "QLC FAILED" in c.state.warnings
        if observed == STOPPED and not desired:
            assert "QLC FAILED" not in c.state.warnings


def test_qlc_toggle_does_not_look_like_shutdown():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.qlc_service.commands[-1] == "stop"
    assert c.state.qlc_observed == STOPPING
    assert c.state.screen == ScreenId.SYSTEM
    assert c.power.request_count == 0
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.system_index == SYSTEM_NET_TOGGLE
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.qlc_service.commands == ["stop"]
    assert c.state.screen == ScreenId.SYSTEM
    assert c.power.request_count == 0
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.system_index == SYSTEM_VERSION
    c.inject_cooked(ButtonEvent(K3, "press"))
    assert c.state.screen == ScreenId.VERSION
    assert c.power.request_count == 0
    c.inject_cooked(ButtonEvent(K2, "press"))
    assert c.state.screen == ScreenId.SYSTEM
    from tests.test_shutdown import _start_shutdown

    _start_shutdown(c)
    assert c.state.screen == ScreenId.SHUTTING_DOWN


def test_system_focus_order_is_three_actions():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    assert SYSTEM_ROW_COUNT == 3
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.system_index == SYSTEM_NET_TOGGLE
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.system_index == SYSTEM_VERSION
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.system_index == SYSTEM_VERSION
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.state.system_index == SYSTEM_NET_TOGGLE
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(EncoderEvent(E2, -1))
    assert c.state.system_index == SYSTEM_QLC_TOGGLE


def test_system_qlc_state_is_not_separately_focusable():
    c = make_controller()
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.system_index == SYSTEM_NET_TOGGLE
    slots = system_slots(c.state)
    assert slots[0].kind == "qlc"
    assert slots[0].rows == 2
    assert slots[1].kind == "net"
    assert slots[2].kind == "version"
    assert slots[2].rows == 1
    assert len(slots) == 3


def test_system_layout_has_no_scrollbar_and_groups_settings():
    fb, c = _render_system(qlc_desired=False, qlc_observed=STOPPED, wiz_enabled=False)
    assert scrollbar_metrics(SYSTEM_ROW_COUNT, SYSTEM_ROW_COUNT, 0, CONTENT_H) is None
    assert region_on_count(fb, SCROLL_X, CONTENT_Y, 3, CONTENT_H) == 0
    slots = system_slots(c.state)
    assert [slot.index for slot in slots] == [
        SYSTEM_QLC_TOGGLE,
        SYSTEM_NET_TOGGLE,
        SYSTEM_VERSION,
    ]
    qlc, net, version = slots
    assert qlc.y == CONTENT_Y
    assert net.y == qlc.y + qlc.rows * ROW
    assert version.y == net.y + net.rows * ROW
    assert _toggle_match(fb, qlc.y, False)
    assert _toggle_match(fb, net.y, True)
    assert not _toggle_match(fb, version.y, True)
    assert not _toggle_match(fb, version.y, False)
    assert region_on_count(fb, 0, qlc.y, FOCUS_W, qlc.rows * ROW) == FOCUS_W * qlc.rows * ROW
    assert region_on_count(fb, 0, qlc.y + ROW, FOCUS_W, ROW) == FOCUS_W * ROW
    c._finish()


def test_system_wiz_off_has_no_redundant_off_line():
    fb, c = _render_system(wiz_enabled=False, qlc_observed=STOPPED, qlc_desired=False)
    assert wiz_setting_detail(c.state) is None
    kinds = [slot.kind for slot in system_slots(c.state)]
    assert "wiz" not in kinds
    assert "wiz_devices" not in kinds
    assert kinds == ["qlc", "net", "version"]
    fb_src = ROOT / "light_console/display/screens.py"
    system_fn = fb_src.read_text(encoding="utf-8").split("def draw_system")[1].split("def draw_wiz_control")[0]
    assert "WIZ CONTROL" not in system_fn
    assert "WIZ DEVICES" not in system_fn
    c._finish()


def test_system_qlc_observed_states_are_subordinate():
    cases = (
        (True, RUNNING),
        (True, STARTING),
        (False, STOPPING),
        (False, STOPPED),
        (True, FAILED),
    )
    for desired, observed in cases:
        fb, c = _render_system(qlc_desired=desired, qlc_observed=observed)
        qlc = system_slots(c.state)[0]
        assert _toggle_match(fb, qlc.y, desired)
        ref = Framebuffer()
        draw_subordinate_status(ref, qlc.y + ROW, observed)
        for dx in range(TOGGLE_LABEL_X, TOGGLE_LABEL_X + 72):
            for dy in range(ROW):
                yy = qlc.y + ROW + dy
                assert fb.get(dx, yy) == ref.get(dx, yy)
        assert region_on_count(fb, ACTIVITY_X, qlc.y, ACTIVITY_W, qlc.rows * ROW) == 0
        c._finish()


def test_wiz_default_off_is_not_a_fault_and_does_not_animate():
    c = make_controller(wiz_online=0, wiz_ap_up=True)
    assert c.state.wiz_enabled is False
    c._finish()
    assert not any("WIZ" in w for w in c.state.warnings)
    c.state.ui_now = 0.6
    r = Renderer()
    r.render(c.state)
    assert activity_frame(c.state.ui_now, False) is None
    c.state.screen = ScreenId.WIZ_CONTROL
    r.force_dirty()
    fb = r.render(c.state)
    wiz_y = CONTENT_Y
    off = Framebuffer()
    draw_toggle(off, TOGGLE_X, wiz_y, False)
    assert region_on_count(fb, TOGGLE_X, wiz_y, TOGGLE_D, TOGGLE_D) == region_on_count(
        off, TOGGLE_X, wiz_y, TOGGLE_D, TOGGLE_D
    )


def test_wiz_enabled_idle_does_not_animate_lost_does_not_animate():
    assert activity_frame(0.4, False) is None
    c = make_controller(wiz_enabled=True, wiz_online=6, wiz_tx_active=False)
    assert c.state.wiz_enabled is True
    assert wiz_setting_detail(c.state) == "READY"
    assert activity_frame(c.state.ui_now, c.state.wiz_tx_active) is None
    c.state.wiz_tx_active = True
    assert activity_frame(0.0, True) == 0
    c.state.wiz_tx_active = False
    c.state.wiz_online = 0
    c._finish()
    assert wiz_setting_detail(c.state) == "NO DEVICES"
    assert not any("WAIT" in w for w in c.state.warnings)
    assert activity_frame(0.3, False) is None


def test_output_overview_counters_and_wiz_off():
    routes = parse_output_routes(SHIELD.read_text(encoding="utf-8"))
    fixtures = (
        PatchedFixture(1, "BAT PAR", 1, 24, 14),
        PatchedFixture(2, "PAR 2", 1, 40, 14),
        PatchedFixture(3, "PAR 3", 1, 54, 7),
    )
    buf1 = empty_universe()
    buf1[24] = 255
    buf1[25] = 180
    pages = build_output_pages(
        (NetIface("wlan0", True, "192.168.88.246", "LIGHT-CONTROL", 24),),
        routes,
        {1: tuple(buf1)},
        nodes=KNOWN_ARTNET_NODES,
        fixtures=fixtures,
        qlc_observed=RUNNING,
        wiz_enabled=False,
    )
    overview = next(p for p in pages if p.kind == "overview")
    joined = " ".join(overview.lines)
    assert "NETWORK" in joined
    assert "OK" in joined
    assert "SAFE" in joined
    assert "AIR2DMX" not in joined
    assert "DEV 3 / 35 CH" in overview.lines
    assert "LIVE 1 / 2 CH" in overview.lines
    assert any(line.endswith("OFF") and line.startswith("WIZ") for line in overview.lines)
    assert overview.items[0].title == "NET"
    assert overview.items[0].subtitle == "NETWORK"
    live = next(p for p in pages if p.kind == "dmx")
    assert all(item.activity is False for item in live.items)
    assert "127.0.0.1" not in joined
    assert "LOOPBACK" not in joined
    assert "192.168.88.255" not in joined


def test_output_overview_wiz_enabled():
    pages = build_output_pages(
        (),
        (),
        wiz_enabled=True,
        wiz_online=5,
        wiz_expected=6,
    )
    overview = next(p for p in pages if p.kind == "overview")
    assert any("WIZ 5/6" in line for line in overview.lines)


def test_dmx_active_seen_idle_and_only_active_animates():
    seen: set[int] = set()
    fx = PatchedFixture(7, "BAT PAR", 1, 24, 14)
    dmx = {1: tuple(empty_universe())}
    assert fixture_activity(fx, dmx, seen) == IDLE
    buf = empty_universe()
    buf[24] = 40
    dmx = {1: tuple(buf)}
    assert fixture_activity(fx, dmx, seen) == ACTIVE
    buf[24] = 0
    dmx = {1: tuple(buf)}
    assert fixture_activity(fx, dmx, seen) == SEEN
    pages = build_output_pages(
        (),
        (),
        dmx,
        fixtures=(fx,),
        seen_ids=seen,
    )
    devices = next(p for p in pages if p.kind == "devices")
    assert devices.items[0].status == SEEN
    assert devices.items[0].activity is False
    buf[24] = 10
    dmx = {1: tuple(buf)}
    pages = build_output_pages((), (), dmx, fixtures=(fx,), seen_ids=seen)
    devices = next(p for p in pages if p.kind == "devices")
    assert devices.items[0].status == ACTIVE
    assert devices.items[0].activity is True
    assert dmx_output_active(dmx) is True
    assert dmx_output_active({1: tuple(empty_universe())}) is False


def test_pknight_is_idle_not_failed():
    pages = build_output_pages(
        (NetIface("wlan0", True, "192.168.88.246", "LIGHT-CONTROL", 24),),
        (),
        nodes=KNOWN_ARTNET_NODES,
        qlc_observed=RUNNING,
    )
    nodes = next(p for p in pages if p.kind == "node")
    names = {item.title: item.status for item in nodes.items}
    assert names["PKNight"] == IDLE
    assert names["PKNight"] != FAILED
    assert names["AIR2DMX"] == SEEN


def test_network_list_uses_status_words_not_ssid():
    pages = build_output_pages(
        (
            NetIface("wlan0", True, "192.168.88.246", "LIGHT-CONTROL", 24),
            NetIface("wlan1", False, "", "", kind="usb"),
            NetIface("lo", True, "127.0.0.1", "", kind="loopback"),
        ),
        (),
    )
    network = next(p for p in pages if p.kind == "network")
    by_name = {item.title: item.status for item in network.items}
    assert by_name["LIGHT-CONTROL"] == "CLIENT"
    assert by_name["wlan1"] == DISCONNECTED
    assert "lo" not in by_name
    assert "LIGHT-CONTROL" in "\n".join(network.lines)
    assert "CLIENT" in "\n".join(network.lines)


def test_qlc_failed_keeps_enabled_toggle_without_activity():
    c = make_controller(qlc_desired=True, qlc_observed=FAILED)
    c.qlc_service.desired_on = True
    c.qlc_service.observed = FAILED
    c.state.qlc_desired = True
    c.state.qlc_observed = FAILED
    c.state.screen = ScreenId.SYSTEM
    c.state.system_index = SYSTEM_QLC_TOGGLE
    r = Renderer()
    r.force_dirty()
    fb = r.render(c.state)
    filled = Framebuffer()
    draw_toggle(filled, TOGGLE_X, CONTENT_Y, True)
    assert region_on_count(fb, TOGGLE_X, CONTENT_Y, TOGGLE_D, TOGGLE_D) == region_on_count(
        filled, TOGGLE_X, CONTENT_Y, TOGGLE_D, TOGGLE_D
    )
    assert region_on_count(fb, ACTIVITY_X, CONTENT_Y + 8, ACTIVITY_W, 8) == 0
    c._finish()


def test_output_e2_moves_list_focus_not_page():
    c = make_controller()
    c.state.output_routes = parse_output_routes(SHIELD.read_text(encoding="utf-8"))
    c.state.network_ifaces = (
        NetIface("wlan0", True, "192.168.88.246", "LIGHT-CONTROL", 24),
        NetIface("wlan1", False, "", ""),
    )
    c.state.artnet_nodes = KNOWN_ARTNET_NODES
    c.state.screen = ScreenId.OUTPUT
    c.inject_cooked(EncoderEvent(E1, 1))
    page_i = c.state.output_page
    c.inject_cooked(EncoderEvent(E2, 1))
    assert c.state.output_page == page_i


def test_unit_state_mapping():
    assert map_unit_state("active", "running") == RUNNING
    assert map_unit_state("activating", "start") == STARTING
    assert map_unit_state("deactivating", "stop") == STOPPING
    assert map_unit_state("failed", "failed") == FAILED
    assert map_unit_state("inactive", "dead") == STOPPED


def test_prefs_default_wiz_off(tmp_path):
    path = tmp_path / "prefs.yaml"
    prefs = load_prefs(path)
    assert prefs.wiz_enabled is False
    assert prefs.qlc_desired is True
    assert prefs.network_mode == "network"
    save_prefs(path, OperatorPrefs(wiz_enabled=True, qlc_desired=False))
    loaded = load_prefs(path)
    assert loaded.wiz_enabled is True
    assert loaded.qlc_desired is False


def test_mock_qlc_service_start_stop_not_kill():
    svc = MockQlcService()
    svc.set_desired(False)
    assert svc.commands == ["stop"]
    assert svc.observed == STOPPING
    svc.settle()
    assert svc.observed == STOPPED
    svc.set_desired(True)
    assert svc.commands[-1] == "start"
    assert svc.observed == STARTING
    from light_console.qlc.service import START_ARGV, STOP_ARGV

    assert "-9" not in STOP_ARGV
    assert "kill" not in " ".join(STOP_ARGV)
    assert STOP_ARGV[-2:] == ("stop", "qlcplus.service")
    assert START_ARGV[-2:] == ("start", "qlcplus.service")


def test_focus_rail_read_only_vs_editable():
    fb = Framebuffer()
    draw_focus_rail(fb, 24)
    assert region_on_count(fb, 0, 24, FOCUS_W, 8) == FOCUS_W * 8
