#!/usr/bin/env bash
# Dry-run (default) or apply a .qxw into the Shield master workspace.
# Never writes the Mac source file. Never loads or restarts QLC.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MASTER="${LIGHT_CONSOLE_MASTER:-$ROOT/qlc/projects/master.qxw}"

usage() {
  cat <<EOF
Usage:
  $0 --name NAME [--id ID] [--dry-run] FILE.qxw
  $0 --name NAME [--id ID] --apply FILE.qxw

Merge Scene/Chaser content into master.qxw. Machine I/O stays on master.
The source file is not modified. This does not load QLC.

  --dry-run   Print SOURCE -> MASTER mapping (default)
  --apply     Write master.qxw and NAME.yaml next to the master
  --name      Logical show name (e.g. SHOW A)
  --id        Optional show id (default: source stem)
EOF
}

die() { echo "error: $*" >&2; exit 1; }

DRY_RUN=1
NAME=""
SHOW_ID=""
FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --apply) DRY_RUN=0; shift ;;
    --name) NAME="${2:-}"; shift 2 ;;
    --id) SHOW_ID="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) die "unknown option $1 (try --help)" ;;
    *)
      [[ -z "$FILE" ]] || die "unexpected argument: $1"
      FILE="$1"
      shift
      ;;
  esac
done

[[ -n "$FILE" ]] || { usage >&2; exit 1; }
[[ -f "$FILE" ]] || die "not a file: $FILE"
[[ -n "$NAME" ]] || die "--name is required"

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python3 - "$FILE" "$MASTER" "$NAME" "$SHOW_ID" "$DRY_RUN" <<'PY'
import sys
from pathlib import Path
from light_console.merge import format_merge_report, merge_files
from light_console.qxw import safe_show_name

src = Path(sys.argv[1])
master = Path(sys.argv[2])
name = sys.argv[3]
show_id = sys.argv[4] or safe_show_name(src)[:-4]
apply = sys.argv[5] == "0"
plan, _patched = merge_files(
    master, src, show_id=show_id, show_name=name, apply=apply
)
print(format_merge_report(plan))
print("source (unchanged):", src)
print("master:", master)
print("dry-run:" if not apply else "applied:", "yes" if not apply else show_id)
PY
