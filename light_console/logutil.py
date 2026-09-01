from __future__ import annotations

import logging
import sys

LOG = logging.getLogger("light-console")


def setup_logging(debug: bool = False) -> None:
    """journalctl-friendly: stderr, no flood at INFO."""
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("pygame").setLevel(logging.WARNING)
