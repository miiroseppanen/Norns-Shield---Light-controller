"""Transactional QLC Art-Net destination apply with rollback."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import logging
import time

from light_console.output.mutate import (
    RoutePatchError,
    atomic_replace,
    parse_ok,
    patch_managed_artnet,
    restore_exact,
    write_temp_and_validate,
)
from light_console.output.routing import parse_output_routes
from light_console.output.targets import (
    ApplyPlan,
    DetectedTarget,
    TargetId,
    detect_target,
    is_forbidden_apply_host,
)
from light_console.qlc.service import QlcService
from light_console.ui.vocab import FAILED, RUNNING, STARTING, STOPPED, STOPPING

LOG = logging.getLogger("light-console")

APPLYING = "APPLYING"
QLC_STOPPING = "QLC STOPPING"
QLC_STARTING = "QLC STARTING"

Progress = Callable[[str], None]


class RouteApplyError(Exception):
    def __init__(self, message: str, *, restored: bool = False) -> None:
        super().__init__(message)
        self.restored = restored


def wait_qlc(service: QlcService, wanted: str, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        settle = getattr(service, "settle", None)
        observed = service.poll()
        if observed in {STARTING, STOPPING} and callable(settle):
            observed = settle()
        if observed == wanted:
            return True
        if observed == FAILED:
            return False
        time.sleep(0.05)
    return service.poll() == wanted


def apply_managed_target(
    path: Path,
    target_id: TargetId,
    plan: ApplyPlan,
    *,
    qlc_service: QlcService,
    progress: Progress | None = None,
    connected: Callable[[], bool] | None = None,
    wait_stopped: float = 20.0,
    wait_running: float = 25.0,
    wait_web: float = 15.0,
    already: DetectedTarget | None = None,
) -> DetectedTarget:
    if is_forbidden_apply_host(plan.output_ip):
        raise RouteApplyError("forbidden destination")
    if already is not None and _already_applied(already, plan):
        if progress:
            progress("")
        return already

    original = path.read_bytes()
    original_text = original.decode("utf-8")
    patched = patch_managed_artnet(original_text, plan)

    def note(stage: str) -> None:
        if progress:
            progress(stage)

    note(QLC_STOPPING)
    qlc_service.set_desired(False)
    if not wait_qlc(qlc_service, STOPPED, wait_stopped):
        qlc_service.set_desired(True)
        wait_qlc(qlc_service, RUNNING, wait_running)
        raise RouteApplyError("QLC did not stop")

    note(APPLYING)
    replaced = False
    try:
        tmp = write_temp_and_validate(path, original_text, patched, plan)
        atomic_replace(tmp, path)
        replaced = True
        parse_ok(path)
        _verify_file(path, plan)
    except (OSError, RoutePatchError, UnicodeDecodeError) as exc:
        if replaced:
            restore_exact(path, original)
        qlc_service.set_desired(True)
        wait_qlc(qlc_service, RUNNING, wait_running)
        raise RouteApplyError(str(exc), restored=True) from exc

    note(QLC_STARTING)
    qlc_service.set_desired(True)
    if not wait_qlc(qlc_service, RUNNING, wait_running):
        restore_exact(path, original)
        qlc_service.set_desired(True)
        wait_qlc(qlc_service, RUNNING, wait_running)
        raise RouteApplyError("QLC did not start", restored=True)

    if connected is not None and not _wait_connected(connected, wait_web):
        restore_exact(path, original)
        qlc_service.set_desired(False)
        wait_qlc(qlc_service, STOPPED, wait_stopped)
        qlc_service.set_desired(True)
        wait_qlc(qlc_service, RUNNING, wait_running)
        raise RouteApplyError("QLC WebAccess did not return", restored=True)

    try:
        detected = _verify_file(path, plan)
    except RoutePatchError as exc:
        restore_exact(path, original)
        qlc_service.set_desired(False)
        wait_qlc(qlc_service, STOPPED, wait_stopped)
        qlc_service.set_desired(True)
        wait_qlc(qlc_service, RUNNING, wait_running)
        raise RouteApplyError(str(exc), restored=True) from exc
    note("")
    return detected


def _already_applied(already: DetectedTarget, plan: ApplyPlan) -> bool:
    if already.target_id is not plan.target_id:
        return False
    if (already.output_ip or "") != plan.output_ip:
        return False
    route = already.managed
    if route is None:
        return False
    return route.line == plan.line and route.line_uid == plan.line_uid


def _verify_file(path: Path, plan: ApplyPlan) -> DetectedTarget:
    text = path.read_text(encoding="utf-8")
    routes = parse_output_routes(text)
    detected = detect_target(routes)
    route = detected.managed
    if route is None:
        raise RoutePatchError("managed universe missing after write")
    if route.output_ip != plan.output_ip:
        raise RoutePatchError("workspace outputIP did not match plan")
    if route.line != plan.line or route.line_uid != plan.line_uid:
        raise RoutePatchError("workspace Art-Net line did not match plan")
    if plan.target_id is TargetId.SAFE and detected.target_id is not TargetId.SAFE:
        raise RoutePatchError("SAFE target not detected")
    if plan.target_id in {TargetId.AIR2DMX, TargetId.PKNIGHT}:
        if detected.output_ip != plan.output_ip:
            raise RoutePatchError("target IP mismatch")
    return detected


def _wait_connected(connected: Callable[[], bool], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if connected():
                return True
        except Exception:
            LOG.debug("qlc web wait failed", exc_info=True)
        time.sleep(0.1)
    try:
        return bool(connected())
    except Exception:
        return False
