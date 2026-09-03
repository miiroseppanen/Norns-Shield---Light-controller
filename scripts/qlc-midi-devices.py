#!/usr/bin/env python3
"""Show QLC MIDI plugin lines vs the Shield Launchpad identity. Read-only."""

from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from light_console.machine import load_machine_profile


def qlc_midi_lines(html: str) -> list[tuple[str, str]]:
    return sorted(set(re.findall(r'value="(MIDI\|\d+)"[^>]*>([^<]*)', html)))


def main() -> int:
    profile = load_machine_profile()
    lp = profile.launchpad
    print("EXPECTED")
    print(f"  name {lp.name}")
    print(f"  uid  {lp.uid}")
    try:
        html = urllib.request.urlopen("http://127.0.0.1:9999/config", timeout=3).read().decode(
            "utf-8", "replace"
        )
    except OSError as exc:
        print("AVAILABLE IN QLC: no")
        print(f"  /config unreachable: {exc}")
        return 1
    lines = qlc_midi_lines(html)
    print("QLC MIDI LINES")
    for value, label in lines:
        print(f"  {value} {label.strip()}")
    names = " ".join(label for _, label in lines)
    uids_ok = lp.uid in html or lp.name in names
    available = lp.name in names
    print("AVAILABLE IN QLC:", "yes" if available else "no")
    print("UID IN PAGE:", "yes" if lp.uid in html else "no (QLC /config lists names/lines)")
    del uids_ok
    return 0 if available else 2


if __name__ == "__main__":
    raise SystemExit(main())
