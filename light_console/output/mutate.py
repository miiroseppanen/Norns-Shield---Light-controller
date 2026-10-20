"""Surgical QLC workspace Art-Net destination and universe-capacity edits.

Managed-universe patches change only QLC UI U2 / XML ID 1 Art-Net Output
line/UID/Name and PluginParameters outputIP. UniverseChannels edits are a
separate helper and must not change outputIP or routing.
"""

from __future__ import annotations

from pathlib import Path
import os
import re
import xml.etree.ElementTree as ET

from light_console.output.fixtures import parse_fixtures
from light_console.output.routing import is_loopback_ip, parse_output_routes
from light_console.output.targets import (
    MANAGED_QLC_UNIVERSE,
    MANAGED_XML_UNIVERSE_ID,
    PROD_PI,
    ApplyPlan,
    is_forbidden_apply_host,
)
from light_console.qxw import QxwError, _DOCTYPE

_UNIVERSE = re.compile(
    r"(<Universe\b[^>]*\bID=\"(\d+)\"[^>]*>)(.*?)(</Universe>)",
    re.IGNORECASE | re.DOTALL,
)
_ARTNET_OUTPUT = re.compile(
    r"(<Output\b)([^>]*\bPlugin=\"ArtNet\"[^>]*)(>)(.*?)(</Output>)",
    re.IGNORECASE | re.DOTALL,
)
_OUTPUT_IP = re.compile(r'\boutputIP="[^"]*"')
_UNIVERSE_CHANNELS = re.compile(r'\bUniverseChannels="[^"]*"')


class RoutePatchError(ValueError):
    """Managed Art-Net destination could not be patched safely."""


def universe_block(xml: str, universe_id: int) -> str | None:
    for match in _UNIVERSE.finditer(xml):
        if int(match.group(2)) == universe_id:
            return match.group(0)
    return None


def set_artnet_universe_channels(xml: str, xml_universe_id: int, channels: int) -> str:
    """Set Art-Net UniverseChannels on one universe. Leaves outputIP/routing intact."""
    if not isinstance(channels, int) or channels < 1 or channels > 512:
        raise RoutePatchError("UniverseChannels must be 1..512")
    found = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal found
        if int(match.group(2)) != xml_universe_id:
            return match.group(0)
        found += 1
        body = _set_output_channels(match.group(3), channels)
        return f"{match.group(1)}{body}{match.group(4)}"

    patched = _UNIVERSE.sub(repl, xml)
    if found == 0:
        raise RoutePatchError(f"universe ID {xml_universe_id} is missing")
    if found > 1:
        raise RoutePatchError(f"universe ID {xml_universe_id} is ambiguous")
    if PROD_PI in patched:
        raise RoutePatchError("production Pi address present")
    return patched


def _set_output_channels(body: str, channels: int) -> str:
    matches = list(_ARTNET_OUTPUT.finditer(body))
    if len(matches) != 1:
        raise RoutePatchError("Art-Net output is missing or ambiguous")

    def repl(match: re.Match[str]) -> str:
        inner = match.group(4)
        if _UNIVERSE_CHANNELS.search(inner):
            inner = _UNIVERSE_CHANNELS.sub(f'UniverseChannels="{channels}"', inner, count=1)
        else:
            inner = _insert_universe_channels(inner, channels)
        return f"{match.group(1)}{match.group(2)}{match.group(3)}{inner}{match.group(5)}"

    return _ARTNET_OUTPUT.sub(repl, body, count=1)


def _insert_universe_channels(inner: str, channels: int) -> str:
    def insert(match: re.Match[str]) -> str:
        opening, attrs, close = match.group(1), match.group(2), match.group(3)
        if "UniverseChannels=" in attrs:
            return match.group(0)
        return f'{opening}{attrs} UniverseChannels="{channels}"{close}'

    patched, n = re.subn(
        r"(<PluginParameters\b)([^>]*)(/?>)",
        insert,
        inner,
        count=1,
        flags=re.IGNORECASE,
    )
    if n != 1:
        raise RoutePatchError("PluginParameters missing on Art-Net output")
    return patched


def universe_channels(xml: str, xml_universe_id: int) -> int | None:
    block = universe_block(xml, xml_universe_id)
    if block is None:
        return None
    match = _UNIVERSE_CHANNELS.search(block)
    if match is None:
        return None
    raw = match.group(0).split("=", 1)[1].strip().strip('"')
    try:
        return int(raw)
    except ValueError:
        return None


