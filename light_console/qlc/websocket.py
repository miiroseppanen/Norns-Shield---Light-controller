"""Real QLC+ WebSocket transport. Not used in Milestone 0.1."""

from __future__ import annotations


class QLCWebSocket:
    def __init__(self, url: str) -> None:
        self.url = url

    def connect(self) -> None:
        raise NotImplementedError(
            "Real QLC WebSocket is Milestone 0.3. 0.1 uses MockQLCClient. "
            "Documented API: docs/qlc-integration.md"
        )
