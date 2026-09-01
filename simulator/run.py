"""python -m simulator.run"""

from __future__ import annotations

import sys

from light_console.main import main


def run(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--simulator" not in args and "--headless" not in args and "--dump-screen" not in args and "--screenshot" not in args:
        args = ["--simulator", *args]
    return main(args)


if __name__ == "__main__":
    raise SystemExit(run())
