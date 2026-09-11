from __future__ import annotations

from pathlib import Path

from light_console.state import AppState

USB_DEVICES = Path("/sys/bus/usb/devices")


def launchpad_usb_present(usb_id: str = "1235:0036") -> bool:
    """True when the Launchpad USB ids exist in sysfs. No lsusb/ALSA."""
    vendor, _, product = usb_id.lower().partition(":")
    if not vendor or not product:
        return False
    if not USB_DEVICES.is_dir():
        return False
    try:
        children = list(USB_DEVICES.iterdir())
    except OSError:
        return False
    for dev in children:
        try:
            got_v = (dev / "idVendor").read_text().strip().lower()
            got_p = (dev / "idProduct").read_text().strip().lower()
        except OSError:
            continue
        if got_v == vendor and got_p == product:
            return True
    return False


def apply_launchpad(state: AppState, connected: bool) -> None:
    state.launchpad_connected = connected
