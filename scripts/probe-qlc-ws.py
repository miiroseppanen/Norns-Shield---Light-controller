#!/usr/bin/env python3
"""Non-destructive QLC+ 5.2.2 WebSocket probe. Does not start/stop systemd."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from light_console.qlc.ws_client import QlcWebSocketClient  # noqa: E402


def main() -> int:
    qlc = QlcWebSocketClient("ws://127.0.0.1:9999/qlcplusWS", reconnect_seconds=0.2)
    qlc.pump(0.0)
    qlc.pump(0.2)
    print(f"state={qlc.connection_state().value}")
    print(f"connected={qlc.connected()}")
    print(f"project={qlc.project_loaded()}")
    if not qlc.connected():
        qlc.close()
        return 1
    qlc.set_grand_master(128)
    qlc.pump(0.4)
    print(f"gm={qlc.grand_master}")
    print(f"sends={qlc.gm_sends}")
    qlc.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
