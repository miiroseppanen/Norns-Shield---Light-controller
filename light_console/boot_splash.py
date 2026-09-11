"""Early OLED STARTING UP. One-shot process; always exits 0 so boot continues."""

from __future__ import annotations

import logging
import sys

from light_console.display.lifecycle import STARTING_UP_TEXT, render_lifecycle

LOG = logging.getLogger("shieldxl-starting")


def show_starting_up() -> None:
    """Open the SSD1322, paint STARTING UP, release SPI/GPIO. Never clears."""
    from light_console.hardware.oled import Ssd1322

    oled = Ssd1322()
    try:
        oled.init()
        oled.show_framebuffer(render_lifecycle(STARTING_UP_TEXT))
    finally:
        oled.close()


def main(argv: list[str] | None = None) -> int:
    del argv
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    try:
        show_starting_up()
    except Exception:
        LOG.exception("STARTING UP splash failed; continuing boot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
