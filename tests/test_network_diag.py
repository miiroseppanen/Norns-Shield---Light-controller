from light_console.output.network import (
    KIND_ONBOARD,
    KIND_USB,
    collect_network,
    oled_iface_lines,
    parse_nmcli_device_status,
    parse_udev_properties,
    usb_id_from_udev,
)
from light_console.output.pages import pack_network_pages

UDEV_WLAN0 = """
DEVTYPE=wlan
INTERFACE=wlan0
ID_NET_DRIVER=brcmfmac
ID_PATH=platform-fe300000.mmcnr
"""

UDEV_WLAN1 = """
DEVTYPE=wlan
INTERFACE=wlan1
ID_NET_DRIVER=rtw88_8821cu
ID_BUS=usb
ID_MODEL=802.11ac_NIC
ID_MODEL_ID=c811
ID_VENDOR=Realtek
ID_VENDOR_ID=0bda
ID_USB_MODEL=802.11ac_NIC
ID_USB_MODEL_ID=c811
ID_USB_VENDOR=Realtek
ID_USB_VENDOR_ID=0bda
ID_USB_DRIVER=rtw88_8821cu
ID_PATH=platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0
"""

UDEV_ETH0 = """
INTERFACE=eth0
ID_NET_DRIVER=bcmgenet
ID_PATH=platform-fd580000.ethernet
"""

UDEV_LO = """
INTERFACE=lo
"""

NM_STATUS = """
wlan0:wifi:connected:netplan-wlan0-LIGHT-CONTROL
lo:loopback:connected (externally):lo
wlan1:wifi:disconnected:
p2p-dev-wlan0:wifi-p2p:disconnected:
eth0:ethernet:unavailable:
"""

IP_BR = """
lo               UNKNOWN        127.0.0.1/8 ::1/128
eth0             DOWN
wlan0            UP             192.168.88.246/24
wlan1            DOWN
"""

LINK_BR = """
lo               UNKNOWN        00:00:00:00:00:00 <LOOPBACK,UP,LOWER_UP>
eth0             DOWN           88:a2:9e:5f:ca:0f <NO-CARRIER,BROADCAST,MULTICAST,UP>
wlan0            UP             88:a2:9e:5f:ca:10 <BROADCAST,MULTICAST,UP,LOWER_UP>
wlan1            DOWN           00:e0:4c:5d:de:bb <NO-CARRIER,BROADCAST,MULTICAST,UP>
"""

UDEV = {
    "wlan0": parse_udev_properties(UDEV_WLAN0),
    "wlan1": parse_udev_properties(UDEV_WLAN1),
    "eth0": parse_udev_properties(UDEV_ETH0),
    "lo": parse_udev_properties(UDEV_LO),
}


def _collect(**kwargs):
    defaults = dict(
        ip_text=IP_BR,
        link_text=LINK_BR,
        sys_names=("lo", "eth0", "wlan0", "wlan1", "p2p-dev-wlan0"),
        udev_for=UDEV,
        nm_status_text=NM_STATUS,
        ssid_for=lambda name: "LIGHT-CONTROL" if name == "wlan0" else "",
        wireless_for=lambda name: name.startswith("wl") and not name.startswith("p2p"),
        driver_for=lambda name: {
            "wlan0": "brcmfmac",
            "wlan1": "rtw88_8821cu",
            "eth0": "bcmgenet",
        }.get(name, ""),
        mac_for=lambda name: {
            "wlan0": "88:a2:9e:5f:ca:10",
            "wlan1": "00:e0:4c:5d:de:bb",
            "eth0": "88:a2:9e:5f:ca:0f",
        }.get(name, ""),
    )
    defaults.update(kwargs)
    return collect_network(**defaults)


def test_udev_usb_id_and_nm_status_parsers():
    udev = parse_udev_properties(UDEV_WLAN1)
    assert usb_id_from_udev(udev) == "0bda:c811"
    nm = parse_nmcli_device_status(NM_STATUS)
    assert nm["wlan0"].state == "connected"
    assert nm["wlan1"].state == "disconnected"
    assert nm["eth0"].state == "unavailable"
    assert nm["wlan1"].connection == ""


