"""Install a named .qxw as master.qxw and bounce QLC. Never use WebAccess project load."""

from __future__ import annotations

from collections.abc import Callable
import logging

from light_console.output.apply import wait_qlc
from light_console.output.mutate import (
    RoutePatchError,
    atomic_replace,
    preserve_managed_universe,
    restore_exact,
)
from light_console.qlc.service import QlcService
from light_console.qxw import QxwError, prepare_for_shield
from light_console.ui.vocab import RUNNING, STOPPED
from light_console.workspaces import WorkspaceCatalog

LOG = logging.getLogger("light-console")

APPLYING = "APPLYING"
QLC_STOPPING = "QLC STOPPING"
QLC_STARTING = "QLC STARTING"


class WorkspaceSwitchError(Exception):
    def __init__(self, message: str, *, restored: bool = False) -> None:
        super().__init__(message)
        self.restored = restored


Progress = Callable[[str], None]


def switch_workspace(
    catalog: WorkspaceCatalog,
    filename: str,
    *,
    qlc_service: QlcService,
    progress: Progress | None = None,
    wait_stopped: float = 20.0,
    wait_running: float = 25.0,
) -> str:
    """Copy a named show onto master.qxw, preserving live U2. Restarts QLC.

    Does not write the named source. Does not contact 192.168.88.248.
    Does not POST the WebAccess project-load endpoint or open-last.
    """
    entry = catalog.get(filename)
    if catalog.is_open(entry.filename) and catalog.master_path.is_file():
        if progress:
            progress("")
        return entry.filename

    source_text = entry.path.read_text(encoding="utf-8")
    try:
        prepared = prepare_for_shield(source_text)
    except QxwError as exc:
        raise WorkspaceSwitchError(str(exc)) from exc
    if entry.path.read_text(encoding="utf-8") != source_text:
        raise WorkspaceSwitchError("source file changed")

    current = ""
    original = b""
    if catalog.master_path.is_file():
        original = catalog.master_path.read_bytes()
        current = original.decode("utf-8")
        try:
            prepared = preserve_managed_universe(prepared, current)
        except RoutePatchError:
            LOG.info("workspace switch: no U2 to preserve")

    def note(stage: str) -> None:
        if progress:
            progress(stage)

    note(QLC_STOPPING)
    qlc_service.set_desired(False)
    if not wait_qlc(qlc_service, STOPPED, wait_stopped):
        qlc_service.set_desired(True)
        wait_qlc(qlc_service, RUNNING, wait_running)
        raise WorkspaceSwitchError("QLC did not stop")

    note(APPLYING)
    replaced = False
    try:
        if original:
            catalog.last_good_path.write_bytes(original)
        tmp = catalog.master_path.with_name(f".incoming.{entry.filename}")
        tmp.write_text(prepared, encoding="utf-8")
        if "192.168.88.248" in tmp.read_text(encoding="utf-8"):
            tmp.unlink(missing_ok=True)
            raise WorkspaceSwitchError("production Pi address in workspace")
        atomic_replace(tmp, catalog.master_path)
        replaced = True
        catalog.remember_open(entry.filename)
    except (OSError, QxwError, WorkspaceSwitchError) as exc:
        if replaced and original:
            restore_exact(catalog.master_path, original)
        qlc_service.set_desired(True)
        wait_qlc(qlc_service, RUNNING, wait_running)
        raise WorkspaceSwitchError(str(exc), restored=bool(original)) from exc

    note(QLC_STARTING)
    qlc_service.set_desired(True)
    if not wait_qlc(qlc_service, RUNNING, wait_running):
        if original:
            restore_exact(catalog.master_path, original)
        qlc_service.set_desired(True)
        wait_qlc(qlc_service, RUNNING, wait_running)
        raise WorkspaceSwitchError("QLC did not start", restored=bool(original))

    note("")
    return entry.filename
