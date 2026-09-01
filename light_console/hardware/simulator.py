from __future__ import annotations

import logging
from light_console.display.framebuffer import Framebuffer
from light_console.hardware.base import HardwareBackend
from light_console.hardware.events import ButtonEvent, EncoderEvent, HardwareEvent, SimCommandEvent

LOG = logging.getLogger("light-console")

# pygame key constants duplicated as ints so tests need not import pygame
K_q, K_a, K_w, K_s, K_e, K_d = 113, 97, 119, 115, 101, 100
K_z, K_x, K_c = 122, 120, 99
K_1, K_2, K_3 = 49, 50, 51
K_MINUS, K_EQUALS, K_0, K_6 = 45, 61, 48, 54
K_ESCAPE = 27
K_F1, K_F2, K_F3, K_F4, K_F5 = 1073741882, 1073741883, 1073741884, 1073741885, 1073741886
K_LEFT, K_RIGHT, K_UP, K_DOWN = 1073741904, 1073741903, 1073741906, 1073741905
K_COMMA, K_PERIOD = 44, 46
K_b, K_h, K_m = 98, 104, 109

KEY_HOLD = {
    K_z: 1,
    K_x: 2,
    K_c: 3,
    K_1: 1,
    K_2: 2,
    K_3: 3,
}

ENCODER_KEYS = {
    K_q: (1, -1),
    K_a: (1, 1),
    K_LEFT: (1, -1),
    K_RIGHT: (1, 1),
    K_w: (2, -1),
    K_s: (2, 1),
    K_UP: (2, -1),
    K_DOWN: (2, 1),
    K_e: (3, -1),
    K_d: (3, 1),
    K_COMMA: (3, -1),
    K_PERIOD: (3, 1),
}


def events_from_key(key: int, down: bool) -> list[HardwareEvent]:
    """Pure mapping used by tests and the pygame backend."""
    if not down:
        if key in KEY_HOLD:
            return [ButtonEvent(button=KEY_HOLD[key], action="release")]  # type: ignore[arg-type]
        return []
    if key in KEY_HOLD:
        return [ButtonEvent(button=KEY_HOLD[key], action="press")]  # type: ignore[arg-type]
    if key in ENCODER_KEYS:
        enc, delta = ENCODER_KEYS[key]
        return [EncoderEvent(encoder=enc, delta=delta)]  # type: ignore[arg-type]
    if key == K_F1:
        return [SimCommandEvent("toggle_qlc")]
    if key == K_F2:
        return [SimCommandEvent("toggle_launchpad")]
    if key == K_F3:
        return [SimCommandEvent("toggle_pknight")]
    if key == K_F4:
        return [SimCommandEvent("toggle_upstream")]
    if key == K_F5:
        return [SimCommandEvent("toggle_wiz_ap")]
    if key == K_MINUS:
        return [SimCommandEvent("wiz_delta", -1)]
    if key == K_EQUALS:
        return [SimCommandEvent("wiz_delta", 1)]
    if key == K_0:
        return [SimCommandEvent("wiz_set", 0)]
    if key == K_6:
        return [SimCommandEvent("wiz_set", 6)]
    if key == K_ESCAPE:
        return [SimCommandEvent("quit")]
    if key == K_b:
        return [SimCommandEvent("screen_boot")]
    return []