def validate_universe_channels_patch(
    original: str, patched: str, xml_universe_id: int, channels: int
) -> None:
    """Routing, outputIP, and unrelated universes must stay identical."""
    _parse_workspace(patched)
    if PROD_PI in patched:
        raise RoutePatchError("production Pi address present")
    before = parse_output_routes(original)
    after = parse_output_routes(patched)
    if before != after:
        raise RoutePatchError("output routing changed")
    for match in _UNIVERSE.finditer(original):
        uid = int(match.group(2))
        if uid == xml_universe_id:
            continue
        if universe_block(original, uid) != universe_block(patched, uid):
            raise RoutePatchError(f"universe ID {uid} changed")
    block = universe_block(patched, xml_universe_id)
    if block is None:
        raise RoutePatchError(f"universe ID {xml_universe_id} is missing")
    if universe_channels(patched, xml_universe_id) != channels:
        raise RoutePatchError("UniverseChannels mismatch")
    orig_ip = _OUTPUT_IP.search(universe_block(original, xml_universe_id) or "")
    new_ip = _OUTPUT_IP.search(block)
    if (orig_ip.group(0) if orig_ip else "") != (new_ip.group(0) if new_ip else ""):
        raise RoutePatchError("outputIP changed")


def apply_universe_channels(path: Path, xml_universe_id: int, channels: int) -> bool:
    """Atomically set UniverseChannels. Returns False when already at target."""
    original = path.read_text(encoding="utf-8")
    if universe_channels(original, xml_universe_id) == channels:
        validate_universe_channels_patch(original, original, xml_universe_id, channels)
        return False
    patched = set_artnet_universe_channels(original, xml_universe_id, channels)
    validate_universe_channels_patch(original, patched, xml_universe_id, channels)
    tmp = path.with_name(f".{path.name}.next")
    tmp.write_text(patched, encoding="utf-8")
    try:
        text = tmp.read_text(encoding="utf-8")
        validate_universe_channels_patch(original, text, xml_universe_id, channels)
        _parse_workspace(text)
        if PROD_PI in text:
            raise RoutePatchError("production Pi address present")
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    os.replace(tmp, path)
    return True


def patch_managed_artnet(xml: str, plan: ApplyPlan) -> str:
    found = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal found
        if int(match.group(2)) != MANAGED_XML_UNIVERSE_ID:
            return match.group(0)
        found += 1
        body = _patch_artnet_output(match.group(3), plan)
        return f"{match.group(1)}{body}{match.group(4)}"

    patched = _UNIVERSE.sub(repl, xml)
    if found == 0:
        raise RoutePatchError("managed universe ID 1 is missing")
    if found > 1:
        raise RoutePatchError("managed universe ID 1 is ambiguous")
    return patched


def _patch_artnet_output(body: str, plan: ApplyPlan) -> str:
    matches = list(_ARTNET_OUTPUT.finditer(body))
    if len(matches) != 1:
        raise RoutePatchError("managed universe Art-Net output is missing or ambiguous")

    def repl(match: re.Match[str]) -> str:
        attrs = _set_attr(match.group(2), "Name", plan.line_name)
        attrs = _set_attr(attrs, "UID", plan.line_uid)
        attrs = _set_attr(attrs, "Line", str(plan.line))
        inner = _set_output_ip(match.group(4), plan.output_ip)
        return f"{match.group(1)}{attrs}{match.group(3)}{inner}{match.group(5)}"

    return _ARTNET_OUTPUT.sub(repl, body, count=1)


def _set_attr(attrs: str, name: str, value: str) -> str:
    pattern = rf'\b{name}="[^"]*"'
    if re.search(pattern, attrs, re.IGNORECASE):
        return re.sub(pattern, f'{name}="{value}"', attrs, count=1, flags=re.IGNORECASE)
    return attrs.rstrip() + f' {name}="{value}"'


def _set_output_ip(inner: str, ip: str) -> str:
    if _OUTPUT_IP.search(inner):
        return _OUTPUT_IP.sub(f'outputIP="{ip}"', inner, count=1)

    def insert(match: re.Match[str]) -> str:
        opening, attrs, close = match.group(1), match.group(2), match.group(3)
        if "outputIP=" in attrs:
            return match.group(0)
        return f"{opening}{attrs} outputIP=\"{ip}\"{close}"

    patched, n = re.subn(
        r"(<PluginParameters\b)([^>]*)(/?>)",
        insert,
        inner,
        count=1,
        flags=re.IGNORECASE,
    )
    if n != 1:
        raise RoutePatchError("PluginParameters missing on managed Art-Net output")
    return patched


