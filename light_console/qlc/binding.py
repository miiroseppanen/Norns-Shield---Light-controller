"""Push AppState toward QLC. Hardware and pages never call the client."""

from __future__ import annotations

import logging

from light_console.qlc.client import ConnectionState, QLCClient
from light_console.state import AppState

LOG = logging.getLogger("light-console")


class QlcBinding:
    def __init__(self, qlc: QLCClient) -> None:
        self.qlc = qlc
        self._sent_gm: int | None = None
        self._sent_blackout: bool | None = None
        self._sent_speed: int | None = None

    def pull(self, state: AppState) -> None:
        was = state.qlc_connected
        try:
            conn = self.qlc.connection_state()
            state.qlc_state = conn.value
            state.qlc_connected = conn is ConnectionState.CONNECTED
            state.qlc_project_loaded = bool(self.qlc.project_loaded())
            state.qlc_host = self.qlc.host_label()
        except Exception:
            LOG.exception("QLC status read failed")
            state.qlc_connected = False
            state.qlc_project_loaded = False
            state.qlc_state = ConnectionState.ERROR.value
        if was and not state.qlc_connected:
            LOG.warning("QLC connection lost")
            self._sent_gm = None
            self._sent_blackout = None
            self._sent_speed = None
        if not was and state.qlc_connected:
            LOG.info("QLC connected")
            self._sent_gm = None
            self._sent_blackout = None
            self._sent_speed = None

    def push(self, state: AppState) -> None:
        if not state.qlc_connected:
            return
        gm = 0 if state.blackout else int(state.master * 255 / 100)
        try:
            if gm != self._sent_gm:
                self.qlc.set_grand_master(gm)
                self._sent_gm = gm
            if state.blackout != self._sent_blackout:
                self.qlc.set_blackout(state.blackout)
                self._sent_blackout = state.blackout
            if state.speed != self._sent_speed:
                self.qlc.set_speed(state.speed)
                self._sent_speed = state.speed
        except Exception:
            LOG.exception("QLC push failed; UI continues")