class SimulatorBackend(HardwareBackend):
    def __init__(self, scale: int = 6, caption: str = "shieldXL OLED 128x64") -> None:
        try:
            import pygame
        except ImportError as exc:
            raise SystemExit(
                "pygame is required for the OLED simulator.\n"
                "  pip install -e '.[sim]'\n"
                "  python -m simulator.run"
            ) from exc
        self._pygame = pygame
        pygame.init()
        pygame.display.set_caption(caption)
        self.scale = scale
        self.oled_w = 128 * scale
        self.oled_h = 64 * scale
        self.hud_h = 140
        self.screen = pygame.display.set_mode((self.oled_w, self.oled_h + self.hud_h))
        self.clock = pygame.time.Clock()
        self._queue: list[HardwareEvent] = []
        self._closed = False
        self._draw_hud()
        pygame.display.flip()

    def read_events(self) -> list[HardwareEvent]:
        pg = self._pygame
        out: list[HardwareEvent] = []
        for event in pg.event.get():
            if event.type == pg.QUIT:
                out.append(SimCommandEvent("quit"))
            elif event.type == pg.KEYDOWN:
                out.extend(events_from_key(int(event.key), True))
            elif event.type == pg.KEYUP:
                out.extend(events_from_key(int(event.key), False))
            elif event.type == pg.MOUSEBUTTONDOWN:
                cmd = self._hud_click(event.pos)
                if cmd:
                    out.append(cmd)
        out.extend(self._queue)
        self._queue = []
        return out

    def set_display(self, fb: Framebuffer) -> None:
        pg = self._pygame
        surf = pg.Surface((128, 64))
        on = (210, 220, 160)
        off = (10, 12, 10)
        px = pg.PixelArray(surf)
        for y in range(64):
            for x in range(128):
                px[x, y] = on if fb.get(x, y) else off
        del px
        scaled = pg.transform.scale(surf, (self.oled_w, self.oled_h))
        self.screen.blit(scaled, (0, 0))
        # pixel grid
        if self.scale >= 4:
            grid = (18, 22, 16)
            for x in range(0, self.oled_w, self.scale):
                pg.draw.line(self.screen, grid, (x, 0), (x, self.oled_h))
            for y in range(0, self.oled_h, self.scale):
                pg.draw.line(self.screen, grid, (0, y), (self.oled_w, y))
        self._draw_hud()
        pg.display.flip()

    def set_display_brightness(self, level: int) -> None:
        del level

    def close(self) -> None:
        if not self._closed:
            self._pygame.quit()
            self._closed = True

    def idle(self, timeout_s: float) -> None:
        self.clock.tick(max(1, int(1.0 / max(timeout_s, 0.001))))

    def _draw_hud(self) -> None:
        pg = self._pygame
        hud = pg.Rect(0, self.oled_h, self.oled_w, self.hud_h)
        pg.draw.rect(self.screen, (24, 24, 28), hud)
        font = pg.font.SysFont("Menlo", 13) if "Menlo" in pg.font.get_fonts() else pg.font.SysFont(None, 16)
        lines = [
            "OLED 128x64  |  E1 Q/A or LEFT/RIGHT  E2 W/S or UP/DOWN  E3 E/D or ,/.",
            "K1 Z or 1   K2 X or 2   K3 C or 3   (hold for long press)",
            "F1 QLC  F2 Launchpad  F3 PKNight  F4 upstream  F5 WIZ-AP  -/= WiZ  0 empty  6 full",
            "ESC quit   click buttons below",
        ]
        y = self.oled_h + 4
        for line in lines:
            self.screen.blit(font.render(line, True, (200, 200, 200)), (8, y))
            y += 16
        labels = ["QLC", "LP", "PKNight", "UP", "AP", "WiZ-1", "WiZ+1"]
        self._buttons = []
        x = 8
        for lab in labels:
            r = pg.Rect(x, self.oled_h + 108, 84, 24)
            pg.draw.rect(self.screen, (60, 80, 70), r, border_radius=4)
            self.screen.blit(font.render(lab, True, (240, 240, 240)), (r.x + 8, r.y + 4))
            self._buttons.append((r, lab))
            x += 90

    def _hud_click(self, pos: tuple[int, int]) -> SimCommandEvent | None:
        mapping = {
            "QLC": SimCommandEvent("toggle_qlc"),
            "LP": SimCommandEvent("toggle_launchpad"),
            "PKNight": SimCommandEvent("toggle_pknight"),
            "UP": SimCommandEvent("toggle_upstream"),
            "AP": SimCommandEvent("toggle_wiz_ap"),
            "WiZ-1": SimCommandEvent("wiz_delta", -1),
            "WiZ+1": SimCommandEvent("wiz_delta", 1),
        }
        for rect, lab in getattr(self, "_buttons", []):
            if rect.collidepoint(pos):
                return mapping.get(lab)
        return None
