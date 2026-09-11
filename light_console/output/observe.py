"""Background network / MIDI presence snapshot.

The UI tick only reads cached fields. nmcli, ip, and HTTP never run on
the render/input thread.

QLC /config is not polled here. Generating that HTML runs on QLC's Qt
thread and stalls Launchpad MIDI for seconds.
"""

from __future__ import annotations

import logging
import threading
import time

from light_console.output.network import NetIface, collect_network
from light_console.status.midi import launchpad_usb_present

LOG = logging.getLogger("light-console")

NET_INTERVAL_S = 2.0
SLOW_SNAPSHOT_S = 0.12


class LiveDiagnostics:
    """Daemon refresher. Safe to poll from the UI thread."""

    def __init__(
        self,
        *,
        config_url: str = "",
        usb_id: str = "1235:0036",
        net_interval_s: float = NET_INTERVAL_S,
        collect=collect_network,
        usb_present=launchpad_usb_present,
        start: bool = True,
    ) -> None:
        del config_url
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._usb_id = usb_id
        self._net_interval = max(0.2, float(net_interval_s))
        self._collect = collect
        self._usb_present = usb_present
        self.ifaces: tuple[NetIface, ...] = ()
        self.launchpad = False
        self.last_net_ms = 0.0
        self._thread = threading.Thread(target=self._loop, daemon=True, name="lc-diag")
        if start:
            self._thread.start()

    def close(self) -> None:
        self._stop.set()

    def snapshot(self) -> tuple[tuple[NetIface, ...], bool]:
        with self._lock:
            return self.ifaces, self.launchpad

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._refresh_net()
            self._stop.wait(self._net_interval)

    def _refresh_net(self) -> None:
        t0 = time.monotonic()
        try:
            ifaces = self._collect()
        except Exception:
            LOG.debug("network snapshot failed", exc_info=True)
            ifaces = None
        try:
            launchpad = bool(self._usb_present(self._usb_id))
        except Exception:
            LOG.debug("launchpad snapshot failed", exc_info=True)
            launchpad = None
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        if elapsed_ms >= SLOW_SNAPSHOT_S * 1000.0:
            LOG.warning("diag snapshot %.0fms (background)", elapsed_ms)
        with self._lock:
            if ifaces is not None:
                self.ifaces = ifaces
            if launchpad is not None:
                self.launchpad = launchpad
            self.last_net_ms = elapsed_ms
