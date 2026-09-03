#!/usr/bin/env python3
"""Ask live QLC 5.2.2 which functions it has. Does not start/stop systemd."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from light_console.qlc.ws_client import QlcWebSocketClient

def main() -> int:
    q = QlcWebSocketClient(reconnect_seconds=0.2)
    for t in (0.0, 0.3, 0.6, 1.0, 1.5, 2.0):
        q.pump(t)
    print("connected", q.connected())
    print("project", q.project_loaded())
    print("n", q.functions_number)
    for fn in q.list_functions():
        print(f"{fn.function_id}\t{fn.type}\t{fn.name}")
    q.close()
    return 0 if q.connected() else 1

if __name__ == "__main__":
    raise SystemExit(main())
