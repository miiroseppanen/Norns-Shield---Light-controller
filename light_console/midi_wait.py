"""Wait a bounded time for the Shield Launchpad before QLC starts.

Exits 0 whether the pad appears or not. Does not start, stop, or restart QLC.
Does not use ALSA client numbers.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time
from collections.abc import Callable

from light_console.machine import ShieldMachineProfile, load_machine_profile

LOG = logging.getLogger("wait-launchpad")
DEFAULT_TIMEOUT_S = 12.0
POLL_S = 0.4


def launchpad_visible(profile: ShieldMachineProfile) -> bool:
    lp = profile.launchpad
    usb = _cmd_text(["lsusb"])
    if lp.usb_id.lower() in usb.lower():
        return True
    amidi = _cmd_text(["amidi", "-l"])
    if lp.name in amidi:
        return True
    aconnect = _cmd_text(["aconnect", "-l"])
    if lp.name in aconnect:
        return True
    return False


def wait_for_launchpad(
    profile: ShieldMachineProfile | None = None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    visible: Callable[[ShieldMachineProfile], bool] | None = None,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    profile = profile or load_machine_profile()
    probe = visible or launchpad_visible
    deadline = now() + max(0.0, timeout_s)
    if probe(profile):
        LOG.warning(
            "Launchpad present (%s, USB %s)",
            profile.launchpad.name,
            profile.launchpad.usb_id,
        )
        return True
    while now() < deadline:
        sleep(min(POLL_S, max(0.0, deadline - now())))
        if probe(profile):
            LOG.warning(
                "Launchpad present (%s, USB %s)",
                profile.launchpad.name,
                profile.launchpad.usb_id,
            )
            return True
    LOG.warning(
        "Launchpad not seen in %.0fs (%s / USB %s); starting QLC anyway",
        timeout_s,
        profile.launchpad.name,
        profile.launchpad.usb_id,
    )
    return False


def _cmd_text(argv: list[str]) -> str:
    binary = argv[0]
    if shutil.which(binary) is None:
        return ""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout or ""


def main(argv: list[str] | None = None) -> int:
    del argv
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    try:
        profile = load_machine_profile()
    except Exception as exc:
        LOG.warning("Launchpad wait skipped: %s; starting QLC anyway", exc)
        return 0
    wait_for_launchpad(profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
