from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # Pi may run without PyYAML if no config file is used
    yaml = None  # type: ignore[assignment]

DEFAULT_CONFIG_NAME = "light-console.yaml"


@dataclass
class DisplayConfig:
    fps: int = 15
    width: int = 128
    height: int = 64
    scale: int = 6


@dataclass
class WizConfig:
    expected: int = 6
    interface: str = "wlan1"


@dataclass
class KeyMapping:
    short: str = "none"
    long: str = "none"


@dataclass
class ControlsConfig:
    encoder1: str = "master_dimmer"
    encoder2: str = "select"
    encoder3: str = "speed"
    long_press_ms: int = 600
    key1: KeyMapping = field(default_factory=lambda: KeyMapping("blackout", "all_off"))
    key2: KeyMapping = field(default_factory=lambda: KeyMapping("go", "home"))
    key3: KeyMapping = field(default_factory=lambda: KeyMapping("special", "menu"))
    special_name: str = "special"


@dataclass
class QlcConfig:
    websocket: str = "ws://127.0.0.1:9999/qlcplusWS"
    reconnect_seconds: float = 2.0
    engine_version: str = "5.2.2"


@dataclass
class NetworkConfig:
    wiz_interface: str = "wlan1"
    upstream_interface: str = "wlan0"
    wiz_ap_ssid: str = "WIZ-LIGHTS"


@dataclass
class DmxConfig:
    pknight_ip: str = "192.168.88.201"


@dataclass
class MidiConfig:
    launchpad_usb_id: str = "1235:0036"
    launchpad_alsa_name: str = "Launchpad Mini"


@dataclass
class AppConfig:
    display: DisplayConfig = field(default_factory=DisplayConfig)
    wiz: WizConfig = field(default_factory=WizConfig)
    controls: ControlsConfig = field(default_factory=ControlsConfig)
    qlc: QlcConfig = field(default_factory=QlcConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    dmx: DmxConfig = field(default_factory=DmxConfig)
    midi: MidiConfig = field(default_factory=MidiConfig)
    debug: bool = False

    @property
    def fps(self) -> int:
        return self.display.fps


def _key_mapping(raw: Any, default: KeyMapping) -> KeyMapping:
    if not isinstance(raw, dict):
        return default
    return KeyMapping(
        short=str(raw.get("short", default.short)),
        long=str(raw.get("long", default.long)),
    )


def load_config(path: Path | None = None) -> AppConfig:
    data: dict[str, Any] = {}
    if path is not None:
        if yaml is None:
            raise RuntimeError("PyYAML is required to load a config file")
        data = yaml.safe_load(path.read_text()) or {}

    display_raw = data.get("display") or {}
    wiz_raw = data.get("wiz") or {}
    controls_raw = data.get("controls") or {}
    qlc_raw = data.get("qlc") or {}
    network_raw = data.get("network") or {}
    dmx_raw = data.get("dmx") or {}
    midi_raw = data.get("midi") or {}

    defaults = ControlsConfig()
    controls = ControlsConfig(
        encoder1=str(controls_raw.get("encoder1", defaults.encoder1)),
        encoder2=str(controls_raw.get("encoder2", defaults.encoder2)),
        encoder3=str(controls_raw.get("encoder3", defaults.encoder3)),
        long_press_ms=int(controls_raw.get("long_press_ms", defaults.long_press_ms)),
        key1=_key_mapping(controls_raw.get("key1"), defaults.key1),
        key2=_key_mapping(controls_raw.get("key2"), defaults.key2),
        key3=_key_mapping(controls_raw.get("key3"), defaults.key3),
        special_name=str(controls_raw.get("special_name", defaults.special_name)),
    )

    return AppConfig(
        display=DisplayConfig(
            fps=int(display_raw.get("fps", 15)),
            width=int(display_raw.get("width", 128)),
            height=int(display_raw.get("height", 64)),
            scale=int(display_raw.get("scale", 6)),
        ),
        wiz=WizConfig(
            expected=int(wiz_raw.get("expected", 6)),
            interface=str(wiz_raw.get("interface", network_raw.get("wiz_interface", "wlan1"))),
        ),
        controls=controls,
        qlc=QlcConfig(
            websocket=str(qlc_raw.get("websocket", "ws://127.0.0.1:9999/qlcplusWS")),
            reconnect_seconds=float(qlc_raw.get("reconnect_seconds", 2.0)),
            engine_version=str(qlc_raw.get("engine_version", "5.2.2")),
        ),
        network=NetworkConfig(
            wiz_interface=str(network_raw.get("wiz_interface", "wlan1")),
            upstream_interface=str(network_raw.get("upstream_interface", "wlan0")),
            wiz_ap_ssid=str(network_raw.get("wiz_ap_ssid", "WIZ-LIGHTS")),
        ),
        dmx=DmxConfig(pknight_ip=str(dmx_raw.get("pknight_ip", "192.168.88.201"))),
        midi=MidiConfig(
            launchpad_usb_id=str(midi_raw.get("launchpad_usb_id", "1235:0036")),
            launchpad_alsa_name=str(midi_raw.get("launchpad_alsa_name", "Launchpad Mini")),
        ),
        debug=bool(data.get("debug", False)),
    )


def example_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "light-console.example.yaml"
