"""Read-only QLC /config OUTPUT mapping. GET only; never patches plugin lines."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen
import re

from light_console.output.routing import SOURCE_RUNTIME, OutputRoute

_OUTPUT_SELECT = re.compile(
    r"<select[^>]*ioChanged\('OUTPUT',\s*(\d+)[^>]*>\s*(.*?)</select>",
    re.I | re.S,
)
_OPTION = re.compile(
    r"<option\s+value=\"([^\"]+)\"\s*(selected)?\s*>([^<]*)",
    re.I,
)


def config_url_from_websocket(ws_url: str) -> str:
    parsed = urlparse(ws_url)
    scheme = "https" if parsed.scheme in ("wss", "https") else "http"
    return urlunparse((scheme, parsed.netloc, "/config", "", "", ""))


def parse_config_outputs(html: str) -> tuple[OutputRoute, ...]:
    routes: list[OutputRoute] = []
    for match in _OUTPUT_SELECT.finditer(html):
        uni_id = int(match.group(1))
        body = match.group(2)
        selected = None
        for option in _OPTION.finditer(body):
            if option.group(2):
                selected = (option.group(1), option.group(3).strip())
                break
        if selected is None:
            continue
        value, label = selected
        plugin, sep, line_s = value.partition("|")
        if not sep or plugin.lower() == "none":
            continue
        try:
            line = int(line_s)
        except ValueError:
            line = None
        if line is not None and line < 0:
            continue
        uid = label.split("]", 1)[-1].strip() if "]" in label else label
        plugin_name = plugin.upper()
        wire = uni_id if plugin_name == "ARTNET" else None
        routes.append(
            OutputRoute(
                qlc_universe=uni_id + 1,
                name=f"Universe {uni_id + 1}",
                plugin=plugin_name,
                line=line,
                line_uid=uid,
                output_ip=None,
                wire_universe=wire,
                source=SOURCE_RUNTIME,
            )
        )
    return tuple(routes)


def fetch_config_html(url: str, timeout: float = 1.0) -> str:
    with urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")