def validate_managed_patch(original: str, patched: str, plan: ApplyPlan) -> None:
    _parse_workspace(patched)
    before = parse_output_routes(original)
    after = parse_output_routes(patched)
    wiz_before = [r for r in before if r.qlc_universe == 1]
    wiz_after = [r for r in after if r.qlc_universe == 1]
    if wiz_before != wiz_after:
        raise RoutePatchError("unrelated universe routing changed")
    if universe_block(original, 0) != universe_block(patched, 0):
        raise RoutePatchError("Universe 1 XML changed")
    managed = [r for r in after if r.qlc_universe == MANAGED_QLC_UNIVERSE]
    if len(managed) != 1:
        raise RoutePatchError("managed universe missing after patch")
    route = managed[0]
    if route.plugin != "ARTNET":
        raise RoutePatchError("managed output is not Art-Net")
    if route.output_ip != plan.output_ip:
        raise RoutePatchError("managed outputIP mismatch")
    if route.line != plan.line or route.line_uid != plan.line_uid:
        raise RoutePatchError("managed Art-Net line mismatch")
    if is_forbidden_apply_host(route.output_ip or ""):
        raise RoutePatchError("forbidden destination")
    others_before = [r for r in before if r.qlc_universe not in {1, MANAGED_QLC_UNIVERSE}]
    others_after = [r for r in after if r.qlc_universe not in {1, MANAGED_QLC_UNIVERSE}]
    if others_before != others_after:
        raise RoutePatchError("unrelated output routes changed")


def _parse_workspace(text: str) -> ET.Element:
    stripped = _DOCTYPE.sub("", text, count=1)
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError as exc:
        raise RoutePatchError(f"invalid XML: {exc}") from exc
    local = root.tag.rsplit("}", 1)[-1]
    if local != "Workspace":
        raise RoutePatchError(f"root is <{local}>, not Workspace")
    return root


def write_temp_and_validate(path: Path, original: str, patched: str, plan: ApplyPlan) -> Path:
    tmp = path.with_name(f".{path.name}.next")
    tmp.write_text(patched, encoding="utf-8")
    try:
        text = tmp.read_text(encoding="utf-8")
        validate_managed_patch(original, text, plan)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return tmp


def atomic_replace(tmp: Path, dest: Path) -> None:
    os.replace(tmp, dest)


def restore_exact(path: Path, original: bytes) -> None:
    tmp = path.with_name(f".{path.name}.restore")
    tmp.write_bytes(original)
    os.replace(tmp, path)


def parse_ok(path: Path) -> None:
    try:
        parse_output_routes(path.read_text(encoding="utf-8"))
    except (OSError, QxwError) as exc:
        raise RoutePatchError(str(exc)) from exc


def cover_universe_fixtures(xml: str, xml_universe_id: int = 0, cap: int = 512) -> str:
    """Raise advertised UniverseChannels when patched fixtures would be clipped."""
    if cap < 1 or cap > 512:
        raise RoutePatchError("UniverseChannels cap must be 1..512")
    have = universe_channels(xml, xml_universe_id)
    if have is None:
        return xml
    need = 0
    for fx in parse_fixtures(xml):
        if fx.universe_id == xml_universe_id:
            need = max(need, fx.address + fx.channels)
    if need <= have:
        return xml
    if need > cap:
        raise RoutePatchError(
            f"fixtures need {need} channels on universe ID {xml_universe_id}"
        )
    return set_artnet_universe_channels(xml, xml_universe_id, cap)


def preserve_managed_universe(prepared: str, current: str) -> str:
    """Copy current Shield U2 Art-Net onto a prepare_for_shield workspace.

    WiZ / QLC U1 (XML ID 0) stays as prepared (loopback). Current U2
    (XML ID 1) is transplanted verbatim. Never writes the operator source.
    """
    if PROD_PI in prepared or PROD_PI in current:
        raise RoutePatchError("production Pi address present")
    cur_block = universe_block(current, MANAGED_XML_UNIVERSE_ID)
    prep_block = universe_block(prepared, MANAGED_XML_UNIVERSE_ID)
    wiz_prep = universe_block(prepared, 0)
    if cur_block is None or prep_block is None or wiz_prep is None:
        raise RoutePatchError("U1/U2 universe block missing")
    routes = parse_output_routes(current)
    managed = [
        route
        for route in routes
        if route.qlc_universe == MANAGED_QLC_UNIVERSE and route.plugin == "ARTNET"
    ]
    if len(managed) != 1:
        raise RoutePatchError("current Shield master has no unique U2 Art-Net")
    dest = (managed[0].output_ip or "").strip()
    if dest and is_forbidden_apply_host(dest):
        raise RoutePatchError(f"refusing forbidden U2 destination {dest}")
    out = prepared if cur_block == prep_block else prepared.replace(prep_block, cur_block, 1)
    if universe_block(out, 0) != wiz_prep:
        raise RoutePatchError("WiZ loopback routing changed")
    if universe_block(out, MANAGED_XML_UNIVERSE_ID) != cur_block:
        raise RoutePatchError("U2 routing was not preserved")
    if PROD_PI in out:
        raise RoutePatchError("production Pi address present after preserve")
    wiz = [route for route in parse_output_routes(prepared) if route.qlc_universe == 1]
    if not wiz or not is_loopback_ip(wiz[0].output_ip or ""):
        raise RoutePatchError("prepared workspace lost WiZ loopback")
    return out
