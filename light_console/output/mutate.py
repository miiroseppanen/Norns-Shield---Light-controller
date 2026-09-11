"""Surgical QLC workspace Art-Net destination edits.

Changes only the managed universe (QLC UI U2 / XML ID 1) Art-Net Output
line/UID/Name and PluginParameters outputIP. Unrelated XML is preserved.
"""

from __future__ import annotations

from pathlib import Path
import os
import re
import xml.etree.ElementTree as ET

from light_console.output.routing import parse_output_routes
from light_console.output.targets import (
    MANAGED_QLC_UNIVERSE,
    MANAGED_XML_UNIVERSE_ID,
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


class RoutePatchError(ValueError):
    """Managed Art-Net destination could not be patched safely."""


def universe_block(xml: str, universe_id: int) -> str | None:
    for match in _UNIVERSE.finditer(xml):
        if int(match.group(2)) == universe_id:
            return match.group(0)
    return None


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