def test_collect_distinguishes_onboard_usb_ethernet_loopback():
    ifaces = _collect()
    names = [iface.name for iface in ifaces]
    assert "p2p-dev-wlan0" not in names
    by_name = {iface.name: iface for iface in ifaces}
    assert names[:4] == ["wlan0", "wlan1", "eth0", "lo"]
    onboard = by_name["wlan0"]
    assert onboard.kind == KIND_ONBOARD
    assert onboard.driver == "brcmfmac"
    assert onboard.usb_id == ""
    assert onboard.ipv4 == "192.168.88.246"
    assert onboard.ssid == "LIGHT-CONTROL"
    assert onboard.nm_state == "connected"
    assert onboard.managed is True
    usb = by_name["wlan1"]
    assert usb.kind == KIND_USB
    assert usb.usb_id == "0bda:c811"
    assert usb.driver == "rtw88_8821cu"
    assert usb.manufacturer == "Realtek"
    assert "802.11ac" in usb.product
    assert usb.mac == "00:e0:4c:5d:de:bb"
    assert usb.ipv4 == ""
    assert usb.ssid == ""
    assert usb.nm_state == "disconnected"
    assert usb.nm_connection == ""
    assert usb.managed is True
    assert by_name["eth0"].kind == "ethernet"
    assert by_name["eth0"].nm_state == "unavailable"
    assert by_name["lo"].kind == "loopback"


def test_oled_usb_disconnected_shows_driver_not_ip():
    usb = {iface.name: iface for iface in _collect()}["wlan1"]
    assert oled_iface_lines(usb) == ("wlan1", "DISCONNECTED", "rtw88_8821cu")
    onboard = {iface.name: iface for iface in _collect()}["wlan0"]
    assert oled_iface_lines(onboard) == ("wlan0", "LIGHT-CONTROL", "192.168.88.246")


def test_dongle_absent_is_omitted():
    ifaces = _collect(
        ip_text="wlan0            UP             192.168.88.246/24\n",
        sys_names=("wlan0",),
        udev_for={"wlan0": parse_udev_properties(UDEV_WLAN0)},
        nm_status_text="wlan0:wifi:connected:netplan-wlan0-LIGHT-CONTROL\n",
        link_text="wlan0            UP             88:a2:9e:5f:ca:10\n",
    )
    names = [iface.name for iface in ifaces]
    assert names == ["wlan0"]
    assert all(iface.kind != KIND_USB for iface in ifaces)


def test_unmanaged_and_unknown_driver():
    udev = parse_udev_properties(UDEV_WLAN1)
    udev = {**udev, "ID_NET_DRIVER": "", "ID_USB_DRIVER": ""}
    ifaces = _collect(
        sys_names=("wlan1",),
        ip_text="wlan1            DOWN\n",
        udev_for={"wlan1": udev},
        nm_status_text="wlan1:wifi:unmanaged:\n",
        driver_for=lambda name: "",
        ssid_for=lambda name: "",
    )
    usb = ifaces[0]
    assert usb.kind == KIND_USB
    assert usb.driver == ""
    assert usb.managed is False
    assert oled_iface_lines(usb) == ("wlan1", "UNMANAGED")


def test_usb_wifi_not_assumed_to_be_wlan1():
    udev = parse_udev_properties(UDEV_WLAN1.replace("wlan1", "wlan2"))
    ifaces = collect_network(
        ip_text="wlan2            DOWN\n",
        sys_names=("wlan2",),
        udev_for={"wlan2": udev},
        nm_status_text="wlan2:wifi:disconnected:\n",
        wireless_for=lambda name: True,
        driver_for=lambda name: "rtw88_8821cu",
        mac_for=lambda name: "00:e0:4c:5d:de:bb",
        ssid_for=lambda name: "",
    )
    assert ifaces[0].name == "wlan2"
    assert ifaces[0].kind == KIND_USB
    assert ifaces[0].usb_id == "0bda:c811"
    assert oled_iface_lines(ifaces[0]) == ("wlan2", "DISCONNECTED", "rtw88_8821cu")


def test_network_pages_pack_connected_and_disconnected():
    pages = pack_network_pages(_collect())
    joined = "\n".join(pages[0].lines)
    assert "wlan0" in joined
    assert "LIGHT-CONTROL" in joined
    assert "192.168.88.246" in joined
    assert "wlan1" in joined
    assert "DISCONNECTED" in joined
    assert "rtw88_8821cu" in joined
    assert "192.168.88.242" not in joined
    by_name = {item.title: item.status for item in pages[0].items}
    assert by_name["LIGHT-CONTROL"] == "CLIENT"
    assert by_name["wlan1"] == "DISCONNECTED"
    assert "lo" not in by_name
    assert "CLIENT" in joined
