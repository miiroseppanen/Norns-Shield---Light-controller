"""OLED lifecycle splash. One-shot process; always exits 0 so boot/halt continue."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from light_console.display.lifecycle import (
    STARTING_UP_TEXT,
    SHUTTING_DOWN_TEXT,
    render_lifecycle,
    write_starting_mark,
)

LOG = logging.getLogger("shieldxl-lifecycle")
_STAMP = Path("/home/light/light-console/var/lifecycle.log")

MODES = {
    "starting-up": STARTING_UP_TEXT,
    "shutting-down": SHUTTING_DOWN_TEXT,
}


def show_lifecycle(message: str) -> None:
    """Open the SSD1322, paint one lifecycle frame, release SPI/GPIO. Never clears."""
    from light_console.hardware.oled import Ssd1322

    oled = Ssd1322()
    try:
        oled.init()
        oled.show_framebuffer(render_lifecycle(message))
        LOG.info("painted %s", message)
        _stamp(message)
        if message == STARTING_UP_TEXT:
            write_starting_mark()
    finally:
        oled.close()


def _stamp(message: str) -> None:
    """Append a reboot-surviving paint record. Best-effort; never blocks halt."""
    try:
        _STAMP.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with _STAMP.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts} {message}\n")
    except OSError:
        pass


def show_starting_up() -> None:
    show_lifecycle(STARTING_UP_TEXT)


def show_shutting_down() -> None:
    show_lifecycle(SHUTTING_DOWN_TEXT)


def _mode_from_argv(argv: list[str]) -> str:
    if not argv:
        return "starting-up"
    token = argv[0]
    if token in {"--starting-up", "starting-up"}:
        return "starting-up"
    if token in {"--shutting-down", "shutting-down"}:
        return "shutting-down"
    return token


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    mode = _mode_from_argv(args)
    message = MODES.get(mode)
    if message is None:
        LOG.error("unknown lifecycle mode %r", mode)
        return 0
    try:
        if mode == "starting-up":
            show_starting_up()
        else:
            show_shutting_down()
    except Exception:
        LOG.exception("%s splash failed; continuing", message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
