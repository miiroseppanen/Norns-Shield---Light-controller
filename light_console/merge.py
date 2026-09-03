"""Merge imported .qxw show content into a Shield master workspace.

Master owns machine I/O (Launchpad + Art-Net loopback). Imports contribute
fixtures and Scene/Chaser functions only. IDs are remapped; the source file
is never written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from light_console.machine import ShieldMachineProfile, load_machine_profile
from light_console.qxw import QxwError, prepare_for_shield
from light_console.showdef import FunctionRef, ShowDefinition, dump_show_yaml

_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)
_FIXTURE = re.compile(r"<Fixture\b.*?</Fixture>", re.IGNORECASE | re.DOTALL)
_FUNCTION = re.compile(r"<Function\b([^>]*)>.*?</Function>", re.IGNORECASE | re.DOTALL)
_FUNC_ATTR = re.compile(r'\b(ID|Type|Name)="([^"]*)"', re.IGNORECASE)
_FIXTURE_ID = re.compile(r"<ID>(\d+)</ID>", re.IGNORECASE)
_ENGINE_CLOSE = re.compile(r"</Engine>", re.IGNORECASE)
_VC_INNER = re.compile(
    r"<VirtualConsole\b[^>]*>(.*?)</VirtualConsole>", re.IGNORECASE | re.DOTALL
)
_IOMAP = re.compile(
    r"<InputOutputMap\b.*?</InputOutputMap>", re.IGNORECASE | re.DOTALL
)
ALLOWED_TYPES = frozenset({"scene", "chaser"})
UNSUPPORTED = (
    "Collection",
    "EFX",
    "RGBMatrix",
    "Sequence",
    "Script",
    "Audio",
    "Video",
    "Show",
)


@dataclass(frozen=True)
class MergePlan:
    show: ShowDefinition
    fixture_map: dict[int, int]
    function_map: dict[int, int]
    function_names: dict[int, str]
    function_types: dict[int, str]


def empty_master_xml(profile: ShieldMachineProfile | None = None) -> str:
    lp = (profile or load_machine_profile()).launchpad
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE Workspace>\n"
        '<Workspace xmlns="http://www.qlcplus.org/Workspace" '
        'CurrentWindow="FunctionManager">\n'
        " <Creator>\n"
        "  <Name>Q Light Controller Plus</Name>\n"
        "  <Version>5.2.2</Version>\n"
        "  <Author>light-console-master</Author>\n"
        " </Creator>\n"
        " <Engine>\n"
        "  <InputOutputMap>\n"
        '   <Universe Name="Loopback" ID="0">\n'
        f'    <Input Plugin="MIDI" Name="{lp.name}" UID="{lp.uid}" '
        f'Line="{lp.line_fallback}" Profile="{lp.profile}"/>\n'
        f'    <Feedback Plugin="MIDI" Name="{lp.name}" UID="{lp.uid}" '
        f'Line="{lp.line_fallback}"/>\n'
        '    <Output Plugin="ArtNet" UID="127.0.0.1" Line="0">\n'
        '     <PluginParameters outputIP="127.0.0.1" outputUni="0"/>\n'
        "    </Output>\n"
        "   </Universe>\n"
        "  </InputOutputMap>\n"
        " </Engine>\n"
        " <VirtualConsole>\n"
        " </VirtualConsole>\n"
        "</Workspace>\n"
    )


def format_merge_report(plan: MergePlan) -> str:
    lines = [
        f"SHOW {plan.show.name} ({plan.show.show_id})",
        f"source {plan.show.source}",
        "",
        "SOURCE -> MASTER",
        "",
        "Fixture:",
    ]
    for src, dest in sorted(plan.fixture_map.items()):
        lines.append(f"  {src} -> {dest}")
    lines.append("")
    lines.append("Function:")
    for src, dest in sorted(plan.function_map.items()):
        name = plan.function_names.get(src, "")
        lines.append(f"  {src} {name} -> {dest}")
    return "\n".join(lines)


def plan_merge(
    master_text: str,
    source_text: str,
    *,
    show_id: str,
    show_name: str,
    source_name: str,
) -> MergePlan:
    _reject_unsupported(source_text)
    prepare_for_shield(source_text)
    master_used_fx = {fid for fid, _ in _parse_fixtures(master_text)}
    master_used_fn = {fid for fid, _, _ in _parse_functions(master_text)}
    src_fixtures = _parse_fixtures(source_text)
    src_functions = _parse_functions(source_text)
    if not src_functions:
        raise QxwError("source has no Scene/Chaser functions")

    fixture_map: dict[int, int] = {}
    next_fx = 0
    for src_id, _block in src_fixtures:
        dest = _next_free(master_used_fx | set(fixture_map.values()), next_fx)
        fixture_map[src_id] = dest
        next_fx = dest + 1

    function_map: dict[int, int] = {}
    names: dict[int, str] = {}
    types: dict[int, str] = {}
    next_scene = 100
    next_chaser = 200
    used_fn = set(master_used_fn)
    for src_id, type_name, name in src_functions:
        names[src_id] = name
        types[src_id] = type_name
        start = 100 if type_name.lower() == "scene" else 200
        cursor = next_scene if type_name.lower() == "scene" else next_chaser
        dest = _next_free(used_fn | set(function_map.values()), max(start, cursor))
        function_map[src_id] = dest
        used_fn.add(dest)
        if type_name.lower() == "scene":
            next_scene = dest + 1
        else:
            next_chaser = dest + 1

    scenes = tuple(
        FunctionRef(function_map[fid], name)
        for fid, type_name, name in src_functions
        if type_name.lower() == "scene"
    )
    chasers = tuple(
        FunctionRef(function_map[fid], name)
        for fid, type_name, name in src_functions
        if type_name.lower() == "chaser"
    )
    show = ShowDefinition(
        show_id=show_id,
        name=show_name,
        source=source_name,
        scenes=scenes,
        chasers=chasers,
    )
    return MergePlan(
        show=show,
        fixture_map=fixture_map,
        function_map=function_map,
        function_names=names,
        function_types=types,
    )


def apply_merge(master_text: str, source_text: str, plan: MergePlan) -> str:
    if not master_text.strip():
        raise QxwError("empty master workspace")
    io = _IOMAP.search(master_text)
    if io is None:
        raise QxwError("master has no InputOutputMap")
    master_io = io.group(0)
    chunks: list[str] = []
    for src_id, block in _parse_fixtures(source_text):
        dest = plan.fixture_map[src_id]
        chunks.append(_remap_fixture(block, dest))
    src_fn_blocks = {
        int(attrs["id"]): block
        for block, attrs in _function_blocks(source_text)
    }
    for src_id, dest in sorted(plan.function_map.items(), key=lambda kv: kv[1]):
        chunks.append(
            _remap_function(
                src_fn_blocks[src_id],
                dest,
                plan.fixture_map,
                plan.function_map,
            )
        )
    insert = "".join(f"\n{chunk}" for chunk in chunks)
    if not _ENGINE_CLOSE.search(master_text):
        raise QxwError("master has no Engine")
    merged = _ENGINE_CLOSE.sub(insert + "\n </Engine>", master_text, count=1)
    # Restore master I/O in case source leftovers were copied (they are not).
    merged_io = _IOMAP.search(merged)
    if merged_io is None:
        raise QxwError("merged workspace lost InputOutputMap")
    merged = merged[: merged_io.start()] + master_io + merged[merged_io.end() :]
    return prepare_for_shield(merged)


def merge_files(
    master_path: Path,
    source_path: Path,
    *,
    show_id: str,
    show_name: str,
    apply: bool,
) -> tuple[MergePlan, str]:
    source_path = source_path.resolve()
    master_path = master_path.resolve()
    if source_path == master_path:
        raise QxwError("refusing to merge a file onto itself")
    source = source_path.read_text(encoding="utf-8")
    if master_path.is_file():
        master = master_path.read_text(encoding="utf-8")
    else:
        master = empty_master_xml()
    plan = plan_merge(
        master,
        source,
        show_id=show_id,
        show_name=show_name,
        source_name=source_path.name,
    )
    patched = apply_merge(master, source, plan) if apply else master
    if apply:
        master_path.parent.mkdir(parents=True, exist_ok=True)
        master_path.write_text(patched, encoding="utf-8")
        meta = master_path.parent / f"{show_id}.yaml"
        meta.write_text(dump_show_yaml(plan.show), encoding="utf-8")
    return plan, patched


def _next_free(used: set[int], start: int) -> int:
    n = max(0, start)
    while n in used:
        n += 1
    return n


def _reject_unsupported(text: str) -> None:
    inner = _VC_INNER.search(text)
    if inner and inner.group(1).strip():
        raise QxwError("unsupported Virtual Console content in source")
    for kind in UNSUPPORTED:
        if re.search(rf'\bType="{kind}"', text, re.IGNORECASE):
            raise QxwError(f"unsupported function type: {kind}")
        if re.search(rf"<{kind}\b", text, re.IGNORECASE) and kind != "Show":
            raise QxwError(f"unsupported dependency: {kind}")


def _parse_fixtures(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for block in _FIXTURE.findall(text):
        match = _FIXTURE_ID.search(block)
        if not match:
            raise QxwError("fixture missing <ID>")
        found.append((int(match.group(1)), block))
    return found


def _function_blocks(text: str) -> list[tuple[str, dict[str, str]]]:
    found: list[tuple[str, dict[str, str]]] = []
    for match in _FUNCTION.finditer(text):
        attrs = {k.lower(): v for k, v in _FUNC_ATTR.findall(match.group(1))}
        found.append((match.group(0), attrs))
    return found


def _parse_functions(text: str) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    for block, attrs in _function_blocks(text):
        del block
        try:
            fid = int(attrs["id"])
        except (KeyError, ValueError) as exc:
            raise QxwError("function missing ID") from exc
        type_name = (attrs.get("type") or "").strip()
        name = (attrs.get("name") or "").strip()
        if not name:
            raise QxwError(f"function {fid} missing Name")
        if type_name.lower() not in ALLOWED_TYPES:
            raise QxwError(f"unsupported function type: {type_name}")
        found.append((fid, type_name, name))
    return found


def _remap_fixture(block: str, new_id: int) -> str:
    return _FIXTURE_ID.sub(f"<ID>{new_id}</ID>", block, count=1)


def _remap_function(
    block: str,
    new_id: int,
    fixture_map: dict[int, int],
    function_map: dict[int, int],
) -> str:
    block = re.sub(
        r'(<Function\b[^>]*\bID=")\d+(")',
        rf"\g<1>{new_id}\2",
        block,
        count=1,
        flags=re.IGNORECASE,
    )

    def fixture_val(match: re.Match[str]) -> str:
        old = int(match.group(2))
        if old not in fixture_map:
            raise QxwError(f"scene references unknown fixture {old}")
        return f"{match.group(1)}{fixture_map[old]}{match.group(3)}"

    block = re.sub(r'(<FixtureVal ID=")(\d+)(")', fixture_val, block, flags=re.IGNORECASE)

    def step(match: re.Match[str]) -> str:
        old = int(match.group(2))
        if old not in function_map:
            raise QxwError(f"chaser step references unknown function {old}")
        return f"{match.group(1)}{function_map[old]}{match.group(3)}"

    return re.sub(r'(<Step\b[^>]*>)(\d+)(</Step>)', step, block, flags=re.IGNORECASE)
